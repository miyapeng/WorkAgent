#!/usr/bin/env python3
"""Stage 4: approved workspace -> evidence-anchored, jointly compiled draft task."""
import argparse
import getpass
import os
import shutil
import tempfile
from task_common import *
from task_evidence import load_production, eligibility, extract
from task_validation import validate_proposal, validate_audit
from task_verifier import compile_verifier, grade
import task_prompts as prompts
import construct_seeds


class Model:
    def __init__(self, config, llm, cache, offline=False):
        self.config=config;self.llm=llm;self.cache=cache;self.offline=offline;self.calls=[]

    def __call__(self,prompt,context,version):
        require(len(json_bytes(context))<=self.config['max_model_input_bytes'],'model_context_limit_no_silent_truncation')
        previous=construct_seeds.request_json
        def blocked(*a,**kw): raise DataError('offline_model_cache_missing')
        if self.offline:construct_seeds.request_json=blocked
        try:
            for attempt in range(self.config.get('retries',1)+1):
                try:
                    value,meta=construct_seeds.llm_call(self.llm,prompt,context,self.cache,prompt_version=version)
                    self.calls.append(meta);return value
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
                    key=digest({'version':version,'context':context,'model':self.llm})
                    path=self.cache/'request_failures'/(key+'.json')
                    old=read(path) if path.exists() else {'attempt_errors':[]}
                    save(path,{'prompt_version':version,'attempt_errors':old['attempt_errors']+[reason]})
                    retry=isinstance(exc,OSError) or bool(re.fullmatch(r'http_status:(?:5\d\d|429)',reason))
                    if not retry or attempt==self.config.get('retries',1):raise
        finally:construct_seeds.request_json=previous


def schemas():
    return {p.name:read(p) for p in sorted((ROOT/'config').glob('*.schema.json'))}


def generation_context(snapshot,graph):
    return {'work_demand':snapshot['seed']['work_demand'],'plan':snapshot['plan'],
            'workspace_files':[{'file_id':fid,'path':s['workspace_path'],'origin':s['origin']} for fid,s in snapshot['sources'].items()],
            'evidence_graph':graph,'schemas':schemas()}


def snapshot_unchanged(snapshot):
    c=snapshot['directory']/'construction'
    require({p.name:sha256(p.read_bytes()) for p in c.iterdir() if p.is_file()}==snapshot['construction_hashes'],'upstream_construction_changed')
    init=snapshot['directory']/'workspace_init'
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(actual==snapshot['report']['workspace_files'],'upstream_workspace_changed')
    require(not any(p.is_symlink() for p in init.rglob('*')),'upstream_symlink')


def package_id(snapshot,proposal,graph):
    return 'TASK_'+digest({'seed_id':snapshot['plan']['seed_id'],'plan':digest(snapshot['plan']),
        'workspace':snapshot['report']['workspace_files'],'proposal':proposal,'graph':graph,
        'provenance':'synthetic_test_fixture' if snapshot['fixture'] else 'grounded_workspace'})[:24]


def assemble(snapshot,proposal,graph,audit,record,output):
    snapshot_unchanged(snapshot)
    tid=package_id(snapshot,proposal,graph); output=Path(output);output.mkdir(parents=True,exist_ok=True)
    target=output/tid
    with tempfile.TemporaryDirectory(prefix='.assembling-',dir=output) as temp:
        d=Path(temp)
        save(d/'task.json',proposal['task'])
        save(d/'evaluation/evidence_graph.json',graph)
        save(d/'evaluation/rubric.json',proposal['rubric'])
        save(d/'evaluation/verifier_spec.json',compile_verifier(proposal['rubric']))
        save(d/'construction/audit_report.json',{**record,'semantic_audit':audit,'requirement_grounding':proposal['grounding']})
        for path,h in snapshot['report']['workspace_files'].items():
            source=confined(snapshot['directory'],'workspace_init/'+path)
            dest=d/'workspace_init'/relative(path);dest.parent.mkdir(parents=True,exist_ok=True)
            data=source.read_bytes();require(sha256(data)==h,'input_changed_during_assembly');dest.write_bytes(data)
        files={p.relative_to(d).as_posix():sha256(p.read_bytes()) for p in d.rglob('*') if p.is_file()}
        manifest={'task_id':tid,'seed_id':snapshot['plan']['seed_id'],'workspace_id':snapshot['directory'].name,
                  'status':'draft','data_provenance':'synthetic_test_fixture' if snapshot['fixture'] else 'grounded_workspace',
                  'upstream_hashes':snapshot['upstream_hashes'],'plan_sha256':digest(snapshot['plan']),
                  'stage3_construction_hashes':snapshot['construction_hashes'],
                  'workspace_files':snapshot['report']['workspace_files'],'package_files':files,
                  'sources':[{'file_id':fid,'sha256':s['sha256'],'origin':s['origin'],'license':s.get('license',{'status':'unknown','redistribution_allowed':False}),
                              **({k:s[k] for k in ('original_url','source_page') if k in s})} for fid,s in snapshot['sources'].items()],
                  'public_redistribution_allowed':not snapshot['fixture'] and all(s.get('license',{}).get('redistribution_allowed') is True for s in snapshot['sources'].values()),
                  'agent_access':['task.json','workspace_init/','outputs/'],'execution_probe_performed':False,
                  'multimodal_necessity':'not_established'}
        save(d/'manifest.json',manifest)
        expected={p.relative_to(d).as_posix():sha256(p.read_bytes()) for p in d.rglob('*') if p.is_file()}
        if target.exists():
            actual={p.relative_to(target).as_posix():sha256(p.read_bytes()) for p in target.rglob('*') if p.is_file()}
            require(actual==expected,'existing_package_changed_or_different_audit')
        else:shutil.copytree(d,target)
    return tid


