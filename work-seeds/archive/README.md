# Stage 1 历史数据归档

这些文件不属于当前 Raw Work Seed 结果。当前完整数字池位于 [`../data/raw_work_seeds/digital_task_pool.jsonl`](../data/raw_work_seeds/digital_task_pool.jsonl)。

本次将以下目录从 `work-seeds/data/` 原样迁移到 `work-seeds/archive/data/`，逐文件核验 SHA-256 一致：

| 目录 | 保留原因 |
| --- | --- |
| `digital/` | 普通 Tasks 的旧数字筛选基线（5,652 条），旧网页和 P001 开发样例仍使用 |
| `translations/` | 旧目录网页的机器翻译及其缓存 |
| `task_sampling/` | 旧 Task ID 覆盖采样基线 |
| `task_sampling_rules/` | 旧规则筛选采样实验 |
| `work_seed_inventory/` | 旧职业—DWA 证据检索清点 |
| `work_seed_pilot_v2/` | 旧 LLM Work Demand Pilot；历史 Stage 2–4 的输入，不能误换成 Raw Seeds |
| `seed_cache/` | 历史证据检索、模型响应与检查点；继续忽略，不提交 Git |

相关脚本、测试和使用说明只调整了路径，未将新 Raw Seeds 接入历史 Stage 2–4。历史输出、来源报告和缓存字节不改写，其中记录的旧运行路径仍表示当时的运行位置。重跑历史命令时使用现在的归档路径。

删除了 `data/processed-check/`：五个文件与当前 `data/processed/` 逐字节一致，只是重复验证副本。官方原始数据、AI4Work 标注、规范化底表、当前 21 批 Emerging 模型缓存和四个正式输出均保留。
