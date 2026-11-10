#!/usr/bin/env python3
"""Render a read-only static view of the verified four-table catalog."""
import argparse
import csv
import json
from pathlib import Path
import shutil

from build_onet import ROOT, SCHEMA, build
from filter_digital import filter_catalog
from translate_catalog import source_records
import hashlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "site/dist")
    args = parser.parse_args()
    report = build(args.input_dir, args.processed_dir, verify_only=True)
    payload = {"report": report}
    digital_dir = ROOT / "data/digital"
    filter_report = filter_catalog(args.input_dir, args.processed_dir,
                                   ROOT / "data/annotations/ai4work_digital_task_annotation.xlsx", digital_dir)
    payload["digital_report"] = filter_report
    with (digital_dir / "task_decisions.csv").open(encoding="utf-8", newline="") as stream:
        payload["decisions"] = list(csv.DictReader(stream))
    translations = json.loads((ROOT / "data/translations/translations_zh.json").read_text(encoding="utf-8"))
    for table, records in source_records(args.processed_dir).items():
        assert set(translations[table]) == set(records), f"{table}: 翻译覆盖不完整"
        assert translations["metadata"]["source_sha256"][table + ".csv"] == hashlib.sha256((args.processed_dir / (table + ".csv")).read_bytes()).hexdigest(), "译文对应旧版数据"
        assert all(translations[table][key] for key, text in records.items() if text), "译文为空"
    payload["translations"] = translations
    for name in SCHEMA:
        with (args.processed_dir / name).open(encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            next(reader)
            payload[name.removesuffix(".csv")] = list(reader)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    (args.output_dir / "catalog.js").write_text("window.CATALOG=" + serialized + ";\n", encoding="utf-8")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(ROOT / "site" / name, args.output_dir / name)
    for name in [*SCHEMA, "validation_report.json"]:
        shutil.copyfile(args.processed_dir / name, args.output_dir / name)
    (args.output_dir / "digital").mkdir(exist_ok=True)
    for name in [*SCHEMA, "filter_report.json", "task_decisions.csv"]:
        shutil.copyfile(digital_dir / name, args.output_dir / "digital" / name)
    print(f"静态目录：{args.output_dir}；{report['counts']['occupations']} occupations；可直接打开 index.html。")


if __name__ == "__main__":
    main()
