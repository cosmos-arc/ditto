# Ditto 功能能力评级与业界对标

> **首次评估**：2026-07-10<br>
> **最近复核**：2026-07-16<br>
> **状态**：能力事实基准（Capability Baseline）<br>
> **目标**：10 个能力维度全部达到 10/10；当前分数必须由代码与验收证据支持，目标分数不得提前计入。

## 1. 产品目标与当前边界

Ditto 的北极星是全球全品类、AI 原生的量化研究与人工决策平台：

- 优先支持 A 股 ETF、A 股个股、宏观和商品大宗数据。
- 先完成日级数据、研究、回测、选股、仓位管理、风险提示和人工交易闭环。
- 不以全自动交易为近期目标；系统生成建议，人负责审批和实际成交。
- 后续支持分钟级数据、盘中因子与信号、事件驱动计算和可选券商连接。
- AI 支持策略编写、投研、市场与宏观分析、仓位与买卖建议，并最终演进为可审计的多 Agent 工作流。

截至本次复核，系统已通过 G1，达到单操作者、单账户、单执行 sleeve、
本机使用的日频人工交易 Beta；它仍是**内部研发系统**，不是可对外经营的
投资产品，也不是自动交易或真实券商生产系统。

## 2. 文档职责与事实优先级

当文档发生冲突时，按以下顺序判定：

1. 可重复运行的验收证据、数据库约束和真实 API 响应。
2. 当前源码、测试、OpenAPI 与 CLI `--help`。
3. 本文的能力事实与缺口。
4. 母路线图 `docs/superpowers/specs/2026-07-10-ditto-development-roadmap-design.md`。
5. 当前 release 的实施计划，例如 `docs/plans/2026-07-10-r1-implementation-plan.md`。
6. 历史计划和探索记录。

`2026-07-10-phase-a-implementation-plan.md` 已降级为迁移索引，不再是施工入口。

## 3. 评分方法

### 3.1 三套互不替代的量尺

| 量尺 | 用途 | 当前结论 |
|---|---|---|
| 能力广度分 | 10 个维度等权，描述“已经实现了多少” | **5.9/10** |
| R1 日频人工交易就绪度 | 只衡量每日建议到人工成交复盘的目标工作流 | **7.9/10，G1 已通过** |
| Release Gate | 安全、数据、运行、合规等硬门槛 | 任一硬门槛失败即不得发布，平均分不能抵消 |

能力广度分只表示功能覆盖，不表示生产成熟度。R1 就绪度高于或低于某个分数，也不能替代端到端验收。

### 3.2 10 分标尺

| 分数 | 定义 |
|---:|---|
| 0 | 无运行时实现 |
| 1-2 | 占位、原型或孤立代码，不能形成工作流 |
| 3-4 | 局部可运行，关键状态、契约或持久化缺失 |
| 5-6 | 核心能力存在，可供内部研发使用，但产品闭环不完整 |
| 7-8 | 定义范围内稳定可用，有真实数据验收、可观测、恢复和运维证据 |
| 9 | 在目标市场达到优秀产品水平，并形成明确差异化 |
| 10 | 定义范围内的标杆能力；有持续验收、SLO、安全、合规和用户价值证据 |

### 3.3 证据等级

| 等级 | 含义 |
|---|---|
| A | 源码、确定性测试和可重复验收同时证明 |
| B | 源码或局部测试证明，尚缺真实工作流验收 |
| C | 设计、原型或推断，不计为生产能力 |

每个 release 结束时更新评分。没有新增证据不得上调；发现旧结论错误时必须下调。

## 4. 十维能力评级与 10 分目标

