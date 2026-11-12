#!/usr/bin/env python3
"""Stage 3: approved plans -> inspected files, coverage audit and initial workspaces."""
import argparse
import copy
import getpass
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit, urlunsplit

from common import ROOT, REPO, DataError, require, sha256, json_bytes, read_jsonl, write_jsonl, save, llm_call, safe_relative
from acquire import public_url, download, https_request
from profile_files import profile
from coverage import check_audit, admission, validate_origin
import prompts
import plan_intents


def load_inputs(plan_dir, seed_dir):
    plans=read_jsonl(plan_dir/'work_plans.jsonl')
    report=json.loads((plan_dir/'planning_report.json').read_text())
    seeds={r['seed_id']:r for r in read_jsonl(seed_dir/'candidate_seeds.jsonl')}
    accepted={sid for sid,r in report['seeds'].items() if r['status']=='accepted'}
    require(len(plans)==len(accepted) and {p['seed_id'] for p in plans}==accepted,'only_stage2_accepted_plans_allowed')
    for p in plans:
        require(p['seed_id'] in seeds,'stage1_seed_missing')
        receipt=report['seeds'][p['seed_id']]
        original_record={k:v for k,v in receipt.items() if k!='checkpoint_sha256'} | {'plan':p}
        require(sha256(json_bytes(original_record))==receipt.get('checkpoint_sha256'), 'stage2_plan_not_bound_to_approved_checkpoint')
        require(plan_intents.validate_plan(p,accepted,p['seed_id'])['passed'],'stage2_plan_structure_invalid')
    return plans,seeds,{'stage2_plans':sha256((plan_dir/'work_plans.jsonl').read_bytes()),
                        'stage2_report':sha256((plan_dir/'planning_report.json').read_bytes()),
                        'stage1_seeds':sha256((seed_dir/'candidate_seeds.jsonl').read_bytes())}


def validate_queries(value):
    require(isinstance(value,list) and 0<len(value)<=2 and all(isinstance(q,str) and 5<=len(q)<=400
            and 'https://' not in q and 'http://' not in q for q in value),'invalid_search_queries')
    return value


def get_search(query, sid, round_no, config, config_dir, cache, offline=False):
    if config['provider']=='url_manifest':
        manifest=json.loads((config_dir/config['manifest']).read_text())
        rows=[r for r in manifest['searches'] if r['seed_id']==sid and r['round']==round_no and r['query']==query]
        require(len(rows)<=1,'duplicate_manifest_query')
        if not rows: return [],{'provider':'url_manifest','query':query,'status':'awaiting_external_search','results':[]}
        row=rows[0]
        require(row.get('provider') and row.get('searched_at'),'manifest_missing_discovery_provenance')
        results=row['results']
        receipt={**row,'manifest_provider':'url_manifest','status':'external_results_imported','search_api_called_by_script':False}
    elif config['provider']=='http_search':
        key=sha256(json_bytes({'query':query,'config':config})); path=cache/'search'/(key+'.json')
        if path.exists(): receipt=json.loads(path.read_text())
        else:
            require(not offline,'offline_search_cache_missing')
            headers={'Content-Type':'application/json'}
            if config.get('api_key_env'):
                key_value=os.environ.get(config['api_key_env']); require(key_value,'search_key_missing')
                headers['Authorization']='Bearer '+key_value
            raw,transport=https_request(config['endpoint'],payload=json_bytes({'query':query}),headers=headers,
                max_bytes=2_000_000,timeout=25,proxy_env=config.get('trusted_proxy_env'))
            value=json.loads(raw)
            receipt={'provider':'http_search','query':query,'status':'searched','results':value['results'],
                     'searched_at':transport['retrieved_at'],'response_sha256':transport['sha256']}
            save(path,receipt)
        results=receipt['results']
    else: raise DataError('unsupported_search_provider')
    require(isinstance(results,list) and len(results)<=30,'invalid_search_result_count')
    candidates=[]
    for r in results:
        try:
            url=public_url(r['url']); page=public_url(r.get('source_page',url))
            candidates.append({'candidate_id':'c_'+sha256(url.encode())[:24],'url':url,'source_page':page,
                'title':str(r.get('title',''))[:500],'snippet':str(r.get('snippet',''))[:1000],
                'discovery_query':r.get('discovery_query',query)})
        except (ValueError,KeyError,TypeError):
            receipt.setdefault('invalid_results',[]).append({'reason':'invalid_candidate_url'})
    return candidates,receipt


