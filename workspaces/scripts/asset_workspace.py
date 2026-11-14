"""Asset-first case construction using the existing search, download and model clients."""
import json
from urllib.parse import urlsplit
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from common import ROOT, require, DataError, sha256, json_bytes, save, safe_relative, require_workspace_artifact
from planning_common import load_llm, model_call, schema, usage
from agent_retrieval import retrieve, parse_decision, Acquisition
from asset_profile import inspect_asset
from asset_binding import compile_binding, binding_gaps, validate_review, case_schema, assemble_case, model_handles


def verify_asset_workspace(directory, plan, seed):
    c=directory/'construction';report=schema(c/'construction_report.json')
    require(report['seed_id']==seed['seed_id']==plan['seed_id'],'asset_seed_mismatch')
    require(report['seed_sha256']==sha256(json_bytes(seed)),'asset_seed_changed')
    require(report['blueprint_sha256']==sha256(json_bytes(plan)),'asset_blueprint_changed')
    for name,h in report['construction_hashes'].items():
        require(sha256((c/safe_relative(name)).read_bytes())==h,'asset_construction_changed')
    files=report['workspace_files'];init=directory/'workspace_init'
    require(not any(p.is_symlink() for p in init.rglob('*')),'asset_symlink')
    require({p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}==files,'asset_workspace_changed')
    if report['status']=='ready':
        require(report['stage4_eligible'] is True,'asset_not_eligible')
        sources=schema(c/'source_manifest.json')['sources'];profiles={p['file_id']:p for p in schema(c/'file_profiles.json')}
        graph=compile_binding(schema(c/'case_design.json'),plan,profiles,sources)
        require(graph==schema(c/'grounded_graph.json'),'asset_graph_changed')
        require(not binding_gaps(graph,plan),'incomplete_asset_coverage')
        require(validate_review(schema(c/'case_review.json')),'asset_review_not_accepted')
        for asset in graph['assets']:
            require(asset['path'].startswith('workspace_init/'),'asset_outside_workspace')
            require(files.get(asset['path'][15:])==asset['sha256'],'asset_not_in_assembled_workspace')
    return report


