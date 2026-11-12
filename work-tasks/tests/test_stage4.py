"""Mocked LLM fixtures test engineering invariants, not professional validity."""
import copy
import tempfile
import unittest
from unittest.mock import patch
from fixture_support import *
from construct_tasks import process_workspace, export_agent, Model
from task_evidence import eligibility, extract, load_production
from task_validation import validate_proposal, validate_audit
from task_verifier import grade, decimal, pointer, reference_formula, run_check


class Stage4Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.directory,self.plan,self.seed=create_fixture(self.root)
        self.cache=self.root/'cache';self.out=self.root/'generated'
        gate,self.snapshot=eligibility(self.directory,self.plan,self.seed,{},self.cache,fixture=True)
        self.assertTrue(gate['eligible']);self.graph=extract(self.snapshot)

    def tearDown(self):self.temp.cleanup()

    def run_pipeline(self,model=None,fixture=True,stage='all'):
        return process_workspace(self.directory,self.plan,self.seed,{},self.cache,self.out,model or FixtureModel(),stage,fixture=fixture)

    def change_coverage(self,fn):
        p=self.directory/'construction/information_coverage.json';value=read(p);fn(value);save(p,value)

    def test_complete_fixture_pipeline_and_replay(self):
        first=self.run_pipeline();self.assertEqual(first['status'],'draft')
        package=self.out/first['task_id'];manifest=read(package/'manifest.json')
        self.assertEqual(manifest['data_provenance'],'synthetic_test_fixture')
        self.assertFalse(manifest['execution_probe_performed']);self.assertFalse(manifest['public_redistribution_allowed'])
        self.assertEqual(len(first['model_calls']),2)
        self.assertEqual(first,self.run_pipeline())
        names={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
        self.assertIn('evaluation/verifier_spec.json',names)
        self.assertNotIn('evaluation/oracle.json',names)

    def test_export_excludes_hidden_files(self):
        result=self.run_pipeline();package=self.out/result['task_id'];dest=self.root/'agent'
        export_agent(package,dest)
        self.assertEqual({p.name for p in dest.iterdir()},{'task.json','workspace_init','outputs'})
        self.assertFalse((dest/'manifest.json').exists())

    def test_fixture_never_enters_production_gate(self):
        model=FixtureModel();result=self.run_pipeline(model,fixture=False)
        self.assertEqual(result['status'],'blocked_upstream');self.assertFalse(model.calls)

    def test_real_pilots_block_without_llm(self):
        plans,seeds,hashes=load_production(REPO/'work-plans/data/pilot',REPO/'work-seeds/archive/data/work_seed_pilot_v2')
        for ws in ('WS001','WS002'):
            directory=REPO/'workspaces/data/pilot'/ws;sid=read(directory/'construction/construction_report.json')['seed_id']
            model=FixtureModel();r=process_workspace(directory,plans[sid],seeds[sid],hashes,self.cache,self.out,model)
            self.assertEqual(r['status'],'blocked_upstream');self.assertFalse(model.calls)
        self.assertFalse(self.out.exists())

    def test_evidence_extraction_is_deterministic_and_answer_free(self):
        self.assertEqual(self.graph,extract(self.snapshot))
        for n in self.graph['nodes']:
            self.assertNotIn('answer',n);self.assertNotIn('expected_value',n)
            if n['type']!='source_fact':self.assertNotIn('workspace_path',n)

    def test_fabricated_evidence_id_rejected(self):
        def mutate(p):p['grounding'][0]['evidence_ids'].append('fabricated')
        r=self.run_pipeline(FixtureModel(mutate));self.assertEqual(r['status'],'rejected');self.assertIn('invalid_evidence_id',r['reasons'])

    def test_nonexistent_location_blocks(self):
        self.change_coverage(lambda c:c['nodes'][0]['workspace_evidence'][0].update(locator='row:999'))
        r=self.run_pipeline();self.assertEqual(r['status'],'blocked_upstream')

    def test_old_profile_cannot_fabricate_fact(self):
        self.change_coverage(lambda c:c['nodes'][0]['workspace_evidence'][0].update(quote='Invented 999 dollars'))
        self.assertEqual(self.run_pipeline()['status'],'blocked_upstream')

    def test_unrelated_information_goal_rejected(self):
        def mutate(p):p['task']['requirements'][0]['information_node_ids']=['marketing_campaign']
        self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_semantically_unrelated_goal_rejected_by_independent_audit(self):
        def mutate(p):p['task']['instruction']='Design a social media advertising campaign.'
        def audit(a):a['dimensions']['intent_preservation'].update(passed=False,reason='Introduces advertising unrelated to budget work.')
        model=FixtureModel(mutate,audit);r=self.run_pipeline(model)
        self.assertEqual(r['status'],'rejected');self.assertEqual(len(model.calls),2)
        self.assertNotEqual(model.calls[0]['prompt_version'],model.calls[1]['prompt_version'])

    def test_rubric_outside_requirement_rejected(self):
        def mutate(p):p['rubric']['items'][0]['requirement_id']='not_in_task'
        self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_rubric_missing_evidence_rejected(self):
        def mutate(p):p['rubric']['items'][0]['evidence_ids']=[]
        self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_wrong_unit_and_unsafe_formula_rejected(self):
        for key,value in [('unit','EUR'),('formula',{'op':'exec','operands':[]})]:
            with self.subTest(key=key):
                def mutate(p):p['rubric']['items'][0]['verification_spec'][key]=value
                self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_formula_missing_column_rejected(self):
        def mutate(p):p['rubric']['items'][0]['verification_spec']['formula']['operands'][0]['column']='not_there'
        self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_input_answer_leakage_rejected_on_fresh_parse(self):
        file=self.directory/'workspace_init/context.json';v=read(file);v['completed']='Recommendations: immediately transfer money.';save(file,v)
        # Simulate an upstream stale risk assessment with updated hash: independent parsing must still reject it.
        c=self.directory/'construction';r=read(c/'construction_report.json');r['workspace_files']['context.json']=sha256(file.read_bytes());save(c/'construction_report.json',r)
        sources=read(c/'source_manifest.json')
        fid=next(s['file_id'] for s in sources['sources'] if s['workspace_path'].endswith('context.json'))
        for s in sources['sources']:
            if s['file_id']==fid:s['sha256']=sha256(file.read_bytes())
        save(c/'source_manifest.json',sources)
        profiles=read_jsonl(c/'file_profiles.jsonl')
        for p in profiles:
            if p['file_id']==fid:p['sha256']=sha256(file.read_bytes())
        (c/'file_profiles.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in profiles))
        result=self.run_pipeline();self.assertEqual(result['status'],'blocked_upstream')
        self.assertIn('fresh_parse_unresolved_risk',result['reasons'])

    def test_hidden_metadata_and_path_traversal_rejected(self):
        for path in ['outputs/../oracle.json','evaluation/result.csv','outputs/../../hidden.csv']:
            def mutate(p):p['task']['deliverables'][0]['path']=path
            self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')
        def mutate(p):p['task']['instruction']+=' Read evaluation/rubric.json.'
        self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_workspace_hash_change_blocks(self):
        (self.directory/'workspace_init/approved.csv').write_text('corrupted')
        self.assertEqual(self.run_pipeline()['status'],'blocked_upstream')

    def test_incomplete_coverage_blocks(self):
        self.change_coverage(lambda c:c['nodes'][0].update(status='partial'))
        model=FixtureModel();self.assertEqual(self.run_pipeline(model)['status'],'blocked_upstream');self.assertFalse(model.calls)

    def test_conflict_and_excluded_source_block(self):
        self.change_coverage(lambda c:c['coherence'].update(status='conflicted'))
        self.assertEqual(self.run_pipeline()['status'],'blocked_upstream')

    def test_excluded_source_never_supports_coverage(self):
        self.change_coverage(lambda c:c['rejected_files'].update({c['retained_file_ids'][0]:['not appropriate']}))
        self.assertEqual(self.run_pipeline()['status'],'blocked_upstream')

    def test_reverse_audit_requires_every_rubric(self):
        def mutate(a):a['rubrics'].pop()
        self.assertEqual(self.run_pipeline(FixtureModel(audit_mutation=mutate))['status'],'rejected')

    def test_no_near_duplicate_double_scoring(self):
        def mutate(p):
            item=copy.deepcopy(p['rubric']['items'][0]);item['rubric_id']='duplicate';p['rubric']['items'].append(item)
        self.assertEqual(self.run_pipeline(FixtureModel(mutate))['status'],'rejected')

    def test_programmatic_wrong_numbers_units_missing_and_process_pending(self):
        r=self.run_pipeline();package=self.out/r['task_id'];run=self.root/'agent';export_agent(package,run)
        file=run/'outputs/comparison.csv'
        file.write_text('category,difference,unit\nOperations,20.005,USD\nSupplies,-20,USD\n')
        result=grade(package,run,self.cache)
        self.assertEqual(result['scores']['programmatic'],1)
        self.assertIsNone(result['scores']['semantic']);self.assertIsNone(result['overall_score']);self.assertEqual(result['critical_gate'],'pending')
        self.assertTrue(any(r['reason']=='requires_execution_trace' and r['score'] is None for r in result['items']))
        for amount,unit in [('999','USD'),('20','EUR'),('','USD')]:
            file.write_text(f'category,difference,unit\nOperations,{amount},{unit}\nSupplies,-20,USD\n')
            self.assertEqual(grade(package,run,self.cache)['critical_gate'],'failed')

    def test_package_tamper_and_symlink_rejected(self):
        r=self.run_pipeline();package=self.out/r['task_id'];file=package/'workspace_init/approved.csv'
        file.unlink();file.symlink_to(self.directory/'workspace_init/approved.csv')
        with self.assertRaises(DataError):export_agent(package,self.root/'agent')

    def test_json_pointer_and_decimal_formats(self):
        self.assertEqual(pointer({'a/b':[{'x~':3}]},'/a~1b/0/x~0'),3)
        self.assertEqual(decimal('(1,000.50)'),decimal('-1000.50'))
        for value in ('NaN','Infinity','','1,2',True,None):
            with self.assertRaises(DataError):decimal(value)

    def test_stage_execution_no_model_until_generation(self):
        model=FixtureModel();r=self.run_pipeline(model,stage='evidence')
        self.assertEqual(r['stage_complete'],'evidence');self.assertFalse(model.calls)
        self.assertFalse(self.out.exists())

    def test_json_and_xlsx_numeric_targets(self):
        result=self.run_pipeline();package=self.out/result['task_id'];run=self.root/'agent';export_agent(package,run)
        graph=read(package/'evaluation/evidence_graph.json');manifest=read(package/'manifest.json')
        spec=copy.deepcopy(read(package/'evaluation/rubric.json')['items'][0]['verification_spec'])
        save(run/'outputs/result.json',{'difference':20,'unit':'USD'})
        spec['target']={'format':'json','path':'outputs/result.json','pointer':'/difference','unit_pointer':'/unit'}
        run_check(spec,package,run,graph,manifest,self.cache)
        run_check({'kind':'json_fields','path':'outputs/result.json','pointers':['/difference','/unit']},package,run,graph,manifest,self.cache)
        from openpyxl import Workbook
        book=Workbook();sheet=book.active;sheet.title='Result';sheet['A1']='difference';sheet['B1']='unit';sheet['A2']=20;sheet['B2']='USD';book.save(run/'outputs/result.xlsx')
        spec['target']={'format':'xlsx','path':'outputs/result.xlsx','sheet':'Result','cell':'A2','unit_cell':'B2'}
        run_check(spec,package,run,graph,manifest,self.cache)
        sheet['A2']='=120-100';book.save(run/'outputs/result.xlsx')
        with self.assertRaisesRegex(DataError,'materialized_value'):run_check(spec,package,run,graph,manifest,self.cache)

    def test_missing_artifact_and_final_integrity_are_not_process_proof(self):
        result=self.run_pipeline();package=self.out/result['task_id'];run=self.root/'agent';export_agent(package,run)
        graph=read(package/'evaluation/evidence_graph.json');manifest=read(package/'manifest.json')
        with self.assertRaises(DataError):run_check({'kind':'file_exists','path':'outputs/absent.json','format':'json'},package,run,graph,manifest,self.cache)
        run_check({'kind':'input_final_integrity'},package,run,graph,manifest,self.cache)
        self.assertEqual(next(r for r in grade(package,run,self.cache)['items'] if r['verification_type']=='process')['status'],'pending')


if __name__=='__main__':unittest.main()
