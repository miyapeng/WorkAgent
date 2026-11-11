"""Fail-closed upstream gate and deterministic evidence extraction from actual bytes."""
import copy
from pathlib import Path
from task_common import *
from construct_workspace import load_inputs, verify_workspace
from coverage import admission, verify_quote, validate_origin
from profile_files import profile
from acquire import public_url


def load_production(plan_dir, seed_dir):
    plans,seeds,hashes=load_inputs(Path(plan_dir),Path(seed_dir))
    return {p['seed_id']:p for p in plans},seeds,hashes


def eligibility(directory, plan, seed, upstream_hashes, cache, *, fixture=False):
    directory=Path(directory); c=directory/'construction'
    reasons=[]
    def check(condition, reason):
        if not condition: reasons.append(reason)
    report=read(c/'construction_report.json')
    coverage=read(c/'information_coverage.json')
    sources=read(c/'source_manifest.json')['sources']
    is_fixture=report.get('data_provenance')=='synthetic_test_fixture'
    check(is_fixture==fixture,'fixture_provenance_not_allowed')
    check(report.get('status')=='ready','workspace_status:'+str(report.get('status')))
    check(report.get('stage4_eligible') is True,'stage4_eligible_not_true')
    check(report.get('seed_id')==plan['seed_id']==seed['seed_id'],'seed_id_mismatch')
    check(report.get('plan_sha256')==digest(plan),'plan_hash_mismatch')
    check(report.get('work_objective_sha256')==sha256(plan['work_objective'].encode()),'objective_hash_mismatch')
    check(report.get('objective_preserved') is True,'objective_not_preserved')
    if not fixture:
        run=read(directory.parent/'run.json')
        check(run.get('input_sha256')==upstream_hashes,'stage3_upstream_versions_mismatch')
    nodes=unique(coverage['nodes'],'node_id')
    external={n['id'] for n in plan['information_nodes'] if n['type']=='external_input'}
    check(set(nodes)==external,'external_coverage_set_mismatch')
    for nid in sorted(external):
        row=nodes.get(nid,{})
        check(row.get('status')=='supported','unsupported_external_input:'+nid)
        check(bool(row.get('workspace_evidence')),'no_visible_evidence:'+nid)
        check(not row.get('unverified_assumptions') and not row.get('location_errors'),'unresolved_node_assumption:'+nid)
    check(coverage['coherence']['status']=='consistent','case_coherence:'+coverage['coherence']['status'])
    check(not coverage['coherence'].get('unverified_assumptions'),'unresolved_case_assumptions')
    check(not coverage.get('deterministic_scope_checks'),'unresolved_scope_checks')
    check(admission(coverage)[0]=='ready','stage3_admission_recheck_failed')
    if not fixture:
        try: verify_workspace(directory,plan)
        except (ValueError,OSError,KeyError,TypeError) as exc: reasons.append('workspace_integrity:'+str(exc) if isinstance(exc,DataError) else 'workspace_integrity:'+type(exc).__name__)
    # Blocked real inputs must not trigger model calls, parsing or task generation.
    if reasons: return {'eligible':False,'reasons':sorted(set(reasons))},None
    init=directory/'workspace_init'
    require(init.is_dir() and not init.is_symlink(),'workspace_directory_missing_or_symlink')
    expected=report['workspace_files']; require(expected,'empty_ready_workspace')
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(actual==expected,'workspace_files_changed')
    old=unique(read_jsonl(c/'file_profiles.jsonl'),'file_id')
    retained=set(coverage['retained_file_ids'])
    require(retained and not retained & set(coverage['rejected_files']),'excluded_file_in_coverage')
    require(set(coverage['usable_real_anchors'])<=retained,'anchor_not_visible')
    native={}; source_by_file={}; paths=set()
    for source in sources:
        if not source.get('workspace_path'): continue
        fid=source['file_id']; require(fid in retained and fid not in source_by_file,'source_manifest_duplicate_or_excluded')
        path=relative(source['workspace_path'],'workspace_init').as_posix()
        visible_text(path); file=confined(directory,path)
        require(file.is_file() and sha256(file.read_bytes())==source['sha256']==old[fid]['sha256'],'source_hash_mismatch')
        require(not old[fid].get('warnings') and not old[fid].get('risk_signals'),'unresolved_file_risk')
        if fixture:
            require(source['origin']=='synthetic_test_fixture' and not source.get('original_url'),'fixture_source_must_be_explicit')
        else:
            validate_origin(source)
            if source['origin']=='real_original':
                public_url(source['original_url']);public_url(source['final_url']);public_url(source['source_page'])
                require(source.get('retrieved_at') and source.get('download_status')=='downloaded','missing_acquisition_provenance')
            if source['origin']=='synthetic':
                require(set(source['anchor_file_ids'])<=set(coverage['usable_real_anchors']),'synthetic_anchor_not_visible')
        mime=source.get('mime') or {'csv':'text/csv','json':'application/json','text':'text/plain','markdown':'text/markdown'}.get(old[fid]['type'])
        require(mime,'missing_file_mime')
        p=profile(file,source.get('original_url','https://fixture.invalid/'+file.name),mime,cache)
        require(p['parse_status']=='parsed' and p['sha256']==source['sha256'],'fresh_parse_failed')
        # Visual observations are not silently converted into independently verified text facts.
        require(not p.get('warnings') and not p.get('risk_signals'),'fresh_parse_unresolved_risk')
        native[fid]=p; source_by_file[fid]=source; paths.add(path.removeprefix('workspace_init/'))
    require(set(native)==retained and paths==set(expected),'visible_file_manifest_incomplete')
    if not fixture:
        reviewed=unique(coverage['files'],'file_id')
        for fid in retained:
            f=reviewed[fid]
            require(f['case_role'] in ('anchor','support','background') and f['privacy_risk'] is False
                    and f['answer_leakage']=='none','retained_file_not_cleared')
            require(f['scope_evidence'],'missing_file_scope_evidence')
            for ref in f['scope_evidence']:
                require(ref['file_id']==fid,'scope_evidence_wrong_file')
                verify_quote({k:ref[k] for k in ('file_id','locator','quote')},native)
        for fid in coverage['usable_real_anchors']:
            require(source_by_file[fid]['origin']=='real_original' and reviewed[fid]['case_role']=='anchor','anchor_not_real_original')
    for row in nodes.values():
        require(row['workspace_evidence'],'missing_located_evidence')
        for ref in row['workspace_evidence']:
            require(ref['file_id'] in native,'excluded_evidence_file')
            require(ref.get('file_sha256')==native[ref['file_id']]['sha256'],'coverage_hash_mismatch')
            require(ref.get('verification')=='exact_substring_at_parsed_location','visual_fact_requires_supported_independent_check')
            verify_quote({k:ref[k] for k in ('file_id','locator','quote')},native)
    for ref in coverage['coherence']['evidence']:
        verify_quote({k:ref[k] for k in ('file_id','locator','quote')},native)
    snapshot={'plan':plan,'seed':seed,'directory':directory,'report':report,'coverage':coverage,
              'profiles':native,'sources':source_by_file,'fixture':fixture,
              'upstream_hashes':upstream_hashes,
              'construction_hashes':{p.name:sha256(p.read_bytes()) for p in c.iterdir() if p.is_file()}}
    return {'eligible':True,'reasons':[]},snapshot


