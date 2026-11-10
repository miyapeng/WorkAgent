# Executable Multimodal Work Environments for Agent Learning

当前研究数据工程阶段：**[Stage 1 · Occupation-grounded Work Seed Construction](work-seeds/STAGE1.md)**。在已完成的 [O*NET 原始目录](work-seeds/README.md) 上增加数字候选筛选、职业证据检索、模型 Seed 补充和覆盖采样；与以下早期 W001/P001 演示独立。当前不继续构造工作空间或训练数据。

Phase 1 之后的首个种子实例：[P001 · 采购供应商比选](work-tasks/P001/README.md)。从官方 Task 1144 出发，提供合成材料、证据图、验收规则及参考执行；属于开发样例，尚未准入训练集。

这是依据 [V0 方案](数据制造方案.md) 搭建的最小可运行框架。先让一个 W001 销售分析任务走完整个流程，再逐步设计每个环节。原方案保持不变。

当前能真实生成 PNG / XLSX / PDF，重置工作空间、执行受控工具、检查交付物、保存轨迹和奖励。执行器是**手工参考样例**，没有接入模型，也没有进行 SFT / RL 训练。

## 先运行一次

在项目目录中执行（本次已安装依赖并完成演示）：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m workenv demo
```

`demo` 首次自动构建任务包，之后每次创建新的执行目录。预期 `success: true`、`reward: 1.0`。这表示参考解通过了当前验收规则，不代表模型能力或真实职业质量已经得到验证。

终端会打印 `run_directory`。打开里面的：

- `workspace/dashboard.png`：模型应观察的最新转化率看板。
- `workspace/sales_summary.xlsx`：本次生成的汇总表。
- `workspace/quarterly_brief.pdf`：本次生成的两页简报。
- `trajectory.jsonl`：每一步动作与观察。
- `grade.json`：三个维度的分数、每项检查与总奖励。

## 用一张图理解流程

```mermaid
flowchart TD
    A[1. 设计任务 examples/W001.json] --> B[2. 构建任务包 build.py]
    B --> C[可见输入 workspace_init]
    B --> D[隐藏答案与证据映射 evaluation]
    C --> E[3. reset 创建新工作空间]
    E --> F[4. 执行器通过 step 读图、读文件、制作交付物]
    F --> G[5. grade 检查 Outcome / Artifact / Process]
    D --> G
    G --> H[6. 保存产物、轨迹和奖励]
    H --> I[导出轨迹及可重置任务清单]
    G --> J[Probe 正反向检查]
    J --> K[人工判断并修复任务、材料或评分器]
    K --> A
    I -.后续.-> L[真实教师与 SFT 数据筛选]
    I -.后续.-> M[学生策略与 RL Trainer]
    A -.后续独立任务族.-> N[Benchmark]
```

图中的实线流程已实现；虚线部分是后续接入点。Probe 目前只报告问题，由人决定修复哪一环，不自动改写任务。

## 每个环节只回答一个问题

| 环节 | 要回答的问题 | 先看哪个文件 | 输入 → 输出 |
|---|---|---|---|
| 任务设计 | 用户到底要完成什么工作？ | `examples/W001.json` | 职业、目标、事实 → 任务设计 |
| 文件构建 | Agent 能看到哪些证据？ | `workenv/build.py` | 设计 → 输入文件、隐藏答案、证据映射 |
| 文件读写 | 怎样生成实际文件？ | `workenv/artifacts.py` | 数据 → PNG / XLSX / PDF |
| 环境执行 | 每一步怎样改变工作空间？ | `workenv/environment.py` | 动作 → 文件变化与观察 |
| 执行策略 | 谁决定下一步做什么？ | `workenv/reference.py` | 观察 → 下一动作；当前为手工样例 |
| 验证评分 | 怎样知道交付合格？ | `workenv/verify.py` | 实际文件、隐藏答案 → 分项检查与奖励 |
| 探测修复 | 评分器能否识别错误？ | `workenv/probe.py` | 正确解与人为错误 → 检查报告 |
| 数据导出 | 给下一阶段留下什么？ | `workenv/export.py` | 完成的 episodes → 轨迹及任务清单 |

## 工作任务包和一次执行是两件事

```text
examples/W001.json                # 构建端设计；含事实，不给 Agent 看
work_dataset/
├── tasks/W001/
│   ├── task.json                 # 公开任务说明
│   ├── workspace_init/           # 每次 reset 的输入副本来源
│   │   ├── dashboard.png
│   │   ├── orders.xlsx
│   │   ├── previous_report.pdf
│   │   └── report_requirements.md
│   └── evaluation/               # 仅构建端、评分端使用
│       ├── oracle.json
│       ├── evidence_graph.json
│       ├── rubric.json
│       └── probe_report.json     # 运行 probe 后生成
├── runs/W001/<run_id>/
│   ├── workspace/                # 本次输入与最终交付物
│   ├── assets/dashboard.png      # 轨迹中图像观察的持久化副本
│   ├── metadata.json
│   ├── trajectory.jsonl
│   └── grade.json
└── training/
    ├── rollouts.jsonl            # 全部完成且已评分的轨迹，保留成功和失败
    ├── sft_candidates.jsonl      # 当前为空；不把手工演示冒充教师数据
    └── rl_tasks.jsonl            # 环境任务入口与 split，不是预先写好的解答
