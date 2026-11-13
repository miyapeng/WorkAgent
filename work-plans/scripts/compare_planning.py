#!/usr/bin/env python3
"""Compare the same real Seed cohort, with explicit denominators and failure stages."""
import argparse
from collections import Counter
from pathlib import Path
from planning_common import REPO, schema, require, save


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,default=REPO/'work-plans/data/generated/planning_report.json')
    p.add_argument('--current',type=Path,default=REPO/'work-plans/data/semantic_pilot/planning_report.json')
    p.add_argument('--output-dir',type=Path,default=REPO/'work-plans/data/semantic_pilot')
    a=p.parse_args();old=schema(a.baseline);new=schema(a.current)
    require(set(old['seeds'])==set(new['seeds']),'different_seed_cohort')
    require(old['input_sha256']==new['input_sha256'],'different_raw_seed_input')
    require(all(old['seeds'][sid]['seed_sha256']==new['seeds'][sid]['seed_sha256'] for sid in old['seeds']),'raw_seed_changed')
    def rates(report):
        c=report['counts'];attempted=c.get('semantic_review_attempted',c['graph_passed'])
        return {'input':c['input'],'graph_passed':c['graph_passed'],'graph_pass_rate':c['graph_passed']/c['input'],
                'semantic_attempted':attempted,'semantic_valid_responses':c.get('semantic_reviewed',c['graph_passed']),
                'semantic_accepted':c['accepted'],'semantic_accepted_per_input':c['accepted']/c['input'],
                'semantic_accepted_per_attempt':c['accepted']/attempted if attempted else None}
    rows=[]
    for sid,r in new['seeds'].items():
        rows.append({'seed_id':sid,'baseline_status':old['seeds'][sid]['status'],'current_status':r['status'],
                     'failure_stage':r.get('failure_stage'),'failure_reasons':r.get('failure_reasons',[])})
    plans=[r['proposed_blueprint'] for r in new['seeds'].values() if r['status']=='accepted']
    report={'same_raw_input_and_seed_hashes':True,'baseline':rates(old),'current':rates(new),
            'failure_stages':dict(Counter(r['failure_stage'] for r in rows if r['failure_stage'])),
            'accepted_artifact_kinds':dict(Counter(p['deliverables'][0]['type'] for p in plans)),
            'accepted_input_format_preferences':dict(Counter(f for p in plans for n in p['information_nodes'] if n['type']=='external_input' for f in n['preferred_formats'])),
            'visual_hypothesis_plans':sum(bool(p['modality_hypotheses']) for p in plans),
            'actual_materialized_files':0,'new_workspaces_constructed':0,'model_usage':new['model_usage'],
            'rows':rows,'limitations':['Same 10 Seeds and reviewer prompt; small comparison, not a causal ablation or population-quality estimate.',
                                     'Preferred formats are alternatives, not files found or final output contracts.',
                                     'One review returned non-JSON; this is a model-response failure, not a semantic rejection.',
                                     'No repair or format coercion; missing professional premises are not filled by Python.']}
    save(a.output_dir/'comparison_report.json',report)
    lines=['# Semantic Planning Pilot 对照','',
           '| 指标 | 旧版直接 Graph | 新版语义规划 + Python 编译 |','|---|---:|---:|',
           f"| 同批输入 | {old['counts']['input']} | {new['counts']['input']} |",
           f"| 结构通过 | {old['counts']['graph_passed']}/10 | {new['counts']['graph_passed']}/10 |",
           f"| 语义审核通过 / 全部输入 | {old['counts']['accepted']}/10 | {new['counts']['accepted']}/10 |",
           f"| 语义审核通过 / 尝试审核 | {report['baseline']['semantic_accepted']}/{report['baseline']['semantic_attempted']} | {report['current']['semantic_accepted']}/{report['current']['semantic_attempted']} |",'',
           '本轮 1 条审核响应不是合法 JSON，未准入；不将它解释为职业语义错误。其余 4 条因格式或类别约束失败，未进入审核。原始职业任务逐字段、逐哈希保持不变。','',
           '| Seed | 旧版 | 新版 | 原因 |','|---|---|---|---|']
    for r in rows:lines.append(f"| {r['seed_id']} | {r['baseline_status']} | {r['current_status']} | {'; '.join(r['failure_reasons']).replace('|','/')} |")
    sid='raw_31_0_871';r=new['seeds'][sid]
    lines+=['','## 实际示例：建筑图纸合规检查','','模型输出只含语义规划；ID、Graph 与假设状态由程序生成。以下是保存的实际响应，不是人工样例。','','```json',__import__('json').dumps(r['semantic_plan'],ensure_ascii=False,indent=2),'```','','编译后的图：','','```mermaid','flowchart TD']
    graph=r['proposed_blueprint']
    for n in graph['information_nodes']:lines.append(f'    {n["id"]}["{n["type"]}: {n["description"].replace(chr(34),chr(39))}"]')
    for n in graph['deliverables']:lines.append(f'    {n["id"]}["{n["type"]}: {n["description"].replace(chr(34),chr(39))}"]')
    for left,right in graph['dependencies']:lines.append(f'    {left} --> {right}')
    lines+=['```','','文件格式均为偏好；本轮没有检索或生成这些文件，没有证明视觉必要性。Direct Answer、TEX 等已实现并通过夹具测试，但未强制塞入本轮准入样本。']
    (a.output_dir/'comparison.md').write_text('\n'.join(lines)+'\n')
    print({'baseline':report['baseline'],'current':report['current']})


if __name__=='__main__':main()