| # | 能力维度 | 当前 | 证据 | 当前事实与主要缺口 | 达到 10/10 的完成定义 | 主 release |
|---:|---|---:|:---:|---|---|---|
| 1 | 数据覆盖与接入 | 6.0 | B | A 股 ETF 日级主线较完整；stock/macro 已有接入，fx/commodity 较弱；无统一分钟级与 tick 平台 | 全球主要资产统一 schema；日/分钟/tick 分层；跨市场日历、时区、FX、合约与公司行动完整；供应商切换可验收 | R2、R6、R7 |
| 2 | 数据治理与 PIT | 9.0 | A | `knowledge_date` fail-closed、promotion evidence、lineage、source health/fallback 是强项；尚缺全数据集覆盖、长期 SLO 与恢复演练 | 所有资产和频率统一 PIT；质量规则、血缘、版本、许可、回补、降级、审计和 SLO 全覆盖 | R2、R6、R7 |
| 3 | 因子与特征工程 | 7.0 | B | 表达式、物化和 IC 诊断已具备；因子库、正交化、衰减、稳定性和自动发现不足 | 跨资产因子库；PIT 物化；研究到生产一致；完整诊断、版本和复现；支持日频与盘中 | R2、R3、R6 |
| 4 | 策略与研究 | 6.0 | A/B | R1 已闭合 latest-published、seed bootstrap、确定性 EOD 与 package provenance；策略样本、研究工作台、实验比较和完整治理仍不足 | 配置化策略、实验追踪、审批/发布/回滚、参数版本、复现、模板与 AI 辅助形成完整研究生命周期 | R1、R3、R5 |
| 5 | 回测与仿真 | 7.0 | A/B | checkpoint、replay、PIT、费用、T+1、涨跌停等基础较强；流动性、成交量、归因、批量实验和盘中仿真不足 | 日频与事件驱动分钟级统一；真实市场规则、容量与冲击；分布式实验；归因与回放；研究/实盘一致性证明 | R3、R6、R7 |
| 6 | 组合构建与优化 | 5.0 | B | 等权、均值方差和协方差抽象存在；约束求解、风险预算、Black-Litterman、稳健性与前沿分析不足 | 多目标、多约束、交易成本和税费感知；风险预算与情景优化；求解可解释、可复现、可降级 | R4、R7 |
| 7 | 风险管理 | 5.0 | B | 集中度、回撤、止损、市场异常、kill switch 与 `RiskGate` 已有；连续状态、持久化、恢复和组合风险不足 | 事前/事中/事后统一；组合与因子风险；压力测试；状态恢复；事件审计；告警与人工处置闭环 | R4、R6、R7 |
| 8 | 执行、OMS 与账户 | 7.0 | A/B | R1 已闭合手工账户基线、建议数量、多笔部分成交、追加式更正、effective-fill 重建和日终复盘；仍无多账户、多 sleeve 和真实券商 adapter | 多账户/多 sleeve；完整订单与成交账本；幂等、修正、对账、恢复；人工审批与可选券商适配 | R1、R4、R6、R7 |
| 9 | AI、ML 与 Agent | 0.0 runtime / 2.0 adjacent | C | 无正式 LLM/Agent runtime；有 hypothesis、Experience Memory 和前端原型等邻接能力 | 有评测和成本治理的 Copilot；grounded tools；可解释建议；HITL 审批；多 Agent；模型风险、提示注入与数据泄露防护 | R5、R7 |
| 10 | 平台、体验与运营 | 7.0 engineering / 6.0 product | A/B | R1 live 工作台、共享 CLI/Prefect 编排、loopback、runbook 与 SQLite 备份恢复已验收；认证、RBAC、多租户、SLO 和发布治理仍不完整 | 稳定工作台；API 兼容；RBAC；备份恢复；SLO/告警/事件响应；安全供应链；多租户与可运营部署 | R1-R7 横向 |

**等权能力广度分：5.9/10。** 计算时维度 9 取 runtime 0 分、维度 10 取 engineering 7 分；产品工作流另由 R1 就绪度与 Release Gate 衡量。该值不含任何未来规划分，也不代表可对外发布。

## 5. R1 日频人工交易就绪度

### 5.1 R1 已交付

- latest-published 策略选择与幂等 seed bootstrap。
- 日级数据就绪、确定性 EOD、持久化 signal package 与同日重跑冲突保护。
- 原子账户/持仓基线、稳定 sleeve 与可解释 D+1 建议数量。
- 多笔部分成交、append-only void/replace 与 effective-fill read model。
- Daily Decision V2 blocked/review/ready 真值表和 `/api/v1/trade` API。
- `VITE_USE_MOCK=false` 的 Trading live 工作台、成交录入与盘后复盘。
- CLI/Prefect 共用 coordinator、loopback-only、runbook 和 SQLite 备份恢复。

### 5.2 原五个硬阻塞清零

