import copy
import json
import tempfile
import unittest
from pathlib import Path
from build import ROOT, build, dump, rows, sha, write_csv
from reference import solve
from run import reset, verify


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / 'run'
        reset(self.run)
        self.observations = ROOT / 'review/visual_observation.json'
        solve(self.run, self.observations)

    def test_correct_reference_and_private_boundary(self):
        grade = verify(self.run)
        self.assertTrue(grade['automated_checks_passed'])
        self.assertFalse(grade['training_admitted'])
        self.assertFalse((self.run / 'evaluation').exists())
        self.assertFalse((self.run / 'seed.json').exists())
        with self.assertRaises(ValueError): reset(self.run)

    def test_wrong_lowest_price_choice_rejected(self):
        path = self.run / 'outputs/decision.json'
        value = json.loads(path.read_text())
        value['recommended_supplier'] = 'A'
        dump(path, value)
        self.assertFalse(verify(self.run)['checks']['recommendation'])

    def test_wrong_cost_visual_value_and_eligibility_rejected(self):
        path = self.run / 'outputs/comparison.csv'
        records = rows(path)
        for key, value, check in [('total_cost_cny', '20000.00', 'A.total_cost_cny'),
                                   ('defect_pct', '0.24', 'A.defect_pct'),
                                   ('eligible', 'true', 'A.eligible')]:
            changed = copy.deepcopy(records)
            changed[0][key] = value
            write_csv(path, changed)
            self.assertFalse(verify(self.run)['checks'][check])

    def test_duplicate_and_nonfinite_rejected(self):
        path = self.run / 'outputs/comparison.csv'
        records = rows(path)
        write_csv(path, records + [records[0]])
        self.assertFalse(verify(self.run)['checks']['supplier_coverage'])
        records[0]['total_cost_cny'] = 'NaN'
        write_csv(path, records)
        self.assertFalse(verify(self.run)['automated_checks_passed'])

    def test_missing_image_blocks_reference(self):
        (self.run / 'supplier_performance.png').unlink()
        with self.assertRaisesRegex(ValueError, 'BLOCKED'):
            solve(self.run, self.observations)
        self.assertFalse(verify(self.run)['checks']['input_integrity'])

    def test_altered_image_invalidates_observation(self):
        with (self.run / 'supplier_performance.png').open('ab') as f: f.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'different image'):
            solve(self.run, self.observations)

    def test_missing_freight_is_not_imputed(self):
        path = self.run / 'quotes.csv'
        records = rows(path)
        records[1]['freight_cny'] = ''
        write_csv(path, records)
        with self.assertRaises(Exception): solve(self.run, self.observations)
        self.assertFalse(verify(self.run)['checks']['input_integrity'])

    def test_missing_deliverable_or_bad_json_rejected(self):
        (self.run / 'outputs/recommendation.md').unlink()
        self.assertFalse(verify(self.run)['automated_checks_passed'])
        (self.run / 'outputs/decision.json').write_text('[]')
        self.assertFalse(verify(self.run)['checks']['decision_readable'])

    def test_evidence_graph_anchors_and_deterministic_build(self):
        p = ROOT / 'package'
        before = {str(f.relative_to(p)): sha(f) for f in p.rglob('*') if f.is_file()}
        build()
        after = {str(f.relative_to(p)): sha(f) for f in p.rglob('*') if f.is_file()}
        self.assertEqual(before, after)
        graph = json.loads((p / 'evaluation/evidence_graph.json').read_text())
        nodes = {n['id']: n for n in graph['nodes']}
        self.assertEqual(len(nodes), len(graph['nodes']))
        for n in nodes.values():
            if n['status'] == 'supplied': self.assertTrue((p / 'workspace_init' / n['file']).is_file())
        for e in graph['edges']:
            self.assertIn(e['to'], nodes)
            self.assertTrue(set(e['from']) <= nodes.keys())
        for criterion in json.loads((p / 'evaluation/rubric.json').read_text()):
            self.assertTrue(set(criterion['anchors']) <= nodes.keys())


if __name__ == '__main__':
    unittest.main()
