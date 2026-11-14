# Stage 3 · Graph-guided Real Workspace Construction

当前新版入口和两层 Graph 的方法边界见 [ASSET_PIPELINE.md](../ASSET_PIPELINE.md)，本轮批次见 [实际报告](../workspaces/data/asset_pilot_v4/report.md)。以下保留原接口与历史实验说明；标为“本轮”的旧统计属于当时记录，不与新批次合并。

消费 Stage 2 已准入的 Raw Seed Blueprint。先寻找真实案例 Anchor，再根据关键输入缺口补充同一案例的材料。模型负责规划、选择和语义判断；Python 负责真实 Search API、下载、解析、位置恢复、哈希与准入检查。运行过程没有人工选文件或改判环节。本轮不使用合成配套材料。

**当前入口已更新为 `work-plans/data/semantic_pilot/blueprints.jsonl`（raw-blueprint-v2，5 条准入计划）**，包含 Python 组装的 Graph、文件格式偏好和可选视觉依赖假设。默认输出目录为 `data/semantic_workspaces/`，避免覆盖历史实验。本次优化只重跑 Stage 2，没有生成新的 Workspace。

历史记录：原直接 Graph Pilot 为 10 条 Seed → 2 条准入 → 0 ready，保存在 `data/generated/`。后续 [Claude Code + LLMCenter 搜索试验](CLAUDE_SEARCH.md) 实际下载解析 1 个网页，但仍为 0 Anchor / 0 ready；其独立记录保留，不与本轮新 Blueprint 混用。

新增一个**独立可选实验**：[Controlled World Pilot](WORLD_PILOT.md)。对当前项目监控 Blueprint 同时运行真实检索和“模型生成隐藏世界 → Python 渲染 → 实验任务与数值检查”。真实侧仍 incomplete；合成侧得到 5 份文件和一个 experimental_draft，保留模型审核指出的叙述/规则缺口，未通过独立 Agent Probe、未进入训练集。它不修改本文 real-only 准入条件，也不代表正式 Stage 4 已迁移。

## 命令

在仓库根目录执行：

```bash
.venv/bin/python -m pip install -r workspaces/requirements.txt
# 同时运行 Stage 2 和 Stage 3
.venv/bin/python workspaces/scripts/run_pipeline.py --limit 10
# 只消费当前已准入 Blueprint
.venv/bin/python workspaces/scripts/construct_workspace.py
# 只离线重放本轮 Stage 2；本轮未运行新的检索
.venv/bin/python work-plans/scripts/plan_intents.py --offline
# 只生成搜索计划 / 独立重新解析并核验已组装文件
.venv/bin/python workspaces/scripts/construct_workspace.py --stage plan --output-dir /tmp/workagent-search-plans
.venv/bin/python workspaces/scripts/construct_workspace.py --stage verify
# 两条相同 Seed 的极简对照：搜索规划不传显式 Graph
.venv/bin/python workspaces/scripts/construct_workspace.py --mode direct --limit 2 --output-dir workspaces/data/semantic_direct_baseline
# 汇总上轮历史结果，无新模型或搜索调用
.venv/bin/python workspaces/scripts/summarize_pilot.py
.venv/bin/python -m unittest discover -s workspaces/tests -v
```

CLI 支持 `--plan-dir --seed-file --output-dir --config --cache-dir --limit --offline`，以及 `--stage plan/all/verify --mode graph/direct`。普通运行可通过响应、查询、下载与解析缓存恢复进度；重新审查已缓存的材料，不重新下载已缓存字节。调整 Prompt 或配置会改变缓存键；若会改变已组装材料，请用新的输出目录，程序拒绝悄悄覆盖或保留无关旧文件。

## Search Provider 配置

`config/graph_pipeline.json` 当前默认 Tavily，Key 来自 `TAVILY_API_KEY`。也支持 Brave（`BRAVE_SEARCH_API_KEY`）和 Serper（`SERPER_API_KEY`）。只需设置环境变量，并把 `search.provider` / `search.api_key_env` 改为对应配置，无须更改 Python。模型接口仍使用 Stage 1 的 LLMCenter GLM-5.2，推理 Key 与搜索 Key 是两回事。

