"""构建端的正反向验收：失败项要返回 task / workspace / verifier 环节修复。"""

from openpyxl import load_workbook
from reportlab.pdfgen import canvas

from .artifacts import pdf_text
from .build import write_json
from .environment import WorkEnvironment
from .reference import run_reference
from .verify import verify


def probe(root, task_id="W001"):
    env = WorkEnvironment(root)
    env.reset(task_id)
    good = run_reference(env)
    summary = env.workspace / "sales_summary.xlsx"
    report = env.workspace / "quarterly_brief.pdf"
    original_summary = summary.read_bytes()
    original_report = report.read_bytes()
    checks = {"correct_reference_passes": good["success"] and good["reward"] == 1.0}

    def grade():
        # 离线变异检查不改变已结束的真实 episode 评分/轨迹。
        return verify(env.package, env.workspace, env.baseline)

    book = load_workbook(summary)
    book.active["B2"] = -999
    book.save(summary)
    checks["wrong_revenue_rejected"] = not grade()["success"]
    summary.write_bytes(original_summary)

    book = load_workbook(summary)
    book.active["D2"] = 0.999
    book.save(summary)
    checks["wrong_visual_metric_rejected"] = not grade()["success"]
    summary.write_bytes(original_summary)

    report.unlink()
    checks["missing_report_rejected"] = not grade()["success"]
    report.write_bytes(original_report)

    # 两页、保留文字，但去掉图表。
    text = pdf_text(report)
    pdf = canvas.Canvas(str(report))
    for i, line in enumerate(text.splitlines()):
        pdf.drawString(40, 790 - i * 16, line)
    pdf.showPage()
    pdf.drawString(40, 790, "Chart omitted")
    pdf.save()
    checks["missing_chart_rejected"] = not grade()["checks"].get("artifact.chart_present", False)
    report.write_bytes(original_report)

    source = env.workspace / "orders.xlsx"
    original_source = source.read_bytes()
    source.write_bytes(b"tampered")
    result = grade()
    checks["source_change_gates_reward"] = result["reward"] == 0 and result["hard_gate_triggered"]
    source.write_bytes(original_source)

    env.reset(task_id)
    checks["reset_removes_deliverables"] = not (env.workspace / "sales_summary.xlsx").exists()
    denied = env.step({"tool": "read_file", "path": "../../evaluation/oracle.json"})
    checks["hidden_answer_access_denied"] = "error" in denied["observation"]
    env.close()

    env.reset(task_id, condition="no_image")
    no_image = run_reference(env)
    checks["no_image_fixture_stops"] = not no_image["success"]
    env.close()
    result = {"passed": all(checks.values()), "checks": checks,
              "note": "这是手工参考执行器和验证器的工程检查，不是教师 Probe 或多模态能力实验。"}
    write_json(env.package / "evaluation" / "probe_report.json", result)
    return result
