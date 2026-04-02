# Ditto 全库架构重构设计

**日期**: 2026-03-26
**状态**: 已决策，待实施
**目标**: 建立一套面向长期演进的量化系统架构，使 Ditto 在 DDD 边界、数据语义、流程编排、实时/回测统一性方面达到业界最佳实践水位。

---

## 1. 设计摘要

Ditto 的目标形态不是继续围绕 `core / port / datahub` 这种技术层命名做局部修补，而是建立一套真正按业务边界组织、同时兼容量化系统数据特性的架构。

本方案的核心判断如下：

- Ditto 不是经典 CRUD 企业系统，也不是“纯实体驱动”的传统 DDD。
- Ditto 应被设计成一套以 DDD 为骨架、以 DataFrame 为一等业务载体的量化模块化单体。
- 外部数据接入、内部查询语义、行为域、存储实现必须显式拆开。
- `decisioning / trading / analytics` 一律采用“预组装输入”模式，不直接查询 `metadata / marketdata / sources / datahub`。
- `metadata` 和 `marketdata` 是查询语义拥有者，`application` 是跨域编排者，不复制子域内部查询语义。
- `sources` 从 `datahub` 中独立，分别代表“外部世界接入边界”和“内部数据存储实现边界”。

一句话概括：

> `sources` 接外部，`metadata/marketdata` 管查询语义，`application` 管输入装配与流程编排，`decisioning/trading/analytics` 只做业务行为与计算，`datahub` 负责内部持久化与查询实现。

---

## 2. 当前系统的核心问题

当前 Ditto 的主要架构问题不在于“有没有用 DDD”，而在于多种语义轴混在了一起。

### 2.1 技术层轴与业务域轴混杂

- `port / core / datahub / infra` 是技术分层轴。
- `strategy / execution / backtest / derived / evaluation / research / quality` 是业务域轴。
- 当前很多目录同时承载两种含义，导致命名与归属不稳定。

### 2.2 四类模型没有被明确分层

当前系统中至少存在四类不同性质的模型：

- 共享语义原语
- 领域行为模型
- DataFrame 分析模型
- 存储记录模型

它们在很多地方被混用，导致命名冲突、职责漂移、边界失焦。

### 2.3 行为域与查询装配混在一起

- 部分领域逻辑直接持有数据查询能力。
- 部分 application/port 逻辑又承担了隐性领域判断。
- 结果是行为对象不纯，编排对象也不纯。

### 2.4 外部数据接入与内部数据存储混在一起

- `sources` 当前挂在 `datahub` 下面。
- 但从语义上，它更像 ACL/connector/inbound adapter。
- `datahub` 则更像 repository/store/query adapter。

这两类基础设施面向的是完全不同的边界，不应长期捆绑。

### 2.5 实时、回测、研究没有被统一成同一套职责模型

- 回测循环、实时流、研究数据构建、指标评估目前存在多套局部编排方式。
- 长期会造成“同样的概念在不同场景有不同 owner”的问题。

---

## 3. 北极星架构原则

本次重构遵循以下原则。

### 3.1 子域优先于技术层

顶层模块按业务子域命名，技术职责通过模块内部规则和依赖规则体现，不再以 `core` 作为总包。

### 3.2 行为域不直接查数据

`decisioning / trading / analytics` 一律不直接依赖数据查询能力，只消费由 `application` 预组装好的输入契约。

### 3.3 查询语义由数据域拥有

- identity、calendar、universe、rules、metadata PIT 由 `metadata` 拥有。
- bars、quotes、ticks、adj、market PIT 由 `marketdata` 拥有。
- 外部 provider 语义由 `sources` 拥有。

### 3.4 application 是唯一合法的跨域装配层

`application` 负责：

- 选择调用哪些数据域能力
- 组装行为域输入
- 执行 command
- 推进 process
- 进行重试、补偿、checkpoint

### 3.5 DataFrame 是一等业务载体

在量化系统中，DataFrame 不是临时传输格式，而是合法的一等业务模型，尤其适用于：

- `marketdata`
- `analytics`
- `decisioning` 中的决策 frame

但 DataFrame 不能冒充聚合根、实体和值对象。

### 3.6 Shared Kernel 必须保持极小

`kernel` 只允许承载跨域稳定、长期低变更的共享语义原语，不允许演化为“大共享领域中心”。

---

## 4. 目标模块划分

