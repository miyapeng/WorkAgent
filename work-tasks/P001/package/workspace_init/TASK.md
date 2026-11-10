# P001 · 采购供应商比选（合成业务案例）

你是采购专员。为一家虚构企业采购 10,000 个规格相同的包装箱，比较 A、B、C 三家供应商，提交采购建议。

quotes.csv 是同一批次、同规格报价；purchase_policy.json 是本次采购的完整政策。supplier_performance.png 是同口径历史绩效。所有企业、报价和绩效均为教学合成数据，不是实际交易建议。

总成本 = 数量 × 含税单价 + 一次性运费 + 一次性开版费，不扣减不良品、不另加税。必须同时满足：产能足够、交期不超过政策上限、历史准时交付率不低于下限、不良率不高于上限。历史绩效仅作为本次筛选依据，不保证未来表现。通过全部约束后按总成本选择，平局按 ID 字母顺序。没有合格供应商时推荐 null。

请在 outputs/ 提交：

1. comparison.csv：每家供应商一行，字段 supplier_id,total_cost_cny,on_time_pct,defect_pct,eligible。金额保留两位小数；百分数填 99 而非 0.99；eligible 填 true 或 false。
2. decision.json：recommended_supplier（ID 或 null）；evidence 字典，键为 quotes、policy、performance，值分别为对应输入文件名。
3. recommendation.md：中文建议，说明推荐对象、三家总成本、各项资格判断、不选其他供应商的原因、图片中的历史指标、引用文件与对应行/区域，以及历史数据局限。

不得修改输入文件，不得编造缺失值。如果关键材料缺失或无法辨读，应报告阻塞而非猜测。