def process_workspace(directory,plan,seed,upstream_hashes,cache,output,model,stage='all',*,fixture=False):
    record={'workspace_id':Path(directory).name,'seed_id':plan['seed_id'],
            'data_provenance':'synthetic_test_fixture' if fixture else 'grounded_workspace','model_calls':[]}
    try:
        gate,snapshot=eligibility(directory,plan,seed,upstream_hashes,cache,fixture=fixture)
        record['eligibility']=gate
        if not gate['eligible']:return record | {'status':'blocked_upstream','reasons':gate['reasons']}
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
        return record | {'status':'blocked_upstream','reasons':[reason]}
    if stage=='eligibility':return record | {'stage_complete':'eligibility'}
    key=digest({'plan':plan,'construction':snapshot['construction_hashes'],'fixture':fixture})
    artifacts=cache/'construction'/key
    try:
        graph=extract(snapshot);save(artifacts/'evidence_graph.json',graph)
        if stage=='evidence':return record | {'stage_complete':'evidence','evidence_nodes':len(graph['nodes'])}
        context=generation_context(snapshot,graph)
        proposal=model(prompts.GENERATE,context,prompts.GENERATION_VERSION)
        save(artifacts/'proposal.json',proposal)
        record['structural_checks']=validate_proposal(proposal,graph,snapshot)
        record['model_calls']=list(model.calls)
        if stage=='generate':return record | {'stage_complete':'generate'}
        # Fresh native profiles include all source segments. Oversized contexts are rejected, not silently sampled.
        audit_context={**context,'proposal':proposal,'fresh_profiles':list(snapshot['profiles'].values())}
        audit=model(prompts.AUDIT,audit_context,prompts.AUDIT_VERSION)
        save(artifacts/'semantic_audit.json',audit)
        record['semantic_checks']=validate_audit(audit,proposal,graph)
        record['model_calls']=list(model.calls)
        if not record['semantic_checks']['passed']:
            return record | {'status':'rejected','reasons':record['semantic_checks']['failures']}
        if stage=='audit':return record | {'stage_complete':'audit'}
        record['status']='draft';record['reasons']=[]
        tid=assemble(snapshot,proposal,graph,audit,record,output)
        return record | {'task_id':tid}
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        record['model_calls']=list(model.calls)
        reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
        save(artifacts/'failure.json',{'reason':reason})
        return record | {'status':'rejected','reasons':[reason]}


