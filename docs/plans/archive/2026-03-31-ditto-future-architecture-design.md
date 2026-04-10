# Ditto 未来架构设计 v3

**日期**: 2026-03-31
**状态**: 新设计提案，建议作为后续架构讨论与实施的主基线
**设计立场**: Hybrid Bounded Planes + Explicit Runtime Contracts
**适用范围**: Ditto 全库未来 12-24 个月演进

---

## 1. 设计结论

Ditto 的目标形态不应是：

- 继续围绕 `core / datahub / port` 做局部修补
- 机械套用纯 DDD 子域优先拆分
- 过早追求十几个顶层 package 的理论洁癖
- 把回测、实盘、研究三套流程分别演化成互不兼容的系统

Ditto 的目标形态应当是：

> 一套以量化系统真实运行方式为中心、以模块化单体为载体、以清晰 owner 和显式运行时契约为骨架、支持回测/实盘/研究持续统一演进的架构。

本设计采用：

- **顶层用 Bounded Planes 组织**：按长期稳定的职责面划分系统
- **跨平面协作用显式 Runtime Contract**：避免隐式 service 渗透
- **查询与行为明确分层**：读优化不反向污染行为模型
- **ACL + Strangler 渐进迁移**：先抽边界，再迁实现，再改目录
- **DataFrame-first but not DataFrame-everything**：承认 DataFrame 是量化系统的一等业务载体，但不让其吞并订单、账户、执行和风险状态

---

## 2. 为什么不是纯 DDD，为什么也不是旧技术分层

Ditto 的复杂性主要来自：

- 数据语义复杂：identity、PIT、复权、停复牌、规则生效区间、来源差异
- 流程复杂：回测、实时、研究、摄取、物化并存
- 运行时复杂：同一策略链要在不同运行模式下共享核心语义
- 工程复杂：需要在不打断现有功能的前提下持续演进

纯 DDD 子域优先的问题不在于理念错误，而在于容易过早把系统切得过细，把大量精力花在边界搬运和概念洁癖上，而不是花在量化系统最关键的运行时一致性上。

继续沿用旧的 `core / datahub / port` 技术分层的问题，则是 owner 漂移和语义模糊会长期存在。很多“服务”实际上兼具语义 owner、流程编排者、存储实现者三重身份，系统会越来越难解释。

因此本设计选择第三条路：

- 保留 Hybrid 的现实主义
- 保留 DDD 对 owner、边界、ACL、Shared Kernel 的纪律
- 把“运行时契约”而不是“目录命名”作为一等架构资产

---

## 3. 北极星原则

### 3.1 唯一语义 owner

同一类真相只能有一个 owner。

例如：

- `instrument_id`、calendar、universe、交易规则、费率、公司行为的真相 owner 是 `metadata`
- bars、quotes、ticks、adj、停复牌状态、benchmark 的真相 owner 是 `market`
- 订单、成交、账户、头寸、风险状态推进的真相 owner 是 `engine`
- 因子、研究数据集、评估结果、物化产物的真相 owner 是 `research`

“谁在消费”不等于“谁拥有真相”。

### 3.2 Runtime Contract 显式化

跨平面交互不得依赖隐式 service 调用链，而应通过明确 contract 表达：

- 输入是什么
- 谁组装
- 谁消费
- 生命周期是什么
- 是否要求可重放

### 3.3 Query 和 Behavior 分离

查询模型与行为模型必须分层：

- Query 负责检索、聚合、投影、读优化
- Behavior 负责决策、状态推进、约束检查、执行

读优化不得反向决定行为边界。

### 3.4 ACL 严格隔离外部语义

任何 provider、broker、外部 API 的语义都不能直接进入内部模型。必须先经过 `integration` 中的 ACL 翻译，再进入内部 canonical contract。

### 3.5 渐进式替换优先于大爆炸

迁移必须遵循 Strangler 思路：

1. 先定义新边界
2. 再建立适配层
3. 再迁移调用路径
4. 最后才迁目录与命名

---

## 4. 目标顶层结构

