# Stage 5 · Independent Execution Probe (minimal pilot)

Stage 4 的 `draft` 只说明任务包构造完成。Stage 5 让 Solver 实际完成公开任务，再检查真实产物；不能把工程测试或文件存在当作任务已验证。

当前实现：

```text
Frozen Draft Package
  → public-only export → isolated Python tool + Claude Code/GLM Solver
  → actual Markdown submission + tool trace
  → existing programmatic checks
  → independent source statistics + blind claim extraction + semantic Judge
  → controlled mutations of the actual submission
  → diagnostic report (no automatic training admission)
```

## 边界和运行环境

- Solver 只收到公开任务，读取 `task.json` 和 `workspace_init/`，写入 `outputs/`、`scratch/`。原任务只要求 Markdown 报告，没有增加 `metrics.json` 隐藏交付要求。
- Claude Code 禁用内置工具，只连接一个 `mcp__workprobe__python` 工具；工具子进程使用独立 chroot、UID/GID 65534、只读输入、seccomp、CPU/内存/文件限制。没有宿主仓库、凭证、evaluation、construction、网络或子进程权限。
- CLI 通过宿主凭证调用模型，凭证不进入执行子进程。临时 HOME/配置目录、空 setting sources、禁用 hooks、strict MCP、固定工具白名单；不使用会同时禁掉 MCP 的 `--safe-mode`。
- 需要 Linux x86_64、root 的 chroot/setuid 能力和 libseccomp；没有隔离能力时直接失败，不退回宿主任意执行。依赖现有 Python、openpyxl、pypdf 和 Claude Code。不引入容器或训练框架。
- 这是共享宿主内核上的受限执行环境，不是 VM，也不是面向敌对攻击的安全认证。权限/网络/子进程限制经过实际负向测试。
- 正式输入保持不变；现有包仍是 `draft`。单次 Solver/Judge 成功不自动改为 verified。没有执行 Teacher 数据集采集或 SFT/RL。

## 最小实现

| 文件 | 用途 |
|---|---|
| `scripts/run_probe.py` | 校验冻结包、导出公开输入、调用 Solver、保存实际日志和提交物 |
| `scripts/probe_sandbox.py` | 受限 Python 执行与单工具 MCP 服务 |
| `scripts/probe_reference.py` | 显式 STATS19 2024 适配器：从原始 CSV 独立计算统计，禁止读取 Solver 数值作为参考 |
| `scripts/probe_evaluate.py` | 原验证器检查、独立语义审核、数值比较、错误报告测试 |
| `config/probe.json` | Solver/Judge 模型接口和时间预算；没有固定 Agent 轮数 |
| `config/probe_judge.schema.json` / `probe_claims.schema.json` | Judge 的输出 Schema |
| `prompts/probe_solver.v1.txt` / `probe_judge.v4.txt` / `probe_claims.v1.txt` | 独立版本化执行与评分 Prompt |
| `tests/test_probe.py` | 明确标记的小型测试夹具与真实隔离能力测试 |

执行框架可复用，但当前独立参考计算只实现 STATS19，不能宣称已经自动构造任意职业的 Oracle。Judge 引用/Schema 错误最多再请求一次结构修正，不修改报告或评分标准；原始失败响应保留。语义评分可能不确定；没有足够依据时必须保留 unassessable。

数值检查分两步：Python 先为报告中的数字分配稳定 ID；一个独立的声明抽取调用只看到报告和指标定义，看不到参考数值。它选择数字 ID 与统计口径，Python 恢复原文、位置并比较独立重算值。语义 Judge 的评分单独保留。**口径匹配仍依赖模型判断**，因此报告标为 `assisted_numeric_checks`，不能把整个步骤称为纯确定性验证。数值不一致是待核对项，可能来自报告错误，也可能来自抽取模型匹配错口径；不能把不一致条数直接当成事实错误数。

## 运行

在仓库根目录：

```bash
.venv/bin/python work-tasks/scripts/run_probe.py \
  --package work-tasks/generated/TASK_1d5ee1c33b451d320937aaa8 \
  --output-dir work-tasks/data/probes/stats19_v4 \
  --stage all
```

也可分别运行 `--stage solve` 和 `--stage evaluate`。已完成 Solver 的目录按公开任务、包清单、模型配置、Prompt 和隔离版本复用；输入或配置变化使用新目录。中断的未完成 Solver 不自动续写已有输出，以免混淆两次执行；已有完整执行的评估可断点复用模型缓存。

```bash
# 固定实际提交物和模型缓存后，离线重放评分，不再调用 Solver/Judge API
.venv/bin/python work-tasks/scripts/run_probe.py \
  --package work-tasks/generated/TASK_1d5ee1c33b451d320937aaa8 \
  --output-dir work-tasks/data/probes/stats19_v4 --stage all --offline

.venv/bin/python -m unittest discover -s work-tasks/tests -v
```

私有结果（Git 忽略）：