```json
{"search": {"provider": "tavily", "api_key_env": "TAVILY_API_KEY", "max_results": 6, "timeout_seconds": 30, "trusted_proxy_env": "HTTPS_PROXY"}}
```

这里展示的只是配置片段；保留完整配置中的模型与检索预算。凭证不要写入 JSON。未配置时保留 `awaiting_search`，不接入未经验证的公共搜索抓取。`disabled` 或 `url_manifest` 也不执行自动检索；本版本支持缓存离线重放，没有把旧人工 URL 清单作为新 Pipeline 的默认路径。

上述 Tavily/Brave/Serper 后端已实现 HTTP 协议并通过模拟契约测试，尚未有凭证完成实时集成测试；Claude Code 后端的真实试验单独记录。默认预算：Anchor 最多 5 个查询、选择最多 3 个候选；最多 2 轮缺口搜索，每轮最多 3 查询/3 文件。预算放在配置，不写死在 Prompt 中。缺少 Key、查询非法、搜索空结果、下载/解析失败分别记录。

### Claude Code 自主检索模式

原 `claude_code` provider 是每次一个 WebSearch 的查询适配器，不是完整检索 Agent。新增 `claude_code_agent` 在一个会话中提供完整 Raw Seed、已准入 Blueprint 和信息缺口，由 GLM-5.2 自主规划查询、使用 WebSearch/WebFetch、记住拒绝来源、追踪附件与选择案例。Python 不再逐查询调用外部选择模型；会话结束后独立下载、解析和执行原有覆盖准入检查。

**后续自主检索使用 `claude_agent_autonomous.json`：不设置轮数、WebSearch 或 WebFetch 次数上限。** 运行器不传 `--max-turns`，不设置搜索次数环境变量，也不因工具调用次数拒绝结果。Prompt v2 按具体职业、所需事实、案例关系与剩余缺口引导 Agent 自主继续/停止，允许提交仍有缺口的真实案例，不要求搜索到绝对完整才收尾。保留 1,800 秒总超时、单次下载保护和本轮最多 6 个材料文件的组装规模；这些不等于无限制运行。本次完成代码测试，尚未用该新配置重新联网检索。

```bash
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --config workspaces/config/claude_agent_autonomous.json \
  --output-dir workspaces/data/claude_agent_autonomous \
  --cache-dir workspaces/data/cache_claude_agent --limit 1
```

下方命令和次数配置保留用于复现先前有限轮数实验，不要用它启动新的自主检索：

```bash
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --config workspaces/config/claude_agent_pilot.json \
  --output-dir workspaces/data/claude_agent_pilot \
  --cache-dir workspaces/data/cache_claude_agent --limit 1
# 已有完整本机缓存时追加 --offline，无网络或 Claude 进程调用
```

入口仍为相同的新 Blueprint。历史 Pilot 配置为 8 次搜索、10 次 WebFetch、24 轮、600 秒、6 个候选文件；WebFetch 次数通过 Prompt 限定并在完成后检查，进程由轮数/超时限制，不将其描述为逐请求硬配额。工具限 WebSearch/WebFetch，不给模型凭证文件、Shell 或任意代码执行。它是 Claude Code + GLM-5.2，不是 Claude 模型本身的能力评估。

实际文件 URL 必须来自工具搜索结果、匹配到的实际 WebFetch 访问，或者能在 Python 重新下载的页面中找到真实 href。WebFetch 访问仅提供待独立获取的地址，不证明内容存在；Python 必须重新下载真实字节。允许无扩展名的下载接口及带参数的地址；不从模型描述猜下载链接。网页中发现的链接继承页面 URL 和 SHA-256；若落地页只有一个原生附件，自动追踪该真实 href 并解析，多个附件不任意挑选。WebFetch 摘要和最终 Agent 宣称的覆盖仍不算证据；模型输出错误、断链、未实际找到的链接分别记录失败，不自动降级准入。

