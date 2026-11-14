"""Synthetic unit fixtures, distinct from the live-model world experiment."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import ROOT, REPO, DataError, sha256
from world_contract import (validate_world,materialize,oracle,visible_reference,grade_numeric,
                            verify_materialization,grade_submission,csv_bytes,OUTPUT_COLUMNS)
from world_pilot import CHECKS,run,export_agent,validate_review,engineering_checks


def fixture_world():
    row={'work_package_id':'WP1','name':'Synthetic test fixture',
         'baseline_start':'2025-01-01','baseline_due':'2025-02-01','actual_finish':None,
         'baseline_budget_usd':1000,'baseline_effort_hours':100,'planned_completed_effort_hours':40,
         'completed_effort_hours':30,'actual_cost_usd':350,'estimated_remaining_hours':80,
         'hourly_rate_usd':10,'committed_remaining_nonlabor_usd':50,'available_remaining_hours':60}
    return {'provenance':'synthetic','project_name':'Synthetic test fixture',
            'project_brief':'Unit test only, not occupational data.', 'snapshot_date':'2025-01-15',
            'currency':'USD','monitoring_policy':'Fixture approvals required.',
            'work_packages':[{**row,'work_package_id':f'WP{i}'} for i in range(1,4)]}


def write_workspace(root,world):
    hashes={}
    for name,data in materialize(world).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);hashes[name]=sha256(data)
    return hashes


class WorldContractTests(unittest.TestCase):
    def test_visible_solver_matches_independently_known_values(self):
        w=fixture_world()
        expected={'work_package_id':'WP1','currency':'USD','cost_variance_to_date_usd':-650,
                  'schedule_effort_gap_hours':10,'forecast_total_cost_usd':1200,
                  'forecast_budget_variance_usd':200,'resource_gap_hours':20}
        self.assertEqual(oracle(w)[0],expected)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);hashes=write_workspace(root,w)
            self.assertEqual(visible_reference(root)[0],expected)
            self.assertTrue(verify_materialization(root,w,hashes)['passed'])
            checks=engineering_checks(root,w,hashes)
            self.assertEqual(checks['mutations_rejected'],18)

    def test_wrong_units_nan_tolerance_and_sign(self):
        expected=oracle(fixture_world())
        for value in ('NaN','Infinity','-1200','1200.02','not numeric'):
            rows=copy.deepcopy(expected);rows[0]['forecast_total_cost_usd']=value
            self.assertFalse(grade_numeric(rows,expected)['passed'])
        rows=copy.deepcopy(expected);rows[0]['forecast_total_cost_usd']='1200.01'
        self.assertTrue(grade_numeric(rows,expected)['passed'])
        rows=copy.deepcopy(expected);rows[0]['currency']='EUR'
        self.assertFalse(grade_numeric(rows,expected)['passed'])

    def test_world_date_join_and_remaining_constraints(self):
        for key,value,reason in [('actual_finish','2025-01-14','completion'),
                                 ('completed_effort_hours',101,'effort_out_of_range'),
                                 ('baseline_due','2025-01-10','due_package'),
                                 ('estimated_remaining_hours',0,'missing_remaining'),
                                 ('name','=HYPERLINK("x")','spreadsheet_formula')]:
            w=fixture_world();w['work_packages'][0][key]=value
            with self.assertRaisesRegex(DataError,reason):validate_world(w)
        w=fixture_world();w['work_packages'][1]['work_package_id']='WP1'
        with self.assertRaisesRegex(DataError,'duplicate_work_package'):validate_world(w)

    def test_no_generated_answer_fields_allowed(self):
        w=fixture_world();w['work_packages'][0]['forecast_total_cost_usd']=1200
        with self.assertRaises(DataError):validate_world(w)
        w=fixture_world();w['provenance']='real_original'
        with self.assertRaises(DataError):validate_world(w)

    def test_determinism_and_hidden_or_changed_file_block(self):
        w=fixture_world();before=copy.deepcopy(w)
        self.assertEqual(materialize(w),materialize(w));self.assertEqual(w,before)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);hashes=write_workspace(root,w)
            (root/'oracle.json').write_text('[]')
            with self.assertRaisesRegex(DataError,'hash_mismatch'):verify_materialization(root,w,hashes)
            (root/'oracle.json').unlink()
            (root/'records/actuals.csv').write_text('corrupt')
            with self.assertRaisesRegex(DataError,'hash_mismatch'):verify_materialization(root,w,hashes)

    def test_duplicate_and_missing_output_rows(self):
        rows=oracle(fixture_world())
        for output in (rows+[rows[0]],rows[:-1]):
            with self.assertRaises(DataError):grade_numeric(output,rows)

    def test_complete_record_and_no_resource_gap_boundary(self):
        w=fixture_world();p=w['work_packages'][0]
        p.update(completed_effort_hours=100,actual_finish='2025-01-12',estimated_remaining_hours=0,
                 committed_remaining_nonlabor_usd=0,available_remaining_hours=0)
        validate_world(w);self.assertEqual(oracle(w)[0]['forecast_total_cost_usd'],350)
        self.assertEqual(oracle(w)[0]['resource_gap_hours'],0)


class WorldPipelineTests(unittest.TestCase):
    def args(self,path):
        return argparse.Namespace(plan_dir=REPO/'work-plans/data/semantic_pilot',
            seed_file=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl',
            config=ROOT/'config/world_pilot.json', output_dir=path/'package',cache_dir=path/'cache',offline=True)

    def fake_call(self,review):
        def call(llm,path,context,cache,offline):
            value=fixture_world() if path.name.startswith('world_generator') else review
            return value,{'request_sha256':path.name,'usage':{},'test_fixture':True}
        return call

    def review(self):
        return {'accepted':True,'checks':{k:True for k in CHECKS},'issues':[], 'limitations':['Synthetic test fixture, not a live model decision.']}

    def test_full_fixture_export_replay_and_no_false_complete_grade(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);args=self.args(root)
            with patch('world_pilot.model_call',side_effect=self.fake_call(self.review())):
                report=run(args)
                self.assertEqual(report['status'],'experimental_draft',report)
                before={p.relative_to(args.output_dir).as_posix():p.read_bytes() for p in args.output_dir.rglob('*') if p.is_file()}
                run(args)
                self.assertEqual(before,{p.relative_to(args.output_dir).as_posix():p.read_bytes() for p in args.output_dir.rglob('*') if p.is_file()})
            export_agent(args.output_dir,root/'worker')
            self.assertEqual({p.name for p in (root/'worker').iterdir()},{'task.json','workspace_init','outputs'})
            rows=visible_reference(root/'worker/workspace_init')
            (root/'worker/outputs/assessment.csv').write_bytes(csv_bytes(OUTPUT_COLUMNS,rows))
            expected=oracle(fixture_world())
            self.assertFalse(grade_submission(root/'worker',expected)['overall_pass'])
            (root/'worker/outputs/report.md').write_text('Dummy text is not a professionally reviewed report.')
            result=grade_submission(root/'worker',expected)
            self.assertIsNone(result['overall_pass']);self.assertIsNone(result['semantic_score'])
            (root/'worker/outputs/report.md').unlink()
            (root/'worker/outputs/report.md').symlink_to(args.output_dir/'construction/hidden_world.json')
            with self.assertRaisesRegex(DataError,'symlink'):grade_submission(root/'worker',expected)

    def test_semantic_reject_is_not_overridden(self):
        review=self.review();review['accepted']=False;review['checks']['professional_plausibility']=False;review['issues']=['Fixture rejection']
        with tempfile.TemporaryDirectory() as t:
            args=self.args(Path(t))
            with patch('world_pilot.model_call',side_effect=self.fake_call(review)):
                report=run(args)
            self.assertEqual(report['status'],'rejected');self.assertFalse((args.output_dir/'task.json').exists())
            with self.assertRaises(DataError):export_agent(args.output_dir,Path(t)/'worker')

    def test_malformed_review_not_accepted(self):
        r=self.review();r['checks']['intent_preservation']=False
        with self.assertRaisesRegex(DataError,'review_decision_mismatch'):validate_review(r)


if __name__=='__main__':unittest.main()
