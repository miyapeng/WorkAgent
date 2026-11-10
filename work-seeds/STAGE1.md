# Stage 1 · Occupation-grounded Work Seed Construction

当前阶段结束于**有证据支持的候选 Seed 及覆盖采样**。不生成 SOP、具体公司/事件、工作空间、验收器或训练轨迹。早期 P001 保留为独立开发样例，不参加本流程。

依据 [GraphForge §3.1](https://arxiv.org/html/2609.38923v3#S3.SS1)，把现有官方底表作为输入：

```text
O*NET 四表 → AI4Work / 替代候选标注 → 职业–DWA 组合
→ 检索职业原文 → 模型生成 + 单独证据审核 → 覆盖采样
```

另保留一个仅抽取 Task ID 的无模型基线，便于检查覆盖与研究对照。它不是完整 Work Seed。

## A. 无模型 Task ID 采样

在仓库根目录运行，只有 Python 标准库依赖：

```bash
python work-seeds/scripts/sample_seeds.py --n 200 --seed 42
```

默认从 `data/processed/` 读完整四表，复用现有 CSV 解析、主键冲突检查，并检查外键。输出 `data/task_sampling/` 中恰好三份文件：

- `seed_candidates.csv`：`task_id,eligibility`，覆盖所有原始任务，包含 uncertain。
- `sampled_seeds.csv`：仅 `task_id`，顺序就是贪心选择顺序。
- `sampling_report.json`：三类数量、覆盖、类型比例、参数、输入哈希、规则来源及计数。

默认优先复用固定提交、固定哈希的 AI4Work 原始 XLSX。只有 Task ID、职业代码、原始英文全部相同才继承 DIGITAL/PHYSICAL；缺失、空标签、内容变更为 uncertain。映射分别为 digital_candidate / physical_required / uncertain。它是外部研究标注，PHYSICAL 可能包含上游认为需要当面开展的人际工作，不是不可数字化的确定事实。

可显式切换为保守规则基线：

```bash
python work-seeds/scripts/sample_seeds.py --eligibility rules --n 200 --seed 42 --output-dir work-seeds/data/task_sampling_rules
```

规则限定动作与对象（例如驾驶车辆、编写软件、编制报表）；复杂连接词、否定或范围不明的任务转 uncertain。Inspect / advise / operate 等泛化动词本身不会导致 physical_required。规则版本、正则定义和命中数量均写入报告。这一极保守基线会漏掉大量可数字化任务，不能代替 AI4Work 或专家审核。

替代标注接口：`--eligibility labels --labels-file labels.csv`，两列 `task_id,eligibility`。缺失 ID 为 uncertain；未知 ID、冲突标签报错。替代来源必须自行确保对应输入版本，不声称复现 AI4Work。原始目录始终不改动。

Task 采样按以下顺序比较，每个 task_id 只能选一次，DWA 不展开为重复样本：

1. 尚未覆盖的 SOC 两位大类；
2. 尚未覆盖的具体职业；
3. 本条能增加的 DWA 数量（多标签全部计入）；
4. 已选次数更少的职业，再比较大类；
5. 其他条件相同时优先 Core；当已选 Supplemental 低于 `floor(下一样本数 × supplemental_target)` 时，平局优先 Supplemental；默认目标 0.15；
6. 用 `SHA256(seed + task_id)` 确定平局顺序。

这是覆盖优先的词典序贪心；多 DWA 任务在第 3 步占优，Supplemental 目标是软偏好，不会为凑比例牺牲更高优先级。没有 Finance/Research 等领域配额，也没有每职业固定样本量。N 超过候选数时返回可用数量并报告 shortfall，不复制任务凑数。

## B. 完整 Seed 构建

Schema 校验使用一个直接依赖 `jsonschema`；其余使用标准库：

```bash
.venv/bin/python -m pip install -r work-seeds/requirements-seeds.txt
```

配置文件：

- `config/seed_pipeline.example.json`：通用模板，模型默认参考 GLM-5.2，Endpoint 留空。
- `config/seed_pipeline.llmcenter.json`：LLMCenter 实际配置，`model` 是查询 `/v1/models` 得到的 GLM-5.2 accessId。
- `config/execution_patterns.json`：固定的项目自定义 8 类模式及输入文件家族。**不是 GraphForge 的完整 16 类词表**；公开论文未确认完整定义，不补写论文未公开内容。
- `config/seed.schema.json`：Draft 2020-12 Schema，词表 enum 在校验时注入；多余字段、类型错误和重复数组值均拒绝。

模型参数放在配置中，凭证只从指定环境变量或 `--prompt-api-key` 隐藏输入读取。不要把 Key 写进配置。无需安装 llmctl 或接管现有客户端；本项目直接调用 LLMCenter 的兼容推理接口。

本次小规模试跑配置三个职业、六个组合，要求选五个 Seed：

```bash
.venv/bin/python work-seeds/scripts/construct_seeds.py \
  --config work-seeds/config/seed_pipeline.llmcenter.json \
  --output-dir work-seeds/data/work_seed_pilot_v2 \
  --occupations 13-1023.00,13-2031.00,15-1252.00 \
  --max-pairs 6 --n 5 --seed 42 --prompt-api-key
```

这是验证接口的显式 pilot 范围，不代表职业分布或全量生成完成。取消 `--occupations` 和 `--max-pairs` 即遍历全量候选组合；源索引和模型预算须相应扩大。max-pairs 按固定 seed 的组合哈希选择，仅用于前期运行预算，不是最终覆盖采样。

### 检索接口与证据边界

`url_manifest` 读取 `occupational_sources.json` 中真实检索得到的职业 URL 清单，可细化到 dwa_id。对每个组合，由职业名、DWA 和相关任务构造查询，抓取真实 HTML，并按词项重叠检索原文段落。BLS 只提取 What They Do 段落，排除通用导航说明。它是**来源列表内的检索**，不是已经实现全网自动发现。

本次列表只有采购、预算分析、软件开发三个职业的 BLS 来源。主站从命令行返回 403，显式使用可访问的官方 `blsmon1.bls.gov` 页面；页面可能是较旧版本，只用作职业职责依据，不作为当前薪酬、法律或市场事实。

扩展接口：将 retrieval.provider 改为 `http_search`，配置完整 endpoint 和可选 api_key_env。接口接收 `POST {"query":"..."}`，返回 `{"results":[{"url":"https://..."}]}`。搜索片段不直接当证据；程序仍下载 URL 并提取正文。非 HTML、访问失败、无相关段落都会记录失败。

原网页按内容哈希缓存；片段只做 HTML 解码及空白归一化，不由模型补写。Evidence ID 由 URL 与原文确定，相同来源只下载/缓存一次，相同片段合并对应组合。生成前再次核对原文缓存与片段，不能将模型返回的链接或引用直接加入证据库。词项重叠只表示检索相关性，是否支持需求还必须进入后续审核。

### 模型生成与验证

生成器接收官方职业信息、合法 Task ID、职业证据、固定词表。程序派生稳定 seed_id，并检查八字段 Schema、Task→职业→DWA 关系、证据 ID 和组合关系。

随后发起**单独一次模型审核调用**：检查需求中的全部实质要求、职业活动适配、案例中立性、模式与输入类型，以及与最相近五个已接受需求的语义重复。审核需给出逐项原文引用，程序再做引文子串检查。字段合法不代表语义可靠；审核也是模型判断，仍有误判风险，并未得到职业专家认证。

精确/词项近重复另用 Jaccard 阈值 0.8 拒绝。该检查不是完备的语义去重；语义审核也只比较近邻，不声称全库无任何语义重复。无证据、无合法 JSON、越界字段、虚构 ID、无原文引文或审核不支持均不能进入候选文件。接口仅允许去掉包住整个 JSON 的单层 Markdown 代码围栏，不补全坏 JSON。

输出不复制原职业名或 Task Statements；输入文件家族只是预期载体，不表示已下载相关文件。

### 最终覆盖采样

对通过审核的候选执行边际得分：每个维度贡献 `weight × mean(1/(1+已选频次))`。四维是 occupation、DWA、execution pattern、input file family；文件家族多标签取均值，避免仅因声明更多类型占便宜。平局由固定 seed 与 seed_id 哈希打破。

`--weights 1,1,1,1` 可调四维权重；`--max-per-occupation`、`--max-per-pattern` 可设硬上限，0 表示不设硬上限；`--near-duplicate-threshold` 控制最终采样时的词项近重复限制。默认靠频次递减分散职业与模式，没有领域比例。硬上限或去重使 N 不可达时，报告 shortfall 而不放宽约束。

### 四类输出、缓存与断点

每个模型版输出目录只包含：

| 文件 | 用途 |
|---|---|
| `occupational_evidence.jsonl` | Evidence ID、URL、原文、源文件哈希、检索时间、适用职业–DWA 组合 |
| `candidate_seeds.jsonl` | 通过 Schema、来源关联及模型证据审核的八字段 Seed |
| `sampled_seed_ids.jsonl` | 仅最终选中的 seed_id |
| `sampling_report.json` | 各阶段数量、逐组合状态/拒绝原因、审核结论、覆盖、参数与模型运行元数据 |

缓存单独位于 `data/seed_cache/`（不纳入 Git）：原始网页、检索回执、模型原始响应、原子检查点。模型 ID、Endpoint、Prompt 版本、参数、生成时间、请求哈希保存到报告；凭证不保存。程序常量保存完整 Prompt，报告记录脚本哈希。数据与缓存一起归档才能复现外部网页及模型原始响应。

`--stage filter|retrieve|enrich|sample|all` 可分阶段运行。保持同一范围、配置和输出目录；已完成组合复用缓存，生成状态用单个原子检查点记录。`--retry-failed` 重试失败或完全被拒绝的组合，保留之前的尝试记录；已缓存的模型响应仍复用，若确实要重新生成，应显式使用新缓存目录并保留旧实验。

改变输入、词表、检索范围或源索引时要求新输出目录，但网页缓存可复用。重新调用远程模型不能保证逐字确定性；**固定已缓存候选与采样参数时，采样结果确定**。

纯采样复现无需模型凭证：将上述 pilot 命令的 `--prompt-api-key` 换成 `--stage sample`。

## 验证

```bash
.venv/bin/python -m unittest discover -s work-seeds/tests -v
```

测试覆盖模糊规则、关联与外键、完整分类、DWA 多标签、采样顺序复现、Schema、虚构证据 ID、无原文支持、语义审核拒绝、模型响应缓存和无来源失败。测试使用的模拟模型数据只存在临时目录，不进入正式候选。

## 本次实际运行（2026-11-10）

- AI4Work 基线：18,838 条原始任务分为 5,652 digital_candidate、8,808 physical_required、4,378 uncertain。抽取 200 条，覆盖 22 大类、200 职业、463 DWA；Core 188、Supplemental 11、Missing 1。相同参数三份输出逐字节一致。
- 极保守规则基线：9 条 digital_candidate、0 条 physical_required、18,829 条 uncertain；请求 200 实得 9，不补齐数量。这说明规则覆盖率很低，不表示其他任务不能数字化。
- 全量组合检索清点：5,894 个 eligible 职业–DWA 组合。当前三个职业来源列表支持 33 个组合，得到去重后 30 个证据片段；5,858 个无来源 URL，3 个无有效相关段落。结果在 `data/work_seed_inventory/`，没有声称完成全职业检索。
- GLM-5.2 实际 pilot：6 个组合、11 个去重证据片段，17 个成功模型响应（6 次生成、11 次审核）。使用 `occupation-seed-v2` Prompt，11 条提案中 4 条通过、7 条拒绝：输入家族不适配 3、引文对不上原文 2、审核引用未列入 Seed 的证据 1、Seed 引用未被审核引文覆盖 1。候选覆盖 3 职业、3 DWA、3 模式、4 输入家族。请求 N=5，实际采样 4，shortfall=1。
- 第一轮发现合理推测被写成需求约束后，收紧 Prompt 再跑，最终结果以 `data/work_seed_pilot_v2/` 为准；旧轮次归档到缓存，不混入最终候选。没有为了补足 N 放宽证据门槛。
- 33 项测试通过。禁止网络调用后完整回放 `--stage all` 成功，四份模型版输出逐字节一致；凭证未写入项目文件或缓存。

模型审核通过仍不是专家认证。原始标注的不确定性、来源覆盖不足和模型审核误判，是本阶段必须保留的研究限制。