```text
apps/
  interfaces/
    http/
    cli/
    jobs/
    streams/
    bootstrap/

packages/
  kernel/
  application/
  metadata/
  marketdata/
  decisioning/
  trading/
  analytics/
  sources/
  datahub/
  infra/
```

### 4.1 `kernel`

职责：

- 共享语义原语
- 稳定枚举
- 极小值对象
- 通用基础错误类型

允许示例：

- `InstrumentId`
- `AssetClass`
- `Exchange`
- `TradeDate`
- `Currency`

禁止示例：

- 厚输入模型
- 领域协调逻辑
- Query/Repository 接口

### 4.2 `metadata`

职责：

- identity 体系
- instrument 基本信息
- identifier 映射
- calendar / trading days
- universe / constituents
- trading rules / fee schedule
- metadata 自身的 PIT 语义
- 基础数据质量语义

这是 supporting domain，但拥有强语义真相，不能继续被降格为“datahub 里的一组表”。

### 4.3 `marketdata`

职责：

- stock / etf / index / fx / commodity 的市场时序数据
- bars / quotes / ticks / order book snapshot
- adj factor 与复权语义
- benchmark series
- market data 自身的 PIT/asof 语义

这是 DataFrame-first supporting domain。

### 4.4 `decisioning`

职责：

- strategy spec
- signal / score / ranking
- selection
- constraints
- portfolio construction
- target generation

这个模块只负责回答：

> 在当前输入下，我想持有什么？

### 4.5 `trading`

职责：

- order
- account
- position
- execution
- brokerage abstraction
- pre-trade / post-trade risk

这个模块只负责回答：

> 如何把目标意图转化为订单、成交和账户状态变化？

### 4.6 `analytics`

职责：

- derived
- research
- evaluation
- simulation

这个模块承认 DataFrame 是一等模型，但不直接持有底层查询实现。

### 4.7 `sources`

职责：

- 外部 provider 接入
- API client
- ACL 适配
- 重试、限流、认证
- raw payload -> normalized frame
- `SourceSchema`
- source diagnostics / preview / capabilities

`sources` 面向的是外部世界，不应继续作为 `datahub` 子模块存在。

### 4.8 `datahub`

职责：

- repository/store/query implementation
- cache / archive / read optimization
- materialized storage
- 实现各域定义的稳定存储抽象

`datahub` 面向的是内部世界，不拥有业务语义所有权。

### 4.9 `application`

职责：

- 构建行为域输入
- command 执行
- process 编排
- 查询结果投影
- 跨域流程治理

它是整个系统中唯一合法的跨域装配者。

### 4.10 `interfaces`

职责：

- HTTP/CLI/jobs/streams 等入口
- 参数解析
- DTO 翻译
- application 调用
- 响应序列化

`interfaces` 不承担业务编排。

### 4.11 `infra`

职责：

- 配置
- 日志
- 锁
- 连接
- 文件系统
- 任务底座
- 通用技术能力

---

## 5. 顶层依赖规则

允许依赖：

```text
interfaces -> application
application -> metadata | marketdata | decisioning | trading | analytics | sources
sources -> infra
datahub -> metadata | marketdata | decisioning | trading | analytics 的稳定存储抽象 + infra
metadata -> kernel
marketdata -> kernel
decisioning -> kernel
trading -> kernel
analytics -> kernel
infra -> none
kernel -> none
```

禁止依赖：

- `decisioning / trading / analytics` 直接依赖 `metadata`
- `decisioning / trading / analytics` 直接依赖 `marketdata`
- `decisioning / trading / analytics` 直接依赖 `sources`
- `decisioning / trading / analytics` 直接依赖 `datahub`
- `interfaces` 直接依赖业务域或 `datahub`
- `datahub` 依赖各域的 `service / process / pipeline / aggregate behavior`
- 通过 `TYPE_CHECKING`、延迟导入、运行时字符串绕过依赖约束

唯一例外：

- `interfaces/bootstrap` 可以依赖 `application + sources + datahub + infra`
- 其职责仅限于装配依赖与启动

---

## 6. 模型分层与所有权

本架构明确区分以下几类模型。

### 6.1 Kernel Primitives

归属：`kernel`

定义标准：

- 跨多个子域稳定复用
- 语义一致
- 低变更频率
- 零流程逻辑

示例：

- `InstrumentId`
- `AssetClass`
- `TradeDate`
- `Currency`

### 6.2 Behavior Input Contracts

归属：消费它们的行为域

