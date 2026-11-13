#!/usr/bin/env python3
"""Approved raw-seed blueprints -> bounded anchor search -> grounded initial workspace."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urljoin,urlsplit
from common import ROOT,REPO,DataError,require,sha256,json_bytes,read_jsonl,write_jsonl,save,safe_relative
from acquire import download,public_url
from profile_files import profile,add_segment_ids
from coverage import external_nodes,check_audit,empty_coverage,resolve_refs
from search_provider import search,available
from vision import inspect_visual
from planning_common import schema,validate,load_llm,model_call,usage
from plan_intents import load_raw,validate_blueprint,validate_review
from compile_blueprint import compile_blueprint


def load_inputs(plan_dir,seed_file):
    seeds=load_raw(seed_file);report=schema(plan_dir/'planning_report.json');plans=read_jsonl(plan_dir/'blueprints.jsonl')
    require(report['interface']=='raw-blueprint-v2','legacy_plan_interface_not_supported')
    require(report['blueprints_sha256']==sha256((plan_dir/'blueprints.jsonl').read_bytes()),'blueprints_file_changed')
    accepted={k for k,r in report['seeds'].items() if r['status']=='accepted'}
    require(len(plans)==len(accepted) and {p['seed_id'] for p in plans}==accepted,'only_accepted_blueprints_allowed')
    for p in plans:
        record=report['seeds'][p['seed_id']];require(p['seed_id'] in seeds,'raw_seed_missing')
        require(sha256(json_bytes(seeds[p['seed_id']]))==record['seed_sha256'],'raw_seed_changed')
        require(sha256(json_bytes(p))==record['blueprint_sha256'],'approved_blueprint_changed')
        require(compile_blueprint(record['semantic_plan'],p['seed_id'])==p,'compiled_graph_does_not_match_semantic_plan')
        validate_blueprint(p,seeds[p['seed_id']]);validate_review(record['semantic_review']);require(record['semantic_review']['accepted'],'blueprint_not_accepted')
    return plans,seeds,report


def profile_view(p,plan,limits):
    terms=set(re.findall(r'[a-z]{4,}',' '.join(n['description'] for n in external_nodes(plan)).lower()))
    segments=p.get('segments',[])
    scored=sorted(enumerate(segments),key=lambda x:(-len(terms & set(re.findall(r'[a-z]{4,}',x[1]['text'].lower()))),x[0]))
    indices=set(range(min(12,len(segments))))|{i for i,_ in scored[:limits['max_segments_per_file']]}
    chosen=[];chars=0
    for i in sorted(indices):
        s=segments[i]
        if chars+len(s['text'])>limits['max_profile_chars']:continue
        chosen.append(s);chars+=len(s['text'])
    return {k:v for k,v in p.items() if k!='segments'}|{'segments':chosen,'total_segments':len(segments),'model_received_all_segments':len(chosen)==len(segments)}


def validate_search(plan,blueprint,budget,anchor):
    validate(plan,schema(ROOT/'config/search.schema.json'))
    require(len(plan['queries'])<=budget,'query_budget_exceeded')
    allowed={n['id'] for n in external_nodes(blueprint)}
    for q in plan['queries']:
        require(set(q['target_node_ids'])<=allowed,'query_targets_non_retrievable_node')
        require(len(q['query'])<=500 and '://' not in q['query'],'invalid_query')
    require((plan['strategy']=='stop')==(not plan['queries']),'inconsistent_search_stop')
    if plan['strategy']!='stop':require(plan['strategy']==('gap_filling' if anchor else 'anchor_search'),'search_strategy_mismatch')


def discover_links(data,url):
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):
            if tag=='a':
                href=dict(attrs).get('href')
                if href:
                    try:self.links.append(public_url(urljoin(url,href)))
                    except ValueError:pass
    parser=Links();parser.feed(data.decode('utf-8-sig'));links=[]
    for link in dict.fromkeys(parser.links):
        if re.search(r'\.(?:pdf|csv|xlsx|docx|pptx|json|png|jpe?g|tiff|svg|tex|txt|md|py|js|ipynb|zip)(?:\?|$)',link,re.I):
            links.append({'candidate_id':'c_'+sha256(link.encode())[:24],'url':link,'source_page':url,'title':Path(urlsplit(link).path).name,
                          'snippet':'Actual href extracted from downloaded source page; not yet inspected.'})
    return links[:40]


def assemble(directory,sources,profiles,coverage,cache):
    init=directory/'workspace_init';init.mkdir(parents=True,exist_ok=True);expected={}
    for fid in coverage['retained_file_ids']:
        p=profiles[fid];source=sources[fid]
        require(source['origin']=='real_original','synthetic_not_allowed')
        raw=(cache/'blobs'/p['sha256']).read_bytes();require(sha256(raw)==source['sha256']==p['sha256'],'source_hash_changed')
        filename=re.sub(r'[^A-Za-z0-9._-]','_',Path(urlsplit(source['final_url']).path).name)[:100] or ('source.'+p['type'])
        if '.' not in filename:filename+='.'+('html' if p['type']=='html' else p['type'])
        relative=safe_relative(('tables' if p['type'] in ('csv','xlsx') else 'materials')+'/'+fid+'_'+filename)
        target=init/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():require(sha256(target.read_bytes())==p['sha256'],'existing_workspace_file_changed')
        else:target.write_bytes(raw)
        expected[relative.as_posix()]=p['sha256'];source['workspace_path']=relative.as_posix();p['actual_path']=relative.as_posix()
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(actual==expected and not any(p.is_symlink() for p in init.rglob('*')),'unexpected_workspace_file')
    return expected


def verify_workspace(directory,plan=None):
    report=schema(directory/'construction/construction_report.json');manifest=schema(directory/'construction/source_manifest.json')
    coverage=schema(directory/'construction/information_coverage.json');profiles={p['file_id']:p for p in schema(directory/'construction/file_profiles.json')}
    init=directory/'workspace_init';require(not any(p.is_symlink() for p in init.rglob('*')),'workspace_symlink')
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(actual==report['workspace_files'],'workspace_hash_changed')
    native={}
    for fid in coverage['retained_file_ids']:
        s=manifest['sources'][fid];require(s['origin']=='real_original','synthetic_source')
        require(actual.get(s['workspace_path'])==s['sha256']==profiles[fid]['sha256'],'source_file_relation_changed')
        native[fid]=profile(init/safe_relative(s['workspace_path']),s['final_url'],s['mime'],ROOT/'data/cache_graph')
        require(native[fid]['parse_status']=='parsed','assembled_source_unreadable')
    for n in coverage['nodes']:
        refs=[{k:e[k] for k in ('file_id','segment_id')} for e in n['evidence']]
        require(resolve_refs(refs,profiles,set(coverage['retained_file_ids']))==n['evidence'],'restored_evidence_changed')
        direct=[{k:e[k] for k in ('file_id','segment_id')} for e in n['evidence'] if e['evidence_method']=='programmatic_extraction']
        recovered=resolve_refs(direct,native)
        require(recovered==[e for e in n['evidence'] if e['evidence_method']=='programmatic_extraction'],'evidence_not_in_actual_bytes')
    if plan:require(report['blueprint_sha256']==sha256(json_bytes(plan)) and report['seed_id']==plan['seed_id'],'blueprint_changed')
    require(report['status']==coverage['status'],'admission_state_mismatch')
    if report['status']=='ready':
        require(coverage['selected_anchor'] and not coverage['missing_critical_nodes'] and coverage['cross_file_coherence']['status']=='coherent' and not coverage['suspected_answer_leakage'],'ready_without_support')
        require(bool(actual) and all(n['evidence'] and not n['unverified_assumptions'] and all(e['verification_status']=='source_located' for e in n['evidence']) for n in coverage['nodes'] if n['status']=='supported'),'ready_with_unverified_evidence')
        if plan:
            byid={n['node_id']:n for n in coverage['nodes']}
            require(set(byid)=={n['id'] for n in external_nodes(plan)},'coverage_node_set_changed')
            require(all(byid[n['id']]['status']=='supported' for n in external_nodes(plan) if n['critical']),'ready_missing_critical_input')
    return {'status':report['status'],'hash_checks':'passed','file_count':len(actual)}


def build_one(plan,seed,config,config_path,cache,directory,offline=False,stage='all',mode='graph'):
    llm=load_llm(config,config_path,offline);limits=config['limits'];construction=directory/'construction'
    calls=[];events=[];sources={};profiles={};links=[];seen=set();coverage=empty_coverage(plan,'not_searched');failures=[]
    trace={'mode':mode,'events':events,'rounds':[]};search_state='not_started';download_attempts=0;download_success=0;duplicates=0;parse_rejected=0
    def call(name,context):
        value,meta=model_call(llm,ROOT/'prompts'/name,context,cache,offline);calls.append(meta);return value
    def audit(items):
        views={fid:profile_view(profiles[fid],plan,limits) for fid in items}
        value=call('evidence_auditor.v2.txt',{'raw_seed':seed,'blueprint':plan,'existing_anchor':coverage['selected_anchor'],
                   'file_profiles':list(views.values()),'sources':{fid:sources[fid] for fid in views},'schema':schema(ROOT/'config/audit.schema.json')})
        # The model may cite only segments actually present in its bounded context.
        checked=check_audit(value,plan,views,sources)
        trace['rounds'].append({'event':'coverage_audit','audit':value,'program_status':checked['status']})
        return checked
    max_rounds=1+limits['gap_rounds']
    for round_no in range(max_rounds):
        retrieval=None
        budget=limits['anchor_queries'] if round_no==0 else limits['queries_per_gap']
        state={'existing_anchor':coverage['selected_anchor'],'missing_information':[n for n in coverage['nodes'] if n['status']!='supported'],
               'previous_queries':[e['query'] for e in events],'remaining_search_budget':{'queries_this_round':budget,'rounds_after_this':max_rounds-round_no-1}}
        try:
            if mode=='graph':
                retrieval=call('search_planner.v2.txt',{'raw_seed':seed,'approved_blueprint':plan,'schema':schema(ROOT/'config/search.schema.json'),**state})
                validate_search(retrieval,plan,budget,coverage['selected_anchor'])
            else:
                direct=call('direct_search.v1.txt',{'raw_seed':seed,**{k:v for k,v in state.items() if k!='missing_information'}})
                require(set(direct)=={'queries','stop_reason'} and isinstance(direct['queries'],list) and len(direct['queries'])<=budget and all(isinstance(q,str) and 1<=len(q)<=500 and '://' not in q for q in direct['queries']),'invalid_direct_queries')
                retrieval={'strategy':'direct_search','queries':[{'query':q,'target_node_ids':[],'desired_source_type':'raw-seed-only comparison','reason':'No explicit graph supplied to search planner.'} for q in direct['queries']],'stop_reason':direct['stop_reason']}
            trace['rounds'].append({'round':round_no,'retrieval_plan':retrieval});save(construction/'search_trace.json',trace)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            if retrieval is not None:trace['rounds'].append({'round':round_no,'event':'invalid_retrieval_plan','proposed_retrieval_plan':retrieval})
            failures.append({'stage':'retrieval_planning','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__});break
        if not retrieval['queries']:search_state='planner_stopped';break
        if stage=='plan':search_state='planned_only';break
        candidates=list(links);links=[]
        for query in retrieval['queries']:
            try:
                receipt=search(query['query'],config['search'],cache,offline);events.append(receipt)
                candidates.extend(receipt['results']);search_state=receipt['status']
                if search_state=='awaiting_search':break
            except (OSError,ValueError,KeyError,TypeError) as exc:
                events.append({'query':query['query'],'provider':config['search']['provider'],'status':'failed','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__,'results':[],'search_api_called':True});search_state='search_failed'
            save(construction/'search_trace.json',trace)
        if search_state=='awaiting_search':break
        candidates=list({c['candidate_id']:c for c in candidates if c['url'] not in seen}.values())
        if not candidates:failures.append({'stage':'search','reason':'no_new_results'});continue
        limit=limits['anchor_candidates'] if not coverage['selected_anchor'] else limits['files_per_gap']
        try:
            selection=call('candidate_selector.v1.txt',{'raw_seed':seed,**({'blueprint':plan} if mode=='graph' else {}),
                           'existing_anchor':coverage['selected_anchor'],'candidates':candidates,'limit':limit,'schema':schema(ROOT/'config/selection.schema.json')})
            validate(selection,schema(ROOT/'config/selection.schema.json'))
            ids=[r['candidate_id'] for r in selection['selected']+selection['rejected']]
            require(len(ids)==len(set(ids)) and set(ids)=={c['candidate_id'] for c in candidates},'selection_must_account_for_candidates')
            require(len(selection['selected'])<=limit,'selection_budget_exceeded')
            trace['rounds'].append({'round':round_no,'candidates':candidates,'selection':selection})
        except (OSError,ValueError,KeyError,TypeError) as exc:
            failures.append({'stage':'candidate_selection','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__});break
        byid={c['candidate_id']:c for c in candidates};new_ids=[]
        for decision in selection['selected']:
            c=byid[decision['candidate_id']];seen.add(c['url']);download_attempts+=1
            try:
                raw,transport=download(c['url'],cache,limits,offline);download_success+=1
                fid='f_'+transport['sha256'][:24]
                if fid in sources:duplicates+=1;continue
                sources[fid]={**c,**transport,'file_id':fid,'origin':'real_original','selection_reason':decision['reason'],'license_status':'unknown'}
                p=profile(cache/'blobs'/transport['sha256'],transport['final_url'],transport['mime'],cache)
                require(p['parse_status']=='parsed','file_parse_rejected:'+p.get('reason','unknown'))
                if p['type']=='html':links.extend(discover_links(raw,transport['final_url']))
                if config.get('vision') and p['type'] in ('image','pdf') and plan['modality_hypotheses']:
                    try:p=inspect_visual(raw,p,config['vision'],cache,offline)
                    except (OSError,ValueError,KeyError,TypeError) as exc:p['warnings'].append('vision_failed:'+type(exc).__name__)
                p['source_url']=transport['final_url'];profiles[fid]=add_segment_ids(p);new_ids.append(fid)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                parse_rejected+=1;failures.append({'stage':'download_or_profile','url':c['url'],'reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
        if new_ids:
            try:
                if not coverage['selected_anchor']:
                    # Evaluate unrelated anchor candidates separately; never present them as one case.
                    options=[audit([fid]) for fid in new_ids]
                    grounded=[a for a in options if a['selected_anchor'] and a['status']!='rejected']
                    if grounded:coverage=max(grounded,key=lambda a:sum(n['status']=='supported' for n in a['nodes']))
                else:
                    checked=audit(sorted(set(coverage['retained_file_ids'])|set(new_ids)))
                    if checked['selected_anchor']:
                        require(checked['selected_anchor']['identity']==coverage['selected_anchor']['identity'],'anchor_identity_changed_without_restart')
                    coverage=checked
            except (OSError,ValueError,KeyError,TypeError) as exc:
                failures.append({'stage':'evidence_audit','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
        save(construction/'search_trace.json',trace)
        if coverage['status'] in ('ready','rejected'):break
    if search_state=='awaiting_search':failures.append({'stage':'search','reason':'awaiting_search: configure a real Search API key; no autonomous search executed'})
    if not coverage['selected_anchor']:failures.append({'stage':'anchor_discovery','reason':'no_grounded_anchor'})
    workspace_files=assemble(directory,sources,profiles,coverage,cache)
    for assessment in coverage['file_assessments']:sources[assessment['file_id']]['license_status']=assessment['license']['status']
    critical=[n for n in external_nodes(plan) if n['critical']];supported=[n['node_id'] for n in coverage['nodes'] if n['status']=='supported']
    report={'interface':'grounded-workspace-v2','seed_id':seed['seed_id'],'seed_sha256':sha256(json_bytes(seed)),
            'blueprint_sha256':sha256(json_bytes(plan)),'work_objective_sha256':sha256(plan['work_objective'].encode()),
            'mode':mode,'config_sha256':sha256(json_bytes(config)),'selected_anchor':coverage['selected_anchor'],
            'status':coverage['status'],'search_state':search_state,'stage4_interface':'requires_new_adapter_not_legacy_eligible',
            'workspace_files':workspace_files,'retrieved_files':list(sources),'search_queries':[e['query'] for e in events],
            'supported_nodes':supported,'missing_nodes':coverage['missing_critical_nodes'],'cross_file_coherence':coverage['cross_file_coherence'],
            'modality_evidence':coverage['modality_evidence'],'public_distribution_eligible':coverage['public_distribution_eligible'],
            'counts':{'planned_queries':sum(len(r.get('retrieval_plan',{}).get('queries',[])) for r in trace['rounds']),
                      'actual_search_requests':sum(e.get('search_api_called',False) for e in events),'download_attempts':download_attempts,'downloaded_urls':download_success,
                      'parsed_unique_files':len(profiles),'download_or_profile_failures':parse_rejected,'duplicate_files':duplicates,'retained_files':len(workspace_files),
                      'critical_external_nodes':len(critical),'supported_critical_nodes':sum(n['id'] in supported for n in critical),
                      'critical_coverage':sum(n['id'] in supported for n in critical)/len(critical) if critical else None,
                      'independently_verified_visual_evidence':0,'synthetic_files':0},
            'failure_reasons':failures,'model_calls':calls,'model_usage':usage(calls),
            'search_cost':{'billed_cost':None if any(e.get('search_api_called') for e in events) else 0,'currency':None,'note':'Exact cost unknown without provider billing receipt; zero requests means zero search API charges.'},
            'limits':limits,'limitations':['Source text and positions are programmatically checked; semantic applicability is model judgment.','Ready concerns input sufficiency, not solver executability.','Instruction-channel requirements must be explicitly fulfilled by Stage 4.']}
    save(construction/'search_trace.json',trace);save(construction/'source_manifest.json',{'sources':sources})
    save(construction/'file_profiles.json',list(profiles.values()));save(construction/'information_coverage.json',coverage);save(construction/'construction_report.json',report)
    verify_workspace(directory,plan);return report


def run(plan_dir,seed_file,output_dir,cache,config_path,offline=False,limit=None,stage='all',mode='graph'):
    plans,seeds,planning=load_inputs(plan_dir,seed_file);config=schema(config_path)
    if limit is not None:require(limit>=0,'negative_limit');plans=plans[:limit]
    results=[]
    for plan in plans:
        ws='WS_'+sha256(plan['seed_id'].encode())[:12]
        print(ws,plan['seed_id'],'starting',flush=True)
        result=build_one(plan,seeds[plan['seed_id']],config,config_path,cache,output_dir/ws,offline,stage,mode)
        results.append({'workspace_id':ws,**result});print(ws,result['status'],result['search_state'],flush=True)
        save(output_dir/'pilot_report.json',{'interface':'grounded-workspace-v2','workspaces':results})
    report={'interface':'grounded-workspace-v2','planning_input':planning['counts'],'mode':mode,'workspaces':results,
            'counts':{'admitted_blueprints_processed':len(results),'ready':sum(r['status']=='ready' for r in results),'anchors':sum(bool(r['selected_anchor']) for r in results),'awaiting_search':sum(r['search_state']=='awaiting_search' for r in results),
                      'actual_search_requests':sum(r['counts']['actual_search_requests'] for r in results),'downloaded_urls':sum(r['counts']['downloaded_urls'] for r in results)}}
    save(output_dir/'pilot_report.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/semantic_pilot');p.add_argument('--seed-file',type=Path,default=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
    p.add_argument('--config',type=Path,default=ROOT/'config/graph_pipeline.json');p.add_argument('--output-dir',type=Path,default=ROOT/'data/semantic_workspaces')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'data/cache_graph');p.add_argument('--offline',action='store_true');p.add_argument('--limit',type=int)
    p.add_argument('--stage',choices=['plan','all','verify'],default='all');p.add_argument('--mode',choices=['graph','direct'],default='graph')
    a=p.parse_args()
    if a.stage=='verify':
        plans,_,_=load_inputs(a.plan_dir,a.seed_file)
        for plan in plans:print(verify_workspace(a.output_dir/('WS_'+sha256(plan['seed_id'].encode())[:12]),plan))
    else:print(run(a.plan_dir,a.seed_file,a.output_dir,a.cache_dir,a.config,a.offline,a.limit,a.stage,a.mode)['counts'])
if __name__=='__main__':main()
