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
        request_context=context;format_retry=False
        try:
            for attempt in range(self.config.get('retries',1)+1):
                try:
                    value,meta=construct_seeds.llm_call(self.llm,prompt,request_context,self.cache,prompt_version=version)
                    if format_retry:meta={**meta,'format_retry':True,'previous_failure':'llm_response_not_json'}
                    self.calls.append(meta);return value
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
                    key=digest({'version':version,'context':request_context,'model':self.llm})
                    path=self.cache/'request_failures'/(key+'.json')
                    old=read(path) if path.exists() else {'attempt_errors':[]}
                    save(path,{'prompt_version':version,'attempt_errors':old['attempt_errors']+[reason]})
                    retry=isinstance(exc,OSError) or bool(re.fullmatch(r'http_status:(?:5\d\d|429)',reason))
                    if reason=='llm_response_not_json' and not format_retry:
                        # One fresh generation for syntax only. Raw bad responses stay cached;
                        # structural/semantic failures are never repaired or waived here.
                        format_retry=True;retry=True
                        request_context={**context,'format_retry_instruction':'The previous response was not valid JSON. Regenerate the requested result as strictly valid JSON using the same evidence and requirements. Do not add facts, modify intent, or skip any required schema fields.'}
                    if not retry or attempt==self.config.get('retries',1):raise
        finally:construct_seeds.request_json=previous


def schemas():
    return {p.name:read(p) for p in sorted((ROOT/'config').glob('*.schema.json'))}


def grounded_call(model,prompt,context,version):
    # Short local handles reduce copying errors; canonical source IDs remain unchanged.
    aliases={n['evidence_id']:f'fact_{i:03d}' for i,n in enumerate(context['evidence_graph']['nodes'],1) if n['type']=='source_fact'}
    reverse={v:k for k,v in aliases.items()}
    def encode(value):
        if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
        if isinstance(value,list):return [encode(v) for v in value]
        return aliases.get(value,value) if isinstance(value,str) else value
    def decode(value):
        if isinstance(value,dict):
            return {k:([reverse.get(e,e) for e in v] if k=='evidence_ids' and isinstance(v,list) else decode(v)) for k,v in value.items()}
        if isinstance(value,list):return [decode(v) for v in value]
        return value
    return decode(model(prompt,encode(context),version))


def compile_artifact_checks(proposal,graph):
    """Compile shared requirements and file checks; add no professional facts or goals."""
    require(all(r['verification_spec']['kind']!='file_exists' for r in proposal['rubric']['items']),
            'file_checks_are_compiled_not_model_generated')
    replacements={}
    for d in proposal['task']['deliverables']:
        path=relative(d['path'],'outputs')
        if not path.suffix:replacements[d['path']]=d['path']+'.'+d['format']
    def paths(value):
        if isinstance(value,dict):return {k:paths(v) for k,v in value.items()}
        if isinstance(value,list):return [paths(v) for v in value]
        if isinstance(value,str):
            for old,new in replacements.items():value=re.sub(re.escape(old)+r'(?![A-Za-z0-9_./-])',lambda _:new,value)
        return value
    # A missing extension is structural. Explicit conflicting extensions still fail validation.
    proposal.update(paths(proposal))
    requirements={r['requirement_id']:r for r in proposal['task']['requirements']}
    semantic_ids=[]
    for item in proposal['rubric']['items']:
        if item['verification_spec']['kind']=='semantic_guide':
            rid=item['requirement_id'];semantic_ids.append(rid)
            require(rid in requirements,'rubric_outside_task')
            description=requirements[rid]['description']
            item['requirement']=description
            clause='Satisfy every part of this task requirement: '+description
            item['verification_spec']['full_credit']=[clause]+[x for x in item['verification_spec']['full_credit'] if x!=clause]
    require(len(semantic_ids)==len(set(semantic_ids)),'multiple_semantic_criteria_for_same_requirement')
    source_ids={n['evidence_id'] for n in graph['nodes'] if n['type']=='source_fact'}
    grounding={r['requirement_id']:r['evidence_ids'] for r in proposal['grounding']}
    for d in proposal['task']['deliverables']:
        linked=[r for r in proposal['task']['requirements'] if d['deliverable_id'] in r['deliverable_ids']]
        refs=sorted({e for r in linked for e in grounding[r['requirement_id']]} & source_ids)
        require(refs,'artifact_without_source_context')
        rid='artifact_'+d['deliverable_id'];bid='check_'+rid
        require(rid not in grounding and all(r['rubric_id']!=bid for r in proposal['rubric']['items']),'compiled_check_id_collision')
        description=f"Create a readable {d['format']} file at {d['path']}."
        proposal['task']['requirements'].append({'requirement_id':rid,'kind':'outcome','description':description,
            'information_node_ids':sorted({i for r in linked for i in r['information_node_ids']}),
            'deliverable_ids':[d['deliverable_id']],'unscored_reason':None})
        proposal['grounding'].append({'requirement_id':rid,'evidence_ids':refs})
        proposal['rubric']['items'].append({'rubric_id':bid,'requirement_id':rid,'requirement':description,
            'evidence_ids':refs,'verification_type':'programmatic','verification_spec':{'kind':'file_exists','path':d['path'],'format':d['format']},
            'weight':1,'critical':True})
    return proposal


