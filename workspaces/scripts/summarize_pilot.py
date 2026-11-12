#!/usr/bin/env python3
"""Summarize saved real outcomes; never run models or manufacture missing results."""
import argparse
from collections import Counter
import json
from pathlib import Path
from common import REPO, ROOT, save, read_jsonl
from planning_common import schema, usage


def summarize(plan_dir, workspace_dir, baseline_dir):
    planning = schema(plan_dir / 'planning_report.json')
    workspace = schema(workspace_dir / 'pilot_report.json')
    baseline = schema(baseline_dir / 'pilot_report.json')
    raw = {r['seed_id']: r for r in read_jsonl(REPO / 'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')}
    by_seed = {r['seed_id']: r for r in workspace['workspaces']}
    rows, calls = [], []
    for sid, r in planning['seeds'].items():
        ws = by_seed.get(sid)
        rows.append({'seed_id': sid, 'occupation_title': raw[sid]['occupation_title'],
                     'planning_status': r['status'], 'failure_stage': r.get('failure_stage'),
                     'failure_reasons': r.get('failure_reasons', []),
                     'workspace_status': ws['status'] if ws else 'not_run_blueprint_not_admitted',
                     'search_state': ws['search_state'] if ws else 'not_run',
                     'workspace_failure_reasons': ws['failure_reasons'] if ws else []})
        calls.extend(r['model_calls'])
    for ws in workspace['workspaces'] + baseline['workspaces']:
        calls.extend(ws['model_calls'])
    counts = planning['counts']
    critical = sum(w['counts']['critical_external_nodes'] for w in workspace['workspaces'])
    supported = sum(w['counts']['supported_critical_nodes'] for w in workspace['workspaces'])
    summary = {
        'scope': '10 real Raw Seeds; actual GLM generation/review/planning; no Search API credentials.',
        'planning_counts': counts,
        'rates': {
            'blueprint_generated_per_input': counts['generated'] / counts['input'],
            'graph_passed_per_input': counts['graph_passed'] / counts['input'],
            'semantic_accepted_per_reviewed': counts['accepted'] / counts['graph_passed'],
            'admitted_per_input': counts['accepted'] / counts['input'],
            'anchor_discovery_success_per_live_search_attempt': None,
            'ready_per_admitted_blueprint': workspace['counts']['ready'] / counts['accepted'],
            'critical_coverage_per_processed_workspace': supported / critical if critical else None},
        'workspace_counts': workspace['counts'],
        'supported_critical_nodes': supported, 'critical_nodes_in_processed_workspaces': critical,
        'planning_failure_stages': dict(Counter(r['failure_stage'] for r in rows if r['failure_stage'])),
        'multimodal': {'accepted_plans_with_hypotheses': counts['modality_candidate_plans'],
                      'independently_verified_visual_evidence': sum(w['counts']['independently_verified_visual_evidence'] for w in workspace['workspaces']),
                      'necessity': 'not_tested'},
        'model_usage_final_pilot_and_direct_control': usage(calls),
        'direct_search_control': {'counts': baseline['counts'], 'conclusion': 'Not assessable: neither strategy executed a Search API request. This is a raw-seed-only search-planning control, not an end-to-end graph-free baseline.'},
        'rows': rows,
        'limits': ['No live provider, candidate selection, download or semantic evidence audit occurred in this pilot.',
                   'Actual source regressions and synthetic loop tests are reported separately, never as pilot anchors.',
                   'Same-model semantic review is not expert certification; rejected cases are not automatically repaired.',
                   'Money cost is unknown without gateway billing receipts; token usage is recorded.',
                   'The initial v1 development run is archived separately and excluded from final v2 success rates.']}
    archive = REPO / 'work-plans/archive/data/raw_blueprint_v1/planning_report.json'
    if archive.exists():
        old = schema(archive)
        summary['development_v1'] = {'counts': old['counts'], 'model_usage': old['model_usage']}
        old_calls = [c for r in old['seeds'].values() for c in r['model_calls']]
        summary['model_usage_including_development_v1'] = usage(calls + old_calls)
    save(workspace_dir / 'experiment_summary.json', summary)
    lines = ['# Raw Seed → Blueprint → Search → Workspace：本轮实际记录', '',
             '本文件由 summarize_pilot.py 从保存的结果生成。模型确实调用；没有搜索凭证，因此没有新文件或 ready Workspace。', '',
             '| Seed | 职业 | Blueprint | 阻断环节 | Workspace / 搜索状态 |',
             '|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['seed_id']} | {r['occupation_title']} | {r['planning_status']} | {r['failure_stage'] or '—'} | {r['workspace_status']} / {r['search_state']} |")
    lines += ['', '## 三条完整处理记录', '', '以下包含原始 Seed、完整模型输出、图边、审核和实际搜索记录。失败输出不是准入 Blueprint。']
    for sid in ('raw_31_0_16425', 'raw_31_0_21094', 'raw_31_0_871'):
        r = planning['seeds'][sid]
        ws = by_seed.get(sid)
        record = {'raw_seed': raw[sid], 'blueprint': r.get('proposed_blueprint'),
                  'deterministic_checks': r['deterministic_checks'], 'semantic_review': r['semantic_review'],
                  'planning_status': r['status'], 'planning_failures': r.get('failure_reasons', []),
                  'search_trace': schema(workspace_dir / ws['workspace_id'] / 'construction/search_trace.json') if ws else {'status': 'not_run', 'reason': 'blueprint_not_admitted'},
                  'workspace': {k: ws[k] for k in ('workspace_id','status','search_state','selected_anchor','counts','missing_nodes','failure_reasons','modality_evidence')} if ws else {'status': 'not_constructed'}}
        lines += ['', f'### {sid} · {raw[sid]["occupation_title"]}', '', '```json', json.dumps(record, ensure_ascii=False, indent=2), '```']
    lines += ['', '## 实际目录', '', '```text', 'workspaces/data/generated/WS_3ff8d749c6f4/',
              '├── workspace_init/                 # 空；尚未获取真实输入文件', '└── construction/',
              '    ├── search_trace.json', '    ├── source_manifest.json         # sources 为空',
              '    ├── file_profiles.json           # 空', '    ├── information_coverage.json    # 三个关键节点均 missing',
              '    └── construction_report.json     # incomplete / awaiting_search', '```', '',
              '没有可展示的新来源。两份历史 CSV/XLSX 的真实来源、哈希及定位回归见 regression_report.json；它们不构成本轮 Workspace。']
    (workspace_dir / 'examples.md').write_text('\n'.join(lines) + '\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-dir', type=Path, default=REPO / 'work-plans/data/generated')
    p.add_argument('--workspace-dir', type=Path, default=ROOT / 'data/generated')
    p.add_argument('--baseline-dir', type=Path, default=ROOT / 'data/direct_baseline')
    a = p.parse_args()
    result = summarize(a.plan_dir, a.workspace_dir, a.baseline_dir)
    print(json.dumps({'rates': result['rates'], 'workspaces': result['workspace_counts']}, indent=2))


if __name__ == '__main__':
    main()
