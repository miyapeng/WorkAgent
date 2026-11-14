# Stage 4 · Evidence-Anchored Task & Verifier Co-generation

当前新版入口和两层 Graph 的方法边界见 [ASSET_PIPELINE.md](../ASSET_PIPELINE.md)，本轮批次见 [实际报告](../workspaces/data/asset_pilot_v4/report.md)。以下保留原接口与历史实验说明；标为“本轮”的旧统计属于当时记录，不与新批次合并。

Stage 4 把**已经 ready 的 Stage 3 Workspace**编译成 `Draft Work Task Package`。本模块与早期人工开发样例 `P001/` 独立，不读取其参考答案、图、Rubric 或执行记录。

正式采用 **Phase I · Grounded Work Task Construction = Stage 1–4**。第一里程碑是有输入文件、用户指令、证据锚点及初步验收条件的 Draft Package；不是完成一次下载，也不是证明任务已可解。

| Phase | Stage | 产物 |
|---|---|---|
| I · Grounded Work Task Construction | 1 Seed → 2 Information Plan → 3 Workspace → 4 Task & Verifier | Draft Work Task Packages |
| II · Task Verification & Admission | 5，尚未实现 | 经独立执行验证的任务 |
| III · Agent Training Data & Evaluation | 6–7，尚未实现 | 教师轨迹、训练数据及 Benchmark |

## 自动运行的边界

```text
读取已准入 Plan / Stage 3 记录
  → 程序入口校验（失败：blocked_upstream）
  → 从实际位置提取 Evidence Graph
  → 配置的 LLM 联合生成 Task + Rubric
  → Schema、引用、路径、公式和对应关系检查
  → 另一次 LLM 调用逐要求/逐 Rubric 反向审核
  → 自动接受为 draft 或拒绝为 rejected
```

运行时没有开发者挑文件、抄数字、补引文、写答案、选择通过或手工改任务的步骤。程序处理精确事实和边界；模型处理语义设计与审核。**模型判断仍是判断，不等于专家认证**，同一模型的独立调用也不等于独立来源。结构或语义审核不通过就是拒绝，不自动修复、降级 Intent 或增加解释制造成功。仅 JSON 语法错误允许最多一次格式重生成，仍使用相同证据与要求，并保存原始无效响应；新响应必须重新经过全部校验。

当前默认接口已迁移到 `raw-blueprint-v2` / `grounded-workspace-v2`：输入为官方 Raw Seed、Python 编译并审核的 Blueprint，以及真实 Search Agent 获取的 Workspace。Stage 4 不再把历史 LLM `work_demand` 当作官方种子。`--seed-file` 接受 JSONL 文件，替代旧 `--seed-dir`。

v2 不使用旧版 `stage4_eligible` 布尔字段；入口根据 `ready`、已审核 Blueprint/Seed 哈希、实际文件字节、片段 ID、信息覆盖及案例一致性重新计算准入。旧接口和 incomplete/rejected 输入均阻断，不迁移为 ready。

`task_instruction` 是待具体化的用户委托要求，不需要伪造来源文件。Evidence Graph 用 `instruction_requirement` 单独表示，最终 Task 必须明确满足；它不能作为 `source_fact` 或数值 Oracle。真实文件中的事实仍经独立重解析验证。

新实验命令（沿用本机 llmctl 凭证；不在参数中传 Key）：

```bash
.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --plan-dir work-plans/data/native_file_pilot \
  --seed-file work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl \
  --config work-tasks/config/native_file_pilot.json \
  --workspace-dir workspaces/data/native_file_pilot_retry \
  --report-dir work-tasks/data/native_file_pilot_admission
# 相同输入、代码和缓存：追加 --offline。阶段可用 --stage eligibility/evidence/all。
```

以下两个 WS001/WS002 的报告是历史实验；新实验单独保存，不覆盖它们。

[历史可视化任务](VISUALIZATION_PILOT.md) 含 HTML，已停止准入。当前入口与 Agent 导出均拒绝原始 HTML（包含改名后仍被内容解析识别的 HTML），不会把历史 draft 状态当作新政策下的准入证明。

新的 [原生文件实验](NATIVE_FILE_PILOT.md) 使用不同 Raw Seed，记录完整下载、解析、构造与拒绝历史。大 CSV 原件保持完整；构造模型上下文使用明示的记录摘录、字典引用行上下文和已定位证据，不能把摘录当作全表质量结论。

## 历史真实输入阻断结果

正式入口已读取现有两个 Workspace：

