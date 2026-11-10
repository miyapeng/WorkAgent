# P001：从一条职业种子到一个采购任务

这是 Phase 1 之后的**单任务开发样例**。只生成一个任务，供逐环节检查。原始目录、digital 筛选和中文网页保持独立；没有扩增数据集或启动 SFT/RL。

先读 [任务说明](package/workspace_init/TASK.md)，再看 [本次参考交付物](runs/reference/outputs/recommendation.md)。

## 为什么选它

O*NET 31.0 的 Task **1144**，职业 **13-1023.00 Purchasing Agents, Except Wholesale, Retail, and Farm Products**：

> Research and evaluate suppliers, based on price, quality, selection, service, support, availability, reliability, production and distribution capabilities, and the supplier's reputation and history.

本次具体化其中的价格、质量、交期和产能，不声称覆盖整个职责。原始英文、官方 DWA 关联、AI4Work 筛选记录、源表 SHA-256 在 [seed.json](package/seed.json)。O*NET 数据归属 USDOL/ETA，CC BY 4.0；详见 [Phase 1 来源许可](../../work-seeds/README.md)。

## 这一版怎样借鉴两篇论文

| 来源 | 借鉴的环节 | 当前实际实现与差异 |
|---|---|---|
| [GraphForge §3.2–3.4](https://arxiv.org/html/2609.38923v3#S3.SS2) | 从文件证据建立关系，将验收项绑定证据 | JSON 图记录文件、CSV 行和图片区域，rubric 引用节点；本例用合成文件，没有复现它的真实文件检索和模型图构建 |
| [WorkFactory §3.3–3.4](https://arxiv.org/html/2610.37161v1#S3.SS3) | 从交付物反推信息需求，实际执行查缺项 | intent 记录必要输入，计算及决定留给执行者；运行参考程序并注入缺图、缺运费等故障，没有实现自动 Agent 修复循环 |

职业种子是真实官方数据；采购企业、需求、报价、政策、历史绩效均为**明确标注的合成案例**。不存在真实供应商或外部商业来源。图与任务是人工/助手设计后对齐的，不是已经实现自动图编译器。

```mermaid
flowchart LR
    A[官方 Task 1144] --> B[明确工作意图]
    B --> C[准备报价、政策、绩效图片]
    C --> D[证据依赖图与验收项]
    D --> E[独立运行目录]
    E --> F[参考执行与故障探测]
    F --> G[数字检查 + 待人工审核]
```

## 文件对应哪些小环节

| 环节 | 文件 |
|---|---|
| 选种子、确定意图与所需信息 | `package/seed.json`、`package/intent.json` |
| 给执行者的完整材料 | `package/workspace_init/`：中文任务、报价 CSV、政策 JSON、绩效 PNG |
| 证据关系与验收规则 | `package/evaluation/evidence_graph.json`、`rubric.json` |
| 仅评分端使用的独立数值答案 | `package/evaluation/oracle.json` |
| 实际看图后的显式转录 | `review/visual_observation.json`，含图片哈希；不是默认任务输入 |
| 一次参考执行及评分结果 | `runs/reference/outputs/`、`runs/reference/grade.json` |
| 故障探测与限制记录 | `review/probe_report.json` |

只将 `workspace_init/` 内容交给未来的执行 Agent；不能把本项目整个目录给它。当前是目录分离，不是 OS 沙箱。验证器仅检查输入最终哈希，不能判断文件是否曾修改后恢复。

## 多模态依赖与验收边界

准时交付率和不良率只在可见 PNG 像素中，报价和政策中没有这些数值；没有图片就无法判断资格。图表是程序绘制的简单带数值图，不是自然场景视觉基准；OCR 也可读取它，不代表复杂视觉推理。

本次执行由助手查看 PNG 后明确转录，再由参考程序计算；未运行独立教师模型，未采集可供 SFT 的模型轨迹。转录与图片 SHA-256 绑定，防止修改图后误用旧值。

自动检查覆盖金额、六个图片指标、资格、推荐 ID、源文件引用名、文件存在性与输入最终完整性。建议书的事实一致性、解释质量和引用支撑关系仍需人工审核，文件存在检查不能替代这些判断。即使所有自动检查通过，`training_admitted` 仍为 false。

## 复现

在仓库根目录执行。构建图片使用项目已有 Pillow==13.0.0；执行和评分仅需 Python 标准库。

```bash
.venv/bin/python work-tasks/P001/build.py
python work-tasks/P001/run.py reset --run /tmp/p001-review-01
python work-tasks/P001/reference.py --run /tmp/p001-review-01 --observations work-tasks/P001/review/visual_observation.json
python work-tasks/P001/run.py verify --run /tmp/p001-review-01
.venv/bin/python -m unittest discover -s work-tasks/P001 -p 'test_*.py' -v
# 运行同一组测试并保存可审阅的 probe_report.json
.venv/bin/python work-tasks/P001/probe.py
```

reset 拒绝覆盖现有运行目录；重复运行请换一个目录。build 重建这个固定案例，输入不变时输出一致；改变设计后，必须重新看图、转录、审核 oracle，再运行测试，不能沿用旧结论。

下一次最适合讨论 [TASK.md](package/workspace_init/TASK.md)：委托是否符合专业工作、材料是否充分、交付要求是否合理。先把这三个问题审清楚，再设计第二个实例。