def extract(snapshot):
    plan=snapshot['plan']; facts=[]; mapping={}
    for row in sorted(snapshot['coverage']['nodes'],key=lambda x:x['node_id']):
        mapping[row['node_id']]=[]
        for ref in sorted(row['workspace_evidence'],key=lambda x:(x['file_id'],x['locator'],x['quote'])):
            source=snapshot['sources'][ref['file_id']]
            identity={k:ref[k] for k in ('file_id','locator','quote')} | {'information_node_id':row['node_id']}
            eid='e_'+digest(identity)[:24]
            facts.append({'evidence_id':eid,'type':'source_fact','information_node_id':row['node_id'],
                'file_id':ref['file_id'],'workspace_path':source['workspace_path'],'locator':ref['locator'],
                'description':ref['quote'],'verification':'exact_substring_at_freshly_parsed_location'})
            mapping[row['node_id']].append(eid)
    for node in plan['information_nodes']:
        if node['type']=='external_input': continue
        eid='r_'+node['id']; mapping[node['id']]=[eid]
        facts.append({'evidence_id':eid,'type':'derived_requirement' if node['type']=='derived_information' else 'decision_requirement',
                      'information_node_id':node['id'],'description':node['description']})
    edges=[{'type':'supports','from':f['evidence_id'],'to':'information:'+f['information_node_id']} for f in facts if f['type']=='source_fact']
    for a,b in plan['dependencies']:
        if b not in mapping or not mapping[b][0].startswith('r_'):continue
        edges.extend({'type':'requires','from':mapping[b][0],'to':eid} for eid in mapping[a])
    graph={'nodes':facts,'edges':edges}
    schema('evidence_graph',graph)
    return graph


def verify_graph(graph,snapshot):
    schema('evidence_graph',graph)
    require(graph==extract(snapshot),'evidence_graph_not_bound_to_workspace')
