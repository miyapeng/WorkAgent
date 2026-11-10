#!/usr/bin/env python3
"""O*NET 31.0 -> four lossless seed tables. Python standard library only."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from collections import Counter

VERSION = "31.0"
SOURCE = "https://www.onetcenter.org/database.html"
ZIP_URL = "https://www.onetcenter.org/dl_files/database/db_31_0_csv.zip"
BASE = "https://www.onetcenter.org/dl_files/database/db_31_0_csv/"
RAW_HEADERS = {
    "occupation_data.csv": ["O*NET-SOC Code", "Title", "Description"],
    "task_statements.csv": ["O*NET-SOC Code", "Title", "Task ID", "Task", "Task Type",
                            "Incumbents Responding", "Date", "Domain Source"],
    "tasks_to_dwas.csv": ["O*NET-SOC Code", "Title", "Task ID", "Task", "DWA Element ID",
                          "DWA Element Name", "Date", "Domain Source"],
}
SCHEMA = {
    "occupations.csv": ["occupation_code", "occupation_title"],
    "tasks.csv": ["task_id", "occupation_code", "task_text", "task_type"],
    "dwas.csv": ["dwa_id", "dwa_name"],
    "task_dwa.csv": ["task_id", "dwa_id"],
}
ROOT = Path(__file__).resolve().parents[1]


class DataError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def fetch(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": "WorkSeeds/1.0 (O*NET research catalog)"})
    with urllib.request.urlopen(request, timeout=45) as response, path.open("wb") as output:
        shutil.copyfileobj(response, output)
        expected = response.headers.get("Content-Length")
        if expected is not None and output.tell() != int(expected):
            raise OSError(f"{url}: 下载字节数与 Content-Length 不一致")


def download(raw_dir, download_format="zip"):
    """Prefer the official ZIP; fall back only to the three official CSV URLs."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=raw_dir) as tmp:
        stage = Path(tmp)
        archive = stage / "db_31_0_csv.zip"
        provenance = {"version": VERSION, "release": "August 2026", "source": SOURCE}
        if download_format == "zip":
            try:
                cached = raw_dir / archive.name
                if cached.exists() and zipfile.is_zipfile(cached):
                    shutil.copyfile(cached, archive)
                else:
                    fetch(ZIP_URL, archive)
                with zipfile.ZipFile(archive) as zipped:
                    for name in RAW_HEADERS:
                        matches = [item for item in zipped.namelist() if Path(item).name == name]
                        if len(matches) != 1:
                            raise DataError(f"ZIP 中 {name} 匹配到 {len(matches)} 个文件")
                        # 不解压任意路径，只读取白名单文件。
                        (stage / name).write_bytes(zipped.read(matches[0]))
                provenance.update(mode="official_zip", url=ZIP_URL, zip_sha256=sha256(archive.read_bytes()))
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                print(f"官方 ZIP 获取失败：{exc}；尝试官方独立 CSV。", file=sys.stderr)
                download_format = "csv"
        if download_format == "csv":
            for name in RAW_HEADERS:
                fetch(BASE + name, stage / name)
            provenance.update(mode="official_csv", urls=[BASE + name for name in RAW_HEADERS])
        # 全部文件获取成功且格式正确之后再发布到 raw/。
        for name, headers in RAW_HEADERS.items():
            parse_csv((stage / name).read_bytes(), name, headers)
        provenance["sha256"] = {name: sha256((stage / name).read_bytes()) for name in RAW_HEADERS}
        for name in RAW_HEADERS:
            os.replace(stage / name, raw_dir / name)
        if provenance["mode"] == "official_zip":
            os.replace(archive, raw_dir / archive.name)
        (raw_dir / "source_manifest.json").write_bytes(json_bytes(provenance))


def parse_csv(data, name, expected_headers):
    try:
        stream = io.StringIO(data.decode("utf-8-sig"), newline="")
        reader = csv.reader(stream, strict=True)
        headers = next(reader)
        if len(headers) != len(set(headers)) or set(headers) != set(expected_headers):
            raise DataError(f"{name}: 列名与 O*NET 31.0 字典不符：{headers}")
        records = []
        for row in reader:
            if len(row) != len(headers):
                raise DataError(f"{name}:{reader.line_num}: 列数错误，不能跳过该行")
            records.append(dict(zip(headers, row)))
        return records
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise DataError(f"{name}: 无效的 UTF-8 CSV：{exc}") from exc