```text
work-tasks/data/probes/<run>/
  execution.json                  # 实际调用、耗时、模型、token、文件哈希
  isolation_preflight.json         # 隔离负向检查
  stdout.jsonl / tool_trace.jsonl  # 真实执行日志，不作为训练准入数据
  submission/outputs/*.md          # Solver 实际交付物
  evaluation/
    reference.json                # 构造端独立统计，不给 Solver
    programmatic.json
    submission_assessment.json
    mutations/*.md                # 从实际产物修改的错误版本
    model_cache/                  # Judge 响应和失败重放依据
  probe_report.json                # 阶段结果和限制
```

原始附件沿用上游再分发限制，不因运行 Probe 而自动允许公开发布。CLI 金额只是客户端估计，网关实际账单未知。

## 结果解释

- 正常提交物也可能失败；它是待评估结果，不是人工指定的金标准。
- 错误测试包括记录数替换、删除分析章节、错误解释调整概率、添加无依据的绝对结论。无法从实际报告构造的变异不会伪造为成功测试。
- 如果正常报告本来没有通过，错误版本的检出只是诊断，不能据此宣称已估计 Verifier 的误报率/漏报率。删除章节的检测要求分数下降，不把原报告已存在的错误重复计为新检出。
- 同模型的独立 Judge 不是专家认证。程序化分数、语义分数和模型辅助数值比较分开保存。
- 该任务没有已证实的视觉依赖，本次不执行多模态消融。
- 过程类要求继续需要可靠执行证据；结束时输入哈希相同本身不能证明全过程没有修改。当前输入不可写由 OS 权限强制执行。

## 实际 Pilot：2026-11-13

任务：`TASK_1d5ee1c33b451d320937aaa8`，对 DfT STATS19 2024 碰撞、车辆和伤亡数据进行数据适用性评估。沿用 Stage 4 固定任务和六份原始文件（HTML 0），未修改公开要求、输入文件或 Solver 报告。

| 项目 | 实际结果 |
|---|---|
| Solver | Claude Code + GLM_ka48dn（现有 GLM-5.2 接口） |
| 执行耗时 | 348.29 秒 |
| 实际工具调用 | 38 次，6 次错误后继续执行 |
| 交付物 | 一份 38,829 字节 Markdown 报告 |
| 工具边界与输入完整性 | 通过；只暴露并使用 `mcp__workprobe__python` |
| 文件存在/可解析检查 | 通过；只说明文件交付成功 |
| 语义 Judge 分数 | 1.0，但存在漏检，不能解释为事实全部正确 |
| 独立数值声明检查 | 66 项比较，15 项不一致待核对（含重复声明与口径匹配错误） |
| 错误版本测试 | 4 类中检出 3 类；删除分析章节漏检 |
| 最终状态 | `needs_review`；`training_admitted=false` |
| 工程测试 | 68 项通过，包含 19 项新增测试 |
| 离线重放 | 禁止网络和子进程后仍成功，报告字节一致 |

可直接查看本地实际交付物：

`work-tasks/data/probes/stats19_v4/submission/outputs/stats19_2024_data_fitness_report.md`

可提交的精简统计：[data/stage5_pilot/pilot_report.json](data/stage5_pilot/pilot_report.json)。原始附件、完整执行日志、模型缓存和评估资料保留在 Git 忽略的 `data/probes/` 中。

本次暴露了两个不同的问题：

1. **Solver 的事实错误。** 报告第 161、162、239、375 行将致死记录的调整字段描述为空；实际 1,502 条致死碰撞和 1,602 条致死伤亡记录的两个字段均为 `0`，为空的记录数是 0。文档说“致死记录不应用调整”不等于 CSV 中编码为空。这个矛盾已被不提供参考值的声明抽取 + Python 重算自动标记。
2. **Verifier 尚不可靠。** 语义 Judge 对原报告及变异报告仍给出高分，部分问题只出现在 issues 中；删除章节没有带来分数下降。声明抽取也将“所有 100,927 条记录属于 2024 年”错误映射到“年份错误记录数”，造成误报。因此 15 项不一致不能称为 15 个确认的事实错误。

错误测试明细：改错碰撞总数可检出；把概率解释为整数计数可检出；附加无依据的绝对准确性结论可检出；删去最长含数字的分析章节未检出。由于原报告未通过独立一致性检查，这些是诊断结果，不是已经建立可靠正对照的 Verifier 准确率。

Solver 的 CLI 费用估计为约 $7.29，但它不是 LLMCenter 账单；评估调用保留 token 用量，实际账单未知。开发期间被 Schema 拒绝及中断的尝试仍保留在私有目录/缓存，不计入有效评分。

当前完成的是可复现的 Stage 5 实验闭环，尚未完成可靠准入。下一步应先提高“报告声明—统计口径”的匹配和遗漏项判定，再验证错误检出与误报，不能凭单模型满分批量放行任务。
