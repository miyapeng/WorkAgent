"""Engineering reference, using explicitly supplied visual transcription, not a teacher."""
import argparse
import json
from decimal import Decimal
from pathlib import Path


def solve(run, observation_path):
    import csv
    # This solver reads only public inputs and the caller's visual observation.
    with (run / 'quotes.csv').open() as f:
        quotes = list(csv.DictReader(f))
    policy = json.loads((run / 'purchase_policy.json').read_text())
    if not (run / 'supplier_performance.png').is_file():
        raise ValueError('BLOCKED: missing performance image; do not guess')
    observation = json.loads(observation_path.read_text())
    import hashlib
    if observation['image_sha256'] != hashlib.sha256((run / 'supplier_performance.png').read_bytes()).hexdigest():
        raise ValueError('BLOCKED: visual observation belongs to a different image')
    performance = observation['values']
    results = []
    for q in quotes:
        sid = q['supplier_id']
        v = performance[sid]
        cost = Decimal(q['unit_price_cny']) * policy['quantity_units'] + Decimal(q['freight_cny']) + Decimal(q['setup_cny'])
        eligible = (int(q['capacity_units']) >= policy['quantity_units'] and
                    int(q['lead_days']) <= policy['max_lead_days'] and
                    Decimal(str(v['on_time_pct'])) >= Decimal(str(policy['min_on_time_pct'])) and
                    Decimal(str(v['defect_pct'])) <= Decimal(str(policy['max_defect_pct'])))
        results.append(dict(supplier_id=sid, total_cost_cny=f'{cost:.2f}',
                            on_time_pct=str(v['on_time_pct']), defect_pct=str(v['defect_pct']),
                            eligible=str(eligible).lower()))
    eligible_rows = [r for r in results if r['eligible'] == 'true']
    best = min(eligible_rows, key=lambda r: (Decimal(r['total_cost_cny']), r['supplier_id'])) if eligible_rows else None
    selected = best['supplier_id'] if best else None
    out = run / 'outputs'
    out.mkdir(exist_ok=True)
    with (out / 'comparison.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]), lineterminator='\n')
        w.writeheader(); w.writerows(results)
    (out / 'decision.json').write_text(json.dumps({'recommended_supplier': selected, 'evidence': {
        'quotes': 'quotes.csv', 'policy': 'purchase_policy.json', 'performance': 'supplier_performance.png'}}, indent=2) + '\n')
    lines = ['# 采购建议（合成案例）', '', f'推荐供应商：{selected if selected else "无合格供应商"}。', '',
             '成本按数量 × 含税单价 + 一次性运费 + 一次性开版费计算。', '',
             '| 供应商 | 总成本（元） | 准时交付率 | 不良率 | 资格 |', '|---|---:|---:|---:|---|']
    for r, q in zip(results, quotes):
        lines.append(f"| {r['supplier_id']} | {r['total_cost_cny']} | {r['on_time_pct']}% | {r['defect_pct']}% | {r['eligible']} |")
    lines += ['', '证据与逐项判断：']
    for r, q in zip(results, quotes):
        issues = []
        if int(q['capacity_units']) < policy['quantity_units']: issues.append('产能不足')
        if int(q['lead_days']) > policy['max_lead_days']: issues.append('交期超过上限')
        if Decimal(r['on_time_pct']) < policy['min_on_time_pct']: issues.append('准时交付率低于下限')
        if Decimal(r['defect_pct']) > policy['max_defect_pct']: issues.append('不良率高于上限')
        conclusion = '、'.join(issues) if issues else ('满足所有约束，按成本与平局规则选中' if r['supplier_id'] == selected else '满足所有约束，但按成本与平局规则未选中')
        lines.append(f"- {r['supplier_id']}：产能 {q['capacity_units']} 个、交期 {q['lead_days']} 天（quotes.csv 的 supplier_id={r['supplier_id']} 行）；绩效来自 supplier_performance.png 同 ID 行；{conclusion}。")
    lines += ['', f"政策（purchase_policy.json）：数量 {policy['quantity_units']}，最长交期 {policy['max_lead_days']} 天，准时交付率至少 {policy['min_on_time_pct']}%，不良率最多 {policy['max_defect_pct']}%。", '',
              '历史绩效只用于本次规则筛选，不能保证未来表现；签约前仍需确认报价及产能有效性。本结论仅适用于这个合成案例。', '',
              '此文件由工程参考程序及显式图片转录生成，不是独立教师模型执行示范。']
    (out / 'recommendation.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--observations', type=Path, required=True)
    a = p.parse_args()
    solve(a.run, a.observations)