def insert(index, key, value, label):
    keys = key if isinstance(key, tuple) else (key,)
    if any(not part.strip() for part in keys):
        raise DataError(f"{label}: 主键缺失")
    if key in index and index[key] != value:
        raise DataError(f"{label}: 主键 {key!r} 对应冲突内容")
    index[key] = value


def normalize(raw):
    occupations, tasks, dwas, links = {}, {}, {}, {}
    # 原始主键冲突也检查被投影掉的元数据，不能靠删列掩盖冲突。
    raw_indexes = {name: {} for name in RAW_HEADERS}
    for row in raw["occupation_data.csv"]:
        code = row["O*NET-SOC Code"]
        insert(raw_indexes["occupation_data.csv"], code, row, "occupation_data.csv")
        insert(occupations, code, (code, row["Title"]), "occupations")
    for row in raw["task_statements.csv"]:
        code, task_id = row["O*NET-SOC Code"], row["Task ID"]
        insert(raw_indexes["task_statements.csv"], task_id, row, "task_statements.csv")
        if code not in occupations:
            raise DataError(f"Task {task_id}: 职业外键不存在：{code}")
        if row["Title"] != occupations[code][1]:
            raise DataError(f"Task {task_id}: 冗余职业名称与职业表冲突")
        if row["Task Type"] not in ("Core", "Supplemental", ""):
            raise DataError(f"Task {task_id}: 未知 Task Type：{row['Task Type']!r}")
        insert(tasks, task_id, (task_id, code, row["Task"], row["Task Type"]), "tasks")
    for row in raw["tasks_to_dwas.csv"]:
        task_id, dwa_id = row["Task ID"], row["DWA Element ID"]
        insert(raw_indexes["tasks_to_dwas.csv"], (task_id, dwa_id), row, "tasks_to_dwas.csv")
        if task_id not in tasks:
            raise DataError(f"Task-DWA: Task 外键不存在：{task_id}")
        if (row["O*NET-SOC Code"], row["Task"]) != tasks[task_id][1:3]:
            raise DataError(f"Task-DWA {task_id}: 冗余职业代码或 Task 文本冲突")
        if row["Title"] != occupations[row["O*NET-SOC Code"]][1]:
            raise DataError(f"Task-DWA {task_id}: 冗余职业名称冲突")
        insert(dwas, dwa_id, (dwa_id, row["DWA Element Name"]), "dwas")
        insert(links, (task_id, dwa_id), (task_id, dwa_id), "task_dwa")
    tables = {"occupations.csv": sorted(occupations.values()), "tasks.csv": sorted(tasks.values()),
              "dwas.csv": sorted(dwas.values()), "task_dwa.csv": sorted(links.values())}
    return tables, raw_indexes