这是一个关键约束：

> 行为域输入契约不定义在 `application`，而定义在对应行为域本身。

原因：

- 输入契约描述的是“这个域要什么数据才能工作”
- 它是行为域的边界，不是 application 的边界
- 如果把它放在 application，会形成反向依赖和循环语义

示例：

- `decisioning.strategy.input.StrategyInputBundle`
- `trading.execution.context.ExecutionContext`
- `analytics.research.dataset.ResearchDataset`
- `analytics.evaluation.input.EvaluationInput`

`application` 负责构建这些契约，但不拥有其语义。

### 6.3 Application DTO / Process State

归属：`application`

职责：

- use case request / response
- process state
- 任务运行状态
- 对外 transport object

示例：

- `RunBacktestRequest`
- `RunBacktestResult`
- `RunIngestionRequest`
- `IngestionJobState`
- `SourceDiagnosticsResponse`

### 6.4 Domain Models

归属：对应子域

示例：

- `trading` 的 account/order/position
- `decisioning` 的 target / decision result
- `metadata` 的 instrument / rule / universe

### 6.5 Analytical Frames

归属：`marketdata / analytics / decisioning`

示例：

- bars frame
- factor frame
- decision frame
- evaluation frame

这些模型可以是 `polars.DataFrame`，但必须有清晰列约定和契约语义。

### 6.6 Store Records

归属：目标子域与 `datahub` 协作

这类模型只表达最终内部存储语义，不直接暴露给行为域。

---

## 7. 查询与输入装配原则

### 7.1 总原则

单域查询语义归子域，跨域装配归 `application`。

### 7.2 `metadata` 拥有的查询语义

- `source_ticker <-> instrument_id` 解析与反查
- identifier 体系
- instrument 基本信息
- calendar / trading days
- universe / constituents
- trading rules / fee schedule
- metadata 自身的 PIT 查询

### 7.3 `marketdata` 拥有的查询语义

- bars / quotes / ticks / benchmark
- `raw / qfq / hfq`
- adj factor
- `asof` / market PIT

### 7.4 `application` 拥有的查询职责

`application` 不实现 identity/PIT/adj 的底层语义，但负责：

- 选择调用哪些子域能力
- 选择是否使用 `asof`
- 选择是否复权
- 跨域拼装数据
- 构建行为域输入契约

### 7.5 全局采用模式 A

以下模块统一采用“prepared input first”模式：

- `decisioning`
- `trading`
- `analytics`

含义：

- 它们不直接查数据
- 不直接拿 source/store/query 接口
- 只消费 `application` 预组装输入

这是本次重构的核心铁律之一。

---

## 8. `application` 内部组织与角色规则

`application` 的大目录按业务域组织，不单独拉 `queries/commands/processes` 大桶。

推荐结构：

```text
application/
  shared/
  strategy/
    dto.py
    builders.py
    policies.py
    build_strategy_input.py
    run_backtest.py
    run_live_session.py
  trading/
    dto.py
    builders.py
    build_execution_context.py
    submit_orders.py
    rebalance.py
  analytics/
    dto.py
    builders.py
    build_research_dataset.py
    run_evaluation.py
  ingestion/
    dto.py
    builders.py
    preview_mapping.py
    persist_batch.py
    run_ingestion.py
  sources/
    dto.py
    diagnostics.py
```

角色通过命名后缀约束：

- `*Query`
- `*Command`
- `*Process`

### 8.1 `*Query`

职责：

- 只读
- 调用 `sources / metadata / marketdata`
- 组装 read model
- 构建行为域输入契约

禁止：

- 写状态
- 调用 `*Command`
- 调用 `*Process`

### 8.2 `*Command`

职责：

- 单次写操作
- 调用领域行为
- 处理单事务边界

禁止：

- 调用 `*Query`
- 调用 `*Process`

如果与 Query 共享装配逻辑，应提取到 `builders.py`。

### 8.3 `*Process`

职责：

- 长流程
- 多步骤编排
- 调用 `*Query + *Command`
- 重试、补偿、checkpoint、状态推进

默认禁止：

- `Process -> Process`

如需复用，共性应下沉到 `builders.py / policies.py / shared/`。

### 8.4 application 内部依赖规则

- `*Query` 可以依赖 `builders.py / policies.py / shared/`
- `*Command` 可以依赖 `builders.py / policies.py / shared/`
- `*Process` 可以依赖 `*Query / *Command / builders.py / policies.py / shared/`
- `*Query -X-> *Command / *Process`
- `*Command -X-> *Query / *Process`

