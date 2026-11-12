#!/usr/bin/env python3
"""Build the current Raw Work Seed browser; translations never change authoritative data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import shutil

from build_onet import ROOT, build, sha256
from emerging_tasks import require
from translate_catalog import digest, translate_batch


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def build_view(input_dir, output_dir, fetch=False):
    build(ROOT/'data/raw', ROOT/'data/processed', verify_only=True)
    effective=read_jsonl(input_dir/'effective_tasks.jsonl')
    digital=read_jsonl(input_dir/'digital_task_pool.jsonl')
    sampled=read_jsonl(input_dir/'sampled_raw_seeds.jsonl')
    report=json.loads((input_dir/'stage1_report.json').read_text())
    require(report['status']=='complete' and all(report['checks'].values()), 'Stage 1 checks failed')
    require(len(effective)==len({r['task_id'] for r in effective})==len({r['seed_id'] for r in effective}), 'Duplicate seed/task IDs')
    require(digital==[r for r in effective if r['digital_label']=='DIGITAL'], 'Digital pool is not the complete DIGITAL subset')
    lookup={r['seed_id']:r for r in digital}
    require(len(sampled)==len({r['seed_id'] for r in sampled}) and all(lookup.get(r['seed_id'])==r for r in sampled), 'Invalid sampled subset')
    require((len(effective),len(digital),len(sampled))==(report['counts']['effective_tasks'],report['counts']['digital_tasks'],report['sampled']['tasks']), 'Report counts differ')
    raw={}
    for filename in ('task_statements.csv','emerging_tasks.csv'):
        with (ROOT/'data/raw'/filename).open(encoding='utf-8-sig',newline='') as stream:raw[filename]=list(csv.DictReader(stream))
    for r in effective:
        source=raw[report['record_format']['source_files'][r['task_source']]][r['source_metadata']['row']-2]
        require((r['task_text'],r['occupation_code'])==(source['Task'],source['O*NET-SOC Code']), 'Official source text mismatch')
    with (ROOT/'data/processed/dwas.csv').open(encoding='utf-8',newline='') as stream:
        dwas={r['dwa_id']:r['dwa_name'] for r in csv.DictReader(stream)}
    require(all(d in dwas for r in effective for d in r['dwa_ids']), 'Unknown DWA ID')
    # Key translations by exact source text, never inherit an old Task ID's translation for a revision.
    cache={}
    extra=ROOT/'site/translations.jsonl'
    for path in (ROOT/'archive/data/translations/translation_cache.jsonl',extra):
        if path.exists():
            for item in read_jsonl(path):
                require(digest(item['source_text'])==item['source_sha256'], 'Translation source hash mismatch')
                cache[item['source_text']]=item['zh']
    groups=json.loads((ROOT/'config/soc_major_groups.json').read_text())['groups']
    texts=list(dict.fromkeys([t for r in effective for t in (r['task_text'],r['occupation_title'])]+list(dwas.values())+list(groups.values())))
    missing=[t for t in texts if t not in cache]
    if fetch and missing:
        batches=[];batch=[];size=0
        for t in missing:
            if batch and size+len(t)>3000:batches.append(batch);batch=[];size=0
            batch.append(t);size+=len(t)+12
        if batch:batches.append(batch)
        print(f'Translating {len(missing)} missing display texts in {len(batches)} batches',flush=True)
        with ThreadPoolExecutor(max_workers=3) as pool,extra.open('a',encoding='utf-8') as stream:
            for items in pool.map(translate_batch,batches):
                for item in items:
                    stream.write(json.dumps(item,ensure_ascii=False,sort_keys=True)+'\n');cache[item['source_text']]=item['zh']
                stream.flush()
    zh={t:cache[t] for t in texts if t in cache}
    payload={'tasks':effective,'sampled_ids':[r['seed_id'] for r in sampled],'dwas':dwas,'groups':groups,'zh':zh,
             'report':report,'validation':{'digital_pool_complete':True,'official_text_unchanged':True,
              'digital_translated':sum(r['task_text'] in zh for r in digital),
              'all_translated':sum(r['task_text'] in zh for r in effective),
              'digital_sha256':sha256((input_dir/'digital_task_pool.jsonl').read_bytes())}}
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'catalog.js').write_text('window.CATALOG='+json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+';\n',encoding='utf-8')
    for name in ('index.html','app.js','style.css'):shutil.copyfile(ROOT/'site'/name,output_dir/name)
    for name in ('effective_tasks.jsonl','digital_task_pool.jsonl','sampled_raw_seeds.jsonl','stage1_report.json'):shutil.copyfile(input_dir/name,output_dir/name)
    # Remove only the previous browser's generated exports so old and current pools cannot be confused.
    for name in ('occupations.csv','tasks.csv','dwas.csv','task_dwa.csv','validation_report.json'):
        (output_dir/name).unlink(missing_ok=True)
    if (output_dir/'digital').is_dir():shutil.rmtree(output_dir/'digital')
    print(json.dumps({'output':str(output_dir),'digital':len(digital),'effective':len(effective),**payload['validation']},ensure_ascii=False,indent=2))
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,default=ROOT/'data/raw_work_seeds')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'site/dist')
    parser.add_argument('--fetch-translations',action='store_true',help='Fetch missing display translations; never change seeds')
    args=parser.parse_args();build_view(args.input_dir,args.output_dir,args.fetch_translations)


if __name__=='__main__':main()
