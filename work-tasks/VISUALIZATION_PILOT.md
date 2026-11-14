# 历史实验：含 HTML 的可视化任务（已停止准入）

**此样例含原始 HTML，已不符合当前原生文件政策。历史文件与审核记录保留用于复查；新的 Stage 4 校验和 Agent 导出会拒绝它，不应计入当前合格任务。**

本次使用 `raw_31_0_21828`（Data Scientists），没有复用此前项目进度监控、NTIA 或 IT Dashboard 材料。官方原文保持不变：

> Create graphs, charts, or other visualizations to convey the results of data analysis using specialized software.

结果：**1 个 ready Workspace，1 个通过结构检查和独立模型审核的 draft Task Package**。没有执行 Stage 5 Probe，没有生成教师轨迹，没有证明多模态输入必要性。搜索、选案例、生成任务与语义审核均由配置的模型运行；开发者修正通用程序及 Prompt，没有手工挑换本例文件、改任务内容或改审核结论。

## 查看产物

- [最终任务 JSON](generated/TASK_242543866a170e54e3edc6d1/task.json)
- [初始文件](generated/TASK_242543866a170e54e3edc6d1/workspace_init/)
- [Rubric](generated/TASK_242543866a170e54e3edc6d1/evaluation/rubric.json)
- [Verifier 配置](generated/TASK_242543866a170e54e3edc6d1/evaluation/verifier_spec.json)
- [综合实验报告](data/visualization_pilot_complete/experiment_report.json)
- [Stage 4 准入报告](data/visualization_pilot_complete/stage4_report.json)
- [Blueprint](../work-plans/data/visualization_pilot/blueprints.jsonl)
- [来源清单](../workspaces/data/visualization_pilot_final/WS_df663f328a47/construction/source_manifest.json)
- [覆盖审核](../workspaces/data/visualization_pilot_final/WS_df663f328a47/construction/information_coverage.json)

任务概述：面向劳动力市场分析人员，用加拿大 2026 年 10 月劳动力调查资料制作图表 PDF，呈现相关月度、年度变化，准确表达单位、时期、季节调整口径。最终交付路径是 `outputs/labour_force_visualizations.pdf`。完整要求以 task.json 为准；这里没有提供完成后的图表或参考答案。

## 实际数量与边界

| 环节 | 结果 |
|---|---|
| Raw Seeds / Blueprint | 1 / 1，通过独立审核 |
| 唯一真实搜索会话 | 13 WebSearch，20 WebFetch，34 turns；未配置轮数上限 |
| Python 获取 | 20 次获取尝试，14 个 URL 下载成功（包括导航页及后续拒绝文件） |
| 解析并准入 | 5 份：4 个正式 HTML 结果表、1 份原生 CSV |
| 必需检索输入覆盖 | i1：supported，1/1；i2 属于 task_instruction，由 Stage 4 明确受众与目的 |
| 合成文件 | 0 |
| Task / Rubric | 7 条要求，7 条评分项：6 semantic、1 programmatic |
| 确定性验证器 | 检查交付 PDF 的存在、声明格式与可解析性；不把它当作图表正确性证明 |
| 状态 | Stage 3 ready；Stage 4 draft；Stage 5 未执行 |

数据来自同一个 Statistics Canada 发布案例。正式 HTML 表是实际资料，不是把搜索摘要充作证据；Agent 也沿真实链接找到原生 CSV。下载端点的 `.action` 后缀被按实际解析格式补上 `.csv`，字节和 SHA-256 保持原样。

来源入口：[Labour Force Survey, October 2026](https://www150.statcan.gc.ca/n1/daily-quotidien/261106/dq261106a-eng.htm)、[Table 14-10-0287-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410028701)。精确下载地址、最终 URL、哈希及获取时间见来源清单。许可仍为 unknown；实际源文件和任务包保存在本地并被 Git 忽略，不视为可公开再分发的数据集。

完整历史 ZIP 超过大小限制，被拒绝。另有 4 份带标题/脚注的官方 CSV 未通过现有矩形 CSV 解析器；它们没有被用来证明覆盖。这是保留的解析器限制，不代表文件伪造。

## 开发中发现并保留的失败

- `workspaces/data/visualization_pilot/`：实际搜索完成，但 JSON 前有说明文字，旧解析器拒绝。现接受唯一的 JSON 代码块，多个代码块仍拒绝。
- `workspaces/data/visualization_pilot_inspected/`：Anchor 文件列表与角色不一致，审核被拒绝。v3 Prompt 明确字段关系与口径检查，重新调用模型审核同一批资料；没有改原响应。
- `work-tasks/data/visualization_pilot_v4/`：旧任务未明确受众、评分重叠，审核还混入错误类型的引用 ID；未准入。
- `work-tasks/data/visualization_pilot_task/`：审核抓到工资值被误写为工时值，拒绝。v4 生成器获得完整解析上下文，避免只看与表头分离的数字片段；没有手工修改那条评分项。
- `work-tasks/data/visualization_pilot_context/`：完整审核输入导致两次接口超时。压缩重复 JSON 表达但保留全部位置与原文后，重新审核同一份已生成任务，最终通过。
- 其他 `visualization_pilot_*` Stage 4 报告保留了入口备注处理、上下文大小及目录句末标点等工程失败。模型原始响应按请求哈希保存在忽略目录的缓存中。

这是一次经过开发调试的单例实验，**不能据此声称无人干预批量成功率为 100%**。多次重放引用同一个搜索会话，不能将 13/20 的日志计数累加成新搜索。CLI 搜索费用只是估计，LLMCenter 实际账单未核实。

## 复现

在仓库根目录，使用本机 llmctl 凭证：

```bash
.venv/bin/python work-plans/scripts/plan_intents.py \
  --config work-plans/config/visualization_pilot.json \
  --output-dir work-plans/data/visualization_pilot

.venv/bin/python workspaces/scripts/construct_workspace.py \
  --plan-dir work-plans/data/visualization_pilot \
  --config workspaces/config/visualization_pilot.json \
  --output-dir workspaces/data/visualization_pilot_final \
  --cache-dir workspaces/data/cache_claude_agent

.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --config work-tasks/config/visualization_pilot.json \
  --plan-dir work-plans/data/visualization_pilot \
  --workspace-dir workspaces/data/visualization_pilot_final \
  --report-dir work-tasks/data/visualization_pilot_complete
```

相同缓存下，各命令追加 `--offline`。已经实际在禁用 socket 连接和子进程调用的条件下重放三个阶段，30 个当时的产物文件内容完全一致。跨机器重放需要同步原始字节与模型缓存；仅 clone Git 仓库不会取得许可未知的文件。

测试：Stage 2 21 项、Stage 3 66 项、Stage 4 37 项通过。合成单元测试不计入上述真实样本数量。

## 与目标流程图的关系

现已演示 Seed → Semantic Plan → Graph → 自主搜索与页面探索 → 实际文件 → Coverage → Ready Workspace → Task/Rubric/Verifier。仍需区分：

1. 真实资料齐全时直接进入一致性检查，无需强制经过合成。
2. Python 覆盖审核结果自动回传 Search Agent 的跨阶段缺口循环，以及真实 Anchor + 受控补充，尚未完整接入本条路线。
3. Benchmark 应从独立留出的已准入任务构建；多模态验证任务是其子集。这里产出图表，但没有证明输入需要视觉推理。