---

## 9. `sources`、摄取链与 SourceSchema

### 9.1 `sources` 的定位

`sources` 是外部世界进入系统的边界，属于 ACL/connector/inbound adapter。

其职责包括：

- provider client
- token / auth
- rate limit / retry
- provider-specific raw payload 解析
- 列字段标准化
- source diagnostics / preview

### 9.2 SourceSchema 的定位

`SourceSchema` 定义在 `sources`，不定义在各业务子域。

原因：

- 它表达的是外部数据接入后的字段标准化
- 不是内部领域真相
- 还未进入 identity 统一和最终存储语义

`SourceSchema` 包含：

- 标准化列名
- 基础类型
- source 主键
- `source_ticker`
- source business date / event time

`SourceSchema` 不包含：

- `instrument_id`
- 内部主键/外键
- PIT 存储列
- 最终分区/落盘规则

### 9.3 摄取流程

正式链路如下：

```text
provider raw payload
-> sources 输出符合 SourceSchema 的标准化 frame
-> application.ingestion 做 identity 统一 / DQ / 路由 / duplicate policy
-> datahub 按目标子域 StoreSchema 落库
```

### 9.4 标识符统一化的 owner

`source_ticker -> instrument_id` 的统一化不属于 `SourceSchema`，也不属于 `datahub` 内部私有实现逻辑。

它属于：

- `metadata` 提供 identity 解析语义
- `application.ingestion` 编排调用该能力

### 9.5 排障与诊断能力

`http`/`cli` 需要暴露 source 结构与诊断信息，这是合理需求。

但这些能力应通过 `application.sources.*Query` 暴露，而不是让 `interfaces` 直接持有 provider 实现。

建议提供：

- `ListSourcesQuery`
- `GetSourceCapabilitiesQuery`
- `GetSourceSchemaQuery`
- `PreviewNormalizedFrameQuery`
- `ProbeSourceQuery`

---

## 10. `StoreSchema` 与 `datahub`

### 10.1 StoreSchema 的 owner

`StoreSchema` 属于目标子域，不属于 `sources`。

它表达的是：

- 最终内部存储字段
- `instrument_id`
- PIT 列
- 内部主键/外键
- 分区/落盘语义

### 10.2 `datahub` 的职责边界

`datahub` 不拥有业务语义，只负责实现各子域定义的稳定存储抽象。

它可以反向依赖：

- repository interface
- store interface
- snapshot record contract
- schema contract

它不可以依赖：

- service
- pipeline
- process
- aggregate behavior

### 10.3 `datahub` 与 `sources` 的关系

二者同属基础设施，但边界不同：

- `sources` 面向外部世界
- `datahub` 面向内部世界

它们不应再被一个更大的模块名强行绑定。

---

## 11. 行为域输入边界

### 11.1 `decisioning`

只消费：

- `StrategyInputBundle`
- `DecisionInput`
- 其他本域定义的输入契约

不直接持有：

- market query
- metadata query
- source query

### 11.2 `trading`

只消费：

- `ExecutionContext`
- `MarketSnapshot`
- `TradingRuleSnapshot`
- `AccountState`

不直接持有：

- market query
- metadata query
- storage query

### 11.3 `analytics`

只消费：

- `ResearchDataset`
- `EvaluationInput`
- `SimulationInput`

不直接持有：

- source/store/query adapter

### 11.4 关于“模型依赖”的最终判断

以下依赖是允许的：

- 行为域依赖 `kernel` 原语
- `application` 依赖行为域输入契约并负责构建它们

以下依赖是不允许的：

- 行为域直接依赖 `metadata / marketdata / sources / datahub` 的查询模型
- 行为域依赖 `application` 的 DTO 或 process state

结论：

> 行为域输入契约由行为域自己定义，`application` 只负责组装与注入。

---

## 12. 回测、实时、实盘、研究的统一模型

本方案不再把“回测”和“实时”看作两套独立架构。

统一方式如下：

- `application.strategy.RunBacktestProcess`
- `application.strategy.RunLiveSessionProcess`
- `interfaces.jobs` 触发离线任务
- `interfaces.streams` 接收市场流、broker 回报、事件消息
- `decisioning` 负责目标生成
- `trading` 负责执行与状态推进
- `analytics` 负责评估、归因、仿真

