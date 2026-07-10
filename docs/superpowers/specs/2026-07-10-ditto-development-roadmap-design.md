# Ditto 后续发展规划与分阶段开发设计

> Date: 2026-07-10
> Status: strategic roadmap design
> Scope: 从当前 RC1/Wave1a 基线出发，规划 Ditto 向「全球全品类 AI 量化系统」演进的分阶段产品与工程路线。

## 1. 背景与目标

Ditto 当前已经具备强工程底座、严格数据治理、日频 A 股 ETF/个股研究 primitives、回测与交易意图/手工成交骨架，并且 ditto-app Trading 域已经完成 live-connected smoke。上一轮评估给出的核心判断是：

- 工程架构成熟度高，12 包边界、lint/type/test/import-linter 合约已通过。
- A 股日频后端能力基本成型，但真实每日人工交易产品闭环尚未完全 ready。
- 全球全品类、分钟级、AI-Agent 化仍处于早期或规划阶段。
- 当前最关键缺口不是再堆新模块，而是把「真实数据 -> 策略 -> 信号 -> 决策 -> 人工成交 -> 复盘」打成每天可用的产品闭环。

长期目标仍然是全球全品类 AI 量化系统，但阶段优先级必须服从产品可用性：

1. 优先支持 A 股 ETF、个股、指数、宏观和商品大宗日频数据。
2. 优先完成日级别投研、回测、信号、仓位建议和人工交易复核。
3. 后续扩展分钟级数据、盘中信号和盘中因子计算。
4. 不把全自动交易作为近期目标；AI 和 Agent 必须先服务投研、解释、建议和人工审批。

## 2. 文档关系

本文是后续发展的母版路线图。相关文档分工如下：

| 文档 | 角色 |
|---|---|
| `docs/plans/2026-07-10-capability-benchmark-design.md` | 当前功能能力评级、业界对标、A-D 大阶段方向 |
| `docs/plans/2026-07-10-phase-a-implementation-plan.md` | 阶段 A 的候选实施计划，面向具体开发执行 |
| `docs/acceptance/wave1-data-readiness.md` | RC1 真实数据与 promotion 验收证据 |
| `docs/acceptance/wave1a-first-real-use.md` | ditto-app Trading live smoke 与剩余阻塞 |
| 本文 | 产品路线、阶段边界、依赖关系、验收门槛、后续计划生成入口 |

后续每个阶段进入开发前，应从本文抽取一份单独 implementation plan，而不是直接把所有阶段并行开工。

## 3. 路线选择

比较三种路线：

| 路线 | 优点 | 风险 | 结论 |
|---|---|---|---|
| 平台优先 | 架构最完整，长期扩展好 | 继续停留在工程系统，产品感弱 | 不作为主线 |
| AI 优先 | 体验有想象力，容易展示 | 底层数据/信号未闭环时 AI 容易空转 | 作为中期增强 |
| 产品闭环优先 | 最快进入真实日用，能暴露高价值缺口 | 需要强约束范围 | 作为主线 |

推荐路线：产品闭环优先。先把 A 股日频人工交易信号产品打穿，再扩研究深度、回测实验、组合优化、AI Copilot、分钟级和全球多资产。

## 4. 阶段命名与总览

为避免和历史 Wave1 文档混淆，本文把未来路线定义为 R0-R7 release roadmap：

| 阶段 | 名称 | 目标产品状态 | 预计节奏 |
|---|---|---|---|
| R0 | 产品边界固化 | 统一目标、验收和里程碑口径 | 约 1 周 |
| R1 | 日频人工交易 MVP | 每天可生成并复核真实 A 股信号 | 2-3 周 |
| R2 | A 股日频数据与研究升级 | 可支撑多策略研究和较长历史回测 | 3-5 周 |
| R3 | 回测、选股、策略管理产品化 | 策略研发工作台 Beta | 4-6 周 |
| R4 | 组合优化、风险、复盘工作台 | 投资决策工作台 Beta | 4-6 周 |
| R5 | AI Copilot / Agent v1 | 只读和审批式智能助手 | 4-8 周 |
| R6 | 分钟级和盘中信号 Beta | 盘中观察、提醒和因子快照 | 6-10 周 |
| R7 | 全球全品类扩展 | 多资产平台化 | 长期 |

和已有 A-D 阶段的关系：

- R1-R4 对应当前 `阶段 A：日级人工交易闭环深化` 的产品化展开。
- R5 对应 `阶段 B：AI 能力注入`。
- R6 对应 `阶段 C：分钟级/盘中架构演进`。
- R7 对应 `阶段 D：全球化/机构化`。

## 5. 当前基线

当前系统状态按产品闭环口径从严评估：

