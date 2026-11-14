"""Private Stage 5 assessment; semantic scores remain distinct from exact comparisons."""
import json
import re
from decimal import Decimal
from pathlib import Path
import sys
from task_common import ROOT, REPO, read, save, require, digest, sha256, confined
from task_verifier import grade, decimal
sys.path.insert(0,str(REPO/'work-plans/scripts'))
from planning_common import model_call, load_llm, validate
from probe_reference import stats19


def lines(text):return {'line_'+str(i):line for i,line in enumerate(text.splitlines(),1)}


def report_numbers(text):
    result={}
    pattern=r'(?<![\w.])[-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)'
    for line_id,line in lines(text).items():
        for i,match in enumerate(re.finditer(pattern,line),1):
            result['num_'+line_id[5:]+'_'+str(i)]={'report_line_id':line_id,'literal':match.group()}
    return result


def compare_claims(claims,text,reference):
    segments=lines(text);numbers=report_numbers(text);numeric=[]
    for selected in claims:
        require(selected['report_number_id'] in numbers,'numeric_reference_not_in_report')
        claim={**selected,**numbers[selected['report_number_id']]}
        require(claim['metric_id'] in reference['metrics'],'unknown_reference_metric')
        require(claim['report_line_id'] in segments and claim['literal'] in segments[claim['report_line_id']],'numeric_claim_not_in_report')
        ref=reference['metrics'][claim['metric_id']]
        difference=abs(decimal(claim['literal'])-decimal(ref['value']))
        tolerance=Decimal(str(ref['absolute_tolerance']))
        if ref['unit']=='expected_records':
            # Probability totals can legitimately be rounded at the displayed precision.
            tolerance=max(tolerance,Decimal('0.5') * Decimal(10) ** decimal(claim['literal']).as_tuple().exponent)
        numeric.append({**claim,'value':str(decimal(claim['literal'])),'expected':ref['value'],'unit':ref['unit'],'tolerance':str(tolerance),'passed':difference<=tolerance})
    return numeric


def check_judge(result,text,rubric,graph,reference):
    validate(result,read(ROOT/'config/probe_judge.schema.json'))
    expected={r['rubric_id']:r for r in rubric['items'] if r['verification_type']=='semantic'}
    require(len(result['items'])==len(expected) and {r['rubric_id'] for r in result['items']}==set(expected),'judge_rubric_set_mismatch')
    segments=lines(text);numbers=report_numbers(text);eids={n['evidence_id'] for n in graph['nodes']};numeric=[]
    for row in result['items']:
        require(set(row['report_line_ids'])<=set(segments),'judge_invalid_report_line')
        require(set(row['evidence_ids'])<=eids,'judge_invalid_evidence_id')
        require(row['verdict']!='passed' or (row['score']==1 and row['report_line_ids'] and row['evidence_ids']),'judge_unsupported_pass')
        require(row['verdict']!='unassessable' or row['score'] is None,'judge_unassessable_scored')
        require(row['verdict']!='failed' or (row['score'] is not None and row['score']<1),'judge_failed_with_full_credit')
    for issue in result['issues']:require(set(issue['report_line_ids'])<=set(segments),'issue_invalid_report_line')
    numeric=compare_claims(result['numeric_claims'],text,reference)
    weights={k:r['weight'] for k,r in expected.items()}
    score=sum(row['score']*weights[row['rubric_id']] for row in result['items'])/sum(weights.values()) if all(r['score'] is not None for r in result['items']) else None
    return {'items':result['items'],'issues':result['issues'],'semantic_score':score,'assisted_numeric_checks':numeric,
            'limitations':result['limitations'],
            'numeric_note':'Python compares numbers; identifying the claim and matching its scope to a reference is model-assisted, not fully deterministic semantic validation.',
            'full_credit_candidate':not result['issues'] and all(r['verdict']=='passed' for r in result['items']) and bool(numeric) and all(n['passed'] for n in numeric)}


