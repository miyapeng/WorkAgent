# Claude Code 自主检索：同 Seed 实测

本页记录先前的有限轮数实验，保留其配置与结果供复现。后续采用 [claude_agent_autonomous.json](config/claude_agent_autonomous.json)：轮数、搜索次数和 Fetch 次数均为 null；运行器省略相应限制，Prompt 使用 v2 的信息需求和自主停止条件。保留 30 分钟总超时与下载保护。新配置已经过工程测试，尚未重新联网实跑；下列下载成果仍来自先前实验。

已下载的 4 份原始材料已从缓存复制到本地 `data/claude_agent_closeout/review_materials/`，以 PDF/CSV 文件名提供查看。原字节 SHA-256 保持一致，来源清单在该目录中；仅供查看，不进入准入 Workspace，不提交 Git。

这次修正的是检索接法：旧 `claude_code` provider 每次只做一个 WebSearch，新 `claude_code_agent` 获得完整 Raw Seed、已准入 Blueprint、信息需求与预算，自主搜索、WebFetch、跟随链接并记住拒绝来源。模型仍为 GLM-5.2；不是 Claude 模型能力测试。

同一 `raw_31_0_18983`（网络项目进度、预算与成本控制），同一 Blueprint：

| 项目 | 原查询适配器 | 自主检索 + 已有记录收尾 |
|---|---:|---:|
| 实际 WebSearch 调用 | 4 | 10 |
| 实际 WebFetch 调用 | 0 | 31 |
| Python 实际下载并解析 | 1 个课程网页 | 1 个项目网页、1 个 PDF、3 份 CSV 内容 |
| 准入 Workspace | 0 | 0 |

**自主 Agent 确实能推进到具体案例和下载入口；原来的实验不足以评价它。** 但此次同时改变了上下文、工具使用方式和预算，只是可行性探索，不是严格消融或能力提升比例。

## 实际过程与文件

Agent 自主从泛搜转向政府 IT Dashboard、GAO 和 NTIA 宽带项目，查看数据入口、发现带查询/路径参数的 CSV 接口，并找到 Comanche Nation 年报的落地页。没有由开发者预先指定这几个网站或抄入下载地址。

Python 重新获取实际字节，并从年报页面中的唯一附件 href 下载 PDF：

- NTIA Comanche Nation Annual Report FY24 Q3：149,731 字节，PDF 2 页；与页面的来源关系可追溯。
- IT Dashboard cost variance：78 行数据。
- IT Dashboard schedule variance：78 行数据。
- IT Dashboard performance metrics：48 行数据。

三份 CSV 的服务器 Content-Type 实际为 `text/html`，但文件字节是 CSV。当前通用 Profiler 以文本行解析它们；汇总脚本另外用标准库 CSV 解析器检查列名、行数及矩形结构。没有将文件后缀、HTTP 头或 WebFetch 摘要当成内容证据。

来源 URL、SHA-256、结构检查及真实计数见 [experiment_report.json](data/claude_agent_closeout/experiment_report.json)。原始字节在 `data/cache_claude_agent/blobs/`，许可未知，不提交 Git；它们也没有进入 Agent 的准入 workspace_init。

## 为什么还没 ready

1. **检索没有正常收尾。** 会话耗时 569.39 秒，达到 24 轮上限，返回 `error_max_turns`。Prompt/环境配置的 8 次搜索、10 次 Fetch 未成为可靠硬上限：日志实际为 10/31，报告如实保存超限。
2. **不能丢掉已发生的发现。** 可选 closeout 模式仅用一次无工具模型调用整理原始工具观察，未再搜索。原失败状态保留；即使后续材料完整，本次也不准入 ready。这不是把一次失败改成成功。
3. **文件内容仍有缺口。** IT Dashboard CSV 是机构层面的汇总计数，没有单个项目的预算金额、实际支出或里程碑。NTIA 报告是真实项目记录，但不能仅凭报告名称断言所有财务、计划与完成信息齐全。
4. **审核输出也存在工程问题。** NTIA 审核同时标记文件 `sensitive=true` 与 `retain=true`，触发 `unsafe_retained_file`；机构汇总数据审核的节点集合不符合接口，触发 `node_coverage_mismatch`。这些是程序阻断，不是已证明每个信息节点都没有任何相关内容。原始审核没有被手工改判。

完整会话保存在 `data/claude_agent_pilot/`；收尾和独立获取保存在 `data/claude_agent_closeout/`。初版获取代码只接受搜索返回链接，错误阻断了 Agent 实际 WebFetch 访问过的官方入口，该失败另外保存在 `initial_provenance_gate_failure.json`。修正后，匹配到的实际 WebFetch 访问只提供待验证地址，Python 仍必须重新下载并核验，不接受助手正文里随口写的链接。

收尾模型自述“8/8 搜索、10/10 Fetch”不准确；统计一律使用实际 tool_use/tool_result 记录的 10/31。CLI 显示的费用估计不是 LLMCenter 账单，实际金额未知；收尾及审核用量单独保存，不重复把缓存重放计为新调用。

## 复现

```bash
# 新自主检索运行；同一 Seed 是当前准入列表的第一条
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --config workspaces/config/claude_agent_pilot.json \
  --output-dir workspaces/data/claude_agent_pilot \
  --cache-dir workspaces/data/cache_claude_agent --limit 1

# 从同一已缓存会话无工具收尾，独立下载/解析/审核；不再产生搜索
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --config workspaces/config/claude_agent_closeout.json \
  --output-dir workspaces/data/claude_agent_closeout \
  --cache-dir workspaces/data/cache_claude_agent --limit 1

# 本机缓存齐全时，上述命令加 --offline
.venv/bin/python workspaces/scripts/summarize_agent_pilot.py
.venv/bin/python -m unittest discover -s workspaces/tests -v
```

测试替身检查完整成功链、实际 href、无扩展名下载、唯一附件追踪、未观察地址拒绝、失败后收尾不能变 ready，以及离线缓存。它们与这次真实联网结果分开。没有生成最终任务、合成配套文件或运行教师 Agent。

验证：Stage 3 的 62 项测试、Stage 2 的 21 项测试通过；禁止网络与外部进程后，20 个结果文件逐字节重放一致，见 [replay_report.json](data/claude_agent_closeout/replay_report.json)。

下一步应把“先返回一个可核验的案例文件”作为明确的阶段性交付，及时保存发现，并把后续缺口交回 Agent；不要一开始要求它在一次会话里集齐整套 Workspace。还需要改善停止条件和审核的结构化接口。当前不能再将“下载不到文件”作为放弃真实路线的理由，但文件下载成功也没有证明整个任务已经信息充分。