def export_agent(package,destination):
    package=Path(package);destination=Path(destination)
    require(not destination.exists(),'agent_destination_exists')
    require(not destination.resolve().is_relative_to(package.resolve()),'agent_export_inside_private_package')
    m=read(package/'manifest.json');require(m['status']=='draft','only_draft_export')
    schema('task',read(package/'task.json'));visible_text(read(package/'task.json'))
    allowed={'task.json':m['package_files']['task.json']} | {'workspace_init/'+p:h for p,h in m['workspace_files'].items()}
    for path,h in allowed.items():
        visible_text(path);data=confined(package,path).read_bytes();require(sha256(data)==h,'package_export_hash_mismatch')
    with tempfile.TemporaryDirectory(prefix='workagent-export-') as temp:
        d=Path(temp)
        for path in allowed:
            target=d/relative(path);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(confined(package,path).read_bytes())
        (d/'outputs').mkdir();shutil.copytree(d,destination)
    return {'exported_files':len(allowed),'private_directories_exported':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/stage4.json')
    parser.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/pilot')
    parser.add_argument('--seed-dir',type=Path,default=REPO/'work-seeds/archive/data/work_seed_pilot_v2')
    parser.add_argument('--workspace-dir',type=Path,default=REPO/'workspaces/data/pilot')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'generated')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'data/stage4_pilot')
    parser.add_argument('--cache-dir',type=Path,default=ROOT/'data/stage4_cache')
    parser.add_argument('--stage',choices=['eligibility','evidence','generate','audit','assemble','all'],default='all')
    parser.add_argument('--limit',type=int,default=2)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--prompt-api-key',action='store_true')
    parser.add_argument('--export-agent',type=Path,help='Export only visible data from this draft package')
    parser.add_argument('--destination',type=Path)
    parser.add_argument('--grade-package',type=Path)
    parser.add_argument('--submission-dir',type=Path)
    args=parser.parse_args()
    if args.export_agent:
        require(args.destination is not None,'destination_required');print(json.dumps(export_agent(args.export_agent,args.destination)));return
    if args.grade_package:
        require(args.submission_dir is not None,'submission_dir_required');print(json.dumps(grade(args.grade_package,args.submission_dir,args.cache_dir),indent=2));return
    require(args.limit>=0,'negative_limit')
    config=read(args.config);llm=read((args.config.parent/config['llm_config']).resolve())['llm']
    llm={k:v for k,v in llm.items() if k in ('endpoint','model','api_key_env','parameters','timeout_seconds')}
    llm={**llm,'parameters':{**llm.get('parameters',{}),'max_tokens':config['max_tokens']},'timeout_seconds':config['timeout_seconds']}
    if args.prompt_api_key:os.environ[llm['api_key_env']]=getpass.getpass('LLMCenter access key: ')
    for source in (args.plan_dir,args.seed_dir,args.workspace_dir):
        for dest in (args.output_dir,args.report_dir,args.cache_dir):
            require(not dest.resolve().is_relative_to(source.resolve()) and not source.resolve().is_relative_to(dest.resolve()),'upstream_output_overlap')
    plans,seeds,hashes=load_production(args.plan_dir,args.seed_dir)
    directories=sorted(p.parent.parent for p in args.workspace_dir.glob('*/construction/construction_report.json'))[:args.limit]
    run={'config':config,'llm':llm,'upstream_hashes':hashes,'limit':args.limit,
         'workspaces':{p.name:sha256((p/'construction/construction_report.json').read_bytes()) for p in directories},
         'code_sha256':{p.name:sha256(p.read_bytes()) for p in (ROOT/'scripts').glob('*.py')},
         'schema_sha256':digest(schemas())}
    marker=args.report_dir/'run.json'
    if marker.exists():require(read(marker)==run,'changed_run_use_new_report_directory')
    save(marker,run);records=[];seen=set()
    for directory in directories:
        r=read(directory/'construction/construction_report.json');sid=r.get('seed_id')
        if sid not in plans or sid not in seeds or sid in seen:
            record={'workspace_id':directory.name,'status':'blocked_upstream','reasons':['unapproved_or_duplicate_seed_id']}
        else:
            seen.add(sid);model=Model(config,llm,args.cache_dir,args.offline)
            record=process_workspace(directory,plans[sid],seeds[sid],hashes,args.cache_dir,args.output_dir,model,args.stage)
        records.append(record);save(args.report_dir/(directory.name+'.json'),record)
        print(json.dumps(record,ensure_ascii=False),flush=True)
    require(load_production(args.plan_dir,args.seed_dir)[2]==hashes,'upstream_inputs_changed')
    report={'data_provenance':'real_stage3_pilot','stage':args.stage,'input_workspaces':len(records),
            'draft_packages':sum(r.get('status')=='draft' for r in records),
            'blocked_upstream':sum(r.get('status')=='blocked_upstream' for r in records),
            'rejected':sum(r.get('status')=='rejected' for r in records),'workspaces':records,
            'human_runtime_decisions_required':False,'execution_probe_performed':False}
    save(args.report_dir/'stage4_report.json',report)


if __name__=='__main__':main()