def bounded_context(segments,cited,kind,budget):
    """Keep citation context first; explicitly bound only the model's view."""
    size=lambda s:len(s['locator'])+len(s['text'])+2
    if sum(map(size,segments))<=budget:return segments,False
    required={i for i,s in enumerate(segments) if s['locator'] in cited}
    if kind=='pdf':
        pages={segments[i]['locator'].split(':')[1] for i in required}
        required.update(i for i,s in enumerate(segments) if s['locator'].split(':')[1] in pages)
    elif kind=='xlsx':
        rows={}
        for loc in cited:
            match=re.match(r'^(sheet:.*)(?::row:|![A-Z]+)(\d+)$',loc)
            if match:rows.setdefault(match[1],set()).update(range(max(1,int(match[2])-2),int(match[2])+3))
        for i,s in enumerate(segments):
            match=re.match(r'^(sheet:.*):row:(\d+)$',s['locator'])
            if match and (int(match[2])<=2 or int(match[2]) in rows.get(match[1],set())):required.add(i)
    else:
        required={j for i in required for j in range(max(0,i-3),min(len(segments),i+4))}
    used=sum(size(segments[i]) for i in required)
    require(used<=budget,'mandatory_citation_context_exceeds_budget')
    for i,s in enumerate(segments):
        if i not in required and used+size(s)<=budget:required.add(i);used+=size(s)
    return [s for i,s in enumerate(segments) if i in required],True