def mutations(text,reference):
    """Transparent edits to actual output; no substituted hand-written positive solution."""
    result=[];n=reference['metrics']['collision.rows']['value']
    for token in (f'{int(n):,}',n):
        if re.search(r'(?<!\d)'+re.escape(token)+r'(?!\d)',text):
            altered=re.sub(r'(?<!\d)'+re.escape(token)+r'(?!\d)',f'{int(n)+1000:,}',text)
            result.append({'id':'wrong_collision_count','text':altered,'edit':'Replace observed collision total with total + 1000.'});break
    # Remove the largest headed section containing actual numbers (if present).
    headings=list(re.finditer(r'^#{1,6}\s+.+$',text,re.M))
    spans=[(m.start(),headings[i+1].start() if i+1<len(headings) else len(text)) for i,m in enumerate(headings)]
    spans=[(a,b) for a,b in spans if re.search(r'\d',text[a:b]) and b-a>200]
    if spans:
        a,b=max(spans,key=lambda ab:ab[1]-ab[0]);result.append({'id':'missing_analysis_section','text':text[:a]+text[b:],'edit':'Remove largest numeric headed section.','removed_excerpt':text[a:b][:200]})
    result.extend([
        {'id':'probability_as_count','text':text+'\n\n## Final interpretation of adjustment fields\nEach adjusted serious/slight field is an integer casualty count, not a probability. Count nonempty cells to obtain adjusted casualty totals, including fatal records. Summing the field values is incorrect.\n','edit':'Append explicitly incorrect interpretation contradicting supplied guidance.'},
        {'id':'unsupported_clean_claim','text':text+'\n\n## Definitive accuracy certification\nThese files prove that every casualty in Great Britain was recorded in 2024, with no missing, miscoded or inaccurate values. All reporting bias and revision uncertainty have been eliminated. No caveats or further validation are necessary.\n','edit':'Append unsupported absolute accuracy and population-coverage claims.'}])
    return result


