# Stage 3 · Evidence-grounded Workspace Construction

本模块读取 Stage 2 最终准入的两个计划，按照工作目标和信息依赖寻找材料，实际下载、解析并核对位置，最后构建 `workspace_init/`。`ready` 才可进入 Stage 4；`incomplete` 与 `rejected` 均不能进入正式任务生成。这里的准入仅检查输入信息充分性，尚未执行任务可解性 Probe。

## 方法依据与本项目选择

| 论文公开方法 | 本阶段借鉴 | 本项目自行制定的实现边界 |
|---|---|---|
| [WorkFactory §3.3、Appendix B.3](https://arxiv.org/html/2610.37161v1#S3.SS3)：从输出倒推信息，再将其绑定到复用、适配或合成材料 | 由 Stage 2 的 external_input 驱动材料获取；计算与判断留给执行 Agent | 不生成用户任务、不做执行式修复；保守逐节点准入 |
| [GraphForge §3.2](https://arxiv.org/html/2609.38923v3#S3.SS2)：检索同一公开案例、下载原生文件、按类型解析、去重 | 先选一个 Anchor，再围绕它扩展检索 | 不加入干扰文件，也不构建 Evidence Graph |
| [WorkForge §2.2](https://arxiv.org/html/2610.04906)：迭代获取真实资源，Profile 记录结构与可检查事实 | Profile 来自下载字节，保留实际页/行/单元格位置 | 本项目使用受控 Python 循环及保守风险拦截，不声称复现其未公开工具细节 |
| [WorkGenesis §3.2](https://arxiv.org/html/2609.39325#S3.SS2)：真实 Anchor 加配套合成附件 | 支持明确缺口的结构化配套文件渲染与重新审核 | 本轮不强行合成核心记录；合成必须显式选择，且标注虚构身份 |

总体仍为 **Intent-first + Evidence Grounding**。以上只借鉴论文中可确认的做法，不声称复现完整论文流水线。

## 文件职责

| 文件 | 用途 |
|---|---|
| `scripts/construct_workspace.py` | CLI、上游准入检查、两轮检索、模型选择、覆盖审核、组装、独立哈希检查 |
| `scripts/acquire.py` | HTTPS、公网地址检查、DNS 固定、重定向、下载上限、缓存及失败记录 |
| `scripts/profile_files.py` | 实际文件解析、结构统计、可定位片段；解析进程限时限内存 |
| `scripts/coverage.py` | 校验引用位置、剔除不合格文件、覆盖状态与跨文件口径检查、准入判断 |
| `scripts/prompts.py` | 检索、候选选择、审核和查询改写的版本化提示 |
| `scripts/companions.py` | 显式传入、经过审核的结构化事实渲染成配套 JSON/CSV；不是自动补全业务数据 |
| `scripts/vision.py` | 可选图像/扫描页模型检查，显式保留“模型观察”属性 |
| `config/pilot.json` | LLM 配置引用、检索提供商、轮数及下载限制 |
| `config/pilot_urls.json` | 本次真实外部搜索及沿官方链接发现的候选 URL，不代表已成功下载 |
| `tests/test_workspaces.py` | 临时合成测试夹具，绝不作为 Pilot 的证据 |

复用 Stage 1 的 LLM 调用、原始响应缓存、JSONL 和哈希工具，复用 Stage 2 的 Schema/图检查。所有上游数据只读。模型仍为 LLMCenter `GLM_ka48dn`，实际响应为 `glm-5.2`。较长覆盖审核允许 7,000 个输出 token、180 秒请求超时；其他调用继承 Stage 1 参数。模型请求错误最多重试一次；无效 JSON 不自动修补。

## 运行与复现

在仓库根目录执行：

```bash
.venv/bin/python -m pip install -r workspaces/requirements.txt

# 已有本机缓存：完全离线重建到新目录，不需要 Key
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --offline --output-dir /tmp/workagent-stage3-replay

# 独立检查保存的工作空间
.venv/bin/python workspaces/scripts/construct_workspace.py --stage verify

# 新一轮联网实验：隐藏输入 accessKey；使用新输出目录
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --prompt-api-key --output-dir workspaces/data/new_pilot

# 只查看/生成检索计划
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --stage plan --offline --output-dir /tmp/workagent-stage3-plans

.venv/bin/python -m unittest discover -s workspaces/tests -v
```

CLI 还支持 `--plan-dir`、`--seed-dir`、`--cache-dir`、`--config` 和 `--limit`。当前 Pilot 限制最多两个准入计划；`--limit 0` 不调用模型。输出目录记录代码、输入、配置、URL Manifest 的哈希，变化后需要新目录。相同输入与原始响应/下载缓存可离线复现；重新访问网站或重新生成模型响应不保证内容相同。

缓存位于 `data/cache/`，包含原始字节、下载回执、模型原始响应、失败记录及解析结果。失败下载也缓存，离线重放不会把原来的 HTTP 错误替换成模拟文件。明确重试某个来源前，应先归档其 `downloads/` 失败回执；格式错误的模型响应同样应归档后再发起新实验。不要直接编辑原始缓存字节。

`workspace_init/` 和详细 Profile/证据片段默认不进 Git：本轮没有完成逐文件再分发权利确认。Git 中的来源清单和报告可审阅，但换机器完整离线重建需要另外复制本地缓存。公开可访问的文件不因此被标记为可公开发布。

## 检索接口与真实执行边界

本机没有配置独立 Search API。本次使用外部真实 Web Search，按照模型初始查询及基于已下载材料提出的改写查询执行检索，再将结果导入 `url_manifest`。少量沿官方目录发现的原生下载链接和人工追加发现查询也单独记录。**脚本没有调用 LLMCenter Web Search，也没有把 Manifest 查询次数冒充脚本联网搜索次数。**

Manifest 的一条记录包含 `seed_id`、`round`、精确 `query`、实际搜索 `provider`、`searched_at`、`supplemental_queries` 和 `results`。结果包含 `url`、`source_page`、`title`、`snippet`、`discovery_query`。这些是发现线索，不直接成为覆盖证据。第二轮查询没有对应记录时，保存 `awaiting_external_search`；不会凭空补 URL。可以导入真实新结果后在新输出目录恢复，已有下载和模型响应会继续复用。

也支持 `http_search`：配置 HTTPS `endpoint`、可选 `api_key_env`，接口接收 `POST {"query":"..."}`，返回 `{"results":[{"url":"https://...","title":"...","snippet":"..."}]}`。搜索请求及实际响应按哈希缓存。此适配器提供可配置能力，本次真实 Pilot 使用的是 Manifest 路线。

默认最多两轮、每轮最多两条查询。首轮只选择一个 Anchor 候选，第二轮最多选择三份同案例补充材料。模型只能选择工具实际给出的候选 ID；不能自行提供文件地址。每个未选候选也须给出理由。

## 下载与解析

- URL 只允许 HTTPS、标准端口、无嵌入凭证；初始地址及每次重定向均检查。所有 DNS 地址必须是公网地址，连接固定到已检查 IP，同时以原主机名验证 TLS 证书，防止检查后重新解析。
- 本机经显式配置的 `HTTPS_PROXY` 访问公网；这是可信传输入口，CONNECT 目标仍是已检查的公网 IP。它不允许下载 URL 指向本地网络。无代理环境可移除 `trusted_proxy_env`。
- 默认 20 MB、25 秒下载 I/O 期限、最多四次重定向及一次重试。校验 Content-Length、MIME、文件魔数、扩展名和 SHA-256；同字节只存一份。保留原 URL、最终 URL、跳转链、获取时间；临时签名 URL 的完整查询串仅存私有缓存，公开清单保留最终路径及查询哈希。
- PDF 提取每页文字与表格，记录页码和行；XLSX 记录 Sheet/单元格/类型/数值范围；CSV 记录列、逻辑行和类型；DOCX/PPTX 提取正文、段落及表格结构；JSON 使用 JSON Pointer；Markdown/TXT 记录行号；小型 ZIP 源码包记录目录、文本源码和配置，**不运行源码或测试**。
- Office 宏/嵌入对象、危险压缩包路径、过量展开、加密文件和无法解析的文件拒绝。解析在受资源限制的子进程执行。CSV 空行单独计数，不修改原文件；不执行工作簿公式。
- HTML 作为发现材料解析，默认不直接装入 Agent 工作空间。没有把脚本网页当成已核实的原生业务文件。
- 图片只验证可解码时，会保留 `visual_inspection_required`。可通过 `vision` 配置提供具备图像能力的模型；其观察绑定实际像素哈希和区域，并标为模型观察。扫描 PDF 最多检查四页。**本次没有实际进行视觉模型审核，不声称验证了图中信息或构成多模态依赖。**

解析器是有限支持：PDF 超过 150 页、仓库包超过 300 个条目等会明确拒绝；不以截断后的小片段声称完整解析。模型审核接收有明确定位的有限片段，完整解析内容保存在私有 Profile；语义覆盖仍可能漏判。

## 覆盖、一致性与合成边界

每个 external_input 都有一条覆盖记录，状态为 `supported / partial / missing / conflicted / unreadable`。模型必须提供已有 File ID、定位和短引文；程序检查引文确实在该文件的对应解析位置。不存在的位置、未消除的假设、引用被隔离的文件，都不能算完整覆盖。

报告同时保留“模型观察到的覆盖”和“实际放进 workspace_init 的覆盖”，防止把相关文件、被拒绝文件或网页标题算成可用输入。组织、年度、币种、单位、版本的适用关系属于模型推断；源文件字节与引文位置由程序核验。缺少证据时保留 unknown，不自动补齐。字符串口径检查较保守，需要人工复核；它不能替代财务或项目专家的判断。

所有必需节点都 supported、有可用真实 Anchor、案例一致且没有关键未验证假设，才允许 ready。文件有明显联系信息风险、包含预先完成的分析、与案例无关或需未完成的视觉检查时，不装入 Agent 目录。这些筛查可能误伤，也不是完备的隐私或泄漏证明。

本轮先走纯真实材料，并对缺口继续检索；不自动将核心预算、软件成本、验收记录全部合成。可选 `--companions reviewed_specs.json` 接收明确审核过的规格数组，只有存在真实 Anchor、覆盖审核认为小范围补充安全、目标恰为缺失 external_input 时才渲染。每份文件只补一个节点，最多两份，限定 JSON/CSV，文件名和内容都带 SYNTHETIC，身份必须以 `Fictional ` 开头。规格绑定原计划 SHA-256，记录 Anchor 与目标节点，再解析并重新审核全部材料。真实原件保持原样；不允许把合成物标为真实来源。此路径有单元测试，本轮没有使用。

`real_adapted` 来源要求父文件哈希和变换记录；本轮没有实现自动文档改写，也没有产出适配文件。构造端不生成最终用户任务、完整 Evidence Graph、答案、Oracle、Rubric、Verifier、执行轨迹或训练数据。

## 实际 Pilot

本轮实际输入两个准入 Plan，**ready 0、incomplete 1、rejected 1**。已经实现并运行构造流水线，但尚未产出可进入 Stage 4 的合格 Workspace。机器可读汇总见 [pilot_report.json](data/pilot/pilot_report.json)。

| 最终 Pilot 记录 | WS001：预算差异与调整建议 | WS002：软件项目进度监控 |
|---|---:|---:|
| 实际外部搜索查询数 | 5 | 5 |
| 脚本 Manifest 查询数 | 4 | 4 |
| 成功下载 URL 数 | 1 | 3 |
| 下载失败 URL 数 | 1 | 1 |
| 成功解析的独立文件 | 1 | 3 |
| 解析拒绝 | 0 | 0 |
| 通过准入审核的真实 Anchor | 1 | 0 |
| 放入初始目录的原始 / 适配 / 合成文件 | 1 / 0 / 0 | 0 / 0 / 0 |
| 必需外部信息节点 | 5 | 4 |
| 已验证完整覆盖 | 0/5 | 0/4（审核失败，未建立覆盖） |
| 补充后完整覆盖 | 0/5；未合成 | 0/4；未合成 |
| 最终状态 | `incomplete` | `rejected` |

这些是最终 Pilot 所选择和引用的获取记录；开发过程中的解析修正、提示调试和较早获取尝试保存在本地 `data/cache/archive/`，未混入最终覆盖统计。网络失败会重试一次，表中按独立 URL 计数，不把两次失败算成两个文件。

**WS001 的实际材料。** 来自[加拿大政府开放数据目录](https://open.canada.ca/data/en/dataset/fc6ba156-a167-4abd-b172-d1293efebe55?wbdisable=true)的原生 `eav_eac_en.csv`，下载后有 5,336 条数据记录、7 列，以及一条末尾空行；年度字段范围 2011–2019。文件原样保留，648,257 字节，SHA-256 为 `3032f3110f52feb3fdc86642163fb14c7df81ac4c1a1730b670080681f767dac`。没有将这些历史记录声称为当前年度数据。

```text
workspaces/data/pilot/WS001/
├── workspace_init/
│   └── tables/
│       └── 3032f311_eav_eac_en.csv
└── construction/
    ├── source_manifest.json
    ├── file_profiles.jsonl
    ├── information_coverage.json
    ├── construction_report.json
    ├── retrieval_log.json
    ├── model_audit_round_1.json
    └── model_audit_round_2.json
```

未来执行 Agent 只读取 `workspace_init/`。此处的文件树确实存在于本机；Git 不包含未确认再分发权利的 CSV 和详细抽取内容。

| WS001 外部节点 | 覆盖 | 具体限制 |
|---|---|---|
| i1：批准预算 | partial | 实际 CSV 有 `authorities` 列，但仅凭该文件不能核定它与任务所需批准预算基线的关系 |
| i2：同口径实际支出 | partial | 有 `expenditures` 列，仍缺少经核实的字段定义、单位及周期口径 |
| i3：预算管理与调整规则 | missing | CSV 未提供适用政策和授权条件 |
| i5：支出差异的背景解释 | missing | 数值记录不包含成因说明 |
| i7：报告受众要求 | missing | 未找到对应工作场景的受众与汇报要求 |

因此完整覆盖率为 0%，但存在两项部分覆盖。追加检索选中了 [Public Accounts 2010–2011 Volume II](https://publications.gc.ca/collections/collection_2011/tpsgc-pwgsc/P51-1-2011-2-eng.pdf)，实际获取两次返回 HTTP 202，未下载成 PDF；不能把搜索命中算作新增证据。当前尚未确定一个口径完整的机构—期间案例，不通过一致性准入。

**WS002 的实际材料与失败。** 最终下载并解析了同一 California State Payroll System（CSPS）项目的三份资料：[LAO 预算分析网页](https://lao.ca.gov/Publications/Report/5011)、[2026–27 Budget Change Proposal](https://bcp.dof.ca.gov/2627/FY2627_ORG0840_BCP9253.pdf)、[2023–24 年度立法报告](https://www.sco.ca.gov/Files-EO/2023-24_CSPS_Report_to_the_Legislature.pdf)。另一个项目状态页实际返回 HTTP 404，未获取成功。

两轮覆盖审核均因 `quote_not_at_actual_location` 未通过：模型将原文的弯引号改成直引号，或省略了表格空单元格的分隔符。程序要求实际位置上的精确片段，未放宽检查、自动修正引文或把模型结论直接提升为证据。原始模型响应和文件位置均保留在私有构造记录中。第二轮模型请求此前还发生两次超时；延长超时后返回了真实响应，但仍未通过定位检查。

下表仅概述**未通过程序验证的模型判断**，不计入覆盖率：

| WS002 外部节点 | 未通过验证的模型判断 | 待核实问题 |
|---|---|---|
| i1：批准计划、里程碑、标准与成本目标 | partial | 预算申请与概述不能替代完整的批准计划和验收标准 |
| i2：实际进展 | partial | 有个别里程碑陈述，缺少同一基线下系统性的当前进度记录 |
| i3：实际与承诺成本 | partial | 确有历史支出表，不能因此认定当前期间的实际及承诺成本已齐全 |
| i4：实际质量与验收证据 | missing | 测试计划和测试岗位预算不等于已执行的测试结果 |

资料横跨不同预算周期和计划版本；其适用关系尚未通过完整审核。HTML 只能作为发现材料，报告也包含可能预先完成的分析，需进一步评估答案泄漏。当前 `workspace_init/` 为空，三个解析文件均留在构造端缓存，**拒绝状态不等于已经证明这些文件毫无用处**。

本轮没有用合成材料替代以上核心缺口，没有生成任务答案，也没有声称多模态依赖。下一次实验应先核实字段和批准版本、取得可用进度/成本/质量资料，并改善模型逐字引用能力，再重新执行相同准入检查。

验证使用 26 个单元测试（临时夹具与真实联网 Pilot 分开）。禁用网络连接和 DNS 后，17 个实际输出文件从缓存重建，逐字节一致；两个目录的独立哈希检查通过。Stage 1/2 的 35 个已跟踪数据文件与原 Git 版本一致。验证记录见 [validation_report.json](data/validation_report.json)。