def encode_csv(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def validate(tables, raw):
    occupations, tasks, dwas, links = [tables[name] for name in SCHEMA]
    occ_ids = {r[0] for r in occupations}
    task_ids = {r[0] for r in tasks}
    dwa_ids = {r[0] for r in dwas}
    mapped = {r[0] for r in links}
    checks = {
        "occupation_primary_key": len(occ_ids) == len(occupations),
        "task_primary_key": len(task_ids) == len(tasks),
        "dwa_primary_key": len(dwa_ids) == len(dwas),
        "task_dwa_primary_key": len(set(links)) == len(links),
        "task_occupation_foreign_key": all(r[1] in occ_ids for r in tasks),
        "task_dwa_foreign_keys": all(t in task_ids and d in dwa_ids for t, d in links),
        "all_occupations_preserved": set(occupations) == {(r["O*NET-SOC Code"], r["Title"]) for r in raw["occupation_data.csv"]},
        "all_tasks_preserved": set(tasks) == {(r["Task ID"], r["O*NET-SOC Code"], r["Task"], r["Task Type"]) for r in raw["task_statements.csv"]},
        "all_observed_dwas_preserved": set(dwas) == {(r["DWA Element ID"], r["DWA Element Name"]) for r in raw["tasks_to_dwas.csv"]},
        "all_links_preserved": set(links) == {(r["Task ID"], r["DWA Element ID"]) for r in raw["tasks_to_dwas.csv"]},
    }
    if not all(checks.values()):
        raise DataError(f"完整性校验失败：{checks}")
    types = Counter(r[3] for r in tasks)
    return checks, {"occupations": len(occupations), "tasks": len(tasks), "dwas": len(dwas),
                    "task_dwa": len(links), "task_types": {"Core": types["Core"], "Supplemental": types["Supplemental"], "Missing": types[""]},
                    "tasks_without_dwa": len(task_ids - mapped),
                    "occupations_without_tasks": len(occ_ids - {r[1] for r in tasks})}


def build(input_dir, output_dir, verify_only=False):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if input_dir.resolve() == output_dir.resolve():
        raise DataError("输入和输出目录不能相同")
    missing = [name for name in RAW_HEADERS if not (input_dir / name).is_file()]
    if missing:
        raise DataError("缺失原始文件：" + ", ".join(missing) + "。使用 --download 或 --input-dir 指定官方原始目录。")
    blobs = {name: (input_dir / name).read_bytes() for name in RAW_HEADERS}
    hashes = {name: sha256(data) for name, data in blobs.items()}
    manifest_path = input_dir / "source_manifest.json"
    if manifest_path.exists():
        provenance = json.loads(manifest_path.read_text(encoding="utf-8"))
        if provenance.get("version") != VERSION or provenance.get("sha256") != hashes:
            raise DataError("原始文件与 source_manifest.json 的版本或 SHA-256 不一致")
    else:
        provenance = {"version": VERSION, "mode": "local_user_supplied",
                      "note": "版本由调用者声明；CSV 本身不包含发行版本，未独立认证下载来源。"}
    raw = {name: parse_csv(data, name, RAW_HEADERS[name]) for name, data in blobs.items()}
    tables, indexes = normalize(raw)
    checks, counts = validate(tables, raw)
    encoded = {name: encode_csv(SCHEMA[name], rows) for name, rows in tables.items()}
    # 将实际写出的 CSV 字节重新读取，验证序列化不改写任何值。
    decoded = {name: [tuple(row[h] for h in SCHEMA[name]) for row in parse_csv(data, name, SCHEMA[name])]
               for name, data in encoded.items()}
    checks["csv_roundtrip_preserves_values"] = decoded == tables
    if not checks["csv_roundtrip_preserves_values"]:
        raise DataError("CSV 序列化发生信息损失")
    source_stats = {name: {"raw_rows": len(rows), "unique_rows": len(indexes[name]),
                           "exact_duplicate_rows_removed": len(rows) - len(indexes[name]),
                           "sha256": hashes[name]} for name, rows in raw.items()}
    report = {"version": VERSION, "release": "August 2026", "source": SOURCE,
              "provenance": provenance, "raw_files": source_stats, "counts": counts,
              "checks": checks, "all_checks_passed": all(checks.values()),
              "outputs_sha256": {name: sha256(data) for name, data in encoded.items()},
              "dwa_scope": "Distinct DWAs observed in tasks_to_dwas.csv; not a claim of the full DWA taxonomy."}
    if verify_only:
        for name, expected in encoded.items():
            path = output_dir / name
            if not path.is_file() or path.read_bytes() != expected:
                raise DataError(f"{name}: 已保存输出与原始数据重新构建的内容不一致")
        report_path = output_dir / "validation_report.json"
        if not report_path.is_file() or report_path.read_bytes() != json_bytes(report):
            raise DataError("validation_report.json 与当前输入及输出不一致")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        # 先完成所有检查，再在同一文件系统内替换每个输出。
        with tempfile.TemporaryDirectory(dir=output_dir) as tmp:
            stage = Path(tmp)
            for name, data in {**encoded, "validation_report.json": json_bytes(report)}.items():
                (stage / name).write_bytes(data)
            for path in stage.iterdir():
                os.replace(path, output_dir / path.name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--download", action="store_true", help="下载固定版本官方 ZIP；失败时尝试官方 CSV")
    parser.add_argument("--download-format", choices=("zip", "csv"), default="zip", help="默认优先 ZIP；网络较慢时可直接选择官方 CSV")
    parser.add_argument("--verify-only", action="store_true", help="从原始输入重新计算，并逐字节核对已保存输出；不改写")
    args = parser.parse_args()
    try:
        if args.download:
            download(args.input_dir, args.download_format)
        report = build(args.input_dir, args.output_dir, args.verify_only)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}\n未生成虚构替代数据。可通过 --input-dir 提供 O*NET 31.0 官方 CSV。", file=sys.stderr)
        return 1
    print(json.dumps({"counts": report["counts"], "all_checks_passed": report["all_checks_passed"],
                      "output_dir": str(args.output_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
