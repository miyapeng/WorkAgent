"""Deterministic location checks and conservative admission around a semantic audit."""
import copy
import re
from common import require, normalized, sha256, json_bytes

STATES={'supported','partial','missing','conflicted','unreadable'}


def verify_quote(ref, profiles):
    require(isinstance(ref,dict) and set(ref)=={'file_id','locator','quote'},'invalid_evidence_reference')
    require(ref['file_id'] in profiles,'unknown_file_reference')
    require(isinstance(ref['quote'],str) and 12<=len(ref['quote'])<=240,'invalid_quote_length')
    units={s['locator']:s for s in profiles[ref['file_id']].get('segments',[])}
    require(ref['locator'] in units and ref['quote'] in units[ref['locator']]['text'], 'quote_not_at_actual_location')
    visual=units[ref['locator']].get('evidence_method')=='model_visual_observation'
    return {**ref,'verification':'pixels_and_bounds_checked_content_is_model_observation' if visual else 'exact_substring_at_parsed_location',
            'file_sha256':profiles[ref['file_id']]['sha256']}


def check_audit(audit, plan, profiles):
    require(isinstance(audit,dict) and set(audit)=={'files','coverage','coherence','completion'},'audit_schema')
    expected={n['id'] for n in plan['information_nodes'] if n['type']=='external_input'}
    require(isinstance(audit['files'],list) and len(audit['files'])==len(profiles)
            and {f['file_id'] for f in audit['files']}==set(profiles),'audit_files_not_exact')
    require(isinstance(audit['coverage'],list) and len(audit['coverage'])==len(expected)
            and {n['node_id'] for n in audit['coverage']}==expected,'audit_nodes_not_exact')
    result=copy.deepcopy(audit); rejected={}; retained=[]; deterministic=[]
    for f in result['files']:
        require(set(f)=={'file_id','case_role','scope','scope_evidence','applicability','privacy_risk','answer_leakage'},'file_audit_schema')
        require(f['case_role'] in ('anchor','support','background','unrelated') and type(f['privacy_risk']) is bool
                and f['answer_leakage'] in ('none','possible','present'),'file_audit_value')
        require(isinstance(f['applicability'],str) and f['applicability'].strip(),'missing_applicability')
        require(isinstance(f['scope'],dict) and set(f['scope'])=={'entity','period','currency','units','version'}
                and all(isinstance(v,str) and v for v in f['scope'].values()),'scope_schema')
        f['scope_evidence']=[verify_quote(e,profiles) for e in f['scope_evidence']]
        require(all(e['file_id']==f['file_id'] for e in f['scope_evidence']),'scope_cites_other_file')
        f['scope_status']='model_inference_with_verified_quotes'
        p=profiles[f['file_id']]; reasons=[]
        if p['parse_status']!='parsed': reasons.append('unreadable')
        if f['case_role']=='unrelated': reasons.append('unrelated_to_case')
        if not f['scope_evidence']: reasons.append('case_relation_has_no_located_evidence')
        if f['privacy_risk'] or 'potential_personal_identifiers' in p.get('risk_signals',[]): reasons.append('personal_information_risk')
        if f['answer_leakage']!='none' or 'possible_precomputed_analysis' in p.get('risk_signals',[]): reasons.append('possible_answer_leakage')
        if p.get('type')=='html': reasons.append('html_discovery_page_not_native_workspace_file')
        if p.get('warnings'): reasons += p['warnings']
        if reasons: rejected[f['file_id']]=reasons
        else: retained.append(f['file_id'])
    rows=[]
    for row in result['coverage']:
        require(set(row)=={'node_id','status','evidence','reason','unverified_assumptions'},'coverage_row_schema')
        require(row['status'] in STATES and isinstance(row['reason'],str) and row['reason'].strip()
                and isinstance(row['unverified_assumptions'],list),'coverage_value')
        refs=[]; errors=[]
        for e in row['evidence']:
            try: refs.append(verify_quote(e,profiles))
            except ValueError as exc: errors.append(str(exc))
        observed_status=row['status']; row['evidence']=refs
        row['model_status']=observed_status
        row['location_errors']=errors
        row['workspace_evidence']=[e for e in refs if e['file_id'] in retained]
        if errors or (observed_status=='supported' and (not row['workspace_evidence'] or row['unverified_assumptions'])):
            row['status']='partial' if row['workspace_evidence'] else 'missing'
        elif observed_status in ('supported','partial') and len(row['workspace_evidence'])!=len(refs):
            row['status']='partial' if row['workspace_evidence'] else 'missing'
        row['scope_of_claim']='semantic_assessment_of_located_material_not_fact_guarantee'
        rows.append(row)
    coherence=result['coherence']
    require(set(coherence)=={'status','reason','evidence','unverified_assumptions'} and
            coherence['status'] in ('consistent','conflicted','unverified'),'coherence_schema')
    coherence['evidence']=[verify_quote(e,profiles) for e in coherence['evidence']]
    # Conservative string comparison supplements the semantic audit; background standards are excluded.
    case=[f for f in result['files'] if f['file_id'] in retained and f['case_role'] in ('anchor','support')]
    for field in ('entity','period','currency','units'):
        values={normalized(f['scope'][field]).lower() for f in case if f['scope'][field].lower()!='unknown'}
        if len(values)>1: deterministic.append('scope_conflict:'+field)
        if any(f['scope'][field].lower()=='unknown' for f in case): deterministic.append('scope_unverified:'+field)
    if any(x.startswith('scope_conflict:') for x in deterministic): coherence['status']='conflicted'
    elif deterministic or coherence['unverified_assumptions'] or not coherence['evidence']:
        if coherence['status']=='consistent': coherence['status']='unverified'
    completion=result['completion']
    require(set(completion)=={'safe','reason','target_nodes'} and type(completion['safe']) is bool
            and isinstance(completion['reason'],str) and isinstance(completion['target_nodes'],list)
            and set(completion['target_nodes'])<=expected,'completion_schema')
    anchors=[f['file_id'] for f in result['files'] if f['file_id'] in retained and f['case_role']=='anchor'
             and profiles[f['file_id']].get('origin','real_original')=='real_original']
    return {'nodes':rows,'files':result['files'],'retained_file_ids':retained,'rejected_files':rejected,
            'usable_real_anchors':anchors,'coherence':coherence,'deterministic_scope_checks':deterministic,
            'completion':completion}


def admission(coverage):
    missing=[r['node_id'] for r in coverage['nodes'] if r['status']!='supported']
    reasons=[]
    if not coverage['usable_real_anchors']: reasons.append('no_usable_real_anchor')
    if coverage['coherence']['status']=='conflicted': reasons.append('unresolved_case_conflict')
    if reasons: return 'rejected',reasons+['uncovered:'+n for n in missing]
    if missing or coverage['coherence']['status']!='consistent':
        return 'incomplete',['uncovered:'+n for n in missing]+(['case_applicability_unverified'] if coverage['coherence']['status']!='consistent' else [])
    return 'ready',[]


def validate_origin(record):
    require(record.get('origin') in ('real_original','real_adapted','synthetic'),'unknown_file_origin')
    if record['origin']=='real_original':
        require(record.get('original_url','').startswith('https://') and record.get('sha256'), 'real_file_missing_source')
        require(not record.get('synthetic'),'synthetic_mislabeled_real')
    elif record['origin']=='real_adapted':
        require(record.get('parent_sha256') and record.get('transformation'),'adaptation_missing_lineage')
    else:
        require(record.get('anchor_file_ids') and record.get('target_nodes') and record.get('fictional_case')
                and not record.get('original_url'),'synthetic_missing_disclosure_or_false_source')