| Workspace | Stage 3 | Stage 4 | 主要阻断原因 |
|---|---|---|---|
| WS001：预算分析 | incomplete | blocked_upstream | i1/i2 部分覆盖，i3/i5/i7 缺失，口径及适用关系未核实 |
| WS002：软件项目监控 | rejected | blocked_upstream | Stage 3 引文定位审核失败，未准入可见材料，i1–i4 无已验证覆盖 |

**正式 Draft Package：0；真实输入上的模型生成调用：0。** 没有通过 Stage 2 直接生成任务，没有修改上游记录，没有将两个目录升级为 ready。完整机器报告见 [stage4_report.json](data/stage4_pilot/stage4_report.json)。Phase I 的构造代码已延伸到 Stage 4，但真实可交付任务的里程碑仍被 Stage 3 阻断。

独立的 `synthetic_test_fixture` 使用三份完全虚构的 CSV/JSON 文件，包含两类预算、实际支出和案例规则：

- **模拟接口测试**：完整经过入口、实际解析、9 个 source facts、2 个派生/判断要求、联合任务/Rubric、审核结构、打包和可见目录导出；产生一个工程用 draft。生成与审核响应是明确标记的测试替身，不是模型生成质量证据。
- **真实 GLM 接口测试**：同一虚构输入调用了两次 `glm-5.2`。生成 6 条任务要求、10 条 Rubric，结构检查通过；独立语义审核拒绝了重复计分和过程约束验证不充分等问题。未生成包，未人工改判。审核中关于逐类别评分是否重复的判断也可能误判，应视为模型意见；没有用开发者意见覆盖结果。
- 两种测试均不计入真实任务、训练数据或职业覆盖统计。夹具和其模型缓存只用于本地工程验证，正式 CLI 没有“跳过入口”的开关。

验证结果：Stage 4 的 **28 个测试**、Stage 3 的 **26 个回归测试**通过；禁用网络和 DNS 后，真实阻断报告的 4 个文件、模拟接口夹具的 27 个文件、实际 GLM 夹具的 16 个文件均逐字节重放一致。Stage 1–3 的 46 个已跟踪数据文件未变。详见 [验证报告](data/stage4_validation/validation_report.json)、[模拟接口测试记录](data/stage4_validation/synthetic_test_fixture_report.json)和[实际模型测试记录](data/stage4_validation/synthetic_test_fixture_live_report.json)。

## 文件职责

| 文件 | 用途 |
|---|---|
| `scripts/construct_tasks.py` | 分阶段 CLI、复用 LLM 原始响应缓存、独立审核、原子打包和 Agent 可见目录导出 |
| `scripts/task_evidence.py` | Stage 1/2/3 关联校验、实际字节重新解析、证据图确定性提取 |
| `scripts/task_validation.py` | Task–Evidence–Rubric 引用关系、正反向覆盖、公式及审核完整性检查 |
| `scripts/task_verifier.py` | 有限声明式检查、独立读取源操作数、分类型评分、语义 Judge 规范 |
| `scripts/task_prompts.py` | 联合生成与独立反向审核的版本化 Prompt |
| `config/*.schema.json` | Task、Evidence Graph、Rubric、检查 DSL、联合响应、审核及 Verifier Schema |
| `config/stage4.json` | Stage 1 LLM 配置引用、超时、重试与上下文上限；不存凭证 |
| `tests/fixture_support.py` | 明确虚构的数据与模拟响应，仅用于测试 |
| `tests/test_stage4.py` | 完整成功链及负向测试 |
| `scripts/run_synthetic_fixture.py` | 隔离的工程演示入口，可选择模拟响应或实际模型接口 |

依赖沿用 Stage 1–3 的 `jsonschema`、文件解析库及标准库；没有新增 Agent 框架。安装现有依赖：

```bash
.venv/bin/python -m pip install -r workspaces/requirements.txt
```

## 运行与断点复现

在仓库根目录重放已缓存的真实实验（尚无缓存时会记录缺失）：

```bash
.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --config work-tasks/config/native_file_pilot.json \
  --plan-dir work-plans/data/native_file_pilot \
  --workspace-dir workspaces/data/native_file_pilot_retry \
  --report-dir work-tasks/data/native_file_pilot_admission --offline
```

对另一组已准入 Blueprint 和 Workspace：