def selection_valid(selection,candidates,limit):
    require(isinstance(selection,dict) and set(selection)=={'selected','rejected'},'selection_schema')
    require(isinstance(selection['selected'],list) and isinstance(selection['rejected'],list),'selection_list')
    entries=selection['selected']+selection['rejected']
    require(all(isinstance(e,dict) and set(e)=={'candidate_id','reason'} and isinstance(e['reason'],str)
                and e['reason'].strip() for e in entries),'selection_entry')
    ids=[e['candidate_id'] for e in entries]
    require(len(ids)==len(set(ids)) and set(ids)=={c['candidate_id'] for c in candidates},'selection_must_account_for_every_candidate')
    require(len(selection['selected'])<=limit,'selection_limit')


def profile_view(p, plan):
    terms=set(re.findall(r'[a-z]{4,}', ' '.join(n['description'] for n in plan['information_nodes']).lower()))
    units=p.get('segments',[])
    scored=sorted(enumerate(units),key=lambda v:(-len(terms & set(re.findall(r'[a-z]{4,}',v[1]['text'].lower()))),v[0]))
    indices=set(range(min(8,len(units)))) | set(range(max(0,len(units)-8),len(units))) | {i for i,_ in scored[:64]}
    selected=[]; size=0
    for i in sorted(indices):
        item=units[i]
        if size+len(item['text'])>24000: continue
        selected.append(item); size+=len(item['text'])
    return {k:v for k,v in p.items() if k!='segments'} | {'segments':selected,'total_segments':len(units),
        'model_received_all_segments':len(selected)==len(units)}


def public_transport(record):
    # Retain full signed download URLs only in the private download cache.
    result=copy.deepcopy(record)
    def redact(url):
        p=urlsplit(url)
        if re.search(r'(?:^|&)(?:sig|token|access_token|X-Amz-Signature)=',p.query,re.I):
            result.setdefault('signed_query_sha256',[]).append(sha256(p.query.encode()))
            return urlunsplit((p.scheme,p.netloc,p.path,'',''))
        return url
    result['original_url']=redact(result['original_url']); result['final_url']=redact(result['final_url'])
    for r in result['redirects']: r['from']=redact(r['from']); r['to']=redact(r['to'])
    return result


def empty_coverage(plan, reason):
    return {'nodes':[{'node_id':n['id'],'status':'missing','model_status':'not_run','evidence':[],
                     'workspace_evidence':[],'reason':reason,'unverified_assumptions':[]} for n in plan['information_nodes'] if n['type']=='external_input'],
            'files':[],'retained_file_ids':[],'rejected_files':{},'usable_real_anchors':[],
            'coherence':{'status':'unverified','reason':reason,'evidence':[],'unverified_assumptions':[]},
            'completion':{'safe':False,'reason':reason,'target_nodes':[]}}


def call_model(llm,prompt,context,cache,version,calls):
    key=sha256(json_bytes({'prompt':prompt,'context':context,'version':version,'model':llm['model']}))
    failure_path=cache/'model_failures'/(key+'.json')
    for attempt in range(2):
        try:
            value,meta=llm_call(llm,prompt,context,cache,prompt_version=version)
            break
        except (OSError,ValueError,KeyError,TypeError) as exc:
            reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
            history=json.loads(failure_path.read_text())['attempt_errors'] if failure_path.exists() else []
            save(failure_path,{'prompt_version':version,'model':llm['model'],'attempt_errors':history+[reason]})
            retryable=isinstance(exc,OSError) or bool(re.fullmatch(r'http_status:(?:5\d\d|429)',reason))
            if not retryable or attempt==1: raise
    if failure_path.exists(): meta={**meta,'prior_request_errors':json.loads(failure_path.read_text())['attempt_errors']}
    calls.append(meta)
    return value


