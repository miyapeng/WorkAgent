"""Stage 4 v2 gate: recheck approved raw blueprint, actual bytes and segment evidence."""
from task_common import *
from construct_workspace import load_inputs, verify_workspace
from coverage import external_nodes, resolve_refs, check_audit
from profile_files import profile
from acquire import public_url
from common import require_workspace_artifact


def load_production(plan_dir, seed_file):
    plans,seeds,report=load_inputs(Path(plan_dir),Path(seed_file))
    hashes={'planning_report':digest(report),'blueprints':report['blueprints_sha256'],
            'seed_file':sha256(Path(seed_file).read_bytes())}
    return {p['seed_id']:p for p in plans},seeds,hashes


def eligibility(directory, plan, seed, upstream_hashes, cache, *, fixture=False):
    directory=Path(directory); c=directory/'construction'
    report=read(c/'construction_report.json');reasons=[]
    def check(condition,reason):
        if not condition:reasons.append(reason)
    check(report.get('interface')=='grounded-workspace-v2','unsupported_workspace_interface')
    check((report.get('data_provenance')=='synthetic_test_fixture')==fixture,'fixture_provenance_not_allowed')
    check(report.get('status')=='ready','workspace_status:'+str(report.get('status')))
    check(report.get('seed_id')==plan['seed_id']==seed['seed_id'],'seed_id_mismatch')
    check(report.get('blueprint_sha256')==digest(plan),'plan_hash_mismatch')
    check(report.get('seed_sha256')==digest(seed),'seed_hash_mismatch')
    check(report.get('work_objective_sha256')==sha256(plan['work_objective'].encode()),'objective_hash_mismatch')
    if reasons:return {'eligible':False,'reasons':sorted(set(reasons))},None
    # v2 has no legacy stage4_eligible flag: eligibility is recomputed from the
    # approved blueprint, fresh bytes, coverage and provenance, never inferred.
    coverage=read(c/'information_coverage.json')
    sources=read(c/'source_manifest.json')['sources']
    profiles=unique(read(c/'file_profiles.json'),'file_id')
    nodes=unique(coverage['nodes'],'node_id');external={n['id'] for n in external_nodes(plan)}
    require(set(nodes)==external,'external_coverage_set_mismatch')
    require(coverage['status']=='ready' and not coverage['missing_critical_nodes'],'incomplete_stage3_coverage')
    # Stage 4 conservatively requires every planned retrieval input to be supplied.
    require(all(r['status']=='supported' and r['evidence'] and not r['unverified_assumptions'] for r in nodes.values()),'unsupported_external_input')
    require(coverage['cross_file_coherence']['status']=='coherent' and not coverage['cross_file_coherence']['unverified_assumptions'],'unresolved_case_coherence')
    require(not coverage['suspected_answer_leakage'],'workspace_answer_leakage')
    # Free-text notes may describe license limits or deferred instruction inputs.
    # Required information and assumptions are gated above by structured node fields;
    # every note is forwarded to generation and independent semantic audit.
    require(coverage['selected_anchor'],'real_anchor_missing')
    retained=set(coverage['retained_file_ids']); require(retained,'empty_ready_workspace')
    assessed=unique(coverage['file_assessments'],'file_id')
    require(retained=={k for k,a in assessed.items() if a['retain']},'retained_assessment_mismatch')
    require(set(coverage['selected_anchor']['file_ids'])<=retained,'excluded_anchor')
    init=directory/'workspace_init';require(init.is_dir() and not init.is_symlink(),'workspace_directory_missing_or_symlink')
    expected=report['workspace_files']
    actual={p.relative_to(init).as_posix():sha256(p.read_bytes()) for p in init.rglob('*') if p.is_file()}
    require(actual==expected and actual,'workspace_files_changed')
    native={};visible_sources={};paths=set()
    for fid in sorted(retained):
        s=dict(sources[fid]);a=assessed[fid]
        require(not a['sensitive'] and not a['answer_leakage'] and a['role']!='excluded','retained_file_not_cleared')
        path=relative(s['workspace_path']).as_posix();visible_text(path)
        file=confined(init,path);require(file.is_file() and sha256(file.read_bytes())==s['sha256']==profiles[fid]['sha256'],'source_hash_mismatch')
        require(s['file_id']==fid,'source_id_mismatch')
        if fixture:require(s['origin']=='synthetic_test_fixture' and not s.get('original_url'),'fixture_source_must_be_explicit')
        else:
            require(s['origin']=='real_original','unsupported_source_origin')
            for key in ('original_url','final_url','source_page'):public_url(s[key])
            require(s.get('retrieved_at'),'missing_acquisition_provenance')
        p=profile(file,s.get('final_url','https://fixture.invalid/'+file.name),s['mime'],cache)
        require(p['parse_status']=='parsed' and p['sha256']==s['sha256'],'fresh_parse_failed')
        require_workspace_artifact(p,path)
        require(p.get('warnings',[])==profiles[fid].get('warnings',[]) and p.get('risk_signals',[])==profiles[fid].get('risk_signals',[]),'fresh_parse_unresolved_risk')
        native[fid]=p;s['workspace_path']='workspace_init/'+path;visible_sources[fid]=s;paths.add(path)
    require(paths==set(expected),'visible_file_manifest_incomplete')
    for r in nodes.values():
        refs=[{k:e[k] for k in ('file_id','segment_id')} for e in r['evidence']]
        recovered=resolve_refs(refs,native,retained)
        require(recovered==r['evidence'],'evidence_not_in_fresh_bytes')
        require(all(e['verification_status']=='source_located' and e['evidence_method']=='programmatic_extraction' for e in recovered),'unverified_perception_evidence')
    for refs in (coverage['selected_anchor']['evidence'],coverage['cross_file_coherence']['evidence']):
        require(refs and all(e['verification_status']=='source_located' for e in resolve_refs(refs,native,retained)),'unlocated_case_evidence')
    if not fixture:
        verify_workspace(directory,plan)
        # Re-evaluate the exact schema-level audit, including excluded files and
        # source license claims. This does not perform a new semantic judgment.
        audit={'file_assessments':coverage['file_assessments'],'node_coverage':[
            {k:r[k] for k in ('node_id','status','reason','unverified_assumptions')} |
            {'evidence':[{k:e[k] for k in ('file_id','segment_id')} for e in r['evidence']]} for r in nodes.values()],
            'selected_anchor':coverage['selected_anchor'],
            'cross_file_coherence':{**coverage['cross_file_coherence'],'evidence':[{k:e[k] for k in ('file_id','segment_id')} for e in coverage['cross_file_coherence']['evidence']]},
            'suspected_answer_leakage':coverage['suspected_answer_leakage'],
            'unresolved_information_gaps':coverage['unresolved_information_gaps'],'recommendation':coverage['model_recommendation']}
        require(check_audit(audit,plan,{fid:profiles[fid] for fid in assessed},sources)['status']=='ready','stage3_admission_recheck_failed')
    snapshot={'plan':plan,'seed':seed,'directory':directory,'report':report,'coverage':coverage,
              'profiles':native,'sources':visible_sources,'fixture':fixture,'upstream_hashes':upstream_hashes,
              'construction_hashes':{p.name:sha256(p.read_bytes()) for p in c.iterdir() if p.is_file()}}
    return {'eligible':True,'reasons':[]},snapshot


def extract(snapshot):
    plan=snapshot['plan']; facts=[]; mapping={}
    for row in sorted(snapshot['coverage']['nodes'],key=lambda x:x['node_id']):
        mapping[row['node_id']]=[]
        for ref in sorted(row['evidence'],key=lambda x:(x['file_id'],x['locator'],x['quote'])):
            source=snapshot['sources'][ref['file_id']]
            identity={k:ref[k] for k in ('file_id','locator','quote')} | {'information_node_id':row['node_id']}
            eid='e_'+digest(identity)[:24]
            facts.append({'evidence_id':eid,'type':'source_fact','information_node_id':row['node_id'],
                'file_id':ref['file_id'],'workspace_path':source['workspace_path'],'locator':ref['locator'],
                'description':ref['quote'],'verification':'exact_substring_at_freshly_parsed_location'})
            mapping[row['node_id']].append(eid)
    for node in plan['information_nodes']:
        if node['type']=='external_input' and node.get('supply_channel')!='task_instruction': continue
        eid='r_'+node['id']; mapping[node['id']]=[eid]
        facts.append({'evidence_id':eid,'type':('instruction_requirement' if node['type']=='external_input' else 'derived_requirement' if node['type']=='derived_information' else 'decision_requirement'),
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