```text
packages/
  kernel/          # 极小共享原语 + 极薄系统级协议
  metadata/        # identity / calendar / universe / rules / corporate actions 真相 owner
  market/          # 行情时序 / adj / status / benchmark 真相 owner
  engine/          # alpha / portfolio / execution / accounting / risk / sessions
  research/        # expression / factors / datasets / evaluation / simulation / materialization
  application/     # Query / Command / Process，唯一合法跨域编排层
  integration/     # provider / broker / external adapters / ingestion acl / runtime adapters
  infra/           # config / logging / storage engine / cache / filesystem / locks / concurrency

apps/
  api/             # HTTP 入口
  cli/             # CLI 入口
  jobs/            # Prefect / 批任务入口
  web/             # Web 前端
```

### 4.1 设计意图

- `packages/*` 表达业务与系统能力
- `apps/*` 只表达入口与部署单元
- `application` 是 package，不是 app
- `metadata` 明确采用你的偏好命名，但语义会严格收敛，不允许重新沦为“杂物箱”

---

## 5. 顶层依赖矩阵

### 5.1 允许依赖

```text
api  -> application
cli  -> application
jobs -> application

application -> metadata
application -> market
application -> engine
application -> research
application -> integration ports

metadata -> kernel
market   -> kernel
engine   -> kernel
research -> kernel
integration -> kernel
integration -> infra
infra -> none
kernel -> none
```

### 5.2 禁止依赖

```text
engine   -X-> metadata implementation
engine   -X-> market implementation
engine   -X-> application

research -X-> engine
research -X-> application

metadata -X-> engine
metadata -X-> research

market   -X-> engine
market   -X-> research

api/cli/jobs -X-> metadata/market/engine/research/integration concrete services

integration -X-> engine domain internals
integration -X-> metadata/market canonical truth internals
```

### 5.3 关键解释

- `application` 是唯一合法跨域装配者
- `engine` 和 `research` 只消费 contract，不直连底层 query implementation
- `integration` 只翻译外部语义，不拥有内部真相

---

## 6. 模块职责与内部组织

## 6.1 kernel

### 职责

- 极小共享原语
- 稳定枚举
- 极薄系统级协议
- 通用错误基类中的最小公共部分

### 允许进入 kernel 的内容

- `InstrumentId`
- `AssetClass`
- `Exchange`
- `Currency`
- `TradeDate`
- `Clock` Protocol
- 少量最薄 runtime 协议，如 `SessionClock`

### 不允许进入 kernel 的内容

- `Order`
- `Position`
- `Account`
- `ExecutionSnapshot`
- `MarketSnapshot`
- `StrategyInputSnapshot`
- 复杂 query object
- 任何依赖 `polars` 的大模型

### 准入标准

一个类型进入 `kernel` 必须同时满足：

1. 跨多个上下文稳定复用
2. 低变更频率
3. 零或极薄流程逻辑
4. 不依赖具体层实现

---

## 6.2 metadata

### 定位

`metadata` 是参考真相 owner，而不是“任意元数据容器”。

### 内部结构

```text
metadata/
  identity/          # identifier mapping, instrument registration, source ticker resolution
  calendar/          # trading days, sessions, exchange schedule
  universe/          # constituents, membership history
  rules/             # trading rules, fee schedules, settlement cycles
  corporate_actions/ # dividend, split, merger, rights, rename
  query/             # metadata query contracts + read ports
  services/          # 领域服务
  models/            # canonical truth models
```

### 拥有的真相

- `source_ticker <-> instrument_id`
- trading calendar
- universe membership
- trading rules / fee schedule / settlement rule
- corporate actions
- reference-side PIT / as-of 语义

### 关键原则

- 交易规则和费率仍归 `metadata` 拥有真相
- `engine.execution` 只是消费方
- 消费频繁不构成 owner 迁移理由

---

## 6.3 market

### 定位

`market` 拥有价格序列及其解释方式。

### 内部结构

```text
market/
  bars/
  quotes_ticks/
  adjustments/
  status/
  benchmark/
  query/
  services/
  models/
```