def assemble(directory, sources, profiles, coverage, cache):
    init=directory/'workspace_init'; init.mkdir(parents=True,exist_ok=True)
    expected={}
    for fid in coverage['retained_file_ids']:
        p=profiles[fid]; source=next(s for s in sources if s.get('file_id')==fid and (s.get('download_status')=='downloaded' or s.get('origin')=='synthetic'))
        validate_origin(source)
        filename=re.sub(r'[^A-Za-z0-9._-]','_',source.get('filename') or Path(urlsplit(source['original_url']).path).name)[:100]
        if not filename: filename=fid+'.'+p['type']
        folder='tables' if p['type'] in ('csv','xlsx') else 'documents'
        relative=safe_relative(folder+'/'+fid[2:10]+'_'+filename)
        path=init/relative; path.parent.mkdir(parents=True,exist_ok=True)
        raw=(cache/'blobs'/source['sha256']).read_bytes()
        require(sha256(raw)==source['sha256'],'assembly_source_hash_mismatch')
        if path.exists(): require(path.read_bytes()==raw,'existing_workspace_file_changed')
        else: path.write_bytes(raw)
        source['workspace_path']='workspace_init/'+relative.as_posix()
        p['actual_path']=source['workspace_path']
        expected[relative.as_posix()]=source['sha256']
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(actual==expected,'workspace_contains_unexpected_or_modified_files')
    return dict(sorted(expected.items()))


def verify_workspace(directory, plan=None):
    report=json.loads((directory/'construction/construction_report.json').read_text())
    manifest=json.loads((directory/'construction/source_manifest.json').read_text())
    coverage=json.loads((directory/'construction/information_coverage.json').read_text())
    init=directory/'workspace_init'
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(not any(p.is_symlink() for p in init.rglob('*')),'workspace_symlink')
    require(actual==report['workspace_files'],'workspace_hash_or_manifest_mismatch')
    for source in manifest['sources']:
        if source.get('workspace_path'):
            validate_origin(source)
            require(sha256((directory/safe_relative(source['workspace_path'])).read_bytes())==source['sha256'],'workspace_source_hash_mismatch')
    if plan is not None:
        require(report['plan_sha256']==sha256(json_bytes(plan)) and report['seed_id']==plan['seed_id'], 'workspace_plan_changed')
        require(report['work_objective_sha256']==sha256(plan['work_objective'].encode()), 'workspace_objective_changed')
    profiles={p['file_id']:p for p in read_jsonl(directory/'construction/file_profiles.jsonl')}
    from coverage import verify_quote
    for row in coverage['nodes']:
        for ref in row.get('workspace_evidence',[]):
            require(ref['file_id'] in profiles, 'workspace_evidence_profile_missing')
            p=profiles[ref['file_id']]
            require(p['sha256'] in actual.values(), 'workspace_evidence_not_in_visible_files')
            verify_quote({k:ref[k] for k in ('file_id','locator','quote')},profiles)
    require(admission(coverage)[0]==report['status'],'admission_state_mismatch')
    require(report['objective_preserved'] is True and report['stage4_eligible']==(report['status']=='ready'),'invalid_stage4_gate')
    return {'status':report['status'],'file_count':len(actual),'hash_checks':'passed'}