```bash
# accessKey 由 WORK_SEEDS_API_KEY 或隐藏输入提供
.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --plan-dir work-plans/data/new_pilot \
  --seed-file work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl \
  --workspace-dir workspaces/data/new_pilot \
  --report-dir work-tasks/data/new_stage4 \
  --output-dir work-tasks/generated --limit 2 --prompt-api-key
```

可通过 `--plan-dir`、`--seed-file`、`--config` 和 `--cache-dir` 替换输入及配置。`--stage eligibility|evidence|generate|audit|assemble|all` 按阶段停止；后续阶段仍重做入口校验，已执行的模型调用从缓存恢复，不跳过前置条件。只有组装成功才标记 draft。没有必要的模型缓存时，`--offline` 记录失败，不偷偷访问网络。

输出报告目录绑定代码、Schema、配置和上游哈希；输入或实现变化时使用新目录。相同代码、输入及缓存下可以重复运行；已存在包若字节不一致则拒绝覆盖。`data/stage4_cache/` 保存原始模型响应、请求失败、证据图、中间方案和审核；缓存与文件一起归档才能跨机器重放。

```bash
# 测试数据与模拟接口：无网络，无模型费用
.venv/bin/python work-tasks/scripts/run_synthetic_fixture.py

# 实际接口，仅对完全虚构的工程夹具；仍不计入真实 Pilot
.venv/bin/python work-tasks/scripts/run_synthetic_fixture.py \
  --root work-tasks/data/synthetic_test_fixture_live \
  --live-model --prompt-api-key

# 已有本机真实模型响应时离线重放
.venv/bin/python work-tasks/scripts/run_synthetic_fixture.py \
  --root work-tasks/data/synthetic_test_fixture_live --live-model --offline

.venv/bin/python -m unittest discover -s work-tasks/tests -v
```

## 上游与证据校验

正式入口复用 Stage 3 的 `load_inputs`，将 Stage 2 Plan 绑定到其已准入检查点；再核对 Stage 3 的原始输入哈希、seed_id、Plan Hash、工作目标哈希和可见文件清单。所有必需 external_input 必须 supported，不能有未解决假设、口径冲突、位置错误、被排除的证据文件或不合格来源。

对候选 ready 输入，除 Stage 3 独立检查外，再从 Workspace 字节调用已有解析器；旧 Profile 中的片段不能覆盖实际文件内容。来源、覆盖及案例引用都必须在新解析位置找到。路径不能越界或使用软链接。当前 v2 正式入口只接受 `real_original`；受控适配/合成接入尚未实现。

Evidence ID 由来源文件、实际位置、引文和 Information Node 派生。`source_fact.description` 直接取已经定位的原文，不让模型改写事实。派生及判断节点只复用 Stage 2 的计算/决策要求，不计算答案。`supports` 连到 Stage 2 的 `information:<id>` 外部引用；`requires` 表示一个派生/判断要求依赖哪些事实或前置要求，不复制全部抽象信息图和职业字段。

本版保守使用可重新解析的文字/表格位置。图表交付支持 PNG/JPG/SVG 等格式，文件检查仅验证格式和可读性，视觉表达正确性由具体语义评分要求评估。扫描件、图像或尚需视觉检查的文件不会因已有格式或未验证描述而变成 source_fact；当前会阻断这些输入。完整图像事实接入仍需把 Stage 3 的实际视觉检查记录与像素/区域绑定，并在 Stage 4 校验。没有声称本轮已生产多模态任务或证明多模态必要性。

## Task、Rubric 与验证器

同一模型调用联合生成 `task`、私有 `grounding` 和语义 `rubric`。当前配置启用 `compile_artifact_checks`：模型使用短证据句柄，Python 恢复原始证据 ID；任务要求全文由程序纳入对应满分条件，避免模型重复书写时漏掉义务；文件存在/格式可读检查由交付物声明编译，权重为1，与内容评分分开。缺失的文件扩展名按模型已选择的格式补齐并同步路径引用，已有但冲突的扩展名仍报错。原始模型方案另存，不手改专业要求或来源事实。Task 有自然语言委托、交付物和逐项要求；路径位于 `outputs/`。私有 grounding 关联要求与已有 Evidence ID。检查所有派生/判断工作都被保留，每项要求有评分或明确的不评分原因，每条 Rubric 必须指向 Task 中的要求和实际 source_fact。

重复 ID、完全重复的 Rubric/检查规格、无依据单位、未知列、无效路径和不支持的运算会由程序拒绝。语义近重复、任务是否偏题、真实专业含义和复杂度由独立模型审核；这类错误无法仅靠 ID 检查证明不存在。

