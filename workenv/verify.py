"""评测端：读取实际交付物；评分细节不返回给尚在执行的策略。"""

import hashlib
import math

from pypdf import PdfReader

from .artifacts import FIELDS, read_xlsx, report_line
from .build import read_json


def source_hashes(workspace, names):
    result = {}
    for name in names:
        path = workspace / name
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
    return result


def verify(package, workspace, baseline, violated=False):
    oracle = read_json(package / "evaluation" / "oracle.json")
    rubric = read_json(package / "evaluation" / "rubric.json")
    checks = {}
    errors = []
    try:
        rows = read_xlsx(workspace / "sales_summary.xlsx")
        by_region = {row["region"]: row for row in rows}
        checks["outcome.regions"] = (len(rows) == len(oracle) == len(by_region)
                                      and set(by_region) == {r["region"] for r in oracle})
        for expected in oracle:
            actual = by_region.get(expected["region"], {})
            for field in FIELDS[1:]:
                value = actual.get(field)
                if field == "anomaly":
                    ok = type(value) is bool and value == expected[field]
                else:
                    ok = (type(value) in (int, float) and math.isfinite(value)
                          and abs(value - expected[field]) <= (0.01 if field == "revenue" else 1e-6))
                checks[f"outcome.{expected['region']}.{field}"] = ok
    except Exception as exc:
        checks["outcome.readable"] = False
        errors.append(f"Excel: {type(exc).__name__}: {exc}")
    try:
        pdf = PdfReader(workspace / "quarterly_brief.pdf")
        checks["artifact.two_pages"] = len(pdf.pages) == 2
        page1 = pdf.pages[0].extract_text() or ""
        checks["artifact.metrics"] = all(report_line(row) in page1 for row in oracle)
        checks["artifact.chart_present"] = len(pdf.pages) >= 2 and len(pdf.pages[1].images) > 0
        narrative = "\n".join(line for line in page1.splitlines()
                              if "| revenue=" not in line and line.strip() != "Quarterly sales brief")
        checks["artifact.analysis_present"] = len(narrative.strip()) >= 80
    except Exception as exc:
        checks["artifact.readable"] = False
        errors.append(f"PDF: {type(exc).__name__}: {exc}")
    checks["process.source_integrity"] = not violated and source_hashes(workspace, baseline) == baseline
    scores = {}
    for group in ("outcome", "artifact", "process"):
        values = [value for key, value in checks.items() if key.startswith(group + ".")]
        scores[group] = sum(values) / len(values)
    gate = not checks["process.source_integrity"]
    reward = 0.0 if gate else sum(scores[key] * weight for key, weight in rubric["weights"].items())
    return {"success": all(checks.values()), "reward": round(reward, 6),
            "scores": scores, "hard_gate_triggered": gate, "checks": checks, "errors": errors}
