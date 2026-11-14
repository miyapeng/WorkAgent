# Controlled World · 单 Seed 可行性实验

这是新增的、显式选择的合成实验路线，**没有替换默认真实检索流程，也没有修改其 ready 准入条件**。本页对照实验中的真实路线未产生 ready Workspace；这里产出的是 `experimental_draft`，不接入旧 Stage 4，不进入训练集。

## 问题和实验范围

同一条官方 Seed `raw_31_0_18983`（Computer Network Architects）：

> Prepare or monitor project schedules, budgets, or cost control systems.

使用同一份已审核 Blueprint，比较两条路线：

- Real evidence：现有 Claude Code + LLMCenter 搜索、下载、清点和覆盖审核。
- Controlled synthesis：GLM-5.2 生成虚构原始项目记录 → Python 约束检查 → 确定性文件渲染 → 固定任务族的指令与数值验证规则 → 独立模型审核。

此次刻意选文本/表格任务，先检查事实、材料和数值验证器能否对齐。没有生成图像、检验多模态必要性，或者设置 70/30 配额。没有引入新的 Agent 框架或修改 Stage 1–2/正式 Stage 4–7。

这是**一个明确设计的项目成本与进度监控任务族**，不是一个已经可以处理 5,745 条职业任务的通用世界生成器。专业语义来自已准入 Blueprint 与模型生成的案例；字段、计算口径、渲染器和验证器由版本化代码规定。运行时没有人工挑值、补文件、写答案或覆盖模型判定。

## 本次实际结果

| 项目 | Real evidence | Controlled synthesis |
|---|---|---|
| 同一 Seed / Blueprint | 是 | 是 |
| 联网搜索请求 | 4 | 0 |
| 下载尝试 / 实际下载解析 | 2 / 1 | 0 / 0 |
| 可用真实 Anchor | 0 | 0，合成路线不要求真实 Anchor |
| Agent 输入文件 | 0 | 5 份，全部明确为 synthetic |
| 必要输入覆盖 | 需检索的 5 项为 0/5 | 5 项材料输入 + 1 项指令输入共 6/6，有文件定位及模型支持判定 |
| 结果 | incomplete | experimental_draft |
| 独立执行 Agent / 训练准入 | 未执行 / 否 | 未执行 / 否 |

覆盖口径不同：合成侧的片段定位和渲染可由程序核验，专业充分性仍来自模型审核；这不是六项事实获得真实世界认证。

真实路线实际下载的是 `https://mercury-training.com/pdfb`，重定向到培训课程目录页，未构成项目预算/进度记录。另一个地址下载返回 404；覆盖审核还出现 `node_coverage_mismatch`。因此失败同时包含**搜索资料不适合与审核输出结构错误**，不能概括成现实世界不存在完整资料。原始字节只在本地下载缓存中，许可未知，不提交 Git。

合成侧实际调用 GLM-5.2 两次（生成、独立审核），累计输入 8,413 tokens、输出 10,784 tokens；确切费用没有供应商账单，保持 null。真实路线核心规划/审核 5 次调用，22,879 输入和 10,226 输出 tokens；Claude Code 搜索的调用另存搜索记录，不能把这组 token 当成整条搜索路线费用。离线重放不增加调用。

完整机器结果：[comparison_report.json](data/world_pilot/comparison_report.json)。单个案例、不同来源约束和不同准入门槛，**不能得出合成路线成功率或真实性更好的研究结论**。

## 实际产物

```text
data/world_pilot/world/
├── task.json                         # 实验任务指令
├── workspace_init/                   # 可见输入，全部虚构
│   ├── context/
│   │   ├── project_brief.md
│   │   └── monitoring_policy.md
│   └── records/
│       ├── baseline.csv
│       ├── actuals.csv
│       └── remaining_estimates.csv
├── evaluation/                       # 私有，不交给执行者
│   ├── numeric_reference.json
│   └── verifier_spec.json
└── construction/                     # 私有，不交给执行者
    ├── hidden_world.json
    ├── source_manifest.json
    ├── file_profiles.json
    ├── information_coverage.json
    ├── engineering_checks.json
    ├── semantic_review.json
    ├── binding.json
    └── construction_report.json
```

例子是一个虚构园区网络改造项目，有 5 个工作包。任务要求分析计划与实际进度、预算偏差、预计总成本、资源缺口，提交一份 `assessment.csv` 和配套 `report.md`。实际任务见 [task.json](data/world_pilot/world/task.json)。

