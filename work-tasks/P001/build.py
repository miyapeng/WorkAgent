"""Build one traceable development task; business materials are synthetic."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rows(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, records):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(records)


def build():
    from PIL import Image, ImageDraw, ImageFont
    source = REPO / 'work-seeds/archive/data/digital'
    task = next(r for r in rows(source / 'tasks.csv') if r['task_id'] == '1144')
    occupation = next(r for r in rows(source / 'occupations.csv')
                      if r['occupation_code'] == task['occupation_code'])
    decision = next(r for r in rows(source / 'task_decisions.csv') if r['task_id'] == '1144')
    assert decision['decision'] == 'DIGITAL'
    links = [r for r in rows(source / 'task_dwa.csv') if r['task_id'] == '1144']
    dwas = [r for r in rows(source / 'dwas.csv') if r['dwa_id'] in {r['dwa_id'] for r in links}]
    package = ROOT / 'package'
    visible = package / 'workspace_init'
    hidden = package / 'evaluation'
    visible.mkdir(parents=True, exist_ok=True)
    hidden.mkdir(parents=True, exist_ok=True)
    dump(package / 'seed.json', {
        'onet_version': '31.0', 'occupation': occupation, 'task': task, 'dwas': dwas,
        'digital_decision': decision,
        'source_sha256': {f: sha(source / f) for f in
                          ('tasks.csv', 'occupations.csv', 'dwas.csv', 'task_dwa.csv', 'task_decisions.csv')},
        'official_source': 'https://www.onetcenter.org/database.html',
        'license': 'O*NET 31.0: USDOL/ETA, CC BY 4.0; no endorsement.',
    })
    dump(package / 'intent.json', {
        'intent': '比较同规格包装箱供应商，在质量、交付和产能约束下给出最低成本采购建议。',
        'selection_reason': '原始种子明确涉及价格、质量、交付与产能；可用一个小案例核对跨文件推理和图片依赖。',
        'case_scope': '单一采购批次、单币种、同规格、三家供应商，不涉及真实法律或投资判断。',
        'authoring': 'One assistant-authored instance; no scalable intent generator implemented.',
        'required_support': {
            'total_cost': ['quantity', 'unit_price', 'freight', 'setup', 'tax_and_fee_basis'],
            'eligibility': ['capacity', 'lead_days', 'historical_on_time', 'historical_defects', 'policy_thresholds'],
            'recommendation': ['costs', 'eligibility', 'tie_rule'],
        },
        'reserved_for_solver': ['all totals', 'eligibility decisions', 'recommendation and rationale'],
    })
    quotes = [
        dict(supplier_id='A', unit_price_cny='2.00', freight_cny='300.00', setup_cny='200.00', lead_days='7', capacity_units='15000'),
        dict(supplier_id='B', unit_price_cny='2.10', freight_cny='150.00', setup_cny='100.00', lead_days='10', capacity_units='11000'),
        dict(supplier_id='C', unit_price_cny='2.05', freight_cny='600.00', setup_cny='300.00', lead_days='8', capacity_units='12000'),
    ]
    write_csv(visible / 'quotes.csv', quotes)
    dump(visible / 'purchase_policy.json', {
        'quantity_units': 10000, 'max_lead_days': 14,
        'min_on_time_pct': 95, 'max_defect_pct': 1,
        'currency': 'CNY', 'price_basis': '含税；运费、开版费各收一次；无其他费用',
        'decision_rule': '满足全部硬约束后，选择总采购成本最低者；同成本按供应商 ID 字母顺序选。',
    })
    # Only pixels carry these values in the solver-visible package.
    performance = [('A', 99, 2.4), ('B', 96, 0.6), ('C', 98, 0.8)]
    im = Image.new('RGB', (1200, 580), '#f2f5fa')
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=25)
    title = ImageFont.load_default(size=34)
    draw.text((40, 30), 'Supplier performance | Q3 2026', font=title, fill='#11243b')
    draw.text((40, 85), 'SYNTHETIC CASE | SAME PERIOD AND METRIC DEFINITIONS', font=font, fill='#41536b')
    draw.text((40, 155), 'Supplier', font=font, fill='#11243b')
    draw.text((220, 155), 'On-time delivery (%)', font=font, fill='#11243b')
    draw.text((730, 155), 'Defective units (%)', font=font, fill='#11243b')
    for i, (sid, ontime, defect) in enumerate(performance):
        y = 230 + 90 * i
        draw.text((65, y), sid, font=title, fill='#11243b')
        draw.rectangle((220, y, 220 + ontime * 3.5, y + 32), fill='#1d728a')
        draw.text((590, y), str(ontime), font=font, fill='#11243b')
        draw.rectangle((730, y, 730 + defect * 85, y + 32), fill='#a54c40')
        draw.text((1010, y), str(defect), font=font, fill='#11243b')
    draw.text((40, 520), 'Use numeric labels; chart bars have different scales.', font=font, fill='#41536b')
    im.save(visible / 'supplier_performance.png')
    (visible / 'TASK.md').write_text('''# P001 · 采购供应商比选（合成业务案例）

你是采购专员。为一家虚构企业采购 10,000 个规格相同的包装箱，比较 A、B、C 三家供应商，提交采购建议。

quotes.csv 是同一批次、同规格报价；purchase_policy.json 是本次采购的完整政策。supplier_performance.png 是同口径历史绩效。所有企业、报价和绩效均为教学合成数据，不是实际交易建议。

总成本 = 数量 × 含税单价 + 一次性运费 + 一次性开版费，不扣减不良品、不另加税。必须同时满足：产能足够、交期不超过政策上限、历史准时交付率不低于下限、不良率不高于上限。历史绩效仅作为本次筛选依据，不保证未来表现。通过全部约束后按总成本选择，平局按 ID 字母顺序。没有合格供应商时推荐 null。

请在 outputs/ 提交：

1. comparison.csv：每家供应商一行，字段 supplier_id,total_cost_cny,on_time_pct,defect_pct,eligible。金额保留两位小数；百分数填 99 而非 0.99；eligible 填 true 或 false。
2. decision.json：recommended_supplier（ID 或 null）；evidence 字典，键为 quotes、policy、performance，值分别为对应输入文件名。
3. recommendation.md：中文建议，说明推荐对象、三家总成本、各项资格判断、不选其他供应商的原因、图片中的历史指标、引用文件与对应行/区域，以及历史数据局限。

不得修改输入文件，不得编造缺失值。如果关键材料缺失或无法辨读，应报告阻塞而非猜测。
''', encoding='utf-8')
    nodes = [
        {'id': 'quotes', 'status': 'supplied', 'file': 'quotes.csv', 'anchor': 'supplier_id A/B/C; all fields'},
        {'id': 'policy', 'status': 'supplied', 'file': 'purchase_policy.json', 'anchor': 'quantity_units and all thresholds, price_basis, decision_rule'},
        {'id': 'performance', 'status': 'supplied', 'file': 'supplier_performance.png',
         'anchor': {'A': [40, 215, 1100, 280], 'B': [40, 305, 1100, 370], 'C': [40, 395, 1100, 460]},
         'coordinate_system': '1200x580 pixels; x0,y0,x1,y1'},
        {'id': 'cost', 'status': 'solver_derived', 'file': 'outputs/comparison.csv', 'anchor': 'total_cost_cny'},
        {'id': 'eligibility', 'status': 'solver_derived', 'file': 'outputs/comparison.csv', 'anchor': 'eligible'},
        {'id': 'decision', 'status': 'solver_derived', 'file': 'outputs/decision.json', 'anchor': 'recommended_supplier'},
        {'id': 'memo', 'status': 'solver_derived', 'file': 'outputs/recommendation.md', 'anchor': 'whole document'},
    ]
    dump(hidden / 'evidence_graph.json', {'nodes': nodes, 'edges': [
        {'from': ['quotes', 'policy'], 'to': 'cost', 'relation': 'quantity * unit_price + freight + setup'},
        {'from': ['quotes', 'policy', 'performance'], 'to': 'eligibility', 'relation': 'all four hard constraints'},
        {'from': ['cost', 'eligibility', 'policy'], 'to': 'decision', 'relation': 'lowest eligible cost; declared tie rule'},
        {'from': ['quotes', 'policy', 'performance', 'cost', 'eligibility', 'decision'], 'to': 'memo', 'relation': 'evidence-supported explanation'},
    ]})
    # Independent fixed audit values; reference solver never imports this oracle.
    dump(hidden / 'oracle.json', {'rows': [
        dict(supplier_id='A', total_cost_cny='20500.00', on_time_pct='99', defect_pct='2.4', eligible='false'),
        dict(supplier_id='B', total_cost_cny='21250.00', on_time_pct='96', defect_pct='0.6', eligible='true'),
        dict(supplier_id='C', total_cost_cny='21400.00', on_time_pct='98', defect_pct='0.8', eligible='true'),
    ], 'recommended_supplier': 'B'})
    dump(hidden / 'rubric.json', [
        {'id': 'cost', 'anchors': ['quotes', 'policy'], 'check': 'all three costs within 0.01 CNY', 'mode': 'automatic'},
        {'id': 'visual_values', 'anchors': ['performance'], 'check': 'all six percentages exact', 'mode': 'automatic'},
        {'id': 'eligibility', 'anchors': ['quotes', 'policy', 'performance'], 'check': 'all three decisions exact', 'mode': 'automatic'},
        {'id': 'recommendation', 'anchors': ['cost', 'eligibility', 'policy'], 'check': 'correct selected ID and three source filenames', 'mode': 'automatic'},
        {'id': 'memo_quality', 'anchors': ['memo', 'quotes', 'policy', 'performance'],
         'check': 'accurate claims, sufficient rationale, precise citations, no unsupported future guarantees', 'mode': 'human_review_required'},
    ])
    dump(package / 'manifest.json', {
        'task_id': 'P001', 'seed_task_id': '1144', 'split': 'development',
        'materials_provenance': 'Synthetic business case authored for this prototype; only seed is official O*NET.',
        'image_dependency': 'Six historical rates occur only in PNG pixels in workspace_init.',
        'input_sha256': {p.name: sha(p) for p in sorted(visible.iterdir()) if p.is_file()},
        'training_admitted': False, 'boundary': 'Directory separation only, not an OS sandbox.',
    })
    print(package)


if __name__ == '__main__':
    build()
