#!/usr/bin/env python3
"""Cache Chinese reading translations separately from authoritative English CSVs."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "Google Translate public web endpoint (machine translation, not O*NET official)"
ENDPOINT = "https://translate.googleapis.com/translate_a/single"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def source_records(root):
    result = {}
    for table, key, field in [("occupations", "occupation_code", "occupation_title"),
                               ("tasks", "task_id", "task_text"), ("dwas", "dwa_id", "dwa_name")]:
        with (root / (table + ".csv")).open(encoding="utf-8", newline="") as stream:
            result[table] = {row[key]: row[field] for row in csv.DictReader(stream)}
    return result


def translate_batch(texts):
    query = "\n".join(f"[{i:06d}]\n{text}" for i, text in enumerate(texts))
    params = urllib.parse.urlencode(dict(client="gtx", sl="en", tl="zh-CN", dt="t", q=query))
    request = urllib.request.Request(ENDPOINT + "?" + params, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.load(response)
            translated = "".join(piece[0] for piece in value[0] if piece[0])
            parts = re.split(r"\[(\d{6})\]", translated)
            if len(parts) != 1 + 2 * len(texts) or parts[0].strip():
                raise ValueError("翻译返回的记录边界不匹配")
            output = []
            for i, text in enumerate(texts):
                if parts[1 + i * 2] != f"{i:06d}":
                    raise ValueError("翻译记录 ID 顺序不匹配")
                zh = parts[2 + i * 2].strip()
                if not zh or not re.search(r"[\u3400-\u9fff]", zh):
                    raise ValueError("缺失中文译文")
                output.append({"source_sha256": digest(text), "source_text": text, "zh": zh, "provider": PROVIDER})
            return output
        except (OSError, ValueError, IndexError, TypeError):
            if attempt == 3:
                if len(texts) > 1:
                    middle = len(texts) // 2
                    return translate_batch(texts[:middle]) + translate_batch(texts[middle:])
                raise
            time.sleep(2 ** attempt * 2)


def build(processed, output, fetch=False, workers=3):
    records = source_records(processed)
    output.mkdir(parents=True, exist_ok=True)
    cache_path = output / "translation_cache.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if digest(item["source_text"]) != item["source_sha256"]:
                raise ValueError("译文缓存源文本哈希错误")
            cache[item["source_sha256"]] = item
    texts = list(dict.fromkeys(t for table in records.values() for t in table.values() if t))
    missing = [text for text in texts if digest(text) not in cache]
    if missing and not fetch:
        raise ValueError(f"缺少 {len(missing)} 条译文；使用 --fetch 获取并缓存，或提供完整缓存。")
    batches, current, size = [], [], 0
    for text in missing:
        if current and size + len(text) + 11 > 3800:
            batches.append(current); current, size = [], 0
        current.append(text); size += len(text) + 11
    if current:
        batches.append(current)
    print(f"需翻译 {len(missing)} 条文本，{len(batches)} 个批次；已有缓存 {len(cache)}。", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool, cache_path.open("a", encoding="utf-8") as stream:
        futures = [pool.submit(translate_batch, batch) for batch in batches]
        for index, future in enumerate(as_completed(futures), 1):
            for item in future.result():
                cache[item["source_sha256"]] = item
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            stream.flush()
            if index % 10 == 0 or index == len(batches):
                print(f"翻译进度 {index}/{len(batches)}；缓存 {len(cache)}。", flush=True)
    translations = {table: {key: cache[digest(text)]["zh"] if text else "" for key, text in values.items()}
                    for table, values in records.items()}
    metadata = {"provider": PROVIDER, "target_language": "zh-CN", "human_reviewed": False,
                "usage": "Reading aid only; English remains authoritative; never used for filtering.",
                "coverage": {table: len(values) for table, values in records.items()},
                "source_sha256": {table + ".csv": hashlib.sha256((processed / (table + ".csv")).read_bytes()).hexdigest() for table in records}}
    overrides_path = output / "translation_overrides.json"
    if overrides_path.exists():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        for item in overrides:
            source = records[item["table"]][item["id"]]
            if item["source_text"] != source or not re.search(r"[\u3400-\u9fff]", item["zh"]):
                raise ValueError("译文措辞修订与原始记录不匹配")
            translations[item["table"]][item["id"]] = item["zh"]
        metadata["wording_overrides"] = {"count": len(overrides), "reviewer": "coding assistant, not human review",
                                         "sha256": hashlib.sha256(overrides_path.read_bytes()).hexdigest()}
    payload = {"metadata": metadata, **translations}
    temp = output / "translations_zh.json.tmp"
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(output / "translations_zh.json")
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/translations")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    build(args.processed_dir, args.output_dir, args.fetch, args.workers)
