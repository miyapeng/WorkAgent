# Stage 1 · Official Raw Work Seed Construction

默认 Stage 1 现在是：

```text
O*NET 31.0 → Emerging Tasks 合并 → Digital Task Filtering
→ Coverage-aware Sampling → Raw Work Seeds（官方原文）
```

本阶段只筛选与采样。`task_text` 从官方 CSV 逐字保留；不生成、改写或扩写 `work_demand`。LLM 只分类最终有效的 Emerging Tasks。历史职业证据检索和 Work Demand enrichment 保留在 [STAGE1_LEGACY.md](STAGE1_LEGACY.md)，已有代码与实验结果不覆盖。Stage 2–7 本次不改；它们仍使用原有历史 Seed 类型，不自动接入新的 Raw Seeds。

## 输入与来源

复用 `build_onet.py` 的原始 CSV 解析、四表验证，`sample_seeds.py` 的目录关联和采样器，`filter_digital.py` 的 AI4Work 精确匹配，以及 `construct_seeds.llm_call` 的 GLM 接口和原始响应缓存。新增 `emerging_tasks.py` 只承担合并与分类辅助逻辑，没有另一套 CLI 或服务。

- 普通数据：`data/raw/` 原始三份 CSV、`data/processed/` 四张规范化表；构建前逐字节核验既有底表。
- Emerging：同版本官方 [31.0 字典](https://www.onetcenter.org/dictionary/31.0/csv/emerging_tasks.html)及 [CSV](https://www.onetcenter.org/dl_files/database/db_31_0_csv/emerging_tasks.csv)，原始字节保存在 `data/raw/emerging_tasks.csv`，独立清单为 `emerging_source_manifest.json`。原有三文件清单保持不变。
- 普通任务标签：固定提交的 [AI4Work XLSX](https://github.com/zorazrw/ai4work-resources/blob/095db006debf83f2bbda2631964bd1b4c81190ad/real_work/employment/digital_task_annotation.xlsx)，仍校验原有 SHA-256。只有 Task ID、职业代码、原文完全匹配才继承标签。

官方 Emerging 表的八列为 `O*NET-SOC Code, Title, Task, Category, Original Task ID, Original Task, Date, Domain Source`，没有独立 Emerging Task ID。字典说明这些是为未来数据采集提出的新/修订任务。**将 Revision 替换到有效池是本项目的派生政策，不表示官方 Task Statements 已被更改。**

许可及商标声明沿用 [README](README.md)：O*NET 原始文本按 CC BY 4.0 使用，USDOL/ETA 未批准或认可本项目。AI4Work 标注的出处与权利状态单独适用。

## New / Revision 处理

1. 仅移除八个字段完全相同的 Emerging 重复行；不做语义合并。
2. New 直接加入。Emerging ID 使用 `emerging_31_0_` 加官方整行内容的 SHA-256 前 24 位，标为内部 ID；不伪称官方 Task ID。
3. Revision 必须通过 Original Task ID 找到旧任务，再核对职业和非空 Original Task 原文。有效 Revision 取代旧任务，保留 `original_task_id`。
4. 同一旧任务有多条 Revision 时，按官方 `MM/YYYY` 日期取唯一最新记录。相同最新日期有多个不同记录时，不任意选取；该组修订及旧任务均隔离，保留冲突报告。
5. 找不到原 Task 的 Revision 记 unresolved，不用文本相似度匹配。存在 ID 但职业或旧文本矛盾时也记录问题并隔离该 ID；不猜测修复关系。
6. 替换先于数字化分类。Revision 被判为 PHYSICAL 或 UNCERTAIN 时，旧 DIGITAL 也不会恢复。
7. 普通任务保留官方 DWA 映射；Emerging 没有独立官方映射，`dwa_ids=[]`。不把旧 Task 的 DWA 或 Core/Supplemental 自动继承给修订文本。

原始 CSV 不修改。无效字段、职业关联、日期格式及冲突的普通主键直接报错，不生成替代记录。

## 数字化分类

未修改普通任务直接复用 AI4Work：DIGITAL 纳入，PHYSICAL 不纳入，缺失/未知/REVIEW/不匹配转为本项目待审核 UNCERTAIN。`source_metadata.digital_annotation` 保留上游行号及匹配规则；原标签与最终标签不同时才额外保存 `original_label`，方便区分原始标签与本项目保守处理。

Emerging 的有效 New/Revision 单独调用 GLM-5.2。输入为职业、官方原文、类型、Revision 旧文本和来源说明；输出只允许 `task_id, digital_label, reason`，返回任务文本、多余字段、遗漏 ID 或非法标签会报错。接口不接受模型生成的 Seed 内容。

[AI4Work README](https://github.com/zorazrw/ai4work-resources/blob/095db006debf83f2bbda2631964bd1b4c81190ad/real_work/README.md)说明其逐任务 DIGITAL/PHYSICAL 标注与职业数字任务比例，但未给出完整标注协议。本次检查了说明及 XLSX 的 Reason：部分 PHYSICAL 判断包含现场人际活动。可获得的信息写入 `config/emerging_classification_guidance.json`。模型使用本项目操作性定义，不声称完全复现 AI4Work：

- DIGITAL：完整任务的主要工作成果可通过数字信息处理或软件完成，不要求执行真实物理动作。
- PHYSICAL：完成原任务本身必需物理操作，不能用其中的规划/汇报部分代替整个任务。
- UNCERTAIN：描述不足、数字/物理边界不明确或存在争议。

不因使用无人机、图像等就把物理任务判为数字任务，不假设机器人、物理代理或模拟环境可以代替原任务。标签是候选判断，不是数字可执行性的事实认证。

## 采样规则与取舍

仍以 Task ID 为独立单位，复用现有贪心采样器；仅 Raw 模式开启来源覆盖收益。按以下顺序比较：

1. 是否新增 SOC 大类；
2. 是否新增具体职业；
3. `是否新增至少一个官方 DWA + 是否新增任务来源`，各贡献一分；
4. 平分时先覆盖尚未出现的来源，再比较新增 DWA 个数；
5. 职业、大类、来源已选次数更少者优先；
6. 沿用 Core/Supplemental 的末级平局偏好；
7. 固定 `SHA256(seed + task_id)` 打破最后平局。

来源分为 regular、emerging_new、emerging_revision。这里有意将 DWA 与来源作为同一层的边际覆盖目标：严格把 DWA 数量排在来源前面，实际试跑会使 200 条样本全部来自普通任务。当前规则让无官方 DWA 的任务通过新增来源获得覆盖收益，**没有虚构 DWA、没有固定 Emerging 比例，也没有每职业配额**。来源已覆盖后这项收益消失；DWA 覆盖和职业分散仍参与选择。样本结果不保证每次各来源数量相同。

## 运行与复现

在仓库根目录执行；默认 N 由 `--n` 显式指定，本轮为 200：

```bash
# 已有官方底表；仅在缺 Emerging 文件时下载同版本官方 CSV
.venv/bin/python work-seeds/scripts/sample_seeds.py \
  --n 200 --seed 42 --download-emerging --prompt-api-key

# 使用本地官方 Emerging 文件
.venv/bin/python work-seeds/scripts/sample_seeds.py \
  --n 200 --seed 42 --emerging-file /path/to/31.0/emerging_tasks.csv

# 本机已保存模型响应：离线生成完全相同的四个输出
.venv/bin/python work-seeds/scripts/sample_seeds.py --n 200 --seed 42 --offline

# 独立新输出目录
.venv/bin/python work-seeds/scripts/sample_seeds.py --n 200 --seed 42 \
  --offline --output-dir /tmp/workagent-raw-seeds-replay

.venv/bin/python -m unittest discover -s work-seeds/tests -v
```

配置默认复用 `config/seed_pipeline.llmcenter.json` 的 LLM 参数、Endpoint 和 accessId。凭证仅来自环境变量 `WORK_SEEDS_API_KEY` 或隐藏输入，不写入仓库。默认每批 16 个 Emerging、4 个并行 HTTP 请求；`--batch-size`、`--workers` 可调整。并行的是独立分类批次，没有多 Agent 辩论。

原始模型响应位于 `data/raw_seed_cache/llm/`，不进 Git；中断后相同请求复用缓存。缺缓存的 `--offline` 会明确失败，不补 UNCERTAIN 掩盖网络或接口错误。请求/格式失败写入私有 `last_failure.json` 并终止，不发布新的正式结果。重新调用模型或改变批次大小可能改变分类；科研复现应固定输入、Prompt、模型配置和缓存。

旧 Task ID 基线可显式运行，不覆盖其历史输出：

```bash
python work-seeds/scripts/sample_seeds.py --mode task-id --n 200 --seed 42
```

历史 `construct_seeds.py` 仍可明确调用，但输出是派生 Work Demand，不属于本次默认 Stage 1，也不是 Raw Seeds。

## 四个输出

输出目录 `data/raw_work_seeds/`：

| 文件 | 用途 |
|---|---|
| `effective_tasks.jsonl` | 合并后的全部有效 Task，包含三类数字标签；冲突与 unresolved 在报告隔离 |
| `digital_task_pool.jsonl` | effective pool 中 DIGITAL 的子集 |
| `sampled_raw_seeds.jsonl` | 固定参数采样的官方原文记录；没有 Work Demand 改写 |
| `stage1_report.json` | 来源、合并账目、冲突、标签数量、23 大类前后分布、采样、模型调用与代码哈希 |

三个 JSONL 使用同一精简格式：

| 字段 | 用途 |
| --- | --- |
| `seed_id` | 稳定、带版本的 Raw Seed ID，例如 `raw_31_0_3398`；Emerging 为 `raw_31_0_emerging_<原有哈希>`，不重复版本前缀 |
| `work_domain` | 由职业代码前两位查表得到的官方 SOC 大类名称，不是 LLM 推断的行业标签 |
| `occupation_code`, `occupation_title` | 保留完整 O*NET 职业代码及官方名称 |
| `task_id`, `task_text` | 原有 Task ID 与未经改写的官方原文；Emerging 保留既有稳定内部 Task ID |
| `task_source` | `regular` / `emerging_new` / `emerging_revision` |
| `original_task_id` | 仅 Revision 保存，其他类型不输出空字段 |
| `dwa_ids` | 官方关联；Emerging 无官方映射时保留空数组 |
| `digital_label`, `digital_label_source` | 候选分类及 AI4Work / LLM 来源 |
| `source_metadata` | CSV 记录位置、日期、Domain Source；非空的 Task Type；分类行号/规则或模型理由 |

例如 `13-2031.00` 保留为完整职业代码，`occupation_title` 为 `Budget Analysts`，`work_domain` 为 `Business and Financial Operations Occupations`，而不是自行缩窄成 Finance。23 个大类名称来自 [BLS 2018 SOC](https://www.bls.gov/soc/2018/major_groups.htm)，固定查表文件为 `config/soc_major_groups.json`，其来源与哈希写入报告。

精简的是重复元数据，不改变任务文本、任务身份、标签或采样顺序：

- 数据版本、源文件映射、来源 URL 和 SHA-256 放在统一报告中。普通记录对应 `task_statements.csv`，Emerging 对应 `emerging_tasks.csv`；`source_metadata.row` 是含表头的 CSV 记录序号，不是物理文本行号。
- Category、ID 类型及 DWA 映射说明可由 `task_source` 和报告得到，不逐条重复。
- 模型请求哈希、模型参数和时间放在报告 `model_calls` 中，通过 `task_ids` 关联；每条 Emerging 仍保留分类理由。
- 上游标签等于 `digital_label` 时不重复保存；不同时保留 `original_label`。没有 Task Type 时省略，不推测填充。

这是输出格式调整，已有 LLM 请求和缓存键保持不变。离线重建不需要重新分类。

## 实际全量运行

- 普通任务 18,838 条；Emerging 338 条，New 292、Revision 46；完全重复行 0。
- Original Task ID 缺失关联 0；旧文本/职业不匹配 0。
- 成功替换 44 个旧任务。另有旧 Task `21211` 的两条 Revision 同为 `08/2020`，位于 Emerging CSV 记录 323、326：一个描述涂釉，一个描述调制釉料。未确认这是拆分还是互斥修订，因此不猜测版本规则，该组和旧任务隔离。
- 有效数为 `18,838 − 44 − 1 + 44 + 292 = 19,129`，涉及 923 个有任务职业。
- 实际调用 GLM-5.2 分类 **336 个有效 Emerging，21 批**。普通任务 LLM 分类调用为 0；冲突的两条修订未送去分类。每批真实模型 ID、Prompt 版本、参数、时间和请求哈希已保存。

| 有效来源 | DIGITAL | PHYSICAL | UNCERTAIN |
|---|---:|---:|---:|
| 未修改普通任务 | 5,636 | 8,783 | 4,374 |
| Emerging New | 93 | 140 | 59 |
| Emerging Revision | 16 | 18 | 10 |
| 合计 | **5,745** | **8,941** | **4,443** |

数字池覆盖 **749 个职业、22 个有 Task 的 SOC 大类、1,167 个官方 DWA**。N=200、seed=42 的样本覆盖 **200 个职业、22 大类、458 个 DWA**，来源为 **198 regular、1 New、1 Revision**；这个来源分布是采样结果，不是预设配额。

### 23 个 SOC 大类的实际前后分布

“筛选前”是完成 Revision 合并、冲突隔离后的有效池。军事大类 55 在普通 Task Statements 与 Emerging 中都没有任务，因此前后均为 0，不是被数字筛选删除。

| SOC | 原普通 Task | 合并后/筛选前 | DIGITAL | 采样 |
|---|---:|---:|---:|---:|
| 11 | 1,213 | 1,227 | 631 | 16 |
| 13 | 988 | 999 | 607 | 16 |
| 15 | 770 | 776 | 685 | 17 |
| 17 | 1,237 | 1,267 | 660 | 16 |
| 19 | 1,236 | 1,269 | 597 | 16 |
| 21 | 295 | 299 | 86 | 8 |
| 23 | 124 | 127 | 56 | 3 |
| 25 | 1,636 | 1,659 | 641 | 14 |
| 27 | 806 | 816 | 242 | 13 |
| 29 | 1,729 | 1,759 | 450 | 16 |
| 31 | 347 | 352 | 53 | 5 |
| 33 | 519 | 536 | 97 | 9 |
| 35 | 320 | 327 | 13 | 1 |
| 37 | 164 | 167 | 16 | 1 |
| 39 | 617 | 635 | 58 | 6 |
| 41 | 427 | 434 | 138 | 9 |
| 43 | 975 | 981 | 336 | 13 |
| 45 | 225 | 230 | 8 | 1 |
| 47 | 1,140 | 1,151 | 57 | 5 |
| 49 | 1,016 | 1,034 | 95 | 5 |
| 51 | 2,140 | 2,159 | 120 | 5 |
| 53 | 914 | 925 | 99 | 5 |
| 55 | 0 | 0 | 0 | 0 |

### 四条实际采样的 Raw Work Seed

以下英文直接来自官方原文，不是模型生成。完整记录及标签理由见 `sampled_raw_seeds.jsonl`。

- `21128` · regular · 25-1123.00 English Language and Literature Teachers, Postsecondary

  > Schedule courses.

- `18077` · regular · 47-4011.01 Energy Auditors

  > Calculate potential for energy savings.

- `emerging_31_0_ba5e1a2bbed25532730fcf1b` · emerging_new · 25-4011.00 Archivists

  > Write grants and apply for funding to support archival work.

- `emerging_31_0_62f61680a2994ed33e778fcc` · emerging_revision · 11-3013.00 Facilities Managers

  > Plan, create, and manage budgets for contracts, equipment, and supplies.

  Original Task ID：`21280`；当前标签来源：LLM。

## 验证

完整 Stage 1 的 **44 个测试通过**，包括既有底表、数字筛选、历史 enrichment/采样测试及新增的少量 Emerging 夹具。覆盖 New、Revision 替换与重标、普通标签复用、官方原文保持、同日期冲突、无法关联、禁止模型回传改写内容、无 DWA 来源覆盖、采样复现，以及精简输出的 ID、SOC 大类和来源追溯。

实际全量验证：禁用网络与 DNS 后，四个新输出可从缓存逐字节重建；三个 JSONL 中每条任务原文均与来源 CSV 记录一致。旧 Task-ID 基线的三个输出也逐字节一致；检查的 118 个既有数据及 Stage 2–4 文件保持不变。测试夹具不混入正式输出。
