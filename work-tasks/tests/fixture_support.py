"""Entirely fictional engineering fixture. Never an official source or real Pilot."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from task_common import *
from profile_files import parse_bytes
from coverage import resolve_refs


def create_fixture(root):
    root=Path(root);directory=root/'SYNTHETIC_TEST_WS';init=directory/'workspace_init';init.mkdir(parents=True)
    plan={'seed_id':'seed_'+'f'*24,'work_objective':'Analyze budget differences for a fictional department and recommend policy-compliant responses.',
          'deliverables':[{'id':'out1','type':'report','description':'Budget comparison table and justified adjustment memorandum.'}],
          'information_nodes':[{'id':'i1','type':'external_input','description':'Approved amounts for each spending category.'},
                               {'id':'i2','type':'external_input','description':'Actual amounts for the same categories and period.'},
                               {'id':'i3','type':'external_input','description':'Case identity, currency, operational context and adjustment policy.'},
                               {'id':'i4','type':'derived_information','description':'Compute actual minus approved amounts by category.'},
                               {'id':'i5','type':'professional_judgment','description':'Recommend a justified response consistent with operational context and policy.'}],
          'dependencies':[['i1','i4'],['i2','i4'],['i3','i5'],['i4','i5'],['i4','out1'],['i5','out1']]}
    plan['modality_hypotheses']=[]
    for n in plan['information_nodes']:
        if n['type']=='external_input':n.update(supply_channel='workspace',critical=True)
    seed={'seed_id':plan['seed_id'],'task_text':plan['work_objective']}
    data={'approved.csv':b'category,amount,unit\nOperations,100,USD\nSupplies,200,USD\n',
          'actual.csv':b'category,amount,unit\nOperations,120,USD\nSupplies,180,USD\n',
          'context.json':json_bytes({'provenance':'synthetic_test_fixture; fictional engineering data, not real business records',
             'case':'Fictional Example Department','period':'Illustrative period A','unit':'USD',
             'rules':'Transfers require approval. Do not assume authority to transfer funds. Keep all source files unchanged during execution.',
             'context':'Operations needed extra maintenance. Supply purchases were deferred.',
             'audience':'Department manager needs a category comparison and a justified response.'})}
    profiles={};sources=[];filehashes={};coverage=[]
    for name,raw in data.items():
        (init/name).write_bytes(raw);mime='text/csv' if name.endswith('csv') else 'application/json'
        p=parse_bytes(raw,'https://fixture.invalid/'+name,mime);profiles[p['file_id']]=p;filehashes[name]=sha256(raw)
        sources.append({'file_id':p['file_id'],'sha256':sha256(raw),'origin':'synthetic_test_fixture',
                        'workspace_path':name,'mime':mime,
                        'license':{'status':'synthetic_test_fixture','redistribution_allowed':False}})
        nid='i1' if name=='approved.csv' else 'i2' if name=='actual.csv' else 'i3'
        segments=[s for s in p['segments'] if s['locator'] in ('row:2','row:3')] if name.endswith('csv') else [s for s in p['segments'] if s['locator']!='json:/provenance']
        # Short numeric/unit facts are located by their surrounding JSON field instead of inventing text.
        # Currency proof is already in each CSV row; context includes only sufficiently long native quotes.
        refs=resolve_refs([{'file_id':p['file_id'],'segment_id':s['segment_id']} for s in segments if len(s['text'])>=12],profiles)
        coverage.append({'node_id':nid,'status':'supported','model_status':'supported','evidence':refs,'workspace_evidence':refs,
                         'reason':'synthetic_test_fixture only','unverified_assumptions':[],'location_errors':[]})
    assessments=[{'file_id':fid,'retain':True,'role':'anchor' if fid==sources[0]['file_id'] else 'supporting',
                  'sensitive':False,'answer_leakage':False} for fid in profiles]
    cov={'nodes':coverage,'file_assessments':assessments,'retained_file_ids':list(profiles),
         'selected_anchor':{'file_ids':[sources[0]['file_id']],'evidence':coverage[0]['evidence']},
         'cross_file_coherence':{'status':'coherent','reason':'Fictional test case','evidence':coverage[0]['evidence'],'unverified_assumptions':[]},
         'suspected_answer_leakage':False,'unresolved_information_gaps':[],'missing_critical_nodes':[],'status':'ready'}
    report={'interface':'grounded-workspace-v2','seed_id':plan['seed_id'],'seed_sha256':digest(seed),
            'blueprint_sha256':digest(plan),'status':'ready','data_provenance':'synthetic_test_fixture',
            'work_objective_sha256':sha256(plan['work_objective'].encode()),'workspace_files':filehashes}
    c=directory/'construction';save(c/'construction_report.json',report);save(c/'information_coverage.json',cov)
    save(c/'source_manifest.json',{'sources':{r['file_id']:r for r in sources}});save(c/'file_profiles.json',list(profiles.values()))
    return directory,plan,seed


def proposal_for(graph):
    facts=graph['nodes'];by={}
    for f in facts:by.setdefault(f['information_node_id'],[]).append(f['evidence_id'])
    values={f['evidence_id']:f for f in facts}
    approved=next(e for e in by['i1'] if 'Operations' in values[e]['description'])
    actual=next(e for e in by['i2'] if 'Operations' in values[e]['description'])
    policy=next(e for e in by['i3'] if 'Transfers' in values[e]['description'])
    context=next(e for e in by['i3'] if 'maintenance' in values[e]['description'])
    requirements=[{'requirement_id':'req_calc','description':'Compute actual minus approved by category in outputs/comparison.csv; include category, difference, unit. Values must be USD; numeric tolerance 0.01 USD.',
                   'kind':'outcome','information_node_ids':['i4'],'deliverable_ids':['table'],'unscored_reason':None},
                  {'requirement_id':'req_advice','description':'Write outputs/memo.md explaining both category differences and justify a policy-compliant response using maintenance and deferral context.',
                   'kind':'outcome','information_node_ids':['i5'],'deliverable_ids':['memo'],'unscored_reason':None},
                  {'requirement_id':'req_process','description':'Do not modify the input files at any point during execution.',
                   'kind':'constraint','information_node_ids':['i3'],'deliverable_ids':['memo'],'unscored_reason':None}]
    task={'instruction':'For Fictional Example Department, compare approved and actual spending in the illustrative period. Use workspace_init/approved.csv, workspace_init/actual.csv and workspace_init/context.json. Produce the comparison table and a justified manager memo as specified in requirements. Preserve input files throughout execution.',
          'deliverables':[{'deliverable_id':'table','plan_deliverable_id':'out1','path':'outputs/comparison.csv','format':'csv','description':'Category-level comparison.'},
                          {'deliverable_id':'memo','plan_deliverable_id':'out1','path':'outputs/memo.md','format':'md','description':'Reasoned response for the manager.'}],
          'requirements':requirements}
    calc=by['i1']+by['i2']+by['i4'];advice=calc+by['i3']+by['i5']
    rubric={'items':[{'rubric_id':'r_numeric','requirement_id':'req_calc','requirement':'Operations difference equals actual less approved, in USD.',
             'evidence_ids':[actual,approved],'verification_type':'programmatic','weight':1,'critical':True,
             'verification_spec':{'kind':'numeric_formula','target':{'format':'csv','path':'outputs/comparison.csv','key':{'category':'Operations'},'column':'difference','unit_column':'unit'},
               'formula':{'op':'subtract','operands':[{'evidence_id':actual,'column':'amount'},{'evidence_id':approved,'column':'amount'}]},
               'unit':'USD','unit_evidence_id':actual,'absolute_tolerance':0.01,'relative_tolerance':0}},
            {'rubric_id':'r_advice','requirement_id':'req_advice','requirement':'Memo accounts for both categories and justifies a response without assuming transfer authority.',
             'evidence_ids':advice,'verification_type':'semantic','weight':2,'critical':True,
             'verification_spec':{'kind':'semantic_guide','full_credit':['Explain maintenance and deferred purchasing as distinct context for the two categories.','Justify a response consistent with required approval; do not claim authority to transfer.'],
                                  'common_errors':['Assuming deferred purchases mean permanent savings.','Recommending an immediate unauthorized transfer.'],
                                  'conflict_policy':'Unsupported causal claims lose context credit; recommending an unauthorized transfer scores zero for this criterion.'}},
            {'rubric_id':'r_process','requirement_id':'req_process','requirement':'Inputs remain unchanged throughout execution, including temporary edits.',
             'evidence_ids':[policy],'verification_type':'process','weight':1,'critical':True,
             'verification_spec':{'kind':'requires_execution_trace','condition':'No writes to initial source files throughout execution.','required_trace':'Trusted complete file-write audit covering the entire execution interval.'}}]}
    second=copy.deepcopy(rubric['items'][0]);second['rubric_id']='r_numeric_supplies'
    second['requirement']='Supplies difference equals actual less approved, in USD.'
    a=next(e for e in by['i2'] if 'Supplies' in values[e]['description'])
    b=next(e for e in by['i1'] if 'Supplies' in values[e]['description'])
    second['evidence_ids']=[a,b];second['verification_spec']['target']['key']={'category':'Supplies'}
    second['verification_spec']['formula']['operands']=[{'evidence_id':a,'column':'amount'},{'evidence_id':b,'column':'amount'}]
    second['verification_spec']['unit_evidence_id']=a;rubric['items'].insert(1,second)
    return {'task':task,'grounding':[{'requirement_id':'req_calc','evidence_ids':calc},{'requirement_id':'req_advice','evidence_ids':advice},
                                   {'requirement_id':'req_process','evidence_ids':by['i3']}],'rubric':rubric}


def passing_audit(proposal,graph):
    evidence=[next(n['evidence_id'] for n in graph['nodes'] if n['type']=='source_fact')]
    names=['intent_preservation','evidence_support','task_feasibility','deliverable_appropriateness','task_rubric_alignment','verification_soundness','answer_leakage','unnecessary_complexity','multimodal_grounding']
    verdict={'passed':True,'reason':'synthetic_test_fixture mocked audit for engineering validation only','evidence_ids':evidence}
    ground={g['requirement_id']:g['evidence_ids'] for g in proposal['grounding']}
    source_ids={n['evidence_id'] for n in graph['nodes'] if n['type']=='source_fact'}
    return {'dimensions':{k:copy.deepcopy(verdict) for k in names},
            'requirements':[{'requirement_id':r['requirement_id'],**verdict,'evidence_ids':[next(e for e in ground[r['requirement_id']] if e in source_ids)]} for r in proposal['task']['requirements']],
            'rubrics':[{'rubric_id':r['rubric_id'],'requirement_id':r['requirement_id'],**verdict,'evidence_ids':[next(e for e in r['evidence_ids'] if e in source_ids)]} for r in proposal['rubric']['items']]}


class FixtureModel:
    """Mock transport, never presented as an actual GLM call."""
    def __init__(self,mutation=None,audit_mutation=None):self.calls=[];self.mutation=mutation;self.audit_mutation=audit_mutation
    def __call__(self,prompt,context,version):
        self.calls.append({'model_requested':'synthetic_test_fixture_mock','prompt_version':version,'transport':'mock_no_network'})
        if version.startswith('task-rubric-joint'):
            value=proposal_for(context['evidence_graph'])
            if self.mutation:self.mutation(value)
        else:
            value=passing_audit(context['proposal'],context['evidence_graph'])
            if self.audit_mutation:self.audit_mutation(value)
        return value
