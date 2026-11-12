# Stage 3 · Graph-guided Real Workspace Construction

消费 Stage 2 已准入的 Raw Seed Blueprint。先寻找真实案例 Anchor，再根据关键输入缺口补充同一案例的材料。模型负责规划、选择和语义判断；Python 负责真实 Search API、下载、解析、位置恢复、哈希与准入检查。运行过程没有人工选文件或改判环节。本轮不使用合成配套材料。

**当前结果：10 条 Raw Seeds → 2 条准入 Blueprint → 0 个真实 Anchor → 0 个 ready Workspace。** 没有 Search API 凭证；一条停在 `awaiting_search`，另一条查询计划引用了推导节点 `i6`，在调用搜索前被拒绝。下载与实时检索尚未实测成功。

## 命令

在仓库根目录执行：

```bash
.venv/bin/python -m pip install -r workspaces/requirements.txt
# 同时运行 Stage 2 和 Stage 3
.venv/bin/python workspaces/scripts/run_pipeline.py --limit 10
# 只消费当前已准入 Blueprint
.venv/bin/python workspaces/scripts/construct_workspace.py
# 已有本机缓存时离线重放；缺缓存明确失败，不偷偷联网
.venv/bin/python workspaces/scripts/run_pipeline.py --offline
# 只生成搜索计划 / 独立重新解析并核验已组装文件
.venv/bin/python workspaces/scripts/construct_workspace.py --stage plan --output-dir /tmp/workagent-search-plans
.venv/bin/python workspaces/scripts/construct_workspace.py --stage verify
# 两条相同 Seed 的极简对照：搜索规划不传显式 Graph
.venv/bin/python workspaces/scripts/construct_workspace.py --mode direct --limit 2 --output-dir workspaces/data/direct_baseline
# 汇总已有结果，无新模型或搜索调用
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

Provider 已实现实际 HTTP 协议并通过模拟 HTTP 契约测试；尚未有凭证完成实时 API 集成测试。默认预算：Anchor 最多 5 个查询、选择最多 3 个候选；最多 2 轮缺口搜索，每轮最多 3 查询/3 文件。预算放在配置，不写死在 Prompt 中。缺少 Key、查询非法、搜索空结果、下载/解析失败分别记录。

## 信息覆盖怎么验证

- 下载沿用 HTTPS、公共地址检查、DNS 固定、重定向检查、超时/大小上限、类型核验和 SHA-256 缓存。不运行附件代码或宏。
- 真实 PDF、XLSX、CSV、DOCX、PPTX、JSON、文本、图像及仓库材料先解析。程序从文件哈希、定位和原文生成稳定 `segment_id`。
- 审核模型只引用它实际看到的 `file_id + segment_id`；Python 独立恢复原文与页码、行号、工作表单元格等定位。模型无需重新抄录引文。
- 模型上下文有片段数量和字符预算，报告保留是否看到了全部片段；没看到的内容不能当作已审核证据。
- `supported` 必须有真实定位、无未验证假设；缺失、冲突、被排除文件、答案泄漏和敏感资料不会通过准入。案例关系与适用性是模型判断，不包装成程序已证实的职业事实。
- 先分别审核不同 Anchor 候选，只有确定 Anchor 后才合并相关补充材料；缺口不触发自动编造或降级任务。
- `task_instruction` 节点留待 Stage 4 明确提供，不算检索成功；它们不能被用于伪造文件覆盖。

`ready` 要求有真实 Anchor、所有关键可检索输入获得支持、案例一致、没有关键冲突和答案泄漏，并重新解析组装后的实际字节核验引用。`incomplete / rejected` 均不进入任务生成。ready 只是材料充分性的初审，不是执行可解性证明。

## 多模态边界

图像/PDF 可配置具备视觉能力的接口检查，PDF 按配置页码或有限页面检查，记录未检查页。WAV 有真实时长/采样率元数据和可选音频接口；其他音视频元数据可使用本机 `ffprobe`，视频可使用 `ffmpeg` 做有上限的抽帧观察。缺少相应工具/接口就保留未检查状态，不假设 LLMCenter 的文本模型具备这些能力。

`vision`、`audio`、`video` 可选配置沿用 `endpoint / model / api_key_env / parameters`；具体接口须支持对应输入类型。PDF 渲染另需 `pypdfium2`，音视频工具为可选。当前真实 Pilot 没有调用感知模型；音视频接口尚未完成实时集成测试。

程序提取的原文定位与 VLM/音频模型观察分开记录。模型观察仍是未独立验证的候选，不能单凭它把关键节点升为 supported。此版没有独立视觉真值认证机制；即使有图片也不声称多模态必要性。必要性检验留给 Stage 5。

## 输出与复现

```text
workspaces/data/generated/
├── pilot_report.json                 # 每个准入 Blueprint 的构造结果
├── experiment_summary.json           # 10 条的分母、失败、用量及对照
├── examples.md                       # 三条完整 Seed→Blueprint→搜索记录
├── regression_report.json            # 两份历史真实来源解析回归
└── WS_<seed_hash>/
    ├── workspace_init/               # 仅实际准入的输入文件；当前为空
    └── construction/
        ├── search_trace.json          # 计划、真实搜索结果、选择和审核
        ├── source_manifest.json       # 来源 URL、哈希、时间和许可状态
        ├── file_profiles.json         # 实际结构、片段与定位
        ├── information_coverage.json  # 输入节点对应文件片段
        └── construction_report.json   # 状态、缺口、模型和运行配置