### 拥有的真相

- stock / etf / index / fx / commodity 时序数据
- `raw / qfq / hfq`
- market-side PIT / as-of
- 停复牌、涨跌停、交易状态
- benchmark 序列

### 关键原则

凡是“价格序列如何被解释”的问题，优先归 `market`。

---

## 6.4 engine

### 定位

`engine` 只负责：

> 在某个时间点、某个会话上下文下，把策略意图推进成头寸、订单、成交、账户与风险状态变化。

### 内部结构

```text
engine/
  alpha/          # signal / rank / selection
  portfolio/      # target generation / allocation / constraint
  execution/      # order planning / brokerage abstraction / fill / slippage / fee application
  accounting/     # account / position / cash / order book
  risk/           # pre-trade / intra-session / post-trade controls
  sessions/       # backtest session / live session / paper session drivers
  audit/          # domain-side audit record contracts
  events/         # engine domain events
  models/         # engine domain models and runtime snapshots
```

### 不做的事

- 不直接查询 metadata/market 的底层实现
- 不持有 provider/broker 原始语义
- 不承担对外 HTTP/CLI 入口职责

---

## 6.5 research

### 定位

`research` 是 DataFrame-first 的研究与评估平面。

### 内部结构

```text
research/
  expression/
  factors/
  datasets/
  evaluation/
  simulation/
  materialization/
  query/
  models/
```

### 原则

- DataFrame 是一等业务载体
- 但 DataFrame 必须有契约，不允许“隐式列约定漂移”
- `research` 不拥有执行状态机，也不依赖 `engine`

---

## 6.6 application

### 定位

`application` 是唯一合法跨域编排层。

### 内部结构

```text
application/
  backtest/
  live/
  research/
  ingestion/
  strategy/
  metadata/
  market/
  shared/
  registry/
```

### 角色划分

- `*Query`：只读，投影 read model，不写状态
- `*Command`：单次写，不做长流程
- `*Process`：长流程，允许协调 Query 和 Command
- `builders/assemblers`：纯装配，不做查询，不写状态

### 核心纪律

- Query 不调 Command / Process
- Command 不调 Query / Process
- Process 可以调 Query / Command
- builders 只能接收已获取的数据并组装 contract

---

## 6.7 integration

### 定位

`integration` 是外部世界与 Ditto 之间的 ACL。

### 内部结构

```text
integration/
  sources/        # provider clients + normalization
  brokerage/      # broker adapters
  ingestion_acl/  # source shape -> canonical command
  runtime/        # stream adapters / polling adapters / job adapters
  diagnostics/    # external capability / preview / probe
```

### 原则

- 外部语义只在此层出现
- 任何 provider payload、broker 回报、第三方错误码都不得直接进入 `engine` / `metadata` / `market`

---

## 6.8 infra

### 定位

通用技术底座，明确不拥有业务语义。

### 典型内容

- config
- logger
- tracing
- storage engine abstraction
- duckdb / parquet / sqlite utilities
- cache
- file lock
- concurrency primitives

---

## 7. 运行时契约体系

本设计最核心的资产不是目录，而是 Runtime Contract。

## 7.1 基本思想

- `engine` 不到处查数据
- `research` 不复用交易状态 contract
- `application` 负责把 query truth 装配成运行时 snapshot
- snapshot 必须极简且可追溯到真实消费点

## 7.2 engine 侧一级 contract

### SessionContext

表达一次运行会话的上下文：

- `run_id`
- `mode`
- `clock`
- `environment`
- `strategy_id`
- `strategy_version`
- `parameter_overrides`

### MarketSlice

表达某个时间步的市场切片：

- `timestamp`
- `trade_date`
- `bars`
- `benchmark`
- 可选 `quotes/ticks`

### StrategyInputSnapshot

提供 alpha / portfolio 真正需要的输入：

- instrument universe
- market features
- precomputed factors or signals
- optional benchmark context

### ExecutionSnapshot

提供 execution / risk 真正需要的输入：

