# Stage 2 · Raw Seed → Work Blueprint

默认入口改为 Stage 1 的官方 Raw Seeds。`task_text` 只作为原始输入，程序和模型都不得修改；历史 `work_demand` 不再是入口。本模块只生成职业工作目标、交付物和信息依赖，不生成最终用户指令、实际案例、文件或答案。

## 运行

在仓库根目录执行：

```bash
.venv/bin/python -m pip install -r workspaces/requirements.txt
# 默认选择配置中明确列出的 10 条真实 Seed，实际调用 GLM-5.2
.venv/bin/python work-plans/scripts/plan_intents.py
# 完整 Stage 2–3；没有搜索 Key 时保存 awaiting_search
.venv/bin/python workspaces/scripts/run_pipeline.py --limit 10
# 本机已有响应缓存时，禁止新模型请求
.venv/bin/python work-plans/scripts/plan_intents.py --offline
.venv/bin/python -m unittest discover -s work-plans/tests -v
```

CLI 支持 `--input-file`、`--output-dir`、`--cache-dir`、`--config`、`--limit`、`--offline`。默认输入是 `work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl`；所有输入记录必须与当前完整官方派生池逐字段一致。配置中的 `pilot_seeds` 固定 Pilot ID 和选择理由；如需处理输入顺序中的其他记录，使用自己的配置并移除该列表，再指定 `--limit`，不要默认全量运行。

模型配置复用 `work-seeds/config/seed_pipeline.llmcenter.json`。`config/blueprint_pilot.json` 覆盖 temperature=0、JSON 响应格式与 token 上限。网关 accessId 为 `GLM_ka48dn`，响应报告模型 `glm-5.2`。可通过 `WORK_SEEDS_API_KEY` 提供 Key；配置明确选择 `credential_source: llmctl` 时，也可读取本机 llmctl 已保存、域名匹配的推理 Key。Key 不写入报告或缓存。

## 流程与质量边界

1. 版本化 Generator 从原文反推自然交付物、必要分析及前提，输出 Blueprint。
2. JSON Schema 和程序检查唯一 ID、依赖引用、DAG、外部根节点、交付物终点、所有节点服务于输出、多模态标记关系。
3. 独立 Reviewer 调用检查职业意图、交付物、前提、依赖、最小性、多模态依据和案例中立性；不修改或自动修复计划。
4. 只有结构及语义审核都通过的记录进入 `blueprints.jsonl`。其余响应和失败原因保留在报告。

信息节点类型为 `external_input / derived_information / professional_judgment`。外部输入区分 `task_instruction / workspace / external_reference`：用户可以提供的工作要求不等于需要搜索的真实文件。Stage 3 只检索后两类。`critical` 表示必需输入；`modality_hypotheses` 仅是待验证假设，文件格式不证明多模态必要性。

Schema 不能判定专业语义；同一模型的独立审核也不是专家认证。程序不以人工判断覆盖模型结果。当前 Reviewer 对简短职业任务的范围解释可能需要后续校准，拒绝记录按原样保留。

## 文件

- `scripts/plan_intents.py`：原始 Seed 校验、生成、图检查及审核。
- `scripts/planning_common.py`：复用原有模型调用，增加离线缓存检查、Schema 校验和用量汇总。
- `config/blueprint.schema.json`、`review.schema.json`：结构约束。
- `prompts/blueprint_generator.v2.txt`、`blueprint_reviewer.v1.txt`：实际使用的 Prompt。
- `data/generated/blueprints.jsonl`：本轮正式准入的 2 条 Blueprint。
- `data/generated/planning_report.json`：10 条完整尝试、失败原因、输入/输出哈希、Prompt/模型参数、生成时间、token 用量。
- `data/cache_graph/`：本机原始响应和断点缓存，不提交 Git。缓存按输入、Prompt、Schema 和代码版本区分；中断后重复命令即可。

固定输入、配置、Prompt 和缓存可以重放相同结果；temperature=0 不保证重新联网调用逐字相同。新克隆没有私有响应缓存，不能假装离线复现模型生成：可直接阅读已提交结果；完整离线重放需保留原缓存。

## 本轮实测

10 条均实际生成；5 条通过图结构检查；其中 2 条通过独立审核（占全部输入 20%，占已审核 40%）：汽车工程文档维护 `raw_31_0_16425`、法规参考资料识别 `raw_31_0_21094`。软件数据、GIS、预算 3 条被语义审核拒绝；其余 5 条存在 Schema/图问题。未降低门槛，也未人工改判。

初始 Generator v1 的 10 条开发尝试保存在 `archive/data/raw_blueprint_v1/`。v2 只加强 JSON 字段、图及模态对应的输出说明，保留相同职业意图与审核门槛。两轮不合并统计成功率。[完整实验报告](../workspaces/data/generated/experiment_summary.json) 与 [三条完整记录](../workspaces/data/generated/examples.md) 展示实际失败和搜索阻断。

## 历史接口

旧计划、配置、脚本和测试已移入 `archive/`，只是历史快照，不是当前可独立运行的兼容实现。需要原环境时请检出提交 `5e61eae`。新接口是 `raw-blueprint-v1`，旧 `work_plans.jsonl` 和历史职业证据输入不再默认读取。Stage 4 尚未迁移，不能直接消费这批 Blueprint。方法依据及本项目设计见 [METHODS.md](../workspaces/METHODS.md)。