| 能力 | 状态 |
|---|---|
| 工程架构 | 强。12 包边界和质量门禁成熟 |
| 数据治理 | 强。PIT、catalog、promotion、source-health、lineage 体系完整 |
| A 股 ETF/个股日频数据 | 可用但历史覆盖和写入性能仍需增强 |
| 策略与信号 | primitives 具备，但真实 daily-decision ready 链路还受策略定义发布阻塞 |
| 回测 | 日频严谨性较好，缺实验管理、参数扫描、walk-forward |
| 仓位与优化 | v1 可用，行业级优化能力不足 |
| 风险与复盘 | 规则和报告雏形具备，连续状态、审计和产品展示不足 |
| 前端 | Trading 域 live 接通，其他域多为 prototype-only |
| AI/Agent | 占位和原型为主，无正式 runtime |
| 分钟级/盘中 | 尚未进入体系化实现 |

当前最适合的产品定位：

> A 股 ETF/个股日频量化研究与人工交易决策系统的内部 Beta 前夜。

## 6. R0：产品边界固化

### 目标

把 Ditto v1 从「能力集合」收敛为「日频人工交易信号产品」，并为后续阶段建立统一验收语言。

### 范围

必须完成：

- 定义 v1 产品主流程：数据更新 -> 策略运行 -> 信号生成 -> 决策复核 -> 手工成交录入 -> 偏差/复盘。
- 明确近期不做全自动交易、不做真实 broker adapter、不做分钟级交易执行。
- 建立产品级能力 maturity 表，区分 backend primitive、API contract、frontend product、daily operation 四种状态。
- 确认 R1 只以 A 股日频 ETF/个股为主线，宏观/商品作为辅助研究数据。

不做：

- 不引入新数据源大扩张。
- 不启动 AI-Agent runtime。
- 不重构回测引擎。

### 验收

- 有一份产品能力清单，所有能力标注 `ready / partial / experimental / reserved`。
- 有一份 R1 验收清单，包含 API、前端、数据和真实运行证据。

## 7. R1：日频人工交易 MVP

### 目标

每天打开系统，可以看到真实信号、目标仓位、建议操作、风险提示，并能人工记录成交和复盘偏差。

### 核心工作包

1. 策略定义发布链路

   当前 first-real-use evidence 已说明 `publish-signals` 会因 strategy definition 未入 catalog 而阻塞。R1 必须补齐 seed 策略定义发布流程，让至少一个 ETF 策略和一个个股/行业策略能稳定进入 catalog。

2. EOD 信号闭环

   EOD pipeline 应在真实数据下完成 ingestion、materialization、strategy run、signal package publish，并产出可查询的 trade intents。

3. Daily Decision V2

   当前 Daily Decision 主要聚合 signal intents、positions、deviation、pnl。R1 需要升级为真实交易决策报告，至少包含：

   - 数据健康和 freshness。
   - 策略运行状态。
   - 信号摘要和个券明细。
   - 当前仓位、目标仓位和建议买卖。
   - 基础风险提示。
   - 成交偏差和 PnL。
   - readiness status 和阻塞原因。

4. Trading 前端真实态

   ditto-app `/trading`、`/trading/signals`、`/trading/portfolio`、`/trading/orders` 从 live empty state 升级为真实可复核工作台。

5. 手工交易与复盘

   保留 manual/paper 口径：用户复核信号后，系统只记录 intent status、manual fill、actual position、deviation 和 post-trade notes。

### 验收

- 真实环境下 `GET /api/v1/trade/daily-decision` 对至少一个 seed strategy 返回 `ready` 或明确可人工复核的 `review`，不能停留在 `no signal intents available`。
- EOD 运行后可查询最新 signal package 和 trade intents。
- 前端展示真实信号、仓位、建议操作和成交录入，而不是 mock 或 blocked 空态。
- 手工 fill 录入后，偏差报告能反映实际成交状态。
- R1 evidence 写入 `docs/acceptance/`。

## 8. R2：A 股日频数据与研究升级

### 目标

让 A 股日频研究不再只依赖 RC1 小样本，形成可支撑策略开发和回测的较长历史数据层。

### 核心工作包

- 解决 market backfill 写入瓶颈，降低逐日 SQLite 写锁争用。
- ETF、指数、个股日线历史扩展到至少 3-5 年，优先覆盖 2018 年以来。
- 完善复权、停牌、涨跌停、ST/退市、行业分类、指数成分。
- 将宏观数据扩为可研究集合：利率、社融、PMI、CPI/PPI、汇率、商品价格。
- 商品大宗先作为日频观察与宏观因子数据，不作为交易执行品种。

### 验收

- 核心 A 股日频数据集有长期历史、freshness、schema、row count、source snapshot 证据。
- stock + macro 从 experimental 转为可默认研究使用，promotion evidence 完整。
- 至少 3 个策略模板可基于扩展数据运行回测。

