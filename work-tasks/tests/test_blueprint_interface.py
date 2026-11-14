"""New blueprint interface invariants, using only fictional unit-test material."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fixture_support import *
from task_evidence import eligibility,extract
from task_validation import validate_proposal,validate_audit
from construct_tasks import process_workspace,generation_context,export_agent,bounded_context,Model,grounded_call,compile_artifact_checks
from task_verifier import run_check

class BlueprintInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.directory,self.plan,self.seed=create_fixture(self.root);self.cache=self.root/'cache'
    def tearDown(self):self.temp.cleanup()
    def gate(self):return eligibility(self.directory,self.plan,self.seed,{},self.cache,fixture=True)
    def change(self,name,fn):
        p=self.directory/'construction'/name;v=read(p);fn(v);save(p,v)
    def test_production_interface_with_mocked_acquisition_and_fresh_segment_recheck(self):
        # Simulated transport records exist only in this TemporaryDirectory. No network
        # access, no real-source success claim, and no task package is produced.
        self.change('construction_report.json',lambda r:r.update(data_provenance='mocked_acquisition_unit_test'))
        def sources(v):
            for r in v['sources'].values():
                url='https://example.org/'+r['workspace_path']
                r.update(origin='real_original',original_url=url,final_url=url,source_page=url,retrieved_at='unit-test')
        self.change('source_manifest.json',sources)
        def coverage(v):
            v['model_recommendation']='ready'
            for a in v['file_assessments']:
                a.update(reason='Mocked audit only',license={'status':'unknown','reason':'No permission asserted','evidence':[]})
            v['selected_anchor'].update(identity='Mocked fixture',scope='Unit test only')
            v['selected_anchor']['evidence']=[{k:e[k] for k in ('file_id','segment_id')} for e in v['selected_anchor']['evidence']]
        self.change('information_coverage.json',coverage)
        gate,snapshot=eligibility(self.directory,self.plan,self.seed,{},self.cache)
        self.assertTrue(gate['eligible']);self.assertEqual(len(snapshot['sources']),3)
        self.change('information_coverage.json',lambda v:v['cross_file_coherence']['evidence'][0].update(segment_id='seg_fake'))
        with self.assertRaises(DataError):eligibility(self.directory,self.plan,self.seed,{},self.cache)
    def test_generator_receives_complete_located_source_context(self):
        snapshot=self.gate()[1];ctx=generation_context(snapshot,extract(snapshot))
        for p in ctx['fresh_profiles']:
            self.assertEqual(p['located_text'],'\n'.join(s['locator']+'\t'+s['text'] for s in snapshot['profiles'][p['file_id']]['segments']))
        self.assertEqual(ctx['raw_task_text'],self.seed['task_text'])
    def test_large_csv_context_keeps_cited_records_and_declares_excerpts(self):
        snapshot=self.gate()[1]
        p=next(p for p in snapshot['profiles'].values() if p['type']=='csv')
        p['segments']=[{'locator':f'row:{i}','text':f'fixture,{i}'} for i in range(1,101)]
        p['structure'].update(content_fully_segmented=False,rows=200,indexed_data_rows=99)
        graph={'nodes':[{'evidence_id':'e_fixture_excerpt','information_node_id':self.plan['information_nodes'][0]['id'],
                         'type':'source_fact','file_id':p['file_id'],'locator':'row:80'}]}
        ctx=generation_context(snapshot,graph)
        view=next(v for v in ctx['fresh_profiles'] if v['file_id']==p['file_id'])
        self.assertIn('row:80\tfixture,80',view['located_text'])
        self.assertIn('row:79\tfixture,79',view['located_text'])
        self.assertNotIn('row:70\t',view['located_text'])
        self.assertFalse(view['context_selection']['all_source_records_shown'])
        self.assertEqual(len(p['segments']),100)
    def test_generator_gets_programmatically_derived_reference_contract(self):
        snapshot=self.gate()[1];graph=extract(snapshot);ctx=generation_context(snapshot,graph)
        mapping=ctx['allowed_evidence_by_information_node']
        for node in self.plan['information_nodes']:
            ancestors={node['id']}
            while True:
                expanded=ancestors | {a for a,b in self.plan['dependencies'] if b in ancestors}
                if expanded==ancestors:break
                ancestors=expanded
            self.assertEqual(set(mapping[node['id']]),{n['evidence_id'] for n in graph['nodes'] if n['information_node_id'] in ancestors})
    def test_planning_review_can_cite_approved_requirements_but_factual_review_needs_source(self):
        snapshot=self.gate()[1];graph=extract(snapshot);proposal=proposal_for(graph)
        audit=passing_audit(proposal,graph)
        planning_id=next(n['evidence_id'] for n in graph['nodes'] if n['type']=='derived_requirement')
        audit['dimensions']['unnecessary_complexity']['evidence_ids']=[planning_id]
        self.assertTrue(validate_audit(audit,proposal,graph)['passed'])
        audit['dimensions']['evidence_support']['evidence_ids']=[planning_id]
        with self.assertRaisesRegex(DataError,'audit_missing_source_evidence'):validate_audit(audit,proposal,graph)
        audit=passing_audit(proposal,graph)
        audit['dimensions']['unnecessary_complexity']['evidence_ids']=['invented']
        with self.assertRaisesRegex(DataError,'audit_unknown_evidence'):validate_audit(audit,proposal,graph)
    def test_bounded_context_preserves_spreadsheet_neighbours_and_headers(self):
        rows=[{'locator':f'sheet:Dictionary:row:{i}','text':f'A{i}=field B{i}=definition '+('x'*50)} for i in range(1,101)]
        view,bounded=bounded_context(rows,{'sheet:Dictionary:row:80'},'xlsx',1000)
        locs={s['locator'] for s in view}
        self.assertTrue(bounded)
        for i in (1,2,78,79,80,81,82):self.assertIn(f'sheet:Dictionary:row:{i}',locs)
        self.assertLess(len(view),100)
    def test_bounded_context_keeps_whole_cited_pdf_page_or_fails(self):
        rows=[{'locator':f'page:{page}:line:{line}','text':'x'*100} for page in range(1,4) for line in (1,2)]
        view,bounded=bounded_context(rows,{'page:2:line:1'},'pdf',250)
        self.assertTrue(bounded)
        self.assertEqual({s['locator'] for s in view},{'page:2:line:1','page:2:line:2'})
        with self.assertRaisesRegex(DataError,'mandatory_citation_context'):
            bounded_context(rows,{'page:2:line:1'},'pdf',150)
    def test_model_retries_json_syntax_once_without_repairing_semantic_failures(self):
        config={'max_model_input_bytes':10000,'retries':1};ctx={'evidence':'fictional fixture only'}
        model=Model(config,{},self.cache)
        with patch('construct_tasks.construct_seeds.llm_call',side_effect=[DataError('llm_response_not_json'),({'ok':True},{'prompt_version':'fixture'})]) as call:
            self.assertEqual(model('fixture',ctx,'fixture'),{'ok':True})
            self.assertEqual(call.call_count,2)
            retry=call.call_args_list[1].args[2]
            self.assertEqual(retry['evidence'],ctx['evidence']);self.assertIn('format_retry_instruction',retry)
        self.assertNotIn('format_retry_instruction',ctx)
        self.assertTrue(model.calls[0]['format_retry'])
        with patch('construct_tasks.construct_seeds.llm_call',side_effect=DataError('llm_response_not_json')) as call:
            with self.assertRaisesRegex(DataError,'llm_response_not_json'):model('fixture',ctx,'fixture')
            self.assertEqual(call.call_count,2)
        with patch('construct_tasks.construct_seeds.llm_call',side_effect=DataError('unsupported_requirement')) as call:
            with self.assertRaisesRegex(DataError,'unsupported_requirement'):model('fixture',ctx,'fixture')
            self.assertEqual(call.call_count,1)
    def test_short_evidence_handles_roundtrip_only_reference_fields(self):
        context={'evidence_graph':{'nodes':[{'evidence_id':'e_canonical','type':'source_fact'}]},'allowed':['e_canonical']}
        def model(prompt,ctx,version):
            self.assertEqual(ctx['allowed'],['fact_001'])
            return {'evidence_ids':['fact_001','fact_999'],'text':'fact_001'}
        result=grounded_call(model,'fixture',context,'fixture')
        self.assertEqual(result['evidence_ids'],['e_canonical','fact_999'])
        self.assertEqual(context['allowed'],['e_canonical'])
        with self.assertRaisesRegex(DataError,'hidden_metadata_reference'):visible_text(result['text'])
    def test_artifact_compiler_adds_only_declared_output_readability(self):
        proposal={'task':{'deliverables':[{'deliverable_id':'d','path':'outputs/report.md','format':'md'}],
            'requirements':[{'requirement_id':'r','description':'Fictional semantic outcome','information_node_ids':['i1'],'deliverable_ids':['d']}]},
            'grounding':[{'requirement_id':'r','evidence_ids':['e_fixture']}],
            'rubric':{'items':[{'rubric_id':'b','requirement_id':'r','verification_spec':{'kind':'semantic_guide','full_credit':['Fixture evaluation guidance.']}}]}}
        original=copy.deepcopy(proposal['task']['requirements'][0])
        compile_artifact_checks(proposal,{'nodes':[{'type':'source_fact','evidence_id':'e_fixture'}]})
        self.assertEqual(proposal['task']['requirements'][0],original)
        self.assertEqual(proposal['rubric']['items'][0]['requirement'],original['description'])
        self.assertEqual(proposal['rubric']['items'][0]['verification_spec']['full_credit'][0],
                         'Satisfy every part of this task requirement: '+original['description'])
        self.assertEqual(proposal['task']['requirements'][1]['description'],'Create a readable md file at outputs/report.md.')
        check=proposal['rubric']['items'][-1]
        self.assertEqual(check['verification_spec'],{'kind':'file_exists','path':'outputs/report.md','format':'md'})
        self.assertEqual(check['weight'],1)
        self.assertEqual(check['evidence_ids'],['e_fixture'])
        with self.assertRaisesRegex(DataError,'file_checks_are_compiled'):
            compile_artifact_checks(proposal,{'nodes':[{'type':'source_fact','evidence_id':'e_fixture'}]})
    def test_artifact_compiler_only_completes_missing_extensions_and_exact_references(self):
        proposal={'task':{'instruction':'Save to outputs/report; outputs/report_other is unrelated.',
            'deliverables':[{'deliverable_id':'d','path':'outputs/report','format':'pdf'}],
            'requirements':[{'requirement_id':'r','description':'Use outputs/report','information_node_ids':['i1'],'deliverable_ids':['d']}]},
            'grounding':[{'requirement_id':'r','evidence_ids':['e_fixture']}],
            'rubric':{'items':[{'rubric_id':'b','requirement_id':'r','verification_spec':{'kind':'semantic_guide','full_credit':['Fixture evaluation guidance.']}}]}}
        compile_artifact_checks(proposal,{'nodes':[{'type':'source_fact','evidence_id':'e_fixture'}]})
        self.assertEqual(proposal['task']['deliverables'][0]['path'],'outputs/report.pdf')
        self.assertEqual(proposal['task']['instruction'],'Save to outputs/report.pdf; outputs/report_other is unrelated.')
        self.assertEqual(proposal['task']['requirements'][0]['description'],'Use outputs/report.pdf')
    def test_previous_html_workspace_is_blocked_by_new_policy(self):
        directory=REPO/'workspaces/data/visualization_pilot_final/WS_df663f328a47'
        if not (directory/'workspace_init').exists():self.skipTest('Local historical pilot bytes not installed')
        from task_evidence import load_production
        plans,seeds,hashes=load_production(REPO/'work-plans/data/visualization_pilot',REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
        sid='raw_31_0_21828';model=FixtureModel()
        result=process_workspace(directory,plans[sid],seeds[sid],hashes,self.cache,self.root/'out',model)
        self.assertEqual(result['status'],'blocked_upstream')
        self.assertIn('html_not_allowed_in_workspace',result['reasons']);self.assertFalse(model.calls)
    def test_export_rejects_html_disguised_as_native_input(self):
        result=process_workspace(self.directory,self.plan,self.seed,{},self.cache,self.root/'packages',FixtureModel(),fixture=True)
        package=self.root/'packages'/result['task_id'];name='workspace_init/context.json'
        raw=b'<html><body>Not a native JSON input</body></html>'
        (package/name).write_bytes(raw);m=read(package/'manifest.json')
        m['workspace_files']['context.json']=sha256(raw);m['package_files'][name]=sha256(raw);save(package/'manifest.json',m)
        with self.assertRaises(DataError):export_agent(package,self.root/'agent')
        self.assertFalse((self.root/'agent').exists())
    def test_seed_hash_changed_blocks(self):
        self.seed['task_text']+=' altered'
        self.assertIn('seed_hash_mismatch',self.gate()[0]['reasons'])
    def test_blueprint_hash_changed_blocks(self):
        self.plan['work_objective']+=' altered'
        self.assertIn('plan_hash_mismatch',self.gate()[0]['reasons'])
    def test_segment_id_must_exist_in_actual_bytes(self):
        self.change('information_coverage.json',lambda v:v['nodes'][0]['evidence'][0].update(segment_id='seg_fabricated'))
        with self.assertRaisesRegex(DataError,'unknown_segment'):self.gate()
    def test_instruction_is_not_fabricated_source_fact_and_must_be_resolved(self):
        self.plan['information_nodes'].append({'id':'i6','type':'external_input','description':'Intended audience and decision purpose.',
            'supply_channel':'task_instruction','critical':True})
        self.plan['dependencies'].append(['i6','i5'])
        self.change('construction_report.json',lambda r:r.update(blueprint_sha256=digest(self.plan)))
        snapshot=self.gate()[1];g=extract(snapshot)
        node=next(n for n in g['nodes'] if n['information_node_id']=='i6')
        self.assertEqual(node['type'],'instruction_requirement');self.assertNotIn('file_id',node)
        with self.assertRaisesRegex(DataError,'core_intent_information_omitted'):
            validate_proposal(proposal_for(g),g,snapshot)
    def test_visual_file_check_tests_type_not_visual_correctness(self):
        from PIL import Image
        run=self.root/'run';(run/'outputs').mkdir(parents=True)
        Image.new('RGB',(16,16),'white').save(run/'outputs/chart.png')
        run_check({'kind':'file_exists','path':'outputs/chart.png','format':'png'},self.root,run,{}, {},self.cache)
        (run/'outputs/chart.png').write_text('not an image')
        with self.assertRaises(DataError):
            run_check({'kind':'file_exists','path':'outputs/chart.png','format':'png'},self.root,run,{}, {},self.cache)
    def test_documented_file_exists_contract_requires_readability_not_directory_exclusivity(self):
        run=self.root/'file-check';(run/'outputs').mkdir(parents=True)
        target=run/'outputs/report.md';target.write_text('')
        spec={'kind':'file_exists','path':'outputs/report.md','format':'md'}
        with self.assertRaisesRegex(DataError,'deliverable_not_readable'):
            run_check(spec,self.root,run,{}, {},self.cache)
        target.write_text('# Fictional unit test report\n')
        (run/'outputs/extra.txt').write_text('Not forbidden by this check alone')
        run_check(spec,self.root,run,{}, {},self.cache)
    def test_allowed_directory_mention_with_sentence_period(self):
        snapshot=self.gate()[1];graph=extract(snapshot);value=proposal_for(graph)
        value['task']['instruction']+=' Save deliverables under outputs/.'
        self.assertTrue(validate_proposal(value,graph,snapshot)['passed'])
        value['task']['instruction']+=' Read outputs/../hidden.json.'
        with self.assertRaises(DataError):validate_proposal(value,graph,snapshot)
    def test_no_task_calls_for_incomplete_new_workspace(self):
        self.change('construction_report.json',lambda r:r.update(status='incomplete'))
        model=FixtureModel();r=process_workspace(self.directory,self.plan,self.seed,{},self.cache,self.root/'out',model,fixture=True)
        self.assertEqual(r['status'],'blocked_upstream');self.assertFalse(model.calls)

if __name__=='__main__':unittest.main()
