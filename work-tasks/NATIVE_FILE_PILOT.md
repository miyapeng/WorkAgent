# 原生文件新任务实验

**当前结果：1 个 Draft Work Task Package。** Stage 3 为 `ready`，Stage 4 的结构和独立语义审核均通过；后续 [Stage 5](STAGE5.md) 已实际执行并生成报告，因事实不一致和评分器漏检保持 `needs_review`，不是 Verified Task，也没有证明多模态必要性。

- Task ID：`TASK_1d5ee1c33b451d320937aaa8`
- 本机任务包：`work-tasks/generated/TASK_1d5ee1c33b451d320937aaa8/`
- Agent 可见副本：`work-tasks/generated/agent-visible/TASK_1d5ee1c33b451d320937aaa8/`，只有 task.json、workspace_init/ 和空 outputs/。
- 正式构造报告：[stage4_report.json](data/native_file_pilot_admission/stage4_report.json)。
- 复现与导出检查：[replay_report.json](data/native_file_validation/replay_report.json)。
- 8 条要求、8 条评分项（7 个语义项，1 个文件可读性检查）、25 个已定位源事实。

## 新任务阅读版

你作为道路安全数据分析人员，需要判断英国交通部 2024 年 STATS19 数据是否适用于伤亡严重程度和碰撞情形分析，提交一份内部数据适用性评估报告。

1. 明确分析范围、目标变量、编码/单位、粒度与质量接受条件。
2. 根据真实记录和字段字典说明三张表如何关联，统计处理和无法匹配的记录。
3. 检查缺失/未知编码、范围、重复键、关联覆盖及分布；解释严重程度调整字段的适用边界。
4. 选择并实际执行适当的统计检查，报告计算结果与无法完成的检查。
5. 给出有依据的适用性判断、限制与修复建议。允许有条件或否定结论。

交付文件：`outputs/stats19_2024_data_fitness_report.md`。以上中文仅供阅读，正式要求以任务包的 task.json 为准，不增加额外约束。

实际生成的委托原文：

> Act as a road safety data analyst preparing an internal data-fitness assessment for the Department for Transport STATS19 2024 road casualty release. Determine whether the supplied 2024 collision, vehicle and casualty tables, read with the code list and severity-adjustment guidance, are fit for an analysis of casualty severity and collision circumstances. Produce the single report specified in the requirements and deliverables below, and restrict conclusions to the supplied 2024 extract.


这次换用 `raw_31_0_7382`（Operations Research Analysts），从官方 Raw Seed 重新规划和联网搜索，没有沿用之前的 HTML 可视化任务。

官方任务原文：

> Define data requirements, and gather and validate information, applying judgment and statistical tests.

## 文件与来源

Stage 3：`workspaces/data/native_file_pilot_retry/WS_e3babe3a48a1/`。

真实案例是英国交通部 DfT STATS19 的 2024 年碰撞、车辆与伤亡记录，配套字段字典和方法/质量说明。较早的 STATS19 Review 仅作制度和质量限制背景，不作为 2024 年实际统计结果。