## 9. R3：回测、选股、策略管理产品化

### 目标

让用户可以创建、运行、比较、晋级策略，而不是只通过后端 primitives 和 CLI 手工拼流程。

### 核心工作包

- 回测 API 暴露关键参数：`participation_rate`、`fill_mode`、成本模型、执行延迟、benchmark。
- 增加批量回测、参数扫描、walk-forward、策略对比和实验记录。
- 建立策略生命周期：`draft -> research -> candidate -> paper -> production`。
- 选股工作流产品化：universe、过滤条件、因子打分、组合构建、结果解释。
- 增加基础策略模板：ETF 轮动、低波红利、质量价值、动量反转、宏观择时。

### 验收

- 一个策略可以从 draft 创建到 research 回测，再晋级为 candidate/paper。
- 每个策略有回测报告、因子报告、风险报告、晋级建议。
- 参数实验可以被比较和复现。
- 发布后的策略能进入 R1 的 EOD 信号链路。

## 10. R4：组合优化、风险、复盘工作台

### 目标

让系统不仅回答「买什么」，还能解释「买多少、为什么、风险在哪里、执行后偏差如何」。

### 核心工作包

- 引入约束优化器，支持最大权重、现金比例、换手约束、行业/风格暴露、交易成本和流动性约束。
- 在现有 mean-variance v1 基础上引入更完整 optimizer：constrained mean-variance、risk parity、HRP 或 Black-Litterman 可分阶段推进。
- 完善风险：集中度、回撤、波动、VaR、行业/风格暴露、压力测试。
- 建立 post-trade 复盘：信号 vs 实际成交、回测 vs 实盘、成本拖累、贡献归因。
- 在 Daily Decision 中解释目标仓位来源和风险约束。

### 验收

- 每个目标仓位都有 optimizer input、constraint、risk/cost explanation。
- Daily Decision 能说明建议交易的风险和成本影响。
- 周度/月度复盘报告可自动生成。

## 11. R5：AI Copilot / Agent v1

### 目标

AI 首先作为投研、解释和审批式建议助手，不直接自动交易。

### 分层

L0 基础设施：

- LLM provider 网关。
- Agent runtime。
- Tool registry，把 ditto API、reports、artifacts 包装为可审计工具。
- Permission 和 audit。
- Tracing 和 eval。

L1 只读 Copilot：

- 解释今日信号。
- 总结宏观、市场、行业和商品信息。
- 解读回测、因子和风险报告。
- Text-to-SQL 或受控数据查询。
- RAG 研报/公告/内部文档问答。

L2 审批式建议：

- 生成策略草稿和因子表达式。
- 提出仓位和买卖建议。
- 给出风险复核意见。
- 生成复盘总结。

L3 多 Agent 投研：

- Research Agent 提出假设。
- Strategy Agent 生成实验。
- Portfolio Agent 给出仓位建议。
- Risk Agent 做反方检查。
- Ops Agent 检查数据和 EOD 故障。

### 硬约束

- Agent 不得直接下单。
- 所有建议必须引用数据、报告或代码来源。
- 所有写操作必须经过人工审批和审计。
- AI 输出不得绕过 RiskGate 或 maturity gate。

### 验收

- AI 可以基于真实 Ditto 数据回答，不依赖 mock。
- AI 生成策略草稿后，必须经过测试、回测和人工发布。
- Agent tool call、permission、audit、eval 均有证据。

## 12. R6：分钟级与盘中信号 Beta

### 目标

在日频产品稳定后，扩展分钟级数据、盘中因子和盘中信号观察。R6 仍以提醒和观察为主，不引入自动交易。

### 核心工作包

- 建立分钟级 bar 数据模型和 storage。
- 扩展 calendar/session/late-arrival 语义。
- 支持分钟级 rolling、当日累计和盘中截面因子。
- 增加 intraday signal snapshot。
- 增加前端 intraday monitor：信号变化、触发条件、风险变化、数据新鲜度。
- 调度从 EOD 扩展到 intraday jobs。

### 验收

- 至少 ETF 分钟级数据和盘中信号观察可用。
- 盘中链路不破坏 R1-R4 的日频主流程。
- 每个盘中信号有时间戳、数据新鲜度和可复现证据。

## 13. R7：全球全品类扩展

### 目标

从 A 股本土日频产品扩展为多市场、多资产、多币种平台。

### 扩展顺序

1. A 股 ETF、个股、指数、宏观、商品日频。
2. 港股和美股 ETF/指数。
3. FX、商品现货、全球宏观数据。
4. 期货和连续合约。
5. 期权、债券等复杂品类。

### 平台能力