| 原阻塞 | 闭环事实 | 验收证据 |
|---|---|---|
| 活动策略不确定 | 最高 published 版本独立于 draft；bootstrap 可重复且冲突 fail closed | 多版本、幂等与冲突测试；确定性 E2E |
| EOD 结果不可判定 | package、零调仓、失败、冲突和幂等重跑均为持久化事实 | 有交易/零调仓、same-input、changed-input 与中断恢复 E2E |
| 账户与建议数量不闭环 | 原子 baseline 与 D+1 sizing 已进入 Daily Decision | 现金、手数、T+1、参考价和回滚测试 |
| 成交账本不满足人工交易 | 同日多 fill、append-only void/replace 和 effective-fill 重建已闭环 | Task 6 API/E2E、备份恢复后的 raw/effective identity |
| UI 仍是混合原型 | Trading live 路径不使用 prototype fallback | 14/14 desktop/mobile acceptance 与前端完整检查 |

### 5.3 就绪度计算

| 子能力 | 权重 | 当前分 | 加权分 |
|---|---:|---:|---:|
| 日频数据、PIT 与 DQ | 20% | 8.5 | 1.70 |
| 策略生命周期 | 10% | 7.5 | 0.75 |
| EOD、package 与重跑 | 15% | 8.0 | 1.20 |
| 账户基线与建议数量 | 15% | 8.0 | 1.20 |
| 成交账本与复盘 | 15% | 8.0 | 1.20 |
| Daily Decision API 与 UI | 15% | 8.0 | 1.20 |
| 运维、安全与恢复 | 10% | 6.5 | 0.65 |
| **合计** | **100%** |  | **7.90** |

R1 就绪度为 **7.9/10**，十三项完成定义与四层验收全部通过，
**G1 内部本机 Beta Gate = PASS**。该分数和 Gate 只证明 R1 的本机单操作者
边界，不代表认证、多租户、真实券商、自动交易、外部 Beta 或商业发布能力。

## 6. 业界对标方法

不同项目的产品类型不同，不能把交易引擎、研究平台、数据终端和 Agent 示例框架放在同一排行榜。

### 6.1 对标分组

| 分组 | 核心参照 | Ditto 应学习的能力 | 不应机械复制 |
|---|---|---|---|
| 全栈量化引擎 | LEAN | 多资产模型、回测/实盘一致、券商与订单生态 | 近期不追求全自动执行和大规模社区 |
| 事件驱动交易引擎 | NautilusTrader | 高频数据模型、事件时钟、确定性回放、执行仿真 | R1-R5 不引入盘中复杂度 |
| AI 量化研究平台 | Qlib | dataset/feature/model/workflow、实验复现、学习型策略 | 不把 ML 数量当产品价值 |
| A 股在线量化产品 | 聚宽、米筐 | 本土数据、研究体验、模板、用户工作流 | 不复制云端自动交易作为近期目标 |
| 金融数据与分析终端 | OpenBB | 统一数据访问、分析工作台、AI 交互入口 | 不把终端 UI 当成可靠量化内核 |
| 金融 Agent 框架 | TradingAgents、FinRobot | 多角色协作、投研任务分解、Agent 模式 | 示例框架不能替代可审计数据、风控和产品运行时 |

### 6.2 能力矩阵

`强` 表示该项目的主要优势，`中` 表示具备，`弱/非重点` 不表示项目质量差，只表示产品定位不同。

| 能力 | Ditto 当前 | LEAN | Nautilus | Qlib | 聚宽/米筐 | OpenBB | Agent 框架 |
|---|---|---|---|---|---|---|---|
| A 股日频与 PIT 治理 | 中-强 | 中 | 弱 | 强 | 强 | 取决于数据源 | 非重点 |
| 全球多资产 | 弱 | 强 | 强 | 中 | 中 | 强 | 非重点 |
| 分钟/tick 与事件驱动 | 无 | 强 | 强 | 弱-中 | 中 | 非重点 | 非重点 |
| 回测/仿真 | 中 | 强 | 强 | 中-强 | 强 | 弱 | 弱 |
| 因子/ML 研究 | 中 | 中 | 弱 | 强 | 中-强 | 中 | 中 |
| 组合、风险与执行 | 中等骨架 | 强 | 强 | 中 | 中-强 | 弱 | 弱 |
| 人工决策工作台 | 本机 Beta | 中 | 弱 | 弱 | 强 | 强 | 原型 |
| AI Copilot/Agent | 无 runtime | 弱 | 弱 | ML 强、Agent 弱 | 中 | 强入口 | 强模式、弱产品化 |
| 数据治理差异化 | 强 | 中 | 中 | 中-强 | 不透明 | 取决于供应商 | 弱 |