def build_asset(plan,seed,config,config_path,cache,directory,offline=False):
    from construct_workspace import profile_view
    c=directory/'construction';c.mkdir(parents=True,exist_ok=True)
    llm=load_llm(config,config_path,offline);calls=[];failures=[];options=[];profiles={};sources={};receipt=None;acquisition=None
    try:
        receipt=retrieve(plan,seed,config,cache,offline);save(c/'search_trace.json',receipt)
        decision=parse_decision(receipt,plan,config);save(c/'search_decision.json',decision)
        acquisition=Acquisition(receipt['trace'],config,cache,offline)
        acquisition.discover_fetch_chain(receipt['trace'],[f for case in decision['cases'] for f in case['files']])
        for case in decision['cases']:
            fids=[]
            for f in case['files']:
                try:
                    raw,t=acquisition.get(f['url'],'selected_material');fid='f_'+t['sha256'][:24]
                    if fid not in profiles:
                        p=inspect_asset(cache/'blobs'/t['sha256'],t['final_url'],t['mime'],cache,config.get('vision'),offline)
                        require(p['parse_status']=='parsed','asset_parse_rejected:'+p.get('reason','unknown'))
                        require_workspace_artifact(p,urlsplit(t['final_url']).path)
                        # Add a program-generated structure location; not a visual content assertion.
                        from profile_files import add_segment_ids
                        p['segments'].append({'locator':'file:structure','text':json.dumps(p['structure'],sort_keys=True),'evidence_method':'programmatic_extraction'})
                        add_segment_ids(p);profiles[fid]=p
                        fmt=p.get('format') or p['type'];fmt={'jpeg':'jpg','repository_zip':'zip','text':'txt','markdown':'md'}.get(fmt,fmt)
                        if p['type']=='text' and Path(urlsplit(t['final_url']).path).suffix in ('.scss','.css','.py','.js','.ts','.tsx','.jsx'):
                            fmt=Path(urlsplit(t['final_url']).path).suffix[1:]
                        sources[fid]={**f,**t,'file_id':fid,'origin':'real_original',
                            'license':{'status':'unknown','redistribution_allowed':False},
                            'workspace_path':f'workspace_init/references/{fid}.{fmt}',
                            'discovery':acquisition.known[f['url']]}
                    if fid not in fids:fids.append(fid)
                except (ValueError,OSError,KeyError,TypeError) as exc:
                    failures.append({'stage':'acquisition','url':f['url'],'reason':str(exc)})
            if not fids:continue
            views={fid:profile_view(profiles[fid],plan,config['limits']) for fid in fids}
            try:
                model_profiles,model_sources,decode=model_handles(views,{fid:sources[fid] for fid in fids})
                context={'raw_seed':seed,'intent_graph':plan,'discovered_case_identity':case['identity'],
                         'profiles':model_profiles,'sources':model_sources,
                         'schema':case_schema(plan)}
                design,meta=model_call(llm,ROOT/'prompts'/config.get('case_prompt','asset_case.v1.txt'),context,cache,offline);calls.append(meta)
                raw_design=design;design=decode(assemble_case(design,plan))
                entry={'case_identity':case['identity'],'raw_design':raw_design,'design':design};options.append(entry)
                graph=compile_binding(design,plan,views,sources);entry['graph']=graph
                review,meta=model_call(llm,ROOT/'prompts'/config.get('case_review_prompt','asset_reviewer.v1.txt'),{
                    'raw_seed':seed,'intent_graph':plan,'grounded_graph':graph,'profiles':list(views.values()),
                    'schema':schema(ROOT/'config/asset_review.schema.json')},cache,offline);calls.append(meta)
                entry['review']=review
                accepted=validate_review(review)
                entry['status']='ready' if accepted and not binding_gaps(graph,plan) else 'incomplete'
            except (ValueError,OSError,KeyError,TypeError) as exc:
                if getattr(exc,'model_metadata',None):calls.append(exc.model_metadata)
                failures.append({'stage':'case_binding','case':case['identity'],'reason':str(exc)})
    except (ValueError,OSError,KeyError,TypeError) as exc:
        failures.append({'stage':'search','reason':str(exc)})
    save(c/'case_attempts.json',options)
    eligible=[o for o in options if 'status' in o]
    chosen=max(eligible,key=lambda o:(o['status']=='ready',sum(b['status']=='supported' for b in o['graph']['bindings']))) if eligible else None
    graph=chosen['graph'] if chosen else None;status=chosen['status'] if chosen else 'incomplete'
    files={};retained={a['file_id'] for a in graph['assets']} if graph else set()
    for fid in sorted(retained):
        s=sources[fid];path=safe_relative(s['workspace_path']);raw=(cache/'blobs'/s['sha256']).read_bytes()
        require(sha256(raw)==s['sha256'],'asset_cache_changed')
        dest=directory/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files[path.relative_to('workspace_init').as_posix()]=s['sha256']
    save(c/'source_manifest.json',{'sources':sources});save(c/'file_profiles.json',list(profiles.values()))
    if chosen:
        save(c/'case_design.json',chosen['design']);save(c/'grounded_graph.json',graph);save(c/'case_review.json',chosen['review'])
    save(c/'download_trace.json',acquisition.events if acquisition else [])
    external=[n for n in plan['information_nodes'] if n['type']=='external_input' and n['critical']]
    supported=[b['information_node_id'] for b in graph['bindings'] if b['status']=='supported'] if graph else []
    missing=[n['id'] for n in external if n['id'] not in supported]
    trace=receipt['trace'] if receipt else {}
    if chosen and not chosen['review']['accepted']:failures.extend({'stage':'case_review','reason':s} for s in chosen['review']['issues'])
    if missing:failures.append({'stage':'coverage','reason':'unsupported_critical_inputs','node_ids':missing})
    report={'interface':'asset-grounded-workspace-v1','seed_id':seed['seed_id'],'seed_sha256':sha256(json_bytes(seed)),
        'blueprint_sha256':sha256(json_bytes(plan)),'config_sha256':sha256(json_bytes(config)),
        'status':status,'stage4_eligible':status=='ready','selected_anchor':chosen['case_identity'] if chosen else None,
        'search_state':'completed' if receipt and not receipt['run']['timed_out'] else 'incomplete',
        'workspace_files':files,'retrieved_files':list(sources),'supported_nodes':supported,'missing_nodes':missing,
        'counts':{'actual_search_requests':trace.get('websearch_calls',0),'actual_fetch_requests':trace.get('webfetch_calls',0),
            'downloaded_urls':sum(e['status']=='downloaded' for e in acquisition.events) if acquisition else 0,
            'parsed_unique_files':len(profiles),'retained_files':len(retained),'critical_external_nodes':len(external),
            'supported_critical_nodes':sum(n['id'] in supported for n in external),'real_original_files':len(retained),'synthetic_files':0,
            'model_visual_observations':sum(s['evidence_method']=='model_visual_observation' for p in profiles.values() for s in p['segments']),
            'independently_verified_visual_facts':0},
        'modality_evidence':[{'node_id':b['information_node_id'],'evidence_status':'model_inspected_reference_asset',
            'necessity_status':'not_tested'} for b in (graph['bindings'] if graph else []) if any(r['evidence_method']=='model_visual_observation' for r in b['references'])],
        'failure_reasons':failures,'model_calls':calls,'model_usage':usage(calls),'public_distribution_eligible':False,
        'search_cost':{'billed_cost':None,'note':'Gateway/search billing unavailable; no guessed dollar cost.'},
        'limitations':['Ready is a model-reviewed draft construction gate, not proven task solvability.',
            'Model visual observations remain unverified. Video frames are sparse samples; audio is not inspected.',
            'Synthetic commission choices are isolated from source facts. No synthetic source files are used.'],
        'construction_hashes':{p.name:sha256(p.read_bytes()) for p in c.iterdir() if p.is_file() and p.name!='construction_report.json'}}
    save(c/'construction_report.json',report);verify_asset_workspace(directory,plan,seed);return report


def run_assets(plans,seeds,planning,config,config_path,cache,output,offline):
    # Parallel independent seeds, not multiple agents debating a single decision.
    load_llm(config,config_path,offline);results=[]
    def job(plan):
        ws='WS_'+sha256(plan['seed_id'].encode())[:12];print(ws,plan['seed_id'],'starting',flush=True)
        result=build_asset(plan,seeds[plan['seed_id']],config,config_path,cache,output/ws,offline)
        print(ws,result['status'],flush=True);return {'workspace_id':ws,**result}
    with ThreadPoolExecutor(max_workers=config.get('workers',1)) as pool:
        for future in as_completed([pool.submit(job,p) for p in plans]):
            results.append(future.result());results.sort(key=lambda r:r['seed_id'])
            save(output/'pilot_report.json',{'interface':'asset-grounded-workspace-v1','workspaces':results})
    report={'interface':'asset-grounded-workspace-v1','planning_input':planning['counts'],'workspaces':results,
        'counts':{'admitted_blueprints_processed':len(results),'ready':sum(r['status']=='ready' for r in results),
                  'anchors':sum(bool(r['selected_anchor']) for r in results),
                  'actual_search_requests':sum(r['counts']['actual_search_requests'] for r in results),
                  'downloaded_urls':sum(r['counts']['downloaded_urls'] for r in results)}}
    save(output/'pilot_report.json',report);return report
