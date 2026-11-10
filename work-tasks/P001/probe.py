"""Persist actual unittest results, not a synthetic agent rollout."""
import unittest
from build import ROOT, dump
from test_sample import SampleTests


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test.id())


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SampleTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    dump(ROOT / 'review/probe_report.json', {
        'kind': 'engineering_reference_and_fault_injection',
        'tests_run': result.testsRun, 'passed': result.passed,
        'failures': [(t.id(), detail) for t, detail in result.failures],
        'errors': [(t.id(), detail) for t, detail in result.errors],
        'all_passed': result.wasSuccessful(),
        'agent_probe_executed': False, 'automatic_repair_executed': False,
        'human_professional_review': 'pending', 'training_admitted': False,
        'limitation': 'Tests check this single authored case and verifier; they are not model capability results.',
    })
    raise SystemExit(0 if result.wasSuccessful() else 1)