### 6.3 Ditto 的差异化选择

Ditto 不需要在每个参照项目的主场同时取胜。目标差异化是：

1. A 股和宏观数据的 PIT、血缘、质量和许可治理。
2. 从研究证据到人工决策、成交和复盘的完整 provenance。
3. AI 建议必须调用受控工具、通过风险 guardrail、保留依据并由人审批。
4. 同一套领域契约逐步扩展到分钟级和全球资产，不以推翻日频内核为代价。

## 7. 分阶段到 10 分路线

| 宏观阶段 | Releases | 主要结果 | 重点提升维度 |
|---|---|---|---|
| I 日频闭环 | R0-R2 | 本机日频人工交易 Beta；A 股 ETF/个股/宏观数据可靠 | 1、2、4、8、10 |
| II 研究产品化 | R3-R4 | 回测、选股、策略、组合优化、风险与复盘工作台 | 3、4、5、6、7、8、10 |
| III AI 与盘中 | R5-R6 | 可评测 AI Copilot/Agent；分钟级数据与盘中信号 Beta | 1、3、5、7、9、10 |
| IV 全球机构化 | R7 | 多市场、多资产、多账户、安全合规与机构运营 | 全部维度冲刺 9-10 |

“全部 10 分”是逐维度完成定义，不是把平均分改成 10。R7 完成也只代表具备冲刺资格；每一维仍需独立证据审查。

## 8. Release Gates

| Gate | 最早阶段 | 硬条件 |
|---|---|---|
| G1 内部本机 Beta | R1 | 单操作者闭环、五个 R1 阻塞清零、loopback-only、可恢复、验收证据包 |
| G2 日频研究 Beta | R3 | 数据许可明确、策略/回测可复现、API 契约稳定、备份恢复演练 |
| G3 决策工作台 Beta | R4 | 组合/风险解释、账本对账、运行手册、SLO 和告警 |
| G4 受控外部 Beta | R4/R5 后 | 认证/RBAC、密钥治理、安全扫描、隐私与数据再分发审查、用户隔离 |
| G5 A 股商业产品 | 独立商业 Gate | 法务合规、投资建议边界、数据授权、审计留存、灾备、SLA、支持流程 |
| G6 全球机构版 | R7 | 跨市场规则、税费、日历、FX、公司行动、多账户、多租户和区域合规 |

商业 Gate 是横向工程，不能等到 R7 才补；R7 也不是 A 股商业化的必要前提。

## 9. 现在不做

- R1 不做 AI、情绪因子、分钟级、券商自动下单、cvxpy 组合优化或多租户。
- 不为了“看起来全品类”提升没有真实数据证据的 registry maturity。
- 不重复实现已有 strategy handler、账户快照、execution planner、涨跌停和手数基础能力。
- 不把真实供应商 API 测试混入默认确定性单元测试。
- 不用动态 star 数、社区规模或营销文案作为能力评分证据。

## 10. 维护规则

1. 每个 release 完成时更新“当前分数、证据等级、硬阻塞和 Gate”。
2. 所有评分变更必须链接测试、验收记录或运行产物。
3. 外部对标至少每半年复核一次，并记录评估日期；变化快的社区数字不写入基准。
4. 路线图只决定“何时做”，本文决定“能力事实是什么”，实施计划决定“本次怎样做”。
5. 新需求必须映射到能力维度、release 和 release gate；无法映射的需求先进入候选池。

## 11. 主要对标来源

本次外部能力复核日期为 2026-07-15，优先使用官方项目说明：

- [QuantConnect LEAN](https://github.com/QuantConnect/Lean)
- [NautilusTrader](https://nautilustrader.io/)
- [Microsoft Qlib](https://github.com/microsoft/qlib)
- [JoinQuant API 文档](https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf)
- [Ricequant Docs](https://rqopen.ricequant.com/doc/)
- [OpenBB](https://openbb.co/)
- [TradingAgents](https://github.com/TauricResearch/TradingAgents)
- [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [OpenAI Agents SDK Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)
- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/)