这意味着：

- 回测、实时、实盘共享同一套领域规则
- 区别只在流程编排和入口适配上

---

## 13. 质量与风险的重组

不再保留统一的 `quality` 大类。

拆分如下：

- `metadata.quality`
  - schema、完整性、cross-source、基础数据合法性

- `analytics.evaluation`
  - 因子质量、信号质量、评估统计、模型质量

- `trading.risk`
  - pre-trade risk
  - post-trade guard
  - 实盘/实时安全护栏

---

## 14. 约束固化建议

以下约束应进入架构规范与 lint 规则：

### 14.1 importlinter 顶层约束

- 顶层模块依赖矩阵
- `decisioning / trading / analytics` 禁止依赖 `metadata / marketdata / sources / datahub`
- `interfaces` 禁止直接依赖业务域与 datahub
- `datahub` 禁止依赖行为实现

### 14.2 application 内部约束

- `*Query -X-> *Command / *Process`
- `*Command -X-> *Query / *Process`
- `*Process -> *Query / *Command`
- `Process -> Process` 默认禁止

### 14.3 kernel 准入标准

一个类型进入 `kernel` 必须同时满足：

1. 跨域语义一致
2. 低变更频率
3. 零流程逻辑
4. 不依赖具体层实现

### 14.4 文档与规范同步更新

需要同步更新：

- 根 `AGENTS.md`
- `.importlinter`
- `packages/kernel/CLAUDE.md`
- `packages/metadata/CLAUDE.md` 或等价新包说明
- `packages/marketdata/CLAUDE.md` 或等价新包说明
- `packages/decisioning/CLAUDE.md`
- `packages/trading/CLAUDE.md`
- `packages/analytics/CLAUDE.md`
- `packages/sources/CLAUDE.md`
- `packages/data/CLAUDE.md`
- `apps/interfaces/CLAUDE.md`

---

## 15. 高层迁移顺序

本方案不展开逐文件细节，但推荐遵循以下高层顺序：

1. 冻结顶层模块命名与依赖规则
2. 从 `port` 中提炼出清晰的 `application` 与 `interfaces`
3. 将 `Reference Data` 正式升格为 `metadata`
4. 将市场时序数据正式升格为 `marketdata`
5. 将 `sources` 从 `datahub` 中独立
6. 正式建立 `SourceSchema -> application.ingestion -> StoreSchema` 摄取链
7. 将 `decisioning / trading / analytics` 收紧为只消费 prepared inputs
8. 收缩 `datahub` 为存储实现层
9. 用 lint 规则固化边界

---

## 16. 非目标

以下不是本方案当前目标：

- 追求微服务化
- 将所有业务概念都实体化
- 将所有数据都对象化
- 为了“纯粹”而牺牲量化场景下的 DataFrame 可用性
- 在未明确收益前引入多份读写库拆分

---

## 17. 最终结论

Ditto 的最佳长期架构不是“更干净的 core”，而是以下清晰分工：

- `sources`：接外部世界
- `metadata / marketdata`：拥有查询语义
- `application`：拥有数据装配、命令执行和流程编排
- `decisioning / trading / analytics`：只负责行为和计算
- `datahub`：只负责内部持久化与查询实现
- `kernel`：只负责极小共享语义

并且，最关键的边界是：

> 行为域不直接查数据。
> 行为域输入契约由行为域定义。
> `application` 只负责构建和注入这些契约。

这套结构既符合 DDD 的分层精神，也更符合量化系统在数据密度、实时流、研究分析和回测/实盘统一方面的现实需求。

---

## 附录 A：参考资源

- Eric Evans, DDD Reference
  https://www.domainlanguage.com/ddd/reference/

- Microsoft, CQRS Pattern
  https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs

- Microsoft, Anti-Corruption Layer Pattern
  https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer

- Microsoft, Saga Pattern
  https://learn.microsoft.com/en-us/azure/architecture/patterns/saga

- Microsoft, Common Web Application Architectures
  https://learn.microsoft.com/en-us/dotnet/architecture/modern-web-apps-azure/common-web-application-architectures

- Matthias Noback, Does It Belong in the Application or Domain Layer?
  https://matthiasnoback.nl/2021/02/does-it-belong-in-the-application-or-domain-layer/

- QuantConnect, Algorithm Framework Overview
  https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview

- Martin Fowler, Anemic Domain Model
  https://martinfowler.com/bliki/AnemicDomainModel.html
