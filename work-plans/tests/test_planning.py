import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan_intents as planning

SOURCE = planning.REPO / 'work-seeds/archive/data/work_seed_pilot_v2'
CONFIG = planning.REPO / 'work-seeds/config/seed_pipeline.llmcenter.json'


def fixture(sid):
    """Synthetic unit-test plan, never exported to the actual pilot."""
    return {
        'seed_id': sid, 'work_objective': 'Analyze budget differences and recommend appropriate adjustments.',
        'deliverables': [{'id': 'out1', 'type': 'report', 'description': 'Budget comparison and adjustment recommendations'}],
        'information_nodes': [
            {'id': 'i1', 'type': 'external_input', 'description': 'Approved budget by category and scope'},
            {'id': 'i2', 'type': 'external_input', 'description': 'Actual expenditure by matching category and scope'},
            {'id': 'i3', 'type': 'derived_information', 'description': 'Differences between approved and actual expenditure'},
            {'id': 'i4', 'type': 'professional_judgment', 'description': 'Proposed adjustments supported by the budget comparison'},
        ],
        'dependencies': [['i1', 'i3'], ['i2', 'i3'], ['i3', 'i4'], ['i4', 'out1']],
    }


def review_fixture(plan):
    return {'checks': {k: {'passed': True, 'reason': 'Mocked test review, not actual model judgment.'} for k in planning.SEMANTIC_FLAGS},
            'edge_reviews': [{'from': a, 'to': b, 'valid': True, 'reason': 'Mocked test dependency explanation.'} for a,b in plan['dependencies']]}