- 多交易所 calendar。
- 多币种和 FX conversion。
- futures roll 和 contract mapping。
- corporate actions。
- asset-class-specific risk model。
- global data source abstraction。

### 验收

- 新资产类别接入不破坏 A 股主流程。
- 每个资产类别都必须拥有数据、回测、风险、信号和前端展示的最小闭环。
- experimental asset class 不得被文档或 API 描述为 production-ready。

## 14. 跨阶段依赖

```text
R0 product boundary
  -> R1 daily manual trading MVP
    -> R2 A-share daily data/research depth
      -> R3 backtest/selection/strategy management
        -> R4 portfolio/risk/review workbench
          -> R5 AI Copilot/Agent
          -> R6 intraday beta
            -> R7 global multi-asset
```

可以并行但必须受控：

- R1 和 R2 可部分并行：R1 以当前 RC1 数据打通闭环，R2 解决历史和数据广度。
- R3 可在 R1 ready 后启动，不应等待 R2 全部完成。
- R5 和 R6 都以 R4 的日频决策工作台稳定为前置；二者不是严格串行，R5 可以更早预研，R6 应等日频主链路稳定后再启动。
- R5 的 L0 基础设施可以在 R3/R4 稳定后预研，但不应早于 Daily Decision 和 strategy lifecycle 稳定。
- R6 不应早于 R1-R4；分钟级会放大所有日频未闭环的问题。

## 15. 优先级

P0：

- seed 策略发布链路。
- EOD -> signal package -> daily-decision ready。
- Daily Decision V2。
- Trading 前端真实信号态。
- 手工成交和偏差复盘。

P1：

- A 股历史数据扩容和写入瓶颈治理。
- 回测参数、实验对比、策略生命周期。
- 组合优化 v2。
- 风险和复盘报告。

P2：

- 宏观/商品研究数据。
- AI 只读 Copilot。
- 情绪/文本因子。
- 策略代码生成和审计。

P3：

- Agent 审批式投研。
- 分钟级/盘中信号。
- 全球多资产。

## 16. 开发治理

每个阶段启动前必须满足：

- 有单独 implementation plan。
- 明确涉及的 package boundary。
- 明确 API contract 和 maturity。
- 明确测试层级：unit、integration、golden、acceptance。
- 明确真实数据 evidence 或 mock/prototype 限制。

每个阶段结束前必须满足：

- 后端 `pixi run -e dev check` 通过。
- 涉及架构边界时 import-linter 和 architecture smell check 通过。
- 前端阶段需要 ditto-app 独立 `bun run check` 和必要 browser smoke。
- 验收证据写入 `docs/acceptance/` 或对应 review/report 文档。
- capability maturity 文档同步更新。

## 17. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 全球全品类目标过早扩散 | 日频产品继续不成形 | R1-R4 只服务 A 股日频人工交易主线 |
| AI 过早启动 | 形成演示型功能，无法落地交易决策 | R5 前置条件设为 Daily Decision 和 strategy lifecycle 稳定 |
| 分钟级过早启动 | 数据/调度/回测复杂度爆炸 | R6 后置，先留抽象扩展点 |
| 数据历史扩容受写入瓶颈限制 | 回测和因子研究可信度不足 | R2 专门处理 backfill 性能和批量写入 |
| 前端继续 prototype 化 | 后端能力无法产品化 | R1/R3/R4 均设置前端真实态验收 |
| optimizer/risk 引入复杂依赖 | 破坏包边界或 CI 成本上升 | 新依赖必须在阶段计划中 mini-design 和架构检查 |

## 18. 最近一个实施切片

下一份实施计划应聚焦 R1，不要同时启动 R2-R7。R1 推荐拆为：

1. 策略定义发布链路。
2. EOD 信号生成闭环。
3. Daily Decision V2。
4. Trading 前端真实信号态。
5. 手工成交、偏差和复盘 evidence。

已有 `docs/plans/2026-07-10-phase-a-implementation-plan.md` 可作为 R1/R2/R4 的候选素材，但需要在实际开工前按 R1 范围重新裁剪，避免把组合优化、风控连续性、数据 promotion 和前端 production 全部塞入第一批。

## 19. 成功标准

短期成功：

- 一个真实交易日后，系统能展示真实信号、目标仓位、建议操作和风险提示。
- 用户能人工记录成交，并在系统里看到偏差和复盘。
- 该流程可连续运行多个交易日，而不是一次性 smoke。

中期成功：

- 策略可以被创建、回测、比较、晋级和发布。
- 组合优化和风险解释进入每日决策。
- AI 可以解释信号和报告，但仍受审批和审计约束。

长期成功：

- Ditto 成为以 A 股本土和 AI 原生为差异化的全球多资产量化平台。
- 每个资产类别都遵守数据治理、回测、风险、信号和产品展示的统一闭环。