- market snapshots
- rule snapshots
- fee snapshots
- trading status
- session restrictions

### AccountSnapshot

提供账户与持仓只读视图：

- cash
- positions
- frozen quantities
- pending orders
- buying power summary

## 7.3 research 侧一级 contract

### ResearchDataset

研究数据集 contract：

- instruments
- features
- labels
- benchmark
- metadata columns
- lineage metadata

### FactorDataset

- factor values
- validity window
- coverage
- null policy

### EvaluationInput

- returns
- benchmark returns
- exposures
- grouping metadata

## 7.4 契约纪律

- 每个字段必须能追溯到真实消费点
- 不允许为“可能以后会用”预埋字段
- 不允许 contract 退化为共享巨型 DTO

---

## 8. 回测、实盘、研究三条主链路

## 8.1 Backtest Process

```text
application.backtest process
  -> metadata 获取交易日历/identity/规则快照
  -> market 获取区间行情
  -> builders 组装 SessionContext + MarketSlice stream + Snapshot builders
  -> engine.sessions.backtest 驱动时间推进
  -> engine.alpha
  -> engine.portfolio
  -> engine.risk
  -> engine.execution
  -> engine.accounting
  -> research.evaluation
  -> application 持久化 manifest / report / artifacts
```

### 设计目标

- deterministic replay
- 可审计
- 可比较
- 对同一输入稳定产出同一结果

## 8.2 Live Process

```text
external streams / broker callbacks
  -> integration.runtime adapters
  -> application.live process
  -> snapshot builders
  -> engine.sessions.live
  -> engine.alpha / portfolio / risk / execution / accounting
  -> notifications / audit / persistence
```

### 设计目标

- 共享 engine 核心规则
- 隔离第三方 broker / market stream 语义
- 支持 session-level checkpoint 和恢复

## 8.3 Research Process

```text
application.research
  -> metadata/market/research query
  -> assemble ResearchDataset / FactorDataset / EvaluationInput
  -> research.factors / evaluation / simulation / materialization
```

### 设计目标

- 大规模 DataFrame 计算
- 支持重算、对比、版本化物化
- 不污染交易 runtime state

---

## 9. 查询、存储、CQRS 与物化

## 9.1 三类数据形态

### Source Shape

外部 provider 标准化后的接入形态：

- 不含内部真相主键
- 保留 provider 语义
- 仅服务于摄取链前段

### Canonical Store Shape

内部持久化形态：

- 带 `instrument_id`
- 带事件时间或业务时间
- 带版本/生效边界
- 带 lineage / provenance

### Consumer Read Shape

面向查询和装配的读取形态：

- DataFrame
- projection object
- runtime snapshot

## 9.2 CQRS 策略

采用轻量 CQRS，而不是复杂分布式 CQRS：

- 写侧：摄取、规则维护、物化任务
- 读侧：行情查询、PIT 查询、研究数据集、回测预加载
- 允许 materialized views / precomputed datasets 作为读优化
- 不把 materialized read model 误认成 truth source

## 9.3 缓存层次

- `L1`：单次 session 内存缓存
- `L2`：本地持久缓存或中间物化
- `L3`：canonical storage，唯一可审计真相源

## 9.4 存储责任分工

- 语义 owner 定义 contract 与列语义
- 共享数据实现层负责 parquet / duckdb / sqlite 落盘与读优化
- 不让每个域重复造存储底座

---

## 10. 事件模型、审计与可重放

## 10.1 基本立场

Ditto 当前需要：

- 事件契约
- 审计证据
- 可重放与可解释

Ditto 当前不需要：

- 完整事件驱动架构
- 全量 Event Sourcing
- 以异步消息为中心的主流程

## 10.2 事件定义位置

- `kernel`：极小 `DomainEvent` 基类可选保留
- `engine.events`：订单、成交、持仓、风险、session 事件
- `metadata.events`：规则更新、identity 变更、universe 更新
- `market.events`：数据摄取、修复、物化完成
- `research.events`：factor materialized、evaluation completed

## 10.3 engine 稳定事件