def fake_call(config, prompt, context, cache, *, prompt_version):
    sid = context['seed']['seed_id']
    result = fixture(sid) if prompt_version == planning.PROMPT_VERSION else review_fixture(context['plan'])
    return result, {'model_requested': 'unit-test-only', 'prompt_version': prompt_version, 'request_sha256': sid + prompt_version}


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.ids, self.seeds, self.evidence, _ = planning.load_inputs(SOURCE, 4)
        self.plan = fixture(self.ids[0])

    def validate(self, plan=None):
        return planning.validate_plan(self.plan if plan is None else plan, self.ids, self.ids[0])

    def test_valid_plan_and_exact_schema(self):
        self.assertTrue(self.validate()['passed'])
        self.plan['occupation_code'] = '13-2031.00'
        self.assertFalse(self.validate()['checks']['schema'])

    def test_seed_must_be_sampled_and_match_request(self):
        self.plan['seed_id'] = 'seed_' + '0' * 24
        self.assertFalse(self.validate()['checks']['seed_is_sampled'])
        self.plan['seed_id'] = self.ids[1]
        self.assertFalse(self.validate()['checks']['seed_matches_request'])

    def test_duplicate_nodes_and_edges_rejected(self):
        self.plan['information_nodes'].append(copy.deepcopy(self.plan['information_nodes'][0]))
        self.assertFalse(self.validate()['checks']['unique_node_ids'])
        self.plan = fixture(self.ids[0])
        self.plan['dependencies'].append(['i1', 'i3'])
        self.assertFalse(self.validate()['checks']['schema'])

    def test_unknown_edge_endpoint(self):
        self.plan['dependencies'].append(['i99', 'out1'])
        self.assertFalse(self.validate()['checks']['valid_edge_references'])

    def test_cycle_and_self_loop(self):
        for edge in (['i4', 'i3'], ['i3', 'i3']):
            plan = copy.deepcopy(self.plan); plan['dependencies'].append(edge)
            self.assertFalse(self.validate(plan)['checks']['directed_acyclic_graph'])

    def test_unused_information_rejected(self):
        self.plan['information_nodes'].append({'id': 'i5', 'type': 'external_input', 'description': 'Unrelated historical correspondence'})
        self.assertFalse(self.validate()['checks']['all_information_serves_deliverables'])

    def test_each_output_has_information_dependencies_and_is_sink(self):
        self.plan['deliverables'].append({'id': 'out2', 'type': 'memo', 'description': 'Additional independent memorandum'})
        self.assertFalse(self.validate()['checks']['deliverables_have_information_inputs'])
        self.plan['dependencies'].append(['out1', 'out2'])
        self.assertFalse(self.validate()['checks']['deliverables_are_sinks'])

    def test_derived_nodes_need_inputs_external_nodes_are_roots(self):
        self.plan['dependencies'] = [['i3', 'i4'], ['i4', 'out1']]
        self.assertFalse(self.validate()['checks']['derived_and_judgment_have_inputs'])
        self.plan = fixture(self.ids[0]); self.plan['dependencies'].append(['i2', 'i1'])
        self.assertFalse(self.validate()['checks']['external_inputs_are_roots'])

    def test_case_literals_sources_and_answer_markers(self):
        for text, check in [
            ('Actual spending is 10000 dollars', 'no_numeric_case_literals'),
            ('Financial records for Acme LLC', 'no_source_urls_or_company_suffixes'),
            ('Budget available at https://fabricated.invalid/budget', 'no_source_urls_or_company_suffixes'),
            ('The department is over budget', 'no_obvious_filled_answer_markers')]:
            plan = copy.deepcopy(self.plan); plan['information_nodes'][0]['description'] = text
            self.assertFalse(self.validate(plan)['checks'][check])

    def test_no_input_carrier_assignment(self):
        self.plan['information_nodes'][0]['description'] = 'Approved budget supplied in a PDF file'
        self.assertFalse(self.validate()['checks']['no_input_carrier_assignment'])

    def test_semantic_results_are_separate_from_graph_checks(self):
        review = review_fixture(self.plan)
        self.assertTrue(self.validate()['passed'])
        review['checks']['objective_alignment']['passed'] = False
        self.assertEqual(planning.validate_semantic_review(review, self.plan), ['semantic:objective_alignment'])
        review['checks']['objective_alignment']['passed'] = 'true'
        with self.assertRaises(planning.DataError): planning.validate_semantic_review(review, self.plan)

    def test_review_must_explain_every_edge_once(self):
        for mutation in ('missing', 'duplicate', 'unknown'):
            review = review_fixture(self.plan)
            if mutation == 'missing': review['edge_reviews'].pop()
            elif mutation == 'duplicate': review['edge_reviews'].append(review['edge_reviews'][0])
            else: review['edge_reviews'][0]['to'] = 'i99'
            with self.assertRaises(planning.DataError): planning.validate_semantic_review(review, self.plan)

    def test_scope_limit_and_upstream_evidence_foreign_key(self):
        ids, _, _, total = planning.load_inputs(SOURCE, 1)
        self.assertEqual(ids, self.ids[:1]); self.assertEqual(total, 4)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in planning.INPUT_FILES: shutil.copyfile(SOURCE / name, root / name)
            (root / 'occupational_evidence.jsonl').write_text('')
            with self.assertRaises(planning.DataError): planning.load_inputs(root, 4)

    def test_rejected_plan_does_not_run_semantic_review(self):
        call = Mock(return_value=({'seed_id': self.ids[0]}, {'model_requested': 'mock'}))
        r = planning.process_seed(self.seeds[self.ids[0]], self.evidence, self.ids, {}, Path('/unused'), call)
        self.assertEqual(r['status'], 'deterministic_rejected'); call.assert_called_once()
        self.assertEqual(r['semantic']['status'], 'not_run')

    def test_semantic_rejection_is_not_admitted_or_repaired(self):
        def reject(*args, **kwargs):
            result, meta = fake_call(*args, **kwargs)
            if kwargs['prompt_version'] == planning.REVIEW_VERSION:
                result['checks']['case_neutrality']['passed'] = False
            return result, meta
        call = Mock(side_effect=reject)
        r = planning.process_seed(self.seeds[self.ids[0]], self.evidence, self.ids, {}, Path('/unused'), call)
        self.assertEqual(r['status'], 'semantic_rejected'); self.assertEqual(call.call_count, 2)

    def test_interrupt_resume_offline_replay_and_input_immutability(self):
        before = planning.file_hashes(SOURCE)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp); out = root / 'out'; cache = root / 'cache'
            count = 0
            def interrupted(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 3: raise KeyboardInterrupt()
                return fake_call(*args, **kwargs)
            with self.assertRaises(KeyboardInterrupt): planning.run(SOURCE, out, cache, CONFIG, 2, call=interrupted)
            report = json.loads((out / 'planning_report.json').read_text())
            self.assertEqual(report['counts']['successful'], 1)
            resume = Mock(side_effect=fake_call)
            report = planning.run(SOURCE, out, cache, CONFIG, 2, call=resume)
            self.assertEqual(resume.call_count, 2); self.assertEqual(report['counts']['successful'], 2)
            snapshot = {p.name: p.read_bytes() for p in out.iterdir()}
            planning.run(SOURCE, out, cache, CONFIG, 2, call=Mock(side_effect=AssertionError('No network on replay')))
            self.assertEqual(snapshot, {p.name:p.read_bytes() for p in out.iterdir()})
            receipt = next((cache / 'records').glob('*.json'))
            value = json.loads(receipt.read_text()); value['plan']['work_objective'] = 'Changed objective without a matching semantic review.'
            receipt.write_text(json.dumps(value))
            with self.assertRaisesRegex(planning.DataError, 'checkpoint_hash_mismatch'):
                planning.run(SOURCE, out, cache, CONFIG, 2, call=fake_call)
        self.assertEqual(before, planning.file_hashes(SOURCE))

    def test_failures_are_cached_and_zero_limit_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp); error = Mock(side_effect=planning.DataError('http_status:503'))
            r = planning.run(SOURCE, root / 'out', root / 'cache', CONFIG, 1, call=error)
            self.assertEqual(r['counts']['errors'], 1)
            replay = Mock(side_effect=AssertionError('Cached failure must not invoke model'))
            planning.run(SOURCE, root / 'out', root / 'cache', CONFIG, 1, call=replay)
            replay.assert_not_called()
            r = planning.run(SOURCE, root / 'empty', root / 'cache', CONFIG, 0, call=replay)
            self.assertEqual(r['counts']['successful'], 0)

    def test_separate_audit_can_reject_but_not_force_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp); audit = root / 'audit.json'
            decision = {'plan_sha256': planning.sha256(planning.json_bytes(fixture(self.ids[0]))),
                        'reason': 'A required premise is missing.'}
            audit.write_text(json.dumps({self.ids[0]: decision}))
            r = planning.run(SOURCE, root / 'out', root / 'cache', CONFIG, 1,
                             call=fake_call, audit_rejections_path=audit)
            self.assertEqual(r['counts']['successful'], 0)
            self.assertEqual(r['counts']['rejected'], 1)
            row = r['seeds'][self.ids[0]]
            self.assertTrue(row['deterministic']['passed'])
            self.assertEqual(row['status_before_audit'], 'accepted')
            self.assertEqual(row['status'], 'audit_rejected')
            self.assertEqual((root / 'out/work_plans.jsonl').read_text(), '')
            snapshot = (root / 'out/planning_report.json').read_bytes()
            planning.run(SOURCE, root / 'out', root / 'cache', CONFIG, 1,
                         call=Mock(side_effect=AssertionError('No network on replay')), audit_rejections_path=audit)
            self.assertEqual(snapshot, (root / 'out/planning_report.json').read_bytes())
            r = planning.run(SOURCE, root / 'failed', root / 'failed_cache', CONFIG, 1,
                             call=Mock(side_effect=planning.DataError('http_status:503')), audit_rejections_path=audit)
            self.assertEqual(r['counts']['errors'], 1)
            self.assertEqual(r['seeds'][self.ids[0]]['status'], 'generation_error')
            audit.write_text(json.dumps({self.ids[0]: {**decision, 'plan_sha256': '0' * 64}}))
            with self.assertRaisesRegex(planning.DataError, 'audit_rejection_plan_hash_mismatch'):
                planning.run(SOURCE, root / 'stale', root / 'cache', CONFIG, 1,
                             call=fake_call, audit_rejections_path=audit)
            for invalid in ({self.ids[0]: True}, {'unknown_seed': 'Reject'}):
                audit.write_text(json.dumps(invalid))
                with self.assertRaises(planning.DataError):
                    planning.run(SOURCE, root / 'other', root / 'cache', CONFIG, 1,
                                 call=fake_call, audit_rejections_path=audit)


if __name__ == '__main__': unittest.main()
