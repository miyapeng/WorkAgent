import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sample_seeds import ROOT, DataError, load_catalog, eligibility, rule_classify, task_sample, coverage


class SamplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(ROOT / 'data/processed')
        cls.decisions, cls.audit = eligibility(cls.catalog, annotations=ROOT / 'data/annotations/ai4work_digital_task_annotation.xlsx')
        cls.candidates = [t for t, d in cls.decisions.items() if d == 'digital_candidate']

    def test_ambiguous_and_mixed_clauses_are_uncertain(self):
        for text in ('Inspect equipment.', 'Advise clients.', 'Operate systems.',
                     'Drive trucks and prepare reports.', 'Prepare reports and visit plants.', 'Plan to clean equipment.'):
            self.assertEqual(rule_classify(text)[0], 'uncertain', text)
        self.assertEqual(rule_classify('Drive trucks.')[0], 'physical_required')
        self.assertEqual(rule_classify('Prepare financial reports.')[0], 'digital_candidate')

    def test_full_partition_and_original_counts(self):
        self.assertEqual(len(self.decisions), len(self.catalog['tasks']))
        self.assertEqual(self.audit['counts']['digital_candidate'], 5652)
        self.assertEqual(sum(self.audit['counts'].values()), 18838)

    def test_reproducible_order_independent_and_major_group_coverage(self):
        a = task_sample(self.catalog, self.candidates, 30, 42)
        b = task_sample(self.catalog, list(reversed(self.candidates)), 30, 42)
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(set(a)))
        self.assertEqual(coverage(self.catalog, a)['major_groups'], 22)
        self.assertEqual(coverage(self.catalog, a)['occupations'], 30)
        self.assertTrue(set(a) <= set(self.candidates))

    def test_multilabel_coverage_not_exploded_sampling_unit(self):
        ids = self.candidates[:40]
        selected = task_sample(self.catalog, ids, 100, 1)
        expected = set().union(*(self.catalog['task_dwas'][t] for t in ids))
        self.assertEqual(set(selected), set(ids))
        self.assertEqual(coverage(self.catalog, selected)['dwas'], len(expected))
        self.assertEqual(task_sample(self.catalog, ids, 0, 1), [])

    def test_bad_parameters_and_missing_annotation_fail(self):
        with self.assertRaises(DataError): task_sample(self.catalog, [], -1, 0)
        with self.assertRaises(DataError): task_sample(self.catalog, [], 1, 0, 2)
        with self.assertRaises(DataError): eligibility(self.catalog, annotations=Path('/missing/file.xlsx'))

    def test_alternative_labels_keep_unlabeled_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'labels.csv'
            p.write_text('task_id,eligibility\n1144,digital_candidate\n')
            decisions, audit = eligibility(self.catalog, 'labels', labels_file=p)
            self.assertEqual(audit['counts']['digital_candidate'], 1)
            self.assertEqual(audit['counts']['uncertain'], 18837)
            p.write_text('task_id,eligibility\n1144,digital_candidate\n1144,uncertain\n')
            with self.assertRaises(DataError): eligibility(self.catalog, 'labels', labels_file=p)


if __name__ == '__main__': unittest.main()