- `OrderSubmitted`
- `OrderAccepted`
- `OrderRejected`
- `OrderCanceled`
- `FillRecorded`
- `PositionUpdated`
- `RiskTriggered`
- `SessionCheckpointed`

## 10.4 审计四类证据

### Input Evidence

- 数据集版本
- 规则版本
- 参数覆盖
- session 配置

### Decision Evidence

- 信号输出
- 目标头寸
- 风控调整
- 订单规划

### Execution Evidence

- 委托
- 成交
- 费用
- 账户变化

### Result Evidence

- report
- attribution
- artifact URI
- run manifest hash

## 10.5 可重放要求

每次回测至少应可重建：

- 输入引用集合
- 参数
- 策略版本
- 规则版本
- 数据版本
- 关键中间结果摘要

---

## 11. Ingestion 设计

## 11.1 摄取链路

```text
provider raw payload
  -> integration.sources normalize
  -> Source Shape
  -> integration.ingestion_acl translate
  -> application.ingestion command/process
  -> metadata/market/research canonical write contracts
  -> storage implementation persist
```

## 11.2 必须显式定义的生产级契约

- idempotency key
- duplicate policy
- correction policy
- late arrival policy
- event_time vs business_date 语义
- provenance / lineage
- replay / reprocessing 语义

## 11.3 为什么这部分不能继续藏在私有实现中

如果这些语义不显式化，系统迟早会出现：

- 同一数据被重复写入但无法解释
- 晚到数据修复后无法重算一致
- `as_of` 查询结果因补发数据产生隐式漂移

---

## 12. 包命名与物理落地策略

## 12.1 为什么采用 `metadata / market / engine / research`

这些名字同时满足：

- 量化系统语义直观
- 新贡献者认知负担较低
- 与当前代码现实有合理映射

## 12.2 当前包到目标包的映射

| 当前 | 目标 | 说明 |
|------|------|------|
| `packages/kernel` | `packages/kernel` | 保留，继续收紧 |
| `packages/core/strategy` | `packages/engine/alpha` | 重命名并收紧职责 |
| `packages/core/portfolio` | `packages/engine/portfolio` | 迁移 |
| `packages/core/execution` | `packages/engine/execution` | 迁移 |
| `packages/core/accounting` | `packages/engine/accounting` | 迁移 |
| `packages/core/backtest` | `packages/engine/sessions` | 回测 session driver |
| `packages/data/services/metadata*` | `packages/metadata/*` | 语义 owner 回归 |
| `packages/data/services/market*` | `packages/market/*` | 语义 owner 回归 |
| `packages/data/sources/*` | `packages/integration/sources/*` | 外部世界 ACL |
| `interfaces/services/*` | `packages/application/*` | application 收口 |
| `interfaces/api/*` | `apps/api/*` | 入口适配 |
| `interfaces/cli/*` | `apps/cli/*` | 入口适配 |
| `interfaces/jobs/*` | `apps/jobs/*` | 入口适配 |

---

## 13. 迁移策略

本设计明确拒绝大爆炸重构。

## 13.1 总体原则

- 先抽边界，再迁实现，再改命名
- 先让新调用路径跑通，再删除旧路径
- 每阶段必须可验证
- importlinter 先中间态、后最终态

## 13.2 Phase 0：冻结哲学与约束

交付物：

- 最终顶层依赖矩阵
- `kernel` 准入标准
- `application` 内部规则
- `metadata / market / integration` owner 文档
- 中间态 importlinter

## 13.3 Phase 1：抽 `application`

目标：

- 从现有 `interfaces/services` 中提炼真正的 application 逻辑
- 把回测编排、研究编排、摄取编排收口到 `packages/application`

此阶段不着急改大目录名。

## 13.4 Phase 2：抽 `integration`

目标：

- 把现有 `datahub/sources` 与外部 broker/provider adapter 明确迁入 `integration`
- 形成清晰 ACL

## 13.5 Phase 3：恢复 `metadata` / `market` 语义 owner

目标：

