# Stage 2 · Semantic Planning → Python Graph Compilation

默认流程：**官方 Raw Seed → LLM 语义规划 → Python 组装 Graph → 结构校验 → 独立语义审核**。原始 O*NET `task_text` 不改写；Stage 1 数据保持不变。

模型只输出 `objective + deliverable + inputs + operations`。Python 分配 `i1…`、`out1`，把明确的名称引用转换为依赖边。交付物也必须声明 `requires`，程序不猜测输出依赖、不修复环路、不增加专业前提。

## 当前实测结果

对与旧版完全相同的 10 条 Seed，实际调用 GLM-5.2：

| 指标 | 旧版直接输出 Graph | 新版语义规划 + Python |
|---|---:|---:|
| 结构通过 / 全部输入 | 5/10（50%） | 6/10（60%） |
| 语义审核通过 / 全部输入 | 2/10（20%） | 5/10（50%） |
| 语义审核通过 / 尝试审核 | 2/5 | 5/6 |

本轮 4 条因输入类别或格式约束失败；另 1 条审核响应无法解析为 JSON，不算语义拒绝，但不能准入。没有自动修复或人工改判。5 条准入计划分别是网络项目进度/预算、建筑图纸合规、GIS 图形化地籍记录、实验数据报告、游戏设计文档。1 条含视觉依赖假设，尚未检索文件或验证视觉必要性。

[逐条对照及真实示例](data/semantic_pilot/comparison.md) / [机器可读对照](data/semantic_pilot/comparison_report.json)。这是同一批 10 条的小样本比较，不能证明全量职业任务的质量提升。审核仍使用原来的七项标准和 Reviewer Prompt；同模型独立审核不是专家认证。

## 语义格式

这是结构说明，不是新增的真实 Seed：

```json
{
  "objective": "Compare recorded amounts with a requested baseline.",
  "deliverable": {
    "kind": "direct_answer",
    "description": "Explain differences using the supplied records.",
    "preferred_formats": [],
    "requires": ["compare_amounts"]
  },
  "inputs": [
    {"name": "recorded_amounts", "kind": "table", "description": "Recorded amounts", "source": "workspace", "preferred_formats": ["csv", "xlsx"]},
    {"name": "baseline", "kind": "table", "description": "Requested baseline amounts", "source": "workspace", "preferred_formats": ["xlsx"]}
  ],
  "operations": [
    {"name": "compare_amounts", "type": "derived_information", "description": "Calculate and interpret differences", "requires": ["recorded_amounts", "baseline"]}
  ]
}
```

`source` 区分 `task_instruction / workspace / external_reference`。`text_instruction` 对应用户直接提供的请求范围，不可用来虚构业务事实。默认所有列出的输入 `critical=true`；只有模型明确说明是可选信息时才写 `false`。缺失的输入不会由 Python 补充，专业前提是否充分仍由独立审核判断。

`operations.type` 是 `derived_information` 或 `professional_judgment`，描述待执行的工作，不保存已知答案。依赖只允许引用输入或操作的唯一名称，所有节点必须服务于交付物。当前 Pilot 采用一个主要交付物；如果原始职业任务确实必须有多个不可合并的独立交付物，应返回规划失败，不通过删减职业活动迁就 Schema。

## 类型、格式和模态分别处理

固定词表在 [artifact_vocabulary.json](config/artifact_vocabulary.json)。

| 输出 kind | 候选格式 |
|---|---|
| direct_answer | `[]`，直接回答 |
| report | pdf / docx / md / txt / tex |
| spreadsheet | xlsx / csv |
| presentation | pptx / pdf |
| code_notebook | py / ipynb / js |
| visual_design | png / jpg / svg / pdf |
| structured_data | json / csv |
| document_revision | docx / pdf / md / tex |

| 输入 kind | 候选格式 |
|---|---|
| text_instruction | `[]`，直接文本 |
| document | pdf / docx / md / txt / tex |
| table | csv / xlsx |
| image | png / jpg / jpeg / tiff |
| diagram | svg / png / pdf |
| code | py / js / ipynb |
| structured_data | json |

`preferred_formats` 是可替代的规划偏好，不是要同时创建所有格式，也不表示材料已经存在。空列表只允许用于 Direct Answer / Text Instruction，其他种类须至少给一个合法偏好。输入与输出的 Structured Data 词表不同；错误的类别/格式组合直接记录失败，不删改偏好来凑通过率。

Stage 2 推荐格式，Stage 3 根据实际字节记录输入格式，Stage 4 决定最终交付要求。Direct Answer 可以需要复杂分析和跨文件推理，不必额外生成报告。没有强制 XLSX/PPTX/PNG 比例；TEX 是源文件，本阶段不编译 LaTeX。

非文本信息需求使用可选对象，例如：

```json
{"modality_dependency": {
  "modality": "visual_spatial",
  "information_needed": "Relative positions of components in the engineering drawing",
  "required_operation": "Interpret spatial relationships before checking design conflicts",
  "supports": "check_design_conflicts"
}}
```

`modality` 仅允许 `visual / visual_spatial`；`supports` 必须指向确实依赖该输入的操作。Python 只转换名称并标记 `unretrieved / hypothesis`，不会从 PNG/PDF 或 input kind 推断视觉必要性。未提出依赖时，编译图的 `modality_candidates=[]`，表示没有声明额外感知假设，不是已经证明仅需文本。音频、视频不在当前范围。

## 运行与保存位置

在仓库根目录：

```bash
.venv/bin/python -m pip install -r workspaces/requirements.txt
.venv/bin/python work-plans/scripts/plan_intents.py --limit 10
# 有原始响应缓存时重放，不新增模型调用
.venv/bin/python work-plans/scripts/plan_intents.py --limit 10 --offline
.venv/bin/python work-plans/scripts/compare_planning.py
.venv/bin/python -m unittest discover -s work-plans/tests -v
```

- `data/semantic_pilot/blueprints.jsonl`：当前 5 条准入的标准 Graph，含候选格式。
- `data/semantic_pilot/planning_report.json`：10 条原始语义响应、编译结果、失败原因、审核及模型用量。每条的 `semantic_plan` 就是简化 JSON。
- `data/semantic_pilot/comparison_report.json`、`comparison.md`：相同 Seed 哈希核对、前后通过率、失败明细和实际示例。
- `data/cache_graph/`：原始模型响应与断点缓存，不提交 Git。固定输入、Prompt、配置和缓存时可重复生成相同结果；新克隆没有缓存，需要重新调用模型。

CLI 支持 `--input-file --output-dir --cache-dir --config --limit --offline`。固定 Pilot ID 在 `config/blueprint_pilot.json`；使用其他输入时在自定义配置中移除 `pilot_seeds`。模型仍复用现有 LLMCenter accessId `GLM_ka48dn`，temperature=0。Key 来自 `WORK_SEEDS_API_KEY` 或域名匹配的本机 llmctl 配置，不写入报告。

主要实现：`scripts/compile_blueprint.py`、`scripts/plan_intents.py`、`config/semantic_plan.schema.json`、`config/blueprint.schema.json`、`prompts/semantic_planner.v1.txt`。Reviewer 继续使用 `blueprint_reviewer.v1.txt`。不增加 Agent、辩论或自动修复环节。

旧 `data/generated/` 保留上轮直接 Graph Pilot，作为对照，不再是默认入口。更早的历史数据仍在 `archive/`。新接口标记为 `raw-blueprint-v2`；Stage 3 已改为读取 `data/semantic_pilot/`，旧 Stage 4 仍未迁移。本次没有重做 Stage 3 搜索或生成新的 Workspace。