def generation_context(snapshot,graph,max_profile_chars=50000):
    reference_contract={}
    for node in snapshot['plan']['information_nodes']:
        ancestors={node['id']};pending=[node['id']]
        while pending:
            current=pending.pop()
            for a,b in snapshot['plan']['dependencies']:
                if b==current and a not in ancestors:ancestors.add(a);pending.append(a)
        reference_contract[node['id']]=[n['evidence_id'] for n in graph['nodes'] if n['information_node_id'] in ancestors]
    profiles=[]
    for p in snapshot['profiles'].values():
        cited={n['locator'] for n in graph['nodes'] if n['type']=='source_fact' and n['file_id']==p['file_id']}
        segments=p['segments'];policy='all_indexed_segments'
        if p['type']=='csv':
            # Full source bytes are copied to the task. The task designer needs
            # field context and record examples, not a precomputed data analysis.
            selected=set(range(min(13,len(segments))))
            for i,s in enumerate(segments):
                if s['locator'] in cited:selected.update(range(max(0,i-1),min(len(segments),i+2)))
            segments=[s for i,s in enumerate(segments) if i in selected]
            policy='header_first_12_records_and_cited_records_with_neighbours'
        elif p['type']=='xlsx':
            # Row segments already contain every nonempty cell and its address.
            # Avoid duplicating the entire dictionary as both cells and rows.
            rows=[s for s in segments if ':row:' in s['locator']]
            if rows:
                segments=[s for s in segments if ':row:' in s['locator'] or s['locator'] in cited]
                policy='all_rows_plus_exact_cited_cells'
        segments,bounded=bounded_context(segments,cited,p['type'],max_profile_chars)
        if bounded:policy+='_bounded_with_citation_context'
        require(cited <= {s['locator'] for s in segments},'context_omits_cited_location')
        profiles.append({**{k:p[k] for k in ('file_id','sha256','type','structure','warnings','risk_signals')},
            'context_selection':{'policy':policy,'indexed_segments':len(p['segments']),
                'included_segments':len(segments),'all_source_records_shown':
                len(segments)==len(p['segments']) and p['structure'].get('content_fully_segmented',True)},
            'located_text':'\n'.join(s['locator']+'\t'+s['text'] for s in segments)})
    return {'raw_task_text':snapshot['seed']['task_text'],'plan':snapshot['plan'],
            'workspace_files':[{'file_id':fid,'path':s['workspace_path'],'origin':s['origin']} for fid,s in snapshot['sources'].items()],
            'evidence_graph':graph,'schemas':schemas(),'fresh_profiles':profiles,
            'allowed_evidence_by_information_node':reference_contract,
            'verifier_runtime_contract':{
                'file_exists':'Checks declared path exists, file <=20MB, and actual bytes parse as the declared format. Empty Markdown fails parsing. Does not check content quality, completeness of a report, or forbid extra output files.',
                'weights':'Scores are normalized within each verification_type. If every item is scored, overall_score is sum(weight*score) / sum(weight) across all items. Weight the substantive outcomes accordingly; a presence/parseability check should not dominate them.',
                'pending':'Semantic/process checks are not executed in Stage 4. They stay pending with null scores; overall_score is null until all checks are scored. Critical pending checks keep the gate pending.'},
            'profile_encoding':'Lines are locator<TAB>actual extracted text. Read context_selection: bounded views retain all cited positions, XLSX row context and sheet headers, or entire cited PDF pages. Other content is an explicit excerpt, not a representative sample or completed validation. Original workspace files remain complete. XLSX row segments contain cell addresses and values.',
            'workspace_limitations':snapshot['coverage'].get('unresolved_information_gaps',[]),
            'case_coherence':snapshot['coverage'].get('cross_file_coherence',{})}


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
    key=digest({'plan':plan,'construction':snapshot['construction_hashes'],'fixture':fixture,
                'generation_prompt':prompts.GENERATION_VERSION,'audit_prompt':prompts.AUDIT_VERSION,
                'model':getattr(model,'llm',{})})
    artifacts=cache/'construction'/key
    try:
        graph=extract(snapshot);save(artifacts/'evidence_graph.json',graph)
        if stage=='evidence':return record | {'stage_complete':'evidence','evidence_nodes':len(graph['nodes'])}
        context=generation_context(snapshot,graph,getattr(model,'config',{}).get('profile_context_chars',50000))
        compiled=getattr(model,'config',{}).get('compile_artifact_checks',False)
        call=grounded_call if compiled else lambda m,p,c,v:m(p,c,v)
        proposal=call(model,prompts.GENERATE,context,prompts.GENERATION_VERSION)
        save(artifacts/'model_proposal.json',proposal)
        if compiled:
            proposal=compile_artifact_checks(proposal,graph)
            record['artifact_checks_compiled']=True
        save(artifacts/'proposal.json',proposal)
        record['structural_checks']=validate_proposal(proposal,graph,snapshot)
        record['model_calls']=list(model.calls)
        if stage=='generate':return record | {'stage_complete':'generate'}
        audit_context={**context,'proposal':proposal,
            'schemas':{'audit.schema.json':schemas()['audit.schema.json']},
            'allowed_evidence_ids':{'all':[n['evidence_id'] for n in graph['nodes']],
                'requirements':{g['requirement_id']:g['evidence_ids'] for g in proposal['grounding']},
                'rubrics':{r['rubric_id']:r['evidence_ids'] for r in proposal['rubric']['items']}}}
        audit=call(model,prompts.AUDIT,audit_context,prompts.AUDIT_VERSION)
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
        if path.startswith('workspace_init/'):
            import mimetypes
            from profile_files import detect
            from common import require_workspace_artifact
            kind=detect(data,'https://workspace.invalid/'+path,mimetypes.guess_type(path)[0] or 'application/octet-stream')
            require_workspace_artifact({'type':kind},path)
    with tempfile.TemporaryDirectory(prefix='workagent-export-') as temp:
        d=Path(temp)
        for path in allowed:
            target=d/relative(path);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(confined(package,path).read_bytes())
        (d/'outputs').mkdir();shutil.copytree(d,destination)
    return {'exported_files':len(allowed),'private_directories_exported':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/stage4.json')
    parser.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/visualization_pilot')
    parser.add_argument('--seed-file',type=Path,default=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
    parser.add_argument('--workspace-dir',type=Path,default=REPO/'workspaces/data/visualization_pilot')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'generated')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'data/generated')
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
    from planning_common import load_llm
    config=read(args.config);llm=load_llm(config,args.config,args.offline)
    llm={**llm,'parameters':{**llm.get('parameters',{}),'max_tokens':config['max_tokens']},'timeout_seconds':config['timeout_seconds']}
    if args.prompt_api_key:os.environ[llm['api_key_env']]=getpass.getpass('LLMCenter access key: ')
    for source in (args.plan_dir,args.seed_file,args.workspace_dir):
        for dest in (args.output_dir,args.report_dir,args.cache_dir):
            require(not dest.resolve().is_relative_to(source.resolve()) and not source.resolve().is_relative_to(dest.resolve()),'upstream_output_overlap')
    plans,seeds,hashes=load_production(args.plan_dir,args.seed_file)
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
    require(load_production(args.plan_dir,args.seed_file)[2]==hashes,'upstream_inputs_changed')
    report={'data_provenance':'real_stage3_pilot','stage':args.stage,'input_workspaces':len(records),
            'draft_packages':sum(r.get('status')=='draft' for r in records),
            'blocked_upstream':sum(r.get('status')=='blocked_upstream' for r in records),
            'rejected':sum(r.get('status')=='rejected' for r in records),'workspaces':records,
            'human_runtime_decisions_required':False,'execution_probe_performed':False}
    save(args.report_dir/'stage4_report.json',report)


if __name__=='__main__':main()