| 官方原始文件 | 格式 | 独立解析 |
|---|---|---|
| [f_1a60f65f07a44454bc03c63b_dft-road-casualty-statistics-vehicle-2024.csv](https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-vehicle-2024.csv) | CSV | 183,514 条记录 |
| [f_23fc55d06693fda26a6ddb2a_stats-19-review-final-report.pdf](https://assets.publishing.service.gov.uk/media/60ec379ae90e0764c59382bc/stats-19-review-final-report.pdf) | PDF | 34 页，文本解析 |
| [f_32a78f4662e309160f37b1ea_dft-road-casualty-statistics-collision-2024.csv](https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2024.csv) | CSV | 100,927 条记录 |
| [f_51b08606ef3dad1ae5d4c872_dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx](https://assets.publishing.service.gov.uk/media/6ab2a71d997a4b2950cced58/dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx) | XLSX | 实际解析通过 |
| [f_838aad605a6ac638973f0924_dft-road-casualty-statistics-casualty-2024.csv](https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-casualty-2024.csv) | CSV | 128,272 条记录 |
| [f_9a0db9e666e696a8c4e61dd6_dft-road-casualty-statistics-severity-adjustment-figure-guidance.docx](https://assets.publishing.service.gov.uk/media/691c644021ef5aaa6543eef0/dft-road-casualty-statistics-severity-adjustment-figure-guidance.docx) | DOCX | 实际解析通过 |

六个可见文件共 52,391,247 字节，全部 `real_original`；HTML、适配文件、合成文件均为 0。原始文件 SHA-256、原始/最终 URL、获取时间及许可状态保存在 `construction/source_manifest.json`。公开再分发权利尚未在文件证据中确认，因此原始材料不提交 Git。

```text
WS_e3babe3a48a1/
├── workspace_init/
│   ├── tables/
│   │   ├── ...collision-2024.csv
│   │   ├── ...vehicle-2024.csv
│   │   ├── ...casualty-2024.csv
│   │   └── ...data-guide-2025.xlsx
│   └── materials/
│       ├── ...severity-adjustment-figure-guidance.docx
│       └── ...stats-19-review-final-report.pdf
└── construction/              # 不交给 Agent
```

## 审核结果与失败记录

- Stage 2：1 条输入，Schema、Graph、独立语义审核均通过。最初审核请求超时的记录另存于 `work-plans/data/native_file_pilot/initial_transport_failure.json`。
- 自主 Search Agent：实际调用 WebSearch 12 次、WebFetch 22 次。搜索会话完整结束；获取重试复用同一会话，没有将重放计为新搜索。Claude Code 使用的是 LLMCenter GLM-5.2，并非 Claude 模型。
- 首轮获取：三张 CSV 因下载超时/20MB 上限失败，Workspace 为 incomplete。记录保留在 `workspaces/data/native_file_pilot/`。
- 获取重试：单文件上限32MB、120秒，成功获取七个 URL（包含缓存复用，不等于七次新网络请求），其中一个仅为发现附件的网页。六个原生材料全部解析通过，六个保留，一份主 Anchor。
- Stage 3：`ready`。i2 原始观测数据、i3 字段与收集元数据、i4 质量与验证参考三类资料均为 supported，3/3。i1 属于用户委托，由 Stage 4 具体化，不伪造委托文件。
- Stage 4 v5：拒绝 `requirement_evidence_unrelated_to_information`；记录保留在 `work-tasks/data/native_file_pilot/`。这是引用范围错误，不是数据缺失。v6 通过程序提供每个信息节点可用的证据列表、在 Prompt 中明确引用规则；没有改原始数据、Blueprint 或放宽验证规则。
- Stage 4 v6：结构通过，独立语义审核拒绝未充分锚定的跨表关联断言和重复评分。记录保留在 `work-tasks/data/native_file_pilot_v6/`。v7 明确要求区分待验证关系与源事实，并确保每项成果只有一个评分归属；不手工修订模型任务或审核结果。

- Stage 4 v7：两次300秒生成请求均超时；同接口短请求约2秒成功。v8 将长文件上下文显式限定为带位置的摘录，保留每个引用的结构上下文，输入文件与引用准入规则不变。

- Stage 4 v8：首个响应 JSON 语法不合法，原始响应保留；加入最多一次格式重生成后结构通过，但审核存在缺少 source_fact 引用、要求与评分遗漏等问题，未准入。v9 明确了每条审核必须引用源事实、完整对齐指令义务，并向两端提供实际验证器行为与权重计算规则。此前名为 `native_file_pilot_final/` 的目录也是拒绝记录，不是成功任务。

- Stage 4 v9：结构通过，语义审核拒绝不够具体的事实引用及内容要求与文件检查混用。v10 使用短证据句柄并由 Python 恢复原始 ID、编译文件检查；模型遗漏的文件扩展名按已选格式补齐，仍保留原始响应。补齐后审核继续拒绝指令与细则遗漏及格式表述不一致。v11 将 Prompt 整理为单一明确契约：简短委托、单一交付格式、任务要求作为唯一依据，Python 将完整要求纳入对应满分条件。审核仍独立执行。

- v11 的首次语义审核全部判为通过，但旧程序要求“复杂度”等规划审查也引用文件事实，导致 `audit_missing_source_evidence`。已将规划维度与事实维度分开：前者允许引用已准入的需求节点，后者及每条 Task/Rubric 审查仍必须引用源事实；未知或空引用仍拒绝。随后实际重新调用独立审核（reverse-audit-v10），通过全部检查并生成上面的 Draft，没有手改模型判定。
- 最终测试：Stage 3 的71项、Stage 4 的49项通过。禁用网络和外部进程后，Stage 2 Blueprint、Stage 3 的15个文件、Stage 4 的12个文件可从缓存逐字节重放。Agent 导出只有7个可见文件，无隐藏评分目录。

以上是开发迭代记录，不是无调参的生成成功率实验。

资料的专业适用性由模型判断，实际字节、位置与引用由程序核验。同一模型的独立审核不等于专家认证。当前没有证明多模态必要性，也没有执行教师 Agent 或 Probe。

## HTML 排除与大文件边界

网页只用于搜索、跟踪附件链接和保留来源，不能进入证据候选集或 Agent 可见目录。覆盖审核、组装、Stage 4 入口和 Agent 导出都有 HTML 禁入检查；内容识别也会拒绝将 HTML 改名为 TXT 等伪装。没有通过打印网页为 PDF 绕过限制。

CSV 解析逐行遍历完整数据，检查结构并计算解析元数据；私有定位索引只保留前1024条记录。Stage 4 构造上下文明示提供表头、前12条记录及引用记录邻域；每文件上下文上限5万字符，长 XLSX 保留引用行及前后两行、各 Sheet 表头，长 PDF 保留引用所在完整页面，其余内容明确标为摘录。必需引用上下文超限会报错，不截断引用。摘录不是代表性样本或数据质量结论；执行 Agent 收到全部原始记录，负责完整验证。报告中没有把模型看到部分记录说成逐条审核全表。

## 运行

仓库根目录，沿用现有 `.venv`、Claude Code 和本机 llmctl 凭证，不在参数或文件内保存 Key：

```bash
.venv/bin/python work-plans/scripts/plan_intents.py \
  --config work-plans/config/native_file_pilot.json \
  --output-dir work-plans/data/native_file_pilot

.venv/bin/python workspaces/scripts/construct_workspace.py \
  --plan-dir work-plans/data/native_file_pilot \
  --config workspaces/config/native_file_pilot.json \
  --output-dir workspaces/data/native_file_pilot_retry \
  --cache-dir workspaces/data/cache_claude_agent

.venv/bin/python work-tasks/scripts/construct_tasks.py \
  --config work-tasks/config/native_file_pilot.json \
  --plan-dir work-plans/data/native_file_pilot \
  --workspace-dir workspaces/data/native_file_pilot_retry \
  --report-dir work-tasks/data/native_file_pilot_admission
```

同一输入和缓存追加 `--offline` 重放。更改代码或配置应使用新的报告目录。无缓存时，离线模式会明确失败，不会模拟联网成功。网上原始字节可能变化，跨机器严格复现必须保留下载和模型缓存。
