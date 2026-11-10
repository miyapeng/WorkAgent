"""构建端：任务设计 → 可见工作空间 + 隐藏证据/答案。"""

import json
from pathlib import Path

from .artifacts import FIELDS, dashboard, previous_report, write_xlsx


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_task(design_path, root):
    design = read_json(design_path)
    task_id = design["task_id"]
    if not task_id.isalnum():
        raise ValueError("task_id 必须只包含字母和数字")
    package = Path(root) / "tasks" / task_id
    if package.exists():
        raise FileExistsError(f"任务包已存在：{package}；请使用新的输出目录，以免覆盖已有实验。")
    workspace = package / "workspace_init"
    workspace.mkdir(parents=True)
    regions = design["regions"]
    orders = [{"region": r["region"], "amount": value} for r in regions for value in r["orders"]]
    write_xlsx(workspace / "orders.xlsx", ["region", "amount"], orders)
    dashboard(workspace / "dashboard.png", regions)
    previous_report(workspace / "previous_report.pdf", regions)
    threshold = design["anomaly_conversion_drop"]
    requirements = (
        "# W001 交付约定（V0）\n\n"
        "按 region 求和订单收入。收入变化率 = 本季收入 / 上季收入 - 1。\n"
        "conversion 来自最新 PNG 看板；conversion_change = 本季转化率 - 上季转化率。\n"
        f"异常 = 收入下降且转化率下降至少 {threshold:.0%}（百分点差，允许浮点误差）。\n"
        f"Excel 第一行字段为：{', '.join(FIELDS)}；每区域一行，anomaly 为布尔值。\n"
        "PDF 必须两页：第一页数值摘要与分析，第二页收入图。当前文件渲染使用英文。\n"
        "为便于 V0 程序验收，每区域包含如下格式的数值行（四位小数率值）：\n"
        "REGION | revenue=金额两位小数 | change=变化率 | conversion=转化率 | delta=百分点差 | anomaly=0或1\n"
        "分析至少 80 个英文字符；解释证据与可能原因的区别，提出下一步核查建议。\n"
        "输入文件不可修改。不要把相关性直接写成已证实的销售下滑原因。\n"
    )
    (workspace / "report_requirements.md").write_text(requirements, encoding="utf-8")
    task = {key: design[key] for key in ["task_id", "occupation", "family_id", "split", "instruction"]}
    task.update(inputs=sorted(p.name for p in workspace.iterdir()),
                deliverables=["sales_summary.xlsx", "quarterly_brief.pdf"],
                constraints=["preserve_original_files"], max_steps=20)
    write_json(package / "task.json", task)
    oracle = []
    for r in regions:
        revenue = sum(r["orders"])
        delta = r["conversion"] - r["previous_conversion"]
        oracle.append(dict(region=r["region"], revenue=revenue,
                           revenue_change=revenue / r["previous_revenue"] - 1,
                           conversion=r["conversion"], conversion_change=delta,
                           anomaly=revenue < r["previous_revenue"] and delta <= -threshold + 1e-9))
    write_json(package / "evaluation" / "oracle.json", oracle)
    write_json(package / "evaluation" / "evidence_graph.json", [
        {"requirement": "revenue / revenue_change", "sources": ["orders.xlsx", "previous_report.pdf"], "check": "outcome.numeric"},
        {"requirement": "conversion / conversion_change / anomaly", "sources": ["dashboard.png", "previous_report.pdf", "orders.xlsx"], "check": "outcome.numeric_and_anomaly"},
        {"requirement": "two-page report with chart", "sources": ["report_requirements.md"], "check": "artifact.pdf"},
        {"requirement": "preserve sources", "sources": task["inputs"], "check": "process.hashes"}
    ])
    write_json(package / "evaluation" / "rubric.json", {
        "weights": {"outcome": 0.65, "artifact": 0.25, "process": 0.10},
        "hard_gate": "source_integrity", "success": "all_checks_pass",
        "limitations": ["固定格式数值检查", "图片存在性不代表图表正确或清晰", "不评价分析语义或排版质量"]
    })
    return package
