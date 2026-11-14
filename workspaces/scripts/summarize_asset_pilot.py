#!/usr/bin/env python3
"""Summarize the declared batch, including failures before retrieval; no new judgments."""
import argparse
import json
from pathlib import Path
from common import REPO,ROOT,save
from planning_common import schema


def summarize(plans,workspaces,tasks,output):
    planning=schema(plans/'planning_report.json')
    blueprints={r['seed_id']:r for r in (json.loads(l) for l in (plans/'blueprints.jsonl').read_text().splitlines())}
    ws={r['seed_id']:r for r in (schema(p) for p in workspaces.glob('*/construction/construction_report.json'))}
    tr={r['seed_id']:r for r in schema(tasks/'stage4_report.json')['workspaces']}
    raw={r['seed_id']:r for r in (json.loads(l) for l in (REPO/'work-seeds/data/raw_work_seeds/digital_task_pool.jsonl').read_text().splitlines())}
    records=[]
    for sid,p in planning['seeds'].items():
        w=ws.get(sid);t=tr.get(sid)
        material=[n['id'] for n in blueprints.get(sid,{}).get('information_nodes',[]) if n['type']=='external_input' and n['supply_channel']!='task_instruction']
        records.append({'seed_id':sid,'occupation':raw[sid]['occupation_title'],'raw_task_text':raw[sid]['task_text'],
            'blueprint_status':p['status'],'workspace_status':w['status'] if w else 'not_attempted',
            'task_status':t.get('status') if t else 'not_attempted','task_id':t.get('task_id') if t else None,
            'search_requests':w['counts']['actual_search_requests'] if w else 0,
            'fetch_requests':w['counts']['actual_fetch_requests'] if w else 0,
            'downloaded_urls_including_discovery_pages':w['counts']['downloaded_urls'] if w else 0,
            'parsed_native_files':w['counts']['parsed_unique_files'] if w else 0,
            'retained_native_files':w['counts']['retained_files'] if w else 0,
            'critical_inputs':w['counts']['critical_external_nodes'] if w else None,
            'supported_critical_inputs':w['counts']['supported_critical_nodes'] if w else None,
            'material_inputs':len(material) if w else None,
            'supported_material_inputs':sum(n in w['supported_nodes'] for n in material) if w else None,
            'modality_evidence':w['modality_evidence'] if w else [],
            'failures':{'planning':p['failure_reasons'],'workspace':w['failure_reasons'] if w else [],'task':t.get('reasons',[]) if t else []}})
    result={'selection':'Predeclared purposive batch: 4 Web, 3 video-editing, 3 spatial-design seeds from the official pool.',
        'denominator':len(records),'planning_counts':planning['counts'],
        'counts':{'searched_seeds':len(ws),'seeds_with_downloaded_native_assets':sum(w['counts']['parsed_unique_files']>0 for w in ws.values()),
            'ready_workspaces':sum(r['workspace_status']=='ready' for r in records),
            'draft_tasks':sum(r['task_status']=='draft' for r in records),
            'search_requests':sum(r['search_requests'] for r in records),'fetch_requests':sum(r['fetch_requests'] for r in records),
            'parsed_native_files':sum(r['parsed_native_files'] for r in records),
            'supported_material_inputs':sum(r['supported_material_inputs'] or 0 for r in records),
            'material_inputs':sum(r['material_inputs'] or 0 for r in records),
            'independently_verified_visual_facts':0,'new_solver_rollouts':0},
        'billing':{'confirmed_total_cost':None,'reason':'No provider billing reconciliation; token records remain in model receipts.'},
        'limitations':['Development batch used while revising interfaces/prompts; not a held-out success-rate estimate.',
            'Repeated builds reuse the same actual search receipts; counts describe unique retained sessions, not fresh searches on each replay.',
            'Visual observations are model inspections; necessity and scoring reliability have not been established.',
            'Blank/mutated fixture artifact tests are engineering validation, not empirical task success.'],
        'records':records}
    # Deduplicate development receipts; aborted sessions are not free searches.
    aborted={}
    for path in (ROOT/'data').glob('asset_pilot*/*/construction/search_trace.json'):
        receipt=schema(path)
        if receipt['run']['returncode']!=0:aborted[receipt['run']['transcript_sha256']]=receipt
    result['development_overhead']={'cancelled_or_failed_search_sessions':len(aborted),
        'additional_search_requests':sum(r['trace']['websearch_calls'] for r in aborted.values()),
        'additional_fetch_requests':sum(r['trace']['webfetch_calls'] for r in aborted.values()),
        'reason':'Aborted development sessions are separate from the three retained pilot sessions, not hidden as zero cost.'}
    save(output/'batch_report.json',result)
    lines=['# Asset-grounded Pilot · 2026-11-14','',
        '开发批次：预先指定 10 条官方 Raw Seed（Web 4、视频剪辑 3、空间设计 3）。本批次用于调试接口和 Prompt，不是独立评测集。所有上游失败均计入分母。','',
        '| Seed | 职业 | Stage 2 | Stage 3 | Stage 4 | 搜索 / 页面读取 | 原生文件 |',
        '|---|---|---|---|---|---:|---:|']
    for r in records:lines.append(f"| {r['seed_id']} | {r['occupation']} | {r['blueprint_status']} | {r['workspace_status']} | {r['task_status']} | {r['search_requests']} / {r['fetch_requests']} | {r['parsed_native_files']} |")
    lines+=['','`ready` 仅表示模型审核后的构造准入；`draft` 未经执行测试。视觉观察不是 Ground Truth，程序化可读性检查不是专业成果正确性。费用缺少账单核对，不填猜测值。','',
        '## 三条完整处理记录','']
    for r in records:
        if r['seed_id'] not in ws:continue
        w=ws[r['seed_id']];directory=next(p.parent.parent for p in workspaces.glob('*/construction/construction_report.json') if schema(p)['seed_id']==r['seed_id'])
        lines += ['### '+r['seed_id'],'',r['raw_task_text'],'',
            f"Blueprint：{r['blueprint_status']}；Workspace：{r['workspace_status']}；Task：{r['task_status']}。",'',
            f"实际搜索 {r['search_requests']} 次、WebFetch {r['fetch_requests']} 次；解析原生文件 {r['parsed_native_files']} 份、保留 {r['retained_native_files']} 份。",'']
        if (directory/'construction/grounded_graph.json').exists():
            g=schema(directory/'construction/grounded_graph.json');lines += [g['case_title'],'',g['case_objective'],'',
                '| 信息节点 | 状态 | 来源 |','|---|---|---|']
            for b in g['bindings']:
                loc='; '.join(sorted({x['file_id']+':'+x['locator'] for x in b['references']}))
                lines.append(f"| {b['information_node_id']} | {b['status']} | {loc or '显式虚构用户委托'} |")
            lines+=['']
        sources=schema(directory/'construction/source_manifest.json')['sources']
        lines+=['实际获取并解析的来源（许可未自动认证）：','']
        for fid,s in sources.items():lines.append(f"- [{fid}]({s['original_url']}) — SHA-256 `{s['sha256']}`")
        lines+=['','阻断 / 拒绝记录：','', '```json',json.dumps(r['failures'],ensure_ascii=False,indent=2),'```','']
        if r['task_id']:
            package=REPO/'work-tasks/generated/asset_pilot'/r['task_id']
            task=schema(package/'task.json');lines+=['实际用户指令：','',task['instruction'],'','交付：','']
            lines += ['- `'+d['path']+'`：'+d['description'] for d in task['deliverables']]
            lines+=['']
    (output/'report.md').write_text('\n'.join(lines).rstrip()+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plans',type=Path,default=REPO/'work-plans/data/asset_pilot_v2')
    p.add_argument('--workspaces',type=Path,default=ROOT/'data/asset_pilot_v4')
    p.add_argument('--tasks',type=Path,default=REPO/'work-tasks/data/asset_pilot_current')
    p.add_argument('--output',type=Path,default=ROOT/'data/asset_pilot_v4')
    a=p.parse_args();print(summarize(a.plans,a.workspaces,a.tasks,a.output)['counts'])
