import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import filter_digital as digital
from translate_catalog import source_records, digest


class DigitalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.annotations_path = ROOT / "data/annotations/ai4work_digital_task_annotation.xlsx"
        cls.annotations, _ = digital.read_annotations(cls.annotations_path)
        cls.tasks = digital.read_table(ROOT / "data/processed", "tasks.csv")

    def test_exact_labels_and_unknown(self):
        for label in ("DIGITAL", "PHYSICAL", ""):
            task = next(t for t in self.tasks if t["task_id"] in self.annotations and
                        self.annotations[t["task_id"]][1]["Is Digital"] == label)
            decision = digital.classify(task, self.annotations)
            self.assertEqual(decision[0], label or "REVIEW")
            self.assertEqual(decision[2], label)

    def test_never_inherit_changed_text_or_occupation(self):
        task = next(t for t in self.tasks if digital.classify(t, self.annotations)[0] == "DIGITAL")
        for field in ("task_text", "occupation_code"):
            with self.subTest(field=field):
                changed = {**task, field: task[field] + " [test mutation]"}
                result = digital.classify(changed, self.annotations)
                self.assertEqual(result[:2], ("REVIEW", "R4_CHANGED"))

    def test_unmatched_is_review_not_physical(self):
        task = next(t for t in self.tasks if t["task_id"] not in self.annotations)
        self.assertEqual(digital.classify(task, self.annotations)[:2], ("REVIEW", "R3_UNMATCHED"))

    def test_full_partition_reproducible_and_master_unchanged(self):
        processed = ROOT / "data/processed"
        original = {p.name: p.read_bytes() for p in processed.iterdir()}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = digital.filter_catalog(ROOT / "data/raw", processed, self.annotations_path, out)
            files = {p.name: p.read_bytes() for p in out.iterdir()}
            digital.filter_catalog(ROOT / "data/raw", processed, self.annotations_path, out)
            self.assertEqual(files, {p.name: p.read_bytes() for p in out.iterdir()})
            self.assertEqual(sum(report["decisions"].values()), len(self.tasks))
            self.assertTrue(report["all_checks_passed"])
            decisions = digital.read_table(out, "task_decisions.csv")
            admitted = {r["task_id"] for r in decisions if r["decision"] == "DIGITAL"}
            self.assertEqual(admitted, {r["task_id"] for r in digital.read_table(out, "tasks.csv")})
            self.assertTrue(all(r["task_id"] in admitted for r in digital.read_table(out, "task_dwa.csv")))
        self.assertEqual(original, {p.name: p.read_bytes() for p in processed.iterdir()})

    def test_source_hash_and_overwrite_guards(self):
        with self.assertRaisesRegex(digital.DataError, "覆盖"):
            digital.filter_catalog(ROOT / "data/raw", ROOT / "data/processed", self.annotations_path, ROOT / "data/processed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.xlsx"
            path.write_bytes(self.annotations_path.read_bytes() + b"changed")
            with self.assertRaisesRegex(digital.DataError, "SHA-256"):
                digital.filter_catalog(ROOT / "data/raw", ROOT / "data/processed", path, Path(tmp) / "out")

    def test_chinese_coverage_and_source_linkage(self):
        import hashlib
        import re
        path = ROOT / "archive/data/translations/translations_zh.json"
        if not path.exists():
            self.skipTest("Run translate_catalog.py --fetch before translation coverage test")
        translations = json.loads(path.read_text())
        for table, rows in source_records(ROOT / "data/processed").items():
            self.assertEqual(set(rows), set(translations[table]))
            self.assertTrue(all(re.search(r"[\u3400-\u9fff]", text) for text in translations[table].values()))
            actual = hashlib.sha256((ROOT / "data/processed" / (table + ".csv")).read_bytes()).hexdigest()
            self.assertEqual(actual, translations["metadata"]["source_sha256"][table + ".csv"])
        for line in (ROOT / "archive/data/translations/translation_cache.jsonl").read_text().splitlines():
            item = json.loads(line)
            self.assertEqual(digest(item["source_text"]), item["source_sha256"])
        for item in json.loads((ROOT / "archive/data/translations/translation_overrides.json").read_text()):
            self.assertEqual(source_records(ROOT / "data/processed")[item["table"]][item["id"]], item["source_text"])
            self.assertEqual(translations[item["table"]][item["id"]], item["zh"])


if __name__ == "__main__":
    unittest.main()