def evaluate(package,output,config,config_path,offline=False):
    from run_probe import hashes, verify_package
    package=Path(package).resolve();output=Path(output).resolve();execution=read(output/'execution.json')
    require(verify_package(package)==execution['identity']['package_manifest_sha256'],'probe_package_changed')
    require(hashes(output/'submission')==execution['submission_files'],'probe_submission_changed')
    require(execution['execution_completed'],'solver_execution_incomplete')
    task=read(package/'task.json');rubric=read(package/'evaluation/rubric.json');graph=read(package/'evaluation/evidence_graph.json')
    deliverables=task['deliverables'];require(len(deliverables)==1,'pilot_requires_one_markdown_report')
    # Existing schema uses path; do not add any secret deliverable contract.
    artifact=deliverables[0]['path'];report=confined(output/'submission',artifact)
    text=report.read_text();require(report.suffix=='.md' and len(text)<=200000,'unsupported_probe_artifact')
    reference=stats19(package/'workspace_init');private=output/'evaluation';private.mkdir(exist_ok=True)
    save(private/'reference.json',reference)
    programmatic=grade(package,output/'submission',private/'profile_cache');save(private/'programmatic.json',programmatic)
    llm=load_llm(config,config_path,offline);context={'public_task':task,
        'rubric':[r for r in rubric['items'] if r['verification_type']=='semantic'],
        'required_rubric_ids':[r['rubric_id'] for r in rubric['items'] if r['verification_type']=='semantic'],
        'source_facts':[n for n in graph['nodes'] if n['type']=='source_fact'],'reference':reference}
    def judge(value,label):
        request={**context,'report_lines':lines(value),'report_numbers':report_numbers(value)};attempts=[]
        for attempt in range(2):
            raw,meta=model_call(llm,ROOT/'prompts/probe_judge.v4.txt',request,private/'model_cache',offline)
            try:
                result=check_judge(raw,value,rubric,graph,reference)
            except ValueError as exc:
                attempts.append({'model_metadata':meta,'validation_error':str(exc)})
                save(private/(label+'_attempts.json'),attempts)
                if attempt:
                    result={'assessment_status':'invalid_judge_output','validation_error':str(exc),'items':[],
                            'semantic_score':None,'full_credit_candidate':False,'assisted_numeric_checks':[],
                            'issues':[],'attempts':attempts,'model_metadata':meta}
                    save(private/(label+'.json'),result);return result
                request={**request,'validation_feedback':str(exc)}
                continue
            attempts.append({'model_metadata':meta,'validation_error':None})
            result['model_metadata']=meta;result['attempts']=attempts;result['assessment_status']='validated'
            save(private/(label+'.json'),result);return result
    def assess(value,label):
        result=judge(value,label)
        request={'report_lines':lines(value),'report_numbers':report_numbers(value),
                 'metric_definitions':{k:{'definition':v['definition'],'unit':v['unit']} for k,v in reference['metrics'].items()}}
        raw,meta=model_call(llm,ROOT/'prompts/probe_claims.v1.txt',request,private/'model_cache',offline)
        try:
            validate(raw,read(ROOT/'config/probe_claims.schema.json'))
            checks=compare_claims(raw['numeric_claims'],value,reference)
            result['blind_claim_check_status']='validated'
        except ValueError as exc:
            checks=[];result['blind_claim_check_status']='invalid_mapping';result['blind_claim_error']=str(exc)
        result['blind_numeric_checks']=checks;result['claim_model_metadata']=meta
        result['judge_full_credit_candidate']=result['full_credit_candidate']
        result['full_credit_candidate']=result['full_credit_candidate'] and bool(checks) and all(c['passed'] for c in checks)
        save(private/(label+'.json'),result)
        return result
    baseline=assess(text,'submission_assessment')
    tests=[]
    for mutation in mutations(text,reference):
        name=mutation['id'];folder=private/'mutations';folder.mkdir(exist_ok=True)
        (folder/(name+'.md')).write_text(mutation['text'])
        assessed=assess(mutation['text'],name)
        changed=set(lines(mutation['text'])) if name=='missing_analysis_section' else {k for k,v in lines(mutation['text']).items() if lines(text).get(k)!=v}
        specific_issue=any(set(i['report_line_ids']) & changed for i in assessed['issues'])
        wrong_numeric=any(not n['passed'] and n['report_line_id'] in changed for n in assessed['blind_numeric_checks'])
        lower_score=assessed['semantic_score'] is not None and baseline['semantic_score'] is not None and assessed['semantic_score']<baseline['semantic_score']
        # Already-failing baselines are not reliable positive controls. Report this explicitly.
        detected=lower_score if name=='missing_analysis_section' else wrong_numeric or specific_issue
        tests.append({'mutation_id':name,'edit':mutation['edit'],'detected':bool(detected),
                      'semantic_score':assessed['semantic_score'],'score_decreased':lower_score,
                      'explicit_issue_on_changed_lines':specific_issue,'numeric_mismatch':wrong_numeric,
                      'positive_control_passed':baseline['full_credit_candidate'],'assessment_status':assessed['assessment_status']})
    summary={'task_id':execution['task_id'],'execution_completed':True,'stage':'stage5_pilot',
             'programmatic_score':programmatic['scores']['programmatic'],'semantic_score':baseline['semantic_score'],
             'full_credit_candidate':baseline['full_credit_candidate'],
             'assessment_status':baseline['assessment_status'],'numeric_checks':len(baseline['blind_numeric_checks']),
             'claim_check_status':baseline['blind_claim_check_status'],'judge_full_credit_candidate':baseline['judge_full_credit_candidate'],
             'numeric_mismatches':sum(not x['passed'] for x in baseline['blind_numeric_checks']),
             'mutations':tests,'mutations_detected':sum(t['detected'] for t in tests),'mutations_run':len(tests),
             'status':'pilot_passed_pending_replication' if baseline['full_credit_candidate'] and all(t['detected'] for t in tests) and programmatic['scores']['programmatic']==1 else 'needs_review',
             'training_admitted':False,'multimodal_ablation':'not_applicable_no_established_visual_dependency',
             'limitations':['One solver and one same-model independent Judge are not expert certification.',
                            'Mutation detection on a failed baseline is diagnostic, not a validated true/false-positive benchmark.',
                            'Numerical mismatches include possible claim-to-metric mapping errors; they are review flags, not confirmed factual-error counts.',
                            'Only the explicit STATS19 reference adapter is implemented; no automatic arbitrary-domain oracle.',
                            'No reliable process audit beyond sandbox-enforced restrictions and final hashes.'],
             'elapsed_seconds':execution['elapsed_seconds'],'tool_calls':execution['tool_calls']}
    save(output/'probe_report.json',summary);return summary