```

任务包固定，episode 可以反复开始。`reset` 创建新目录，原 episode 留作检查；`close` 结束实例并保留文件。

当前任务全部标记为 `development`。尚未创建独立 Benchmark，也不把同一个 W001 同时当成训练集和测试集。未来按 `family_id` 划分来源/模板家族。

## 可以分开运行

```bash
# 构建任务：如果目录已存在会拒绝覆盖
.venv/bin/python -m workenv build --root work_dataset_v2

# 使用该任务包，执行完整参考样例
.venv/bin/python -m workenv demo --root work_dataset_v2

# 正确解、错误数字、缺报告、缺图表、源文件改动等检查
.venv/bin/python -m workenv probe --root work_dataset_v2

# 缺少看板的流程检查；参考执行器会停止，评分失败
.venv/bin/python -m workenv demo --root work_dataset_v2 --condition no_image

# 重新导出已评分 episodes
.venv/bin/python -m workenv export --root work_dataset_v2

# 自动化回归检查
.venv/bin/python -m unittest discover -s tests -v
```

改动设计后请使用新的 `--root` 重新构建，避免旧任务与新设计混淆。`demo` 遇到已有任务包时会直接使用已有包。

## 环境接口怎么用

```python
from workenv import WorkEnvironment

env = WorkEnvironment("work_dataset", policy_kind="manual")
initial = env.reset("W001")
orders = env.step({"tool": "read_file", "path": "orders.xlsx"})
image = env.step({"tool": "view_image", "path": "dashboard.png"})
# image["observation"]["data_base64"] 是可交给视觉模型的图片内容。
# 下一步由你或未来的策略决定，不由环境生成正确答案。
# env.step({"tool": "write_summary", "rows": [...]})
# env.step({"tool": "write_report", "rows": [...], "narrative": "..."})
env.step({"tool": "finish"})
result = env.grade()  # 未提交文件也可评分，此例会失败。
env.close()
```

`rows` 字段：`region`、`revenue`、`revenue_change`、`conversion`、`conversion_change`、`anomaly`。具体统计口径在任务输入 `report_requirements.md` 中。`step` 返回观察和 `done`，最终奖励由 `grade` 给出；评分后不能再继续动作。错误工具调用也消耗步数，默认上限 20。

## 当前已经验证什么，还缺什么

- **Outcome**：逐区域检查 Excel 中的收入、变化率、转化率及异常标记。当前最新转化率仅出现在看板像素中，未写入其他公开输入。
- **Artifact**：检查 PDF 可解析、两页、数值摘要正确、有分析文字和嵌入图片。暂不判断因果分析质量、图表内容或视觉排版；固定数值行格式是 V0 的公开交付约定。
- **Process**：逐步记录输入文件哈希；观察到源文件变化后，即使后来还原也会触发零奖励门控。不是完整的系统调用审计。
- **执行边界**：Agent 接口只提供列出的受控工具，不暴露 Shell、任意 Python 或隐藏目录。这是工具层访问控制，不是 OS 沙箱；运行 Python 代码的宿主仍可信。未来接入 CLI Agent 必须先增加容器隔离与资源控制，不能直接给它整个项目目录。
- **参考执行器**：`reference.py` 的看板数值是人工预先抄录的，其他数据通过工具读取和计算。它用于检查管线，不证明视觉理解；改动看板后需要人工重新抄录。`no_image` 只是缺图条件下的工程检查，不是消融实验结论。
- **SFT / RL**：已记录动作、观察、图像资产和最终奖励。导出为项目中间格式，还需模型消息协议、训练器适配及真实教师审核；只有 `teacher`、`train`、`full`、成功且 `review.json` 中 `approved=true` 的轨迹能进入候选集。候选集仍需质量审查。尚未实现策略优化。

## 建议下一次只做第一小步

先一起设计 **W001 的任务规格**：用户委托是什么、必须从图中读到什么、哪些输出必须正确。

这一步先看 `examples/W001.json` 和生成的 `report_requirements.md`。完成标准是：你能清楚指出每项输出来自哪份输入，以及怎样判定它对不对。

之后按“材料 → 验证器 → 真实教师 → 轨迹筛选 → RL”的顺序逐环替换。当前四区域报表工具、手工策略和部分校验仍针对 W001；新增职业任务时再抽出通用接口，不需要现在就设计大规模框架。
