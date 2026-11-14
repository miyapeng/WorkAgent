"""Recover exact source evidence from stable segment IDs; gate workspace admission."""
from common import require,sha256,json_bytes,require_workspace_artifact
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'work-plans/scripts'))
from planning_common import validate,schema


def external_nodes(plan):return [n for n in plan['information_nodes'] if n['type']=='external_input' and n['supply_channel']!='task_instruction']


def resolve_refs(refs,profiles,allowed=None):
    found=[];seen=set()
    for ref in refs:
        pair=(ref['file_id'],ref['segment_id']);require(pair not in seen,'duplicate_evidence_reference');seen.add(pair)
        require(ref['file_id'] in profiles and (allowed is None or ref['file_id'] in allowed),'unknown_or_excluded_evidence_file')
        p=profiles[ref['file_id']];matches=[s for s in p['segments'] if s['segment_id']==ref['segment_id']]
        require(len(matches)==1,'unknown_segment_id');s=matches[0]
        expected='seg_'+sha256(json_bytes({'file_sha256':p['sha256'],'segment':{k:v for k,v in s.items() if k!='segment_id'}}))[:24]
        require(expected==s['segment_id'],'segment_hash_mismatch')
        found.append({**ref,'locator':s['locator'],'quote':s['text'],'evidence_method':s['evidence_method'],'verification_status':s['verification_status']})
    return found


def check_audit(value,plan,profiles,sources):
    validate(value,schema(Path(__file__).resolve().parents[1]/'config/audit.schema.json'))
    assessments=value['file_assessments'];require(len(assessments)==len(profiles) and {r['file_id'] for r in assessments}==set(profiles),'file_assessment_coverage')
    for a in assessments:
        require((a['role']=='excluded')== (not a['retain']),'file_role_retention_mismatch')
        require(not a['retain'] or not (a['sensitive'] or a['answer_leakage']),'unsafe_retained_file')
        refs=resolve_refs(a['license']['evidence'],profiles)
        if a['license']['status']=='redistributable':require(refs and all(r['verification_status']=='source_located' for r in refs),'unsupported_license_claim')
    retained={r['file_id'] for r in assessments if r['retain']}
    for fid in retained:
        require_workspace_artifact(profiles[fid],sources.get(fid,{}).get('workspace_path'))
        require(fid in sources and sources[fid]['origin']=='real_original' and sources[fid]['sha256']==profiles[fid]['sha256'],'invalid_real_source')
    nodes={n['id']:n for n in external_nodes(plan)};rows=value['node_coverage']
    require(len(rows)==len(nodes) and {r['node_id'] for r in rows}==set(nodes),'node_coverage_mismatch')
    resolved=[]
    for row in rows:
        evidence=resolve_refs(row['evidence'],profiles,retained);status=row['status'];reason=row['reason']
        if status=='supported':
            require(evidence,'supported_without_evidence');require(not row['unverified_assumptions'],'supported_with_unverified_assumptions')
            if any(r['verification_status']!='source_located' for r in evidence):status='partial';reason+=' [Program gate: model perception is not independently verified.]'
            # A planned visual dependency is a hypothesis, not a compulsory carrier.
            # Located text/structured facts may supply the same information; this does
            # not establish visual necessity. Model-only perception remains partial above.
        resolved.append({**row,'status':status,'model_status':row['status'],'reason':reason,'evidence':evidence})
    anchor=value['selected_anchor']
    if anchor:
        require(set(anchor['file_ids'])<=retained,'anchor_file_not_retained')
        evidence=resolve_refs(anchor['evidence'],profiles,set(anchor['file_ids']))
        require(evidence and all(r['verification_status']=='source_located' for r in evidence),'anchor_identity_unverified')
        require(set(anchor['file_ids'])=={a['file_id'] for a in assessments if a['role']=='anchor'},'anchor_role_mismatch')
    else:require(not any(a['role']=='anchor' for a in assessments),'anchor_role_without_identity')
    coherence={**value['cross_file_coherence'],'evidence':resolve_refs(value['cross_file_coherence']['evidence'],profiles,retained)}
    if coherence['status']=='coherent':require(coherence['evidence'] and not coherence['unverified_assumptions'],'ungrounded_coherence')
    missing=[r['node_id'] for r in resolved if nodes[r['node_id']]['critical'] and r['status']!='supported']
    status='ready' if anchor and not missing and coherence['status']=='coherent' and not value['suspected_answer_leakage'] and value['recommendation']=='ready' else 'incomplete'
    if value['recommendation']=='reject' or coherence['status']=='conflicted':status='rejected'
    modality=[]
    for h in plan['modality_hypotheses']:
        row=next((r for r in resolved if r['node_id']==h['node_id']),None)
        refs=row['evidence'] if row else []
        observed=[r for r in refs if r['evidence_method'].startswith('model_')]
        modality.append({**h,'evidence_status':'model_observed_unverified' if observed else 'no_verified_native_evidence',
                         'necessity_status':'pending_stage5_ablation','evidence':refs,'independently_verified':False})
    return {'nodes':resolved,'selected_anchor':anchor,'file_assessments':assessments,'retained_file_ids':sorted(retained),
            'cross_file_coherence':coherence,'suspected_answer_leakage':value['suspected_answer_leakage'],
            'unresolved_information_gaps':value['unresolved_information_gaps'],'missing_critical_nodes':missing,
            'instruction_requirements':[{'node_id':n['id'],'requirement':n['description'],'status':'deferred_to_stage4'} for n in plan['information_nodes'] if n['type']=='external_input' and n['supply_channel']=='task_instruction'],
            'modality_evidence':modality,'status':status,'model_recommendation':value['recommendation'],
            'public_distribution_eligible':bool(retained) and all(a['license']['status']=='redistributable' for a in assessments if a['retain'])}


def empty_coverage(plan,reason):
    return {'nodes':[{'node_id':n['id'],'status':'missing','evidence':[],'reason':reason,'unverified_assumptions':[]} for n in external_nodes(plan)],
            'selected_anchor':None,'retained_file_ids':[],'file_assessments':[],'missing_critical_nodes':[n['id'] for n in external_nodes(plan) if n['critical']],
            'cross_file_coherence':{'status':'unverified','reason':reason,'evidence':[],'unverified_assumptions':[]},
            'suspected_answer_leakage':False,'unresolved_information_gaps':[reason],
            'instruction_requirements':[{'node_id':n['id'],'requirement':n['description'],'status':'deferred_to_stage4'} for n in plan['information_nodes'] if n['type']=='external_input' and n['supply_channel']=='task_instruction'],
            'modality_evidence':[{**h,'evidence_status':'unretrieved','necessity_status':'hypothesis','independently_verified':False} for h in plan['modality_hypotheses']],
            'status':'incomplete','public_distribution_eligible':False}
