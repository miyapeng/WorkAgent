# Claude Code + LLMCenter 搜索试验

本轮实测使用本机 Claude Code 2.1.299、LLMCenter 的 GLM-5.2 accessId `GLM_ka48dn` 和现有推理 Key，未提供 Tavily/Brave/Serper Key。**WebSearch 与 WebFetch 可以调用并返回工具结果，但本轮没有形成 ready Workspace。**

## 实际结果

| 实验 | WebSearch 工具调用 | WebFetch 工具调用 | 结果 |
|---|---:|---:|---|
| 汽车文档：初次能力探测 | 2 | 0 | 14 个候选 URL，多为泛页或疑似截断路径 |
| 汽车文档：进一步探测 | 2 | 1 | 12 个去重候选 URL；WebFetch 返回 404 |
| 法规资料：独立探测 | 2 | 1 | 14 个去重候选 URL；WebFetch 返回 403 |
| 汽车文档：完整 Stage 3 接入 | 4 | 0 | Python 尝试下载 4 个 URL，1 个 HTML 下载并解析成功；0 Anchor，0 ready |

这些是从 Claude Code 的 `tool_use / tool_result` 对应关系计数，不是模型自述，也不等于底层搜索服务请求数。WebSearch 可能内部发起额外检索；网关的具体搜索后端和内部执行在客户端日志中不可见，不声称此路由必然使用官方 Anthropic 搜索后端。

成功下载的是 `https://community.ptc.com/` 的公开 HTML，原始字节保存在私有缓存。其他下载返回 403/404。覆盖审核输出存在 `node_coverage_mismatch`，不能据此批准该网页为 Anchor；材料未进入 Agent 可见目录，三个关键输入仍未得到验证支持。未将社区首页、搜索摘要或模型解释当成实际工程变更与设计规格文件。

[实验汇总](data/claude_search_pilot/experiment_report.json)、[完整 Stage 3 报告](data/claude_search_pilot/pilot_report.json)、[法规探测记录](data/claude_search_probe/raw_31_0_21094/probe_report.json)。两个早期能力探测保留在 `data/claude_search_probe/probe_glm52*.json`，不混入原来的 10-Seed Pilot 成功率。

## 运行方式

独立试一条已通过 Stage 2 审核的 Blueprint：

```bash
.venv/bin/python workspaces/scripts/probe_claude_search.py --seed-id raw_31_0_21094
```

自动接入现有 Stage 3（当前配置限制为两个 Anchor 查询、两个下载候选、一轮补充检索；此命令只运行一个已准入 Seed）：

```bash
.venv/bin/python workspaces/scripts/construct_workspace.py \
  --config workspaces/config/claude_search_pilot.json \
  --limit 1 \
  --output-dir workspaces/data/claude_search_pilot \
  --cache-dir workspaces/data/cache_claude_search
```

已有本机缓存时，在以上命令末尾加 `--offline` 重放。已禁用网络及 Claude 子进程，逐字节核对 6 个 Stage 3 输出，结果一致，见 [replay_report.json](data/claude_search_pilot/replay_report.json)。首次克隆没有私有缓存，需要实际运行，不能冒充离线重放成功。

```bash
.venv/bin/python workspaces/scripts/summarize_claude_search.py
.venv/bin/python -m unittest discover -s workspaces/tests -v
```

## 实现与证据边界

- `scripts/claude_search.py` 用临时工作目录和配置运行 CLI，不修改全局 Claude 设置；只开放 WebSearch/WebFetch，关闭其他工具、插件发现和 MCP 配置，限制回合数、搜索调用和运行时间。
- `scripts/probe_claude_search.py` 把已准入 Blueprint 交给 CLI 做小规模自主搜索/读取，并保存候选 URL 清单。候选覆盖描述只是模型意见。
- `scripts/search_provider.py` 新增可选 `claude_code` 后端。正式 Stage 3 仍由原 Search Planner 规划查询，Claude Code 执行 WebSearch，原 Candidate Selector 决定下载，Python 继续安全下载、原生解析与独立覆盖检查。
- 只有实际 `WebSearch` 工具结果 `Links` 数组中的 HTTPS URL 能进入候选池。模型最终回答中的 URL、猜测修复的路径和没有配对调用的结果均不采纳。工具输出格式改变时明确失败，不退回从模型回答提取链接。
- `WebFetch` 即使没有 `is_error=true`，也可能返回 HTTP 403/404 文本；这种结果被记录为失败。即使正文摘要返回，也须经过 Python 实际下载与解析，才能进入材料覆盖核验。
- 原始流式日志、请求、缓存及下载字节位于 `data/cache_claude_search/`，不提交 Git。公开报告保留模型配置、CLI 版本、查询、工具 ID、URL、哈希与失败原因，不含 Key。
- `total_cost_usd` 是 CLI 的客户端估计，不是 LLMCenter 账单；实际金额未知。没有额外搜索 Key 不等于没有推理费用。

配置中的 `search.model / api_base / api_key_env` 可调整；默认从 `WORK_SEEDS_API_KEY` 或域名匹配的 llmctl 配置取得现有推理 Key。不自动切换模型或替换现有默认 Tavily 配置。这里测试的是当前具体路由，不保证所有第三方模型/网关均支持这些工具。

[Claude Code 工具文档](https://code.claude.com/docs/en/tools-reference) 区分 WebSearch 与 WebFetch，并说明 WebFetch 通常返回模型处理后的内容；[程序化运行文档](https://code.claude.com/docs/en/headless) 说明 CLI 输出和权限参数。底层网关能力仍以实际日志及独立获取结果为准。

当前应优先改进或排查返回链接的完整性、候选来源质量，以及覆盖审核的节点引用；不能仅因为 CLI 返回成功就扩大生成规模或宣布资料充分。