隐藏世界只保存输入事实及明确标注的项目经理估计。Oracle 在私有 evaluation 中用代码计算，输入文件不含这些计算结果或建议。材料、指令与数值检查共享同一公开计算约定；数值用 Decimal、显式 USD/小时、绝对误差 0.01，不执行模型代码。

`cost_variance_to_date_usd` 在本实验中明确约定为“累计实际支出减总批准预算”，不是完整挣值分析中的成本偏差。负值也不意味着项目最终节省。报告必须解释此限制，不能从命名推断其他专业定义。

## 验证结果和发现的问题

- 独立实现的工程参考程序只读可见的三个 CSV，以 ID 关联乱序记录；其数值结果与隐藏世界计算的参考一致。
- 对 5 个工作包的每项数值加 1，并逐行更换币种：30 个错误全部检出；重复 ID、缺行也被拒绝。
- 测试覆盖日期/完成状态矛盾、输入变化、额外隐藏文件、未允许的答案字段、NaN/无穷大、错误单位、误差边界、符号错误和目录导出。
- Stage 3 共 51 项测试、Stage 2 共 21 项测试通过（含新增 10 项合成实验测试）。测试替身与实际 GLM 结果分开。
- 禁止网络和外部进程后，两条路线共 22 个结果文件逐字节重放一致，见 [replay_report.json](data/world_pilot/replay_report.json)。

**工程参考程序不是 Agent Probe。** 它不分析专业建议，也不证明模型能独立解决任务。仅有报告文件、或数值全部正确，语义分仍为 null，没有完整总分或训练准入。

独立模型审核接受了本轮案例，但同时记录了值得研究的问题：

1. 项目简介写“约三分之一”，表格算出的已完成基准工作量为 42.5%；叙述不够一致，且简介不应提前给出需要分析的汇总结论。
2. 审批政策提到预备金和下游依赖，但没有完整余额和依赖网络；相关建议的可验证范围有限。
3. 数据较整齐，成本预测模型简单，不能因此声称具有真实业务复杂度。

这些没有被开发者手工删除、改值或改判，也没有因为模型 accepted 就升级成 ready / verified。它说明**自动语义审核也会把值得阻断的问题当成 limitation**。后续实验应把“叙述中的数值与状态必须绑定结构化事实”“规则不得要求未提供的输入”变成明确的构造约束与准入条件，然后在新版本重跑。不要修改本次记录来美化结果。

## 运行与复现

在仓库根目录，复用现有 `.venv` 和 LLMCenter 凭证；无凭证写进配置或输出。首次运行会消耗模型/搜索额度：

```bash
# 已准入列表第一条就是本实验 Seed；--limit 1 只处理它
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --config workspaces/config/claude_search_pilot.json \
  --output-dir workspaces/data/world_pilot/real \
  --cache-dir workspaces/data/cache_world_real --limit 1

# 受控世界、实际文件、实验任务与数值检查；仅支持配置中绑定的任务族
.venv/bin/python workspaces/scripts/world_pilot.py

# 已有本机模型/搜索/下载缓存时，两条命令分别添加 --offline 可重放
.venv/bin/python workspaces/scripts/world_pilot.py --offline
.venv/bin/python workspaces/scripts/world_pilot.py --compare workspaces/data/world_pilot

# 导出可见文件；目标必须是一个新目录
.venv/bin/python workspaces/scripts/world_pilot.py --export-agent /tmp/world-pilot-worker
# 将交付物写进该目录的 outputs/ 后检查；报告质量仍 pending
.venv/bin/python workspaces/scripts/world_pilot.py --grade-submission /tmp/world-pilot-worker

.venv/bin/python -m unittest discover -s workspaces/tests -v
```

禁止把整个实验目录挂给执行者；只导出 task.json、workspace_init 和空 outputs。该导出不构成 OS 沙箱，本次也没有运行教师 Agent。

代码、配置、Seed 和 Blueprint 通过哈希绑定；更改实现或场景参数需使用新的 `--output-dir`。模型原始响应缓存在 `data/cache_world/`，真实检索缓存为 `data/cache_world_real/`；二者均不提交 Git。新克隆可直接查看已提交的合成文件，重新调用模型不保证逐字一致，离线重放需要保存的缓存。

默认 real-only 路线继续使用 `construct_workspace.py`。本实验的 `world_pilot.py` 只复用上游准入、LLM 缓存、文件解析和哈希代码，不将合成文件塞进原来的真实 Anchor 准入规则。Task/Verifier 暂为一个显式任务族的确定性模板，后续是否推广、如何连接正式 Stage 4，需要在更严格的事实约束和独立执行验证后决定。
