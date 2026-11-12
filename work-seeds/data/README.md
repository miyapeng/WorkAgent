# 当前 Stage 1 数据

当前阶段性全量结果是 [`raw_work_seeds/digital_task_pool.jsonl`](raw_work_seeds/digital_task_pool.jsonl)：**5,745 条 Raw Work Seeds**，覆盖 **749 个职业、22 个有任务的 SOC 大类**。它包含全部通过当前数字化分类的有效任务，不是 200 条抽样结果。

| 目录 | 用途 |
| --- | --- |
| `raw/` | O*NET 31.0 官方原始 CSV 和来源清单，保持原样 |
| `annotations/` | 固定版本 AI4Work 原始数字化标注 |
| `processed/` | 四张规范化基础表及验证报告，构建依赖 |
| `raw_seed_cache/` | 当前 Emerging 分类的真实模型响应缓存；本机保留，不提交 Git |
| `raw_work_seeds/` | 当前有效池、完整数字池、200 条采样及统一报告 |

`raw_work_seeds/` 的四个文件：

- `effective_tasks.jsonl`：19,129 条有效任务，含 DIGITAL / PHYSICAL / UNCERTAIN。
- **`digital_task_pool.jsonl`：全部 5,745 条 DIGITAL 记录，作为当前 Stage 1 主产物。**
- `sampled_raw_seeds.jsonl`：从完整数字池选出的 200 条；不是全量池。
- `stage1_report.json`：合并、分类、覆盖、冲突、来源和模型调用记录。

完整性范围：数字池与有效池中 `digital_label == "DIGITAL"` 的记录逐条一致，包含普通任务 5,636 条、Emerging New 93 条、Emerging Revision 16 条。任务原文均可定位回官方 CSV。普通任务 18,838 条与 Emerging 338 行经过合并得到有效池，不能直接相加：44 次 Revision 成功替换；原 Task `21211` 有两个同日期冲突 Revision，旧版及两个冲突版本均隔离，尚未解决。不存在找不到 Original Task ID 的关联。PHYSICAL 8,941 条、UNCERTAIN 4,443 条仍保留在有效池，未丢弃。

“全量”指按当前明确规则及已有标签完整纳入，不表示标签已通过真实执行验证，也不表示全部 O*NET 任务都是数字任务。

在仓库根目录复现：

```bash
.venv/bin/python work-seeds/scripts/build_onet.py
.venv/bin/python work-seeds/scripts/sample_seeds.py --n 200 --seed 42 --offline
```

离线运行需要本机 `raw_seed_cache/`。新机器没有缓存时，按 [STAGE1.md](../STAGE1.md) 配置模型并运行分类。

旧筛选、翻译、采样和 Work Demand 实验已移至 [`../archive/data/`](../archive/data/)，说明见 [归档清单](../archive/README.md)。当前[浏览网页](https://onet-seeds-phase-one.miyapeng78.chatgpt.site)已改为直接展示完整数字池；网页中文译文仅供阅读，不修改这些原始结果。