- query contract 回归语义 owner
- 逐步把“服务实现拥有语义”的遗留结构收缩

## 13.6 Phase 4：`engine` / `research` 成型

目标：

- `core` 内部子域正式迁入目标平面
- 回测 session 与 live session 的统一 runtime contract 成立

## 13.7 Phase 5：最后再改顶层包与入口目录

目标：

- 新建最终包结构
- 删除临时兼容层
- 更新文档和 lint 规则

---

## 14. importlinter 与治理规则

## 14.1 顶层约束

- `apps/* -> application`
- `engine -X-> metadata/market concrete implementations`
- `research -X-> engine`
- `integration -X-> engine domain internals`
- `kernel -X-> any non-kernel package`

## 14.2 application 内部约束

- `*Query -X-> *Command / *Process`
- `*Command -X-> *Query / *Process`
- `*Process -> *Query / *Command`
- `builders -> no query, no write`

## 14.3 运行时契约约束

- Snapshot fields 必须可追溯到消费点
- DataFrame contract 必须文档化列语义
- 禁止在 domain 内部偷偷拉底层 query service

---

## 15. 非目标

以下不是当前设计目标：

- 微服务化
- 全量异步事件驱动
- 全量 Event Sourcing
- 为追求形式纯度而拒绝 DataFrame
- 为追求包名整洁而提前做大规模搬家
- 让所有概念都对象化

---

## 16. 风险分析

## 16.1 最大收益

- owner 更清晰
- 回测/实盘/研究的骨架统一
- 未来新增功能的落点更稳定
- 迁移路径更现实
- ACL 和 query/behavior 分层更适合长期演进

## 16.2 最大风险

### 风险 1：`metadata` 再次变成杂物箱

**表现**：

- 什么都往 `metadata` 塞
- 把消费频繁的内容都宣称成 metadata

**应对**：

- 严格限定为 identity / calendar / universe / rules / corporate_actions

### 风险 2：`application` 膨胀成上帝层

**表现**：

- Query 里偷偷写状态
- Process 里塞业务判断
- builder 里发查询

**应对**：

- 用命名和 lint 约束强制角色纪律

### 风险 3：Runtime Contract 变成厚 DTO

**表现**：

- snapshot 字段越来越多
- “以后可能会用”字段泛滥

**应对**：

- 字段必须对应消费点
- 定期裁剪

### 风险 4：迁移中间态太长

**表现**：

- 旧路径和新路径长期并存
- 文档和 lint 不同步

**应对**：

- 每阶段定义明确 exit criteria
- 及时删旧代码

### 风险 5：过早推广通用抽象

**表现**：

- 把 `DataProvider` 做成万能神接口
- 把 `Pipeline` 做成所有东西都得套的框架

**应对**：

- 运行时适配器保持克制
- 先围绕真实场景建 contract，再抽共性

---

## 17. 最终判断

我建议 Ditto 后续架构以本设计为主基线。

一句话概括：

> Ditto 的长期优雅架构，不是“更漂亮的目录树”，而是“metadata/market 明确拥有真相，engine/research 专注运行与计算，application 独占跨域装配，integration 隔离外部语义，kernel 保持极小，回测/实盘/研究通过显式 runtime contract 统一演进”。

这套架构的价值不在于它最“纯”，而在于它最有机会在未来 12-24 个月内持续落地、持续扩展、持续保持解释力。

---

## 18. 参考原则与资料

以下资料用于校准本设计中的原则取向，而不是生搬硬套其具体目录形态：

- QuantConnect, Algorithm Framework Overview
  https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview

- Microsoft Azure Architecture Center, Anti-Corruption Layer pattern
  https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer

- Microsoft Azure Architecture Center, CQRS pattern
  https://learn.microsoft.com/zh-cn/azure/architecture/patterns/cqrs

- Microsoft Azure Architecture Center, Materialized View pattern
  https://learn.microsoft.com/en-us/azure/architecture/patterns/materialized-view

- Microsoft Azure Architecture Center, Strangler Fig pattern
  https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig

- Eric Evans, DDD Reference
  https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf
