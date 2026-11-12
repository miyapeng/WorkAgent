# 方法来源与本项目边界

论文核对日期：2026-11-12。以下是借鉴方向，不声称复现论文全部数据、内部实现或实验结果。

| 参考 | 论文中的做法 | 本次使用与区别 |
|---|---|---|
| [WorkFactory §3.3](https://arxiv.org/html/2610.37161) | 从预期输出倒推计算、判断及前提，规划信息与载体，再构造环境 | 使用 Output-backward 信息依赖规划；不复制其完整信息/载体双图、合成材料与执行修复链 |
| [WorkForge §2.2](https://arxiv.org/html/2610.04906) | 搜索、阅读、下载与预览真实资源，清点文件中的上下文、事实和结构 | 复用真实下载与解析，新增定位片段供审核；未实现论文完整任务与评测构造 |
| [GraphForge §3.2–3.3](https://arxiv.org/html/2609.38923) | 围绕职业需求选择连贯的真实案例，获取原生资源并组织证据 | 借鉴案例连贯性；Stage 2 的抽象信息图并不是论文中已落到文件事实的 Evidence Graph |
| [WorkGenesis §3](https://arxiv.org/html/2609.39325) | Real Anchor 与 Synthetic Companion 相结合 | 本轮只借鉴 Anchor 概念，明确不走合成补齐路线 |

本项目自己的实现包括三种信息供给渠道、stable segment_id 引用恢复、有限查询预算、缺口驱动下一轮查询、同模型独立审核、具体准入规则及状态。它们应通过后续实验验证，而不是由引用论文来证明有效。

模型语义审核与程序核验分工：程序证明下载字节、文件哈希、ID 和定位匹配；模型判断职业意图、材料适用性与案例关系。两者结合仍不构成专家认证或实际执行验证。

Search Provider 协议依据：[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[Brave Web Search](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started)、[Serper](https://serper.dev/)。实现了这些 HTTP 接口，但本轮没有搜索凭证，不能声称已完成实时 Provider 集成验证。