```

`construction/` 和模型缓存不交给未来执行 Agent。未确认再分发许可的来源不允许标记公开发布；下载字节、完整文件清点及覆盖片段默认不提交 Git。当前空 Workspace 的清点文件在本机存在，Git 仅保存报告/搜索记录等。响应缓存位于 `workspaces/data/cache_graph/`，不含明文 Key；它包含来源内容，不能随意公开。

已在禁止网络连接的测试中逐字节比较 13 个重放输出，全部一致，见 [replay_report.json](data/generated/replay_report.json)。对应可执行检查在 `tests/test_cached_replay.py`；新克隆没有缓存时会明确跳过。

对同一输入与缓存，离线重放不产生新请求。报告中的请求元数据与用量保留原始调用，不代表重放又收费；没有供应商账单时金额为 `null`。首次克隆没有本地缓存，只能查看已提交结果或配置接口重新运行，不能保证新模型输出逐字相同。

## 实际 Pilot 与回归

[汇总 JSON](data/generated/experiment_summary.json)、[三条完整记录](data/generated/examples.md)。本轮生成 10/10、图检查通过 5/10、语义准入 2/10。汽车文档计划等待搜索凭证；法规计划查询引用推导节点而被拒绝。关键可检索输入覆盖 0/5，没有新文件、真实 Anchor 或已核实视觉证据。直接搜索对照两条也在等待凭证，不能比较 Graph 的检索收益。

`inspect_regressions.py` 使用本机已有真实下载缓存，重新解析加拿大 CSV 和 HMRC XLSX，核验稳定片段 ID、原始字节与定位；2 份通过。来源、哈希和原始获取时间在 [regression_report.json](data/generated/regression_report.json)。这些不是本轮检索成果，也不证明它们覆盖新 Blueprint；新克隆没有原始字节时不伪造回归结果。

工程测试使用明确的 `synthetic_test_fixture` 和模拟 HTTP/模型验证两轮闭环，与以上真实统计分开。没有拿 fixture 生成正式 Workspace。

## 迁移与后续入口

旧脚本、配置、测试及 Pilot 在 `archive/`，仅供历史审阅；完整旧环境请检出 `5e61eae`。新 Stage 2 接口 `raw-blueprint-v1`，Stage 3 接口 `grounded-workspace-v2`。现有 Stage 4 仍依赖旧数据/函数，**不能直接运行新流水线的结果**，本次未增加兼容层。后续需迁移其入口、哈希关联与 segment_id 定位，并继续强制 ready 准入；不得将本轮 incomplete 改名为成功。方法与论文差异见 [METHODS.md](METHODS.md)。