def build_one(plan, seed, config, config_dir, llm, cache, directory, offline=False, companions=None):
    directory.mkdir(parents=True,exist_ok=True); construction=directory/'construction'
    calls=[]; events=[]; sources=[]; profiles={}; rounds=[]; errors=[]
    context={'plan':plan,'work_demand':seed['work_demand']}
    try:
        retrieval=call_model(llm,prompts.PLAN,context,cache,prompts.PLAN_VERSION,calls)
        require(set(retrieval)=={'anchor_strategy','coherence_requirements','queries','expected_gaps'},'retrieval_plan_schema')
        queries=validate_queries(retrieval['queries'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
        retrieval={'error':reason}; queries=[]; errors.append({'stage':'retrieval_planning','reason':reason})
    limits=config['limits']
    coverage=empty_coverage(plan,'no_sources_yet'); seen=set(); rejected_parse=[]
    for round_no in range(1,limits['rounds']+1):
        candidates=[]
        for query in queries[:config['search'].get('max_queries_per_round',2)]:
            try:
                items,receipt=get_search(query,plan['seed_id'],round_no,config['search'],config_dir,cache,offline)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
                items=[]; receipt={'query':query,'provider':config['search']['provider'],'status':'failed','reason':reason}
                errors.append({'stage':'search','round':round_no,'reason':reason})
            events.append(receipt); candidates.extend(items)
        candidates=list({c['candidate_id']:c for c in candidates if c['url'] not in seen}.values())
        if not candidates:
            rounds.append({'round':round_no,'queries':queries,'reason':'no_new_verified_search_candidates'})
            break
        save(construction/'retrieval_log.json',{'retrieval_plan':retrieval,'events':events,'rounds':rounds})
        selection_limit=1 if round_no==1 else limits['files_per_round']
        try:
            selected=call_model(llm,prompts.SELECT,{**context,'candidates':candidates,'limit':selection_limit,
                'existing_files':[profile_view(p,plan) for p in profiles.values()],
                'missing_information':coverage['nodes']},cache,prompts.SELECT_VERSION,calls)
            selection_valid(selected,candidates,selection_limit)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
            errors.append({'stage':'candidate_selection','round':round_no,'reason':reason});break
        byid={c['candidate_id']:c for c in candidates}
        for decision in selected['selected']:
            candidate=byid[decision['candidate_id']]; seen.add(candidate['url'])
            source={**candidate,'selection_reason':decision['reason'],'origin':'real_original',
                    'license':{'status':'unknown','redistribution_allowed':False,'reason':'Public accessibility alone does not establish redistribution rights.'}}
            try:
                raw,record=download(candidate['url'],cache,limits,offline)
                source.update(public_transport(record),download_status='downloaded',file_id='f_'+record['sha256'][:24])
                if source['file_id'] in profiles:
                    source['deduplicated']=True
                else:
                    parsed=profile(cache/'blobs'/record['sha256'],record['final_url'],record['mime'],cache)
                    parsed.update(file_id=source['file_id'],sha256=record['sha256'],origin='real_original',
                                  actual_path='private_cache/blobs/'+record['sha256'])
                    if parsed['parse_status']=='parsed' and config.get('vision') and parsed['type'] in ('image','pdf'):
                        from vision import inspect_visual
                        parsed=inspect_visual(raw,parsed,config['vision'],cache,offline)
                    if parsed['parse_status']=='parsed': profiles[parsed['file_id']]=parsed
                    else: rejected_parse.append(parsed)
                    source['parse_status']=parsed['parse_status']
            except (OSError,ValueError,KeyError) as exc:
                reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
                if source.get('download_status')=='downloaded':
                    source.update(parse_status='rejected',reason=reason)
                    rejected_parse.append({'file_id':source['file_id'],'sha256':source['sha256'],'parse_status':'rejected','reason':reason})
                else: source.update(download_status='failed',reason=reason)
            sources.append(source)
        save(construction/'source_manifest.json',{'sources':sources})
        write_jsonl(construction/'file_profiles.jsonl',list(profiles.values())+rejected_parse)
        round_record={'round':round_no,'queries':queries,'selection':selected}
        if profiles:
            try:
                audit_llm={**llm,'parameters':{**llm.get('parameters',{}),'max_tokens':7000},'timeout_seconds':config.get('audit_timeout_seconds',90)}
                raw_audit=call_model(audit_llm,prompts.AUDIT,{**context,'files':[profile_view(p,plan) for p in profiles.values()],
                                     'file_ids':list(profiles),'external_node_ids':[n['id'] for n in plan['information_nodes'] if n['type']=='external_input']},
                                     cache,prompts.AUDIT_VERSION,calls)
                save(construction/f'model_audit_round_{round_no}.json',raw_audit)
                coverage=check_audit(raw_audit,plan,profiles)
                round_record['audit']='checked'
            except (OSError,ValueError,KeyError,TypeError) as exc:
                reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
                errors.append({'stage':'coverage_audit','round':round_no,'reason':reason})
                coverage=empty_coverage(plan,reason); round_record['audit_error']=reason
        rounds.append(round_record)
        save(construction/'retrieval_log.json',{'retrieval_plan':retrieval,'events':events,'rounds':rounds})
        status,_=admission(coverage)
        if status=='ready' or round_no==limits['rounds']: break
        try:
            refinement=call_model(llm,prompts.REFINE,{**context,'coverage':coverage,
                'inspected_files':[profile_view(p,plan) for p in profiles.values()]},cache,prompts.REFINE_VERSION,calls)
            require(set(refinement)=={'continue','queries','reason'} and type(refinement['continue']) is bool,'refinement_schema')
            round_record['refinement']=refinement
            if not refinement['continue']: break
            queries=validate_queries(refinement['queries'])
        except (OSError,ValueError,KeyError,TypeError) as exc:
            reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__
            errors.append({'stage':'search_refinement','round':round_no,'reason':reason});break
    # Completion is assessed, but never silently substitutes invented core records.
    completion={'route':'real_only','synthetic_files':0,'decision':'not_materialized',
                'reason':coverage['completion']['reason'], 'model_assessment':coverage['completion']}
    original_supported=sum(r['status']=='supported' for r in coverage['nodes'])
    if companions:
        from companions import render_companions
        synthetic_sources,synthetic_profiles=render_companions(companions,plan,coverage,cache)
        sources.extend(synthetic_sources)
        profiles.update({p['file_id']:p for p in synthetic_profiles})
        raw_audit=call_model({**llm,'parameters':{**llm.get('parameters',{}),'max_tokens':7000},'timeout_seconds':config.get('audit_timeout_seconds',90)},
            prompts.AUDIT,{**context,'files':[profile_view(p,plan) for p in profiles.values()],
                'file_ids':list(profiles),'external_node_ids':[n['id'] for n in plan['information_nodes'] if n['type']=='external_input']},
            cache,prompts.AUDIT_VERSION,calls)
        save(construction/'model_audit_after_completion.json',raw_audit)
        coverage=check_audit(raw_audit,plan,profiles)
        completion={'route':'real_anchor_with_synthetic_companions','synthetic_files':len(synthetic_sources),
                    'decision':'rendered_and_reaudited','specification_sha256':sha256(json_bytes(companions)),
                    'reason':'Explicit reviewed input specification; no automatic replacement of failed downloads.'}
    elif config.get('allow_synthetic'):
        raise DataError('Synthetic completion requires --companions with a reviewed specification')
    workspace_files=assemble(directory,sources,profiles,coverage,cache)
    for fid,parsed in profiles.items():
        if fid not in coverage['retained_file_ids']:
            parsed['actual_path']=str((cache/'blobs'/parsed['sha256']).resolve())
    for parsed in rejected_parse:
        parsed['actual_path']=str((cache/'blobs'/parsed['sha256']).resolve())
    for source in sources:
        if source.get('workspace_path'):
            source['disposition']='retained'
        elif source.get('download_status')=='failed':
            source['disposition']='download_failed'
        elif source.get('parse_status')=='rejected':
            source['disposition']='parse_rejected'
        else:
            source['disposition']='not_admitted'
            source['exclusion_reasons']=coverage['rejected_files'].get(source.get('file_id'),['audit_not_completed_or_no_support'])
    status,reasons=admission(coverage)
    n=len(coverage['nodes']); supported=sum(r['status']=='supported' for r in coverage['nodes'])
    external_queries=sum(1+len(e.get('supplemental_queries',[])) for e in events if e.get('status')=='external_results_imported')
    report={'seed_id':plan['seed_id'],'plan_sha256':sha256(json_bytes(plan)),'status':status,'stage4_eligible':status=='ready',
        'objective_preserved':True,'work_objective_sha256':sha256(plan['work_objective'].encode()),'failure_reasons':reasons,
        'counts':{'external_search_queries_recorded':external_queries,'search_provider_requests':len(events),
                  'downloaded_urls':sum(s['download_status']=='downloaded' for s in sources),
                  'download_failures':sum(s['download_status']=='failed' for s in sources),
                  'parsed_unique_files':len(profiles),'parse_rejected_files':len(rejected_parse),
                  'audit_excluded_unique_files':len(coverage['rejected_files']),
                  'duplicates':sum(bool(s.get('deduplicated')) for s in sources),
                  'usable_real_anchors':len(coverage['usable_real_anchors']),
                  'retained_real_original':sum(profiles[f]['origin']=='real_original' for f in coverage['retained_file_ids']),
                  'retained_real_adapted':0,'retained_synthetic':sum(profiles[f]['origin']=='synthetic' for f in coverage['retained_file_ids']),
                  'external_input_nodes':n},
        'coverage':{'real_supported_nodes':original_supported,'real_coverage':original_supported/n if n else 0,
                    'after_completion_supported_nodes':supported,'after_completion_coverage':supported/n if n else 0,
                    'observed_model_statuses':{r['node_id']:r['model_status'] for r in coverage['nodes']},
                    'node_statuses':{r['node_id']:r['status'] for r in coverage['nodes']}},
        'completion':completion,'workspace_files':workspace_files,'errors':errors,'model_calls':calls,
        'public_redistribution_approved':False,'multimodal_dependency_established':False,
        'limitations':['Semantic coverage and scope are model assessments; quote location and byte hashes are independently checked.',
                      'No execution probe was run; ready would mean input sufficiency, not proven task solvability.',
                      'Unknown redistribution rights: original files and detailed extracted text remain local.']}
    save(construction/'source_manifest.json',{'sources':sources})
    write_jsonl(construction/'file_profiles.jsonl',list(profiles.values())+rejected_parse)
    save(construction/'information_coverage.json',coverage)
    save(construction/'construction_report.json',report)
    save(construction/'retrieval_log.json',{'retrieval_plan':retrieval,'events':events,'rounds':rounds})
    verify_workspace(directory,plan)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=ROOT/'config/pilot.json')
    p.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/pilot')
    p.add_argument('--seed-dir',type=Path,default=REPO/'work-seeds/archive/data/work_seed_pilot_v2')
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/pilot')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'data/cache')
    p.add_argument('--limit',type=int,default=2)
    p.add_argument('--offline',action='store_true')
    p.add_argument('--prompt-api-key',action='store_true')
    p.add_argument('--companions',type=Path,help='Optional JSON array of reviewed structured companion specs; never auto-fill core gaps')
    p.add_argument('--stage',choices=['plan','build','verify'],default='build')
    a=p.parse_args(); config=json.loads(a.config.read_text())
    require(0<=a.limit<=2,'pilot_limit_must_be_between_zero_and_two')
    plans,seeds,hashes=load_inputs(a.plan_dir,a.seed_dir)
    companions=json.loads(a.companions.read_text()) if a.companions else []
    require(isinstance(companions,list) and len({s['seed_id'] for s in companions})==len(companions),'companion_specs_must_be_unique')
    require({s['seed_id'] for s in companions}<={p['seed_id'] for p in plans[:a.limit]},'companion_seed_not_selected')
    for source in (a.plan_dir,a.seed_dir):
        for dest in (a.output_dir,a.cache_dir):
            require(source.resolve()!=dest.resolve() and source.resolve() not in dest.resolve().parents,'stage3_cannot_write_stage1_or_stage2')
    llm=json.loads((a.config.parent/config['llm_config']).resolve().read_text())['llm']
    if a.prompt_api_key: os.environ[llm['api_key_env']]=getpass.getpass('LLMCenter access key: ')
    if a.offline:
        import construct_seeds
        def no_network(*args,**kwargs): raise DataError('offline_model_response_missing')
        construct_seeds.request_json=no_network
    code={f.name:sha256(f.read_bytes()) for f in Path(__file__).parent.glob('*.py')}
    meta={'input_sha256':hashes,'code_sha256':code,'config':config,'llm':llm,'limit':a.limit,
          'companion_specifications':companions,
          'search_manifest_sha256':sha256((a.config.parent/config['search']['manifest']).read_bytes()) if config['search']['provider']=='url_manifest' else None}
    signature=sha256(json_bytes(meta)); a.output_dir.mkdir(parents=True,exist_ok=True)
    marker=a.output_dir/'run.json'
    if marker.exists() and a.stage!='verify': require(json.loads(marker.read_text())['signature']==signature,'changed_inputs_or_code_use_new_output_directory')
    if a.stage!='verify': save(marker,{'signature':signature,**meta})
    reports=[]
    try:
        for i,plan in enumerate(plans[:a.limit],1):
            directory=a.output_dir/f'WS{i:03d}'
            if a.stage=='verify': report=verify_workspace(directory,plan)
            elif a.stage=='plan':
                calls=[]
                retrieval=call_model(llm,prompts.PLAN,{'plan':plan,'work_demand':seeds[plan['seed_id']]['work_demand']},a.cache_dir,prompts.PLAN_VERSION,calls)
                save(directory/'construction/retrieval_plan.json',{'plan':retrieval,'model_calls':calls})
                report=retrieval
            else:
                report=build_one(plan,seeds[plan['seed_id']],config,a.config.parent,llm,a.cache_dir,directory,a.offline,
                                 next((s for s in companions if s['seed_id']==plan['seed_id']),None))
            reports.append(report); print(f'WS{i:03d}: '+json.dumps({k:report[k] for k in ('status','counts','coverage','failure_reasons') if k in report}),flush=True)
    finally:
        require(load_inputs(a.plan_dir,a.seed_dir)[2]==hashes,'upstream_inputs_changed')
    if a.stage=='build': save(a.output_dir/'pilot_report.json',{'workspaces':reports})


if __name__=='__main__': main()