可选 `config/claude_agent_closeout.json` 允许耗尽轮数/时间后的**一次无工具收尾调用**，仅整理已发生的工具观察。原失败状态、实际调用次数和超限事实保留；Python 可以检查已发现的文件，但该次运行即使材料齐全也不准入 ready。不会重复搜索、补造链接或把收尾描述当作文件事实。

该模式支持 `--stage all` 和独立 `--stage verify`，不支持仅生成查询的 `--stage plan` 或不传 Graph 的 direct 对照。代码入口为 `scripts/agent_retrieval.py`，版本化提示为 `prompts/claude_retrieval_agent.v1.txt`。旧数据和查询适配器保留，禁止用新增模式的测试夹具冒充真实联网成功。

实际实验见 [AGENT_SEARCH.md](AGENT_SEARCH.md)：10 次 WebSearch、31 次 WebFetch 后耗尽轮数；无工具收尾并独立获取到 1 个项目网页、1 个 PDF 和 3 份 CSV 内容。没有 ready，停止条件、信息粒度和审核输出仍有问题。调用次数以日志为准，不能把配置预算当作实际调用数。

## 原生工作文件政策

HTML/HTM/XHTML 只用于导航、附件发现和来源追踪，不进入 Agent 可见 Workspace，也不能作为必需输入的覆盖证据。无条件程序检查覆盖审核、材料组装、实际字节复查及 Stage 4 准入；修改后缀不能绕过。Search Agent 必须寻找实际原生附件和元数据文件，不允许把网页改名为 TXT/PDF 代替。缺少原生资料时记录缺口。当前自主模式默认使用 `claude_retrieval_agent.v3.txt` 与 `evidence_auditor.v4.txt`。历史 HTML 样例保留，但不再准入。

## 信息覆盖怎么验证

- 下载沿用 HTTPS、公共地址检查、DNS 固定、重定向检查、超时/大小上限、类型核验和 SHA-256 缓存。不运行附件代码或宏。
- 真实 PDF、XLSX、CSV、DOCX、PPTX、JSON、文本、图像及仓库材料先解析。程序从文件哈希、定位和原文生成稳定 `segment_id`。
- 审核模型只引用它实际看到的 `file_id + segment_id`；Python 独立恢复原文与页码、行号、工作表单元格等定位。模型无需重新抄录引文。
- 模型上下文有片段数量和字符预算，报告保留是否看到了全部片段；没看到的内容不能当作已审核证据。
- `supported` 必须有真实定位、无未验证假设；缺失、冲突、被排除文件、答案泄漏和敏感资料不会通过准入。案例关系与适用性是模型判断，不包装成程序已证实的职业事实。
- 先分别审核不同 Anchor 候选，只有确定 Anchor 后才合并相关补充材料；缺口不触发自动编造或降级任务。
- `task_instruction` 节点留待 Stage 4 明确提供，不算检索成功；它们不能被用于伪造文件覆盖。

`ready` 要求有真实 Anchor、所有关键可检索输入获得支持、案例一致、没有关键冲突和答案泄漏，并重新解析组装后的实际字节核验引用。`incomplete / rejected` 均不进入任务生成。ready 只是材料充分性的初审，不是执行可解性证明。

## 格式和多模态边界

规划的 `preferred_formats` 只是候选，不作为逐文件准入过滤器；程序核验实际文件类型并在 File Profile 的 `format` 中记录。HTML 检索页和仓库 ZIP 等既有获取能力保留，不能据其格式推断多模态价值。最终交付格式留给 Stage 4。

当前收敛到文本、文档、表格、图片和代码。音频/视频下载内容会明确拒绝，停止发现其链接，移除了默认音视频感知调用；旧代码仅保存在 `archive/scripts/*with-media.py`，不在默认流程中运行。

新增 TEX、PY、JS 源文、Notebook JSON、TIFF 和 SVG 的只读解析。不会编译 LaTeX、执行代码或 Notebook。Notebook 已有输出会记录答案泄漏审查提示。SVG 只检查静态结构和坐标，不执行脚本、不加载外部资源、不声称已经理解空间含义。

