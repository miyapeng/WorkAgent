"""Test fixtures are subsets of downloaded official rows, never substitute data."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_onet", ROOT / "scripts/build_onet.py")
onet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onet)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = {}
        for name, headers in onet.RAW_HEADERS.items():
            path = ROOT / "data/raw" / name
            if not path.exists():
                raise RuntimeError("测试需要官方原始 CSV；请先执行 build_onet.py --download")
            cls.official[name] = onet.parse_csv(path.read_bytes(), name, headers)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raw = Path(self.temp.name) / "raw"
        self.out = Path(self.temp.name) / "processed"
        self.raw.mkdir()
        link = self.official["tasks_to_dwas.csv"][0]
        task = next(r for r in self.official["task_statements.csv"] if r["Task ID"] == link["Task ID"])
        other = next(r for r in self.official["task_statements.csv"] if r["Task ID"] != task["Task ID"])
        codes = {task["O*NET-SOC Code"], other["O*NET-SOC Code"]}
        self.rows = {
            "occupation_data.csv": [r.copy() for r in self.official["occupation_data.csv"] if r["O*NET-SOC Code"] in codes],
            "task_statements.csv": [task.copy(), other.copy()],
            "tasks_to_dwas.csv": [link.copy()],
        }

    def write(self):
        for name, rows in self.rows.items():
            with (self.raw / name).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=onet.RAW_HEADERS[name])
                writer.writeheader()
                writer.writerows(rows)

    def build(self):
        self.write()
        return onet.build(self.raw, self.out)

    def test_full_official_data_reproducible_and_conserved(self):
        first = onet.build(ROOT / "data/raw", self.out)
        snapshot = {p.name: p.read_bytes() for p in self.out.iterdir()}
        second = onet.build(ROOT / "data/raw", self.out)
        self.assertEqual(first, second)
        self.assertEqual(snapshot, {p.name: p.read_bytes() for p in self.out.iterdir()})
        onet.build(ROOT / "data/raw", self.out, verify_only=True)
        self.assertTrue(first["all_checks_passed"])
        self.assertEqual(first["counts"]["tasks"], len({r["Task ID"] for r in self.official["task_statements.csv"]}))

    def test_exact_duplicates_and_unmapped_tasks(self):
        for rows in self.rows.values():
            rows.append(rows[0].copy())
        report = self.build()
        self.assertEqual(report["counts"]["tasks"], 2)
        self.assertEqual(report["counts"]["tasks_without_dwa"], 1)
        for stats in report["raw_files"].values():
            self.assertEqual(stats["exact_duplicate_rows_removed"], 1)

    def test_missing_type_stays_empty(self):
        self.rows["task_statements.csv"][0]["Task Type"] = ""
        report = self.build()
        self.assertGreaterEqual(report["counts"]["task_types"]["Missing"], 1)
        with (self.out / "tasks.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        target = self.rows["task_statements.csv"][0]["Task ID"]
        self.assertEqual(next(r["task_type"] for r in rows if r["task_id"] == target), "")

    def test_conflicting_primary_keys(self):
        for name, field in [("occupation_data.csv", "Title"), ("task_statements.csv", "Task"),
                            ("tasks_to_dwas.csv", "DWA Element Name")]:
            with self.subTest(name=name):
                changed = self.rows[name][0].copy()
                changed[field] += " [deliberate negative-test mutation]"
                self.rows[name].append(changed)
                with self.assertRaisesRegex(onet.DataError, "冲突"):
                    self.build()
                self.rows[name].pop()

    def test_dwa_conflict_across_distinct_tasks(self):
        second = self.rows["tasks_to_dwas.csv"][0].copy()
        task = self.rows["task_statements.csv"][1]
        for field in ("Task ID", "Task", "O*NET-SOC Code", "Title"):
            second[field] = task[field]
        second["DWA Element Name"] += " [negative-test mutation]"
        self.rows["tasks_to_dwas.csv"].append(second)
        with self.assertRaisesRegex(onet.DataError, "dwas.*冲突"):
            self.build()

    def test_orphans_fail(self):
        saved = self.rows["occupation_data.csv"]
        self.rows["occupation_data.csv"] = []
        with self.assertRaisesRegex(onet.DataError, "职业外键不存在"):
            self.build()
        self.rows["occupation_data.csv"] = saved
        self.rows["task_statements.csv"] = self.rows["task_statements.csv"][1:]
        with self.assertRaisesRegex(onet.DataError, "Task 外键不存在"):
            self.build()

    def test_all_missing_files_reported(self):
        with self.assertRaises(onet.DataError) as context:
            onet.build(self.raw, self.out)
        for name in onet.RAW_HEADERS:
            self.assertIn(name, str(context.exception))

    def test_empty_id_and_unknown_type_fail(self):
        original = self.rows["task_statements.csv"][0].copy()
        self.rows["task_statements.csv"][0]["Task ID"] = ""
        with self.assertRaisesRegex(onet.DataError, "主键缺失"):
            self.build()
        self.rows["task_statements.csv"][0] = original
        original["Task Type"] = "Inferred"
        with self.assertRaisesRegex(onet.DataError, "未知 Task Type"):
            self.build()

    def test_tampering_detected_and_failure_does_not_overwrite(self):
        self.build()
        original = (self.out / "tasks.csv").read_bytes()
        conflict = self.rows["task_statements.csv"][0].copy()
        conflict["Date"] = "conflicting metadata"
        self.rows["task_statements.csv"].append(conflict)
        with self.assertRaises(onet.DataError):
            self.build()
        self.assertEqual(original, (self.out / "tasks.csv").read_bytes())
        self.rows["task_statements.csv"].pop()
        self.write()
        (self.out / "tasks.csv").write_bytes(original + b"\n")
        with self.assertRaisesRegex(onet.DataError, "不一致"):
            onet.build(self.raw, self.out, verify_only=True)

    def test_bom_and_exact_text_preservation(self):
        self.write()
        path = self.raw / "task_statements.csv"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        onet.build(self.raw, self.out)
        with (self.out / "tasks.csv").open(newline="") as stream:
            actual = {r["task_id"]: r["task_text"] for r in csv.DictReader(stream)}
        self.assertEqual(actual, {r["Task ID"]: r["Task"] for r in self.rows["task_statements.csv"]})

    def test_official_csv_download_and_provenance(self):
        calls = []
        def fetch(url, path):
            calls.append(url)
            path.write_bytes((ROOT / "data/raw" / url.rsplit("/", 1)[1]).read_bytes())
        with patch.object(onet, "fetch", side_effect=fetch):
            onet.download(self.raw, "csv")
        self.assertEqual(calls, [onet.BASE + name for name in onet.RAW_HEADERS])
        self.assertEqual(json.loads((self.raw / "source_manifest.json").read_text())["mode"], "official_csv")
        self.assertTrue(onet.build(self.raw, self.out)["all_checks_passed"])
        with (self.raw / "task_statements.csv").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(onet.DataError, "SHA-256"):
            onet.build(self.raw, self.out)

    def test_official_zip_extracts_only_requested_files(self):
        archive = self.raw / "db_31_0_csv.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for name in onet.RAW_HEADERS:
                zipped.write(ROOT / "data/raw" / name, "db_31_0_csv/" + name)
            zipped.writestr("../../unexpected.txt", "not a catalog record")
        with patch.object(onet, "fetch", side_effect=AssertionError("cached ZIP should be used")):
            onet.download(self.raw)
        self.assertEqual(set(p.name for p in self.raw.iterdir()), set(onet.RAW_HEADERS) | {"db_31_0_csv.zip", "source_manifest.json"})
        self.assertTrue(onet.build(self.raw, self.out)["all_checks_passed"])

    def test_wrong_header_and_malformed_row_fail(self):
        self.write()
        path = self.raw / "tasks_to_dwas.csv"
        path.write_text(path.read_text().replace("DWA Element ID", "DWA ID"))
        with self.assertRaisesRegex(onet.DataError, "列名"):
            onet.build(self.raw, self.out)
        self.write()
        with path.open("a") as stream:
            stream.write("too,few,columns\n")
        with self.assertRaisesRegex(onet.DataError, "列数"):
            onet.build(self.raw, self.out)


if __name__ == "__main__":
    unittest.main()
