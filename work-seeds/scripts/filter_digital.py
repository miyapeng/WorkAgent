#!/usr/bin/env python3
"""Apply pinned AI4Work task annotations without modifying the O*NET master catalog."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from build_onet import ROOT, SCHEMA, DataError, build, encode_csv, json_bytes

COMMIT = "095db006debf83f2bbda2631964bd1b4c81190ad"
SOURCE_PATH = "real_work/employment/digital_task_annotation.xlsx"
SOURCE_URL = f"https://raw.githubusercontent.com/zorazrw/ai4work-resources/{COMMIT}/{SOURCE_PATH}"
SOURCE_PAGE = f"https://github.com/zorazrw/ai4work-resources/blob/{COMMIT}/{SOURCE_PATH}"
RULE_VERSION = "ai4work-exact-match-v1"
EXPECTED_SHA256 = "01ee0ea4c9f5530240f25b5af9fa5df6218e429733e0f49914d6f501ac28167f"
RULES = {
    "R1_DIGITAL": "任务 ID、职业代码和英文任务文本完全一致，且 AI4Work 标注为 DIGITAL：纳入。",
    "R2_PHYSICAL": "任务 ID、职业代码和英文任务文本完全一致，且 AI4Work 标注为 PHYSICAL：排除。",
    "R3_UNMATCHED": "AI4Work 中没有该 Task ID：待核对，不纳入当前 digital 子集。",
    "R4_CHANGED": "同一 Task ID 的职业代码或英文任务文本发生变化：待核对，不继承旧标签。",
    "R5_UNLABELED": "匹配到的原始标签为空或未知：待核对，不自行推测。",
}
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_annotations(path):
    """Read XLSX with zipfile + XML, including sparse/inline/shared-string cells."""
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("s:sheets/s:sheet", NS)
        if len(sheets) != 1:
            raise DataError("AI4Work workbook 必须只有一个标注工作表")
        rel_id = sheets[0].attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == rel_id)
        member = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(t.text or "" for t in item.findall(".//s:t", NS))
                      for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        rows = ET.fromstring(archive.read(member)).findall("s:sheetData/s:row", NS)
        headers, result = {}, {}
        raw_rows = duplicates = blank_rows = 0
        for row in rows:
            cells = {}
            for cell in row.findall("s:c", NS):
                column = re.match(r"[A-Z]+", cell.attrib["r"])[0]
                kind = cell.attrib.get("t")
                value = cell.find("s:v", NS)
                text = value.text or "" if value is not None else ""
                if kind == "s": text = shared[int(text)]
                elif kind == "inlineStr": text = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                cells[column] = text
            if not any(cells.values()):
                blank_rows += 1
                continue
            if not headers:
                headers = cells
                required = {"O*NET-SOC Code", "Task ID", "Task", "Is Digital", "Reason"}
                if not required.issubset(set(headers.values())) or len(headers.values()) != len(set(headers.values())):
                    raise DataError("AI4Work workbook 列名错误")
                continue
            record = {name: cells.get(column, "") for column, name in headers.items()}
            raw_rows += 1
            key = record["Task ID"]
            if not key or not record["O*NET-SOC Code"] or not record["Task"]:
                raise DataError(f"AI4Work 第 {row.attrib['r']} 行缺少任务标识或文本")
            if key in result:
                if result[key][1] != record:
                    raise DataError(f"AI4Work Task {key} 存在冲突标注")
                duplicates += 1
            else:
                result[key] = (row.attrib["r"], record)
        return result, {"raw_rows": raw_rows, "exact_duplicates": duplicates, "blank_rows": blank_rows}


def classify(task, annotations):
    if task["task_id"] not in annotations:
        return "REVIEW", "R3_UNMATCHED", "", "", ""
    row_number, row = annotations[task["task_id"]]
    source_label = row["Is Digital"]
    if row["O*NET-SOC Code"] != task["occupation_code"] or row["Task"] != task["task_text"]:
        return "REVIEW", "R4_CHANGED", source_label, row_number, row["Reason"]
    if source_label in ("DIGITAL", "PHYSICAL"):
        return source_label, "R1_DIGITAL" if source_label == "DIGITAL" else "R2_PHYSICAL", source_label, row_number, row["Reason"]
    return "REVIEW", "R5_UNLABELED", source_label, row_number, row["Reason"]


def read_table(root, name):
    with (root / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def filter_catalog(raw_dir, processed, annotation_path, output):
    if output.resolve() == processed.resolve():
        raise DataError("筛选输出不能覆盖官方全量目录")
    master_report = build(raw_dir, processed, verify_only=True)
    if hashlib.sha256(annotation_path.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise DataError("AI4Work 标注文件与固定提交的 SHA-256 不符；不能冒用上游出处")
    annotations, source_stats = read_annotations(annotation_path)
    master = {name: read_table(processed, name) for name in SCHEMA}
    decisions = []
    for task in master["tasks.csv"]:
        decisions.append((task["task_id"], *classify(task, annotations)))
    keep = {r[0] for r in decisions if r[1] == "DIGITAL"}
    tasks = [t for t in master["tasks.csv"] if t["task_id"] in keep]
    codes = {t["occupation_code"] for t in tasks}
    links = [r for r in master["task_dwa.csv"] if r["task_id"] in keep]
    dwa_ids = {r["dwa_id"] for r in links}
    tables = {"occupations.csv": [r for r in master["occupations.csv"] if r["occupation_code"] in codes],
              "tasks.csv": tasks, "dwas.csv": [r for r in master["dwas.csv"] if r["dwa_id"] in dwa_ids], "task_dwa.csv": links}
    counts = {name[:-4]: len(rows) for name, rows in tables.items()}
    statuses = dict(sorted(Counter(r[1] for r in decisions).items()))
    checks = {
        "all_master_tasks_have_one_decision": len(decisions) == len({r[0] for r in decisions}) == master_report["counts"]["tasks"],
        "only_exact_digital_matches_included": keep == {r[0] for r in decisions if r[2] == "R1_DIGITAL"},
        "all_task_links_retained": {(r["task_id"], r["dwa_id"]) for r in links} == {(r["task_id"], r["dwa_id"]) for r in master["task_dwa.csv"] if r["task_id"] in keep},
        "foreign_keys_valid": all(r["task_id"] in keep and r["dwa_id"] in dwa_ids for r in links) and all(t["occupation_code"] in codes for t in tasks),
        "original_ids_and_english_preserved": all({tuple(r[h] for h in SCHEMA[name]) for r in rows}.issubset({tuple(r[h] for h in SCHEMA[name]) for r in master[name]}) for name, rows in tables.items()),
        "digital_physical_review_partition": sum(statuses.values()) == master_report["counts"]["tasks"],
    }
    if not all(checks.values()): raise DataError(f"筛选验证失败：{checks}")
    contents = {name: encode_csv(SCHEMA[name], [tuple(r[h] for h in SCHEMA[name]) for r in rows]) for name, rows in tables.items()}
    contents["task_decisions.csv"] = encode_csv(["task_id", "decision", "rule_id", "source_label", "source_row", "source_reason"], decisions)
    report = {"rule_version": RULE_VERSION, "rules": RULES, "source": {"project": "AI4Work", "commit": COMMIT, "url": SOURCE_URL, "page": SOURCE_PAGE,
              "sha256": hashlib.sha256(annotation_path.read_bytes()).hexdigest(), **source_stats},
              "master_sha256": master_report["outputs_sha256"], "counts": counts, "decisions": statuses,
              "rules_applied": dict(sorted(Counter(r[2] for r in decisions).items())),
              "source_tasks_not_in_current_catalog": len(set(annotations) - {t["task_id"] for t in master["tasks.csv"]}),
              "checks": checks, "all_checks_passed": all(checks.values()),
              "outputs_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
              "limitations": ["AI4Work 外部研究标注，不是 O*NET 官方标签，也不是可执行性保证。", "PHYSICAL 包括上游认为必须现场进行的人际活动。", "待核对不等于非数字任务。", "职业仅因至少一条 DIGITAL 任务进入子集，不表示整个职业都可数字化。", "本实现不声称复现 GraphForge 未公开的完整预处理和抽样规则。"]}
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        stage = Path(tmp)
        for name, content in {**contents, "filter_report.json": json_bytes(report)}.items():
            (stage / name).write_bytes(content)
        for path in stage.iterdir(): path.replace(output / path.name)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--annotations", type=Path, default=ROOT / "data/annotations/ai4work_digital_task_annotation.xlsx")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "archive/data/digital")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        args.annotations.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            args.annotations.write_bytes(response.read())
    report = filter_catalog(args.raw_dir, args.processed_dir, args.annotations, args.output_dir)
    print(json.dumps({key: report[key] for key in ("counts", "decisions", "rules_applied", "all_checks_passed")}, ensure_ascii=False, indent=2))