| 验证类别 | 支持与边界 |
|---|---|
| Programmatic | 文件存在及声明类型可解析；CSV 列；JSON Pointer 字段；CSV/JSON/XLSX 数值目标；最终输入哈希 |
| 数值公式 | 仅 add / sum / subtract / divide；操作数必须从被引用的源 CSV 行、JSON Pointer 或 XLSX 单元格读取，不接受模型填写 expected answer |
| 数值处理 | Decimal、显式绝对/相对误差、单位字段、空值/NaN 拒绝；允许明确的千分位与括号负数，不猜测单位换算或含糊地区格式 |
| Semantic | 原子化满分条件、常见错误、无支持/矛盾的扣分政策，以及通用 Judge Prompt；当前不对真实 Agent 成果执行模型评分 |
| Process | `requires_execution_trace` 保持 pending；当前没有可信过程日志解释器，不接受首尾哈希作为全过程证明 |

不会执行 LLM 生成的 Python、表达式、下载源码或工作簿公式。XLSX 数值检查要求实际数值单元格，遇到公式返回未支持，不读取未经核实的公式缓存值。

权重为正数，各类型分别按 `Σ(weight × score) / Σ(weight)` 计算。未执行的 semantic/process 分数为 null；存在未评分项时没有总分。关键项失败触发 failed Gate，关键项待检查触发 pending。即使程序化分数满分，也不改变 draft 状态，更不代表 Verified Task。

独立审核覆盖九个维度，并强制**逐 Rubric 反查 Task 与 Evidence，逐 Requirement 正向检查可完成性**。拒绝未知证据、遗漏审核项或映射错误；任意审核项失败都会停止打包。同一模型可能误判，Phase II 仍需执行测试。

## 包结构与 Agent 可见边界

```text
TASK_<deterministic_hash>/
├── task.json
├── manifest.json
├── workspace_init/              # 与 Stage 3 文件字节一致
├── evaluation/
│   ├── evidence_graph.json
│   ├── rubric.json
│   └── verifier_spec.json
└── construction/
    └── audit_report.json
```

Manifest 保存上游版本、来源许可、文件哈希、provenance 和 draft 状态。模型生成时间/参数/Prompt 版本留在构造报告。无完整答案或 Oracle 文件；数值参考值仅在评分时由程序从源事实计算。

不要把整个包或仓库交给执行 Agent。可见导出只复制 `task.json` 和 `workspace_init/`，另建空 `outputs/`：

```bash
.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --export-agent /path/to/TASK_hash --destination /tmp/agent-visible

# 仅执行确定性成果检查；其余分数保持 pending
.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --grade-package /path/to/TASK_hash --submission-dir /tmp/agent-visible
```

这里只导出目录，没有建立执行沙箱、运行教师 Agent 或执行 Probe。Stage 5 必须把导出目录作为实际可访问边界，私有 evaluation/construction 留在执行环境外。

`generated/`、模型缓存和夹具运行目录默认不进 Git。真实文件沿用 Stage 3 权利状态，未知再分发权利仍为 false。测试夹具也明确不作为正式公开任务数据。

## 参考方法与本项目设计

- [GraphForge §3.3](https://arxiv.org/html/2609.38923v3#S3.SS3)：把文件事实和依赖表示为可回溯的图，并据此编译任务、交付物和带证据锚点的评分项。本文明确图本身不是 ground truth。本项目采用简化图、确定性引文提取和声明式验证，不复现其执行后修订、完整负向惩罚与训练流程。
- [WorkForge §2.3](https://arxiv.org/html/2610.04906#S2.SS3)：基于具体 Workspace 事实设计任务，分开记录程序化和语义验证。论文还生成隐藏 solution plan；本阶段没有生成完整解答，只定义需要执行者完成的推导和判断。
- [WorkFactory §3.3–3.4](https://arxiv.org/html/2610.37161#S3.SS3)：通过信息依赖支持工作目标，并在修复时维护原始意图。本项目固定已准入 Plan，以引用关系和独立审核约束任务，不实现其 Probe/Repair。

入口契约、JSON Schema、有限运算 DSL、目录导出和状态设计均为本项目工程选择，不声称论文公开过相同实现。

## Stage 5 最小执行实验

新增独立 Solver 执行、真实 Markdown 产物检查和错误产物测试。详见 [STAGE5.md](STAGE5.md)。当前只对 STATS19 Pilot 实现独立统计参考；不自动将 Draft 升级为 Verified，也不改动 Stage 1–4 数据。
