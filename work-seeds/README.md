# Stage 1 · Official Raw Work Seed Construction

默认流程已调整为 **O*NET 31.0 → Emerging Tasks 合并 → Digital Filtering → Coverage-aware Sampling → Raw Work Seeds**。任务文本直接保留官方英文，LLM 仅分类最终有效的 Emerging Tasks，不生成 `work_demand`。具体规则、运行结果和命令见 [STAGE1.md](STAGE1.md)。

新增官方输入 [`emerging_tasks.csv`](https://www.onetcenter.org/dictionary/31.0/csv/emerging_tasks.html)，原始字节和独立来源清单保存在 `data/raw/`。派生结果写入 `data/raw_work_seeds/`，不覆盖下面记录的普通 Task 底表、`data/digital/`、网页或历史模型实验。当前网页及旧数字子集仍是普通 Tasks 的 5,652 条基线，不包含本轮 Emerging 合并结果。

```bash
# 在仓库根目录；Emerging 原始文件已保存
.venv/bin/python work-seeds/scripts/sample_seeds.py --n 200 --seed 42 --prompt-api-key
# 同一输入和模型响应缓存，离线复现
.venv/bin/python work-seeds/scripts/sample_seeds.py --n 200 --seed 42 --offline
```

职业证据检索与 LLM Work Demand enrichment 保留为显式调用的历史实验，见 [STAGE1_LEGACY.md](STAGE1_LEGACY.md)。新 Raw Seeds 与旧 `candidate_seeds.jsonl` 是不同数据类型；本次不改 Stage 2–7，也不自动把新输出接到旧接口。

官方底表建立完整职业—Task—DWA 种子目录。后续按用户要求新增独立的 AI4Work 数字任务筛选层和中文阅读层，底表不变。尚未生成 Work Tasks 或 SFT/RL 轨迹；与本仓库早期 W001 演示独立。

## 数据来源与许可

使用 [O*NET® 31.0 Database](https://www.onetcenter.org/database.html)，[August 2026 发行版](https://www.onetcenter.org/db_releases.html)。原始四表构建器优先下载固定版本 [官方 CSV ZIP](https://www.onetcenter.org/dl_files/database/db_31_0_csv.zip)，只读取以下三个文件；新的 Raw Seed 层另读取同版本 Emerging Tasks：

- [`occupation_data.csv` 字典](https://www.onetcenter.org/dictionary/31.0/csv/occupation_data.html)
- [`task_statements.csv` 字典](https://www.onetcenter.org/dictionary/31.0/csv/task_statements.html)
- [`tasks_to_dwas.csv` 字典](https://www.onetcenter.org/dictionary/31.0/csv/tasks_to_dwas.html)

来源机构：U.S. Department of Labor, Employment and Training Administration (USDOL/ETA)；数据库由 National Center for O*NET Development 开发。数据按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 使用，参见[官方许可声明](https://www.onetcenter.org/license_db.html)。O*NET® 是 USDOL/ETA 的商标。

原始四表构建器的转换仅包括选取指定字段、规范化拆表、删除完全重复记录和排序。原始 ID、英文文本及空值保持不变。USDOL/ETA 未批准、认可或测试本项目的转换。`data/raw/source_manifest.json` 保留下载地址及 SHA-256；输出报告保留每份原始文件和输出 CSV 的 SHA-256。

## 下载与构建

Python 3.10+，四表构建脚本只用标准库。完整 Stage 1 与历史测试沿用 `requirements-seeds.txt`，不新增依赖。在 `work-seeds/` 目录执行：

```bash
python scripts/build_onet.py --download
```

ZIP 获取失败时只回退到相同官方版本的独立 CSV 下载地址。如果仍失败，程序非零退出，明确报错，不生成替代数据。可自行下载官方文件并放入同一目录：

```bash
python scripts/build_onet.py --input-dir /path/to/official/31.0/csv --output-dir data/processed
```

本次 ZIP 下载遇到超时，实际成功获取的是三个官方独立 CSV。遇到同样问题可直接执行 `python scripts/build_onet.py --download --download-format csv`；仍然从 O*NET 官方固定 31.0 地址获取，不使用镜像或生成数据。

默认输入 `data/raw`，输出 `data/processed`；路径默认值相对于项目而非当前工作目录。缺文件时一次报告全部缺失名称。手动提供的 CSV 没有内嵌发行版本，因此无下载清单时报告标记为用户提供，不能仅凭列名认证其来源版本。

## 四张规范化表

| 文件 | 字段 | 主键与关联 |
|---|---|---|
| `occupations.csv` | `occupation_code, occupation_title` | 主键 `occupation_code` |
| `tasks.csv` | `task_id, occupation_code, task_text, task_type` | 主键 `task_id`；职业外键指向 occupations |
| `dwas.csv` | `dwa_id, dwa_name` | 主键 `dwa_id` |
| `task_dwa.csv` | `task_id, dwa_id` | 联合主键；分别引用 tasks、dwas |

所有 ID 以字符串处理，不转成数值；不 trim、翻译或改写文本。`task_type` 为官方 Core / Supplemental / 空字符串；其他值报错。空值仍写作 CSV 空字段，不填入 “Missing”；Missing 仅是统计/页面显示名称。

职业从 occupation_data 独立建立，Task 从 task_statements 独立建立，不通过映射表内连接过滤。相同 Task 可以拥有多个 DWA；无映射 Task 和无 Task 职业均保留。`dwas.csv` 是指定映射文件中出现的 DWA 集合，不声称覆盖完整 DWA 分类体系。

原始主键相同但内容冲突（包括被投影掉的元数据）会报错；同一 DWA ID 名称冲突也会报错。冗余职业名称、任务文本须与主表一致。完全重复的记录才去重，不做语义去重。

## 验证与复现

构建时自动验证主键、外键和四张表与原始投影集合的逐条一致性。输出 `validation_report.json`，统计职业、Task、DWA、关联、任务类型、无映射 Task、无 Task 职业及完全重复行数。无硬编码目标数量，不为了匹配预期数字过滤记录。

```bash
# 重新计算并逐字节核对已有四张 CSV 和报告，不修改文件
python scripts/build_onet.py --verify-only

# 重复构建：固定字符串排序、UTF-8、LF，报告不含变化时间戳
python scripts/build_onet.py --output-dir data/processed-check

# 从已下载官方行派生测试夹具；人为错误只用于负向测试
python -m unittest discover -s tests -v
```

测试覆盖完整官方数据复现、完全重复、冲突主键、DWA 名称冲突、缺失类型、无映射任务、孤立外键、缺文件、非法类型、空主键、BOM、输出篡改与失败不覆盖已有输出。下载到的原始字节保持不变；验证失败不发布新结果，旧输出若存在仍是旧结果，应以本次 CLI 退出码为准。

## 只读可视化网页

已发布的私有页面：[O*NET Seed Catalog · Phase 1](https://onet-seeds-phase-one.miyapeng78.chatgpt.site)。

```bash
python scripts/build_view.py
```

直接用浏览器打开 `site/dist/index.html` 即可，默认显示数字任务候选和中文译文，支持切换现场/物理任务、待核对、官方全量目录，以及中文、英文、中英对照。职业和任务均支持中英文搜索；可展开逐任务筛选依据，下载全量或数字子集 CSV。构建网页前核对原始目录、筛选依据与翻译覆盖。分页仅控制显示，不截断数据。

网页使用原生 HTML/CSS/JavaScript，无运行时框架、数据库或 Web 后端。托管配置位于 `site/.openai/hosting.json`；本地打开不需要 Sites、Node 或网络连接。

## 数字任务筛选规则（独立派生层）

来源：[AI4Work 的逐任务标注表](https://github.com/zorazrw/ai4work-resources/blob/095db006debf83f2bbda2631964bd1b4c81190ad/real_work/employment/digital_task_annotation.xlsx)，固定提交 `095db006debf83f2bbda2631964bd1b4c81190ad`。这是外部研究标注，不是 O*NET 官方字段。上游表包含 `Is Digital` 和 `Reason`；原始文件保留在 `data/annotations/`，脚本核对固定 SHA-256。来源说明见 [AI4Work README](https://github.com/zorazrw/ai4work-resources/blob/095db006debf83f2bbda2631964bd1b4c81190ad/real_work/README.md)。AI4Work 的出处与权利声明单独适用，不将 O*NET 的许可自动扩展至上游研究标注。

| 规则 | 条件 | 处理 |
|---|---|---|
| R1 | Task ID、职业代码、英文任务文本完全一致；标签 DIGITAL | 纳入数字候选子集 |
| R2 | 上述三项完全一致；标签 PHYSICAL | 排除，保留现场/物理视图 |
| R3 | 没有同一 Task ID | 待核对 |
| R4 | 同一 Task ID 的职业代码或文本改变 | 待核对，不继承旧标签 |
| R5 | 匹配行缺少标签或标签未知 | 待核对，不自行补全 |

不使用模糊匹配、关键词猜测或中文译文进行筛选。不根据职业名称整体删除职业，也不把一条数字任务扩展成整个职业可数字化。所有选中 Task 的 DWA 关系完整保留。Core、Supplemental 和类型缺失均可入选；是否入选只取决于上述规则。

“数字候选”的含义是继承 AI4Work 的任务级判断，不保证当前 Agent 可完成。PHYSICAL 包括上游认为必须现场开展的部分人际活动。没有标签不能据此断言任务是物理任务。这些边界在网页中公开显示。

```bash
# 原始标注已随本项目保留，可离线复现
python scripts/filter_digital.py
# 如需重新获取固定提交的 XLSX
python scripts/filter_digital.py --download
```

输出 `data/digital/` 下的四张同 Schema CSV、`task_decisions.csv`（全量任务的状态、规则、上游行号与原文理由）和 `filter_report.json`（版本、来源哈希、输入输出哈希、完整性检查）。不改写 `data/processed/`。

本次严格对齐结果：**5,652 条数字候选、8,808 条现场/物理任务、4,378 条待核对**。待核对包括 134 条无匹配 ID、4,244 条上游无标签；当前没有职业/文本变更匹配。数字子集涉及 **743 个职业、1,168 个 DWA、7,123 条关联**。这不是 GraphForge 的完整预处理复现，不通过追加筛选去凑论文数量。

## 中文阅读层

```bash
# 首次翻译：仅发送公开 O*NET 英文文本，缓存中间结果以便断点续跑
python scripts/translate_catalog.py --fetch
# 以后离线使用既有缓存生成相同的展示文件
python scripts/translate_catalog.py
python scripts/build_view.py
```

`data/translations/translation_cache.jsonl` 保存英文、源文本 SHA-256、中文和翻译来源。`translations_zh.json` 按官方 ID 关联，覆盖全部 1,016 个职业、18,838 条 Task 和 2,085 个 DWA。重复英文文本共用同一译文，但不合并原始记录。空原文仍为空。

翻译来自 Google Translate 公共网页端点，是**未经逐条人工审校的机器译文**，仅辅助阅读；英文原文仍为权威版本。该网络端点不是稳定性受保证的付费 API；离线复现依赖已保存缓存，不依赖重新调用翻译服务。请求中的记录序号必须完整匹配，防止批量翻译串行；原始英文变化后旧译文不能继续使用。筛选完全不使用译文。

少量由 Coding Agent 检查后修订的措辞记录在 `translation_overrides.json`，带官方 ID 和完整英文匹配条件；这仍属于机器辅助译文，不声称经过人工专家审校。
