"""手工参考执行器，仅用于验收框架，不能作为模型能力或 SFT 示范。"""

import re


# 人工从默认看板抄录；不是视觉推理，不读取 oracle。
# 修改 examples/W001.json 后，需要重新查看看板并更新此处。
MANUALLY_TRANSCRIBED_RATES = {"A": 0.084, "B": 0.051, "C": 0.062, "D": 0.075}


def run_reference(env):
    def act(tool, **kwargs):
        observation = env.step({"tool": tool, **kwargs})["observation"]
        if "error" in observation:
            raise ValueError(observation["error"])
        return observation

    requirements = act("read_file", path="report_requirements.md")["text"]
    threshold = float(re.search(r"至少 (\d+)%", requirements)[1]) / 100
    orders = act("read_file", path="orders.xlsx")["rows"]
    history = act("read_file", path="previous_report.pdf")["text"]
    image = env.step({"tool": "view_image", "path": "dashboard.png"})["observation"]
    if "error" in image:
        # 缺图时停止；不让手工抄录值绕过缺图条件。
        act("finish")
        return env.grade()
    previous = {region: (float(revenue), float(rate)) for region, revenue, rate in
                re.findall(r"([A-D]) revenue=([\d.]+) conversion=([\d.]+)", history)}
    rows = []
    for region, (old_revenue, old_rate) in sorted(previous.items()):
        revenue = sum(order["amount"] for order in orders if order["region"] == region)
        rate = MANUALLY_TRANSCRIBED_RATES[region]
        delta = rate - old_rate
        rows.append(dict(region=region, revenue=revenue, revenue_change=revenue / old_revenue - 1,
                         conversion=rate, conversion_change=delta,
                         anomaly=revenue < old_revenue and delta <= -threshold + 1e-9))
    act("write_summary", rows=rows)
    act("write_report", rows=rows, narrative=(
        "Region B shows declining revenue alongside a lower conversion rate. "
        "This is an association, not an established causal explanation. "
        "Review traffic sources, funnel stages and order mix before deciding on interventions."))
    act("finish")
    return env.grade()