图像/PDF 仍可通过可选视觉接口检查；VLM 描述是未独立核实的观察，不能直接升级为关键事实。候选视觉依赖保留信息需求、所支持操作和待验证状态。等价且可定位的文本/结构化事实可以满足信息需求，不能仅因存在视觉假设就强制使用图片；这种覆盖也不证明视觉必要性。文件扩展名不证明视觉必要性，必要性验证留给 Stage 5。

## 输出与复现

以下是后续运行 Stage 3 时的目录结构，本轮尚未生成该目录：

```text
workspaces/data/semantic_workspaces/
├── pilot_report.json                 # 每个准入 Blueprint 的构造结果
└── WS_<seed_hash>/
    ├── workspace_init/               # 仅实际准入的输入文件
    └── construction/
        ├── search_trace.json          # 计划、真实搜索结果、选择和审核
        ├── source_manifest.json       # 来源 URL、哈希、时间和许可状态
        ├── file_profiles.json         # 实际结构、片段与定位
        ├── information_coverage.json  # 输入节点对应文件片段
        └── construction_report.json   # 状态、缺口、模型和运行配置
```

`construction/` 和模型缓存不交给未来执行 Agent。未确认再分发许可的来源不允许标记公开发布；下载字节、完整文件清点及覆盖片段默认不提交 Git。实际运行后，清点文件保留在本机，Git 仅保存可公开的报告/搜索记录等。响应缓存位于 `workspaces/data/cache_graph/`，不含明文 Key；它包含来源内容，不能随意公开。

上轮的 13 文件重放记录保留在 [历史报告](data/generated/replay_report.json)。当前 `tests/test_cached_replay.py` 核验本轮 Stage 2 字节一致性与新版 Stage 3 入口；新克隆没有缓存时明确跳过，不假装已做新检索。

对同一输入与缓存，离线重放不产生新请求。报告中的请求元数据与用量保留原始调用，不代表重放又收费；没有供应商账单时金额为 `null`。首次克隆没有本地缓存，只能查看已提交结果或配置接口重新运行，不能保证新模型输出逐字相同。

## 历史 Pilot 与回归

[汇总 JSON](data/generated/experiment_summary.json)、[三条完整记录](data/generated/examples.md)。上轮直接 Graph 实验生成 10/10、图检查通过 5/10、语义准入 2/10。汽车文档计划等待搜索凭证；法规计划查询引用推导节点而被拒绝。关键可检索输入覆盖 0/5，没有新文件、真实 Anchor 或已核实视觉证据。直接搜索对照两条也在等待凭证，不能比较 Graph 的检索收益。

`inspect_regressions.py` 使用本机已有真实下载缓存，重新解析加拿大 CSV 和 HMRC XLSX，核验稳定片段 ID、原始字节与定位；2 份通过。来源、哈希和原始获取时间在 [regression_report.json](data/generated/regression_report.json)。这些不是本轮检索成果，也不证明它们覆盖新 Blueprint；新克隆没有原始字节时不伪造回归结果。

工程测试使用明确的 `synthetic_test_fixture` 和模拟 HTTP/模型验证两轮闭环，与以上真实统计分开。没有拿 fixture 生成正式 Workspace。

## 迁移与后续入口

旧脚本、配置、测试及 Pilot 在 `archive/`，仅供历史审阅；完整旧环境请检出 `5e61eae`。新 Stage 2 接口为 `raw-blueprint-v2`，Stage 3 为 `grounded-workspace-v2`。当前 Stage 4 已接入这两个接口，重新核验 ready 状态、Seed/Blueprint 哈希、实际文件和 segment_id；旧 incomplete/rejected 记录仍被阻断。[原生文件实验](../work-tasks/NATIVE_FILE_PILOT.md) 已从新 Seed 构造一份无 HTML 的 ready Workspace 和一个 Draft Task Package；后续 [Stage 5 Probe](../work-tasks/STAGE5.md) 已执行，当前结果为 `needs_review`。方法与论文差异见 [METHODS.md](METHODS.md)。
