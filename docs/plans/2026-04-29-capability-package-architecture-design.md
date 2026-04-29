# Ditto 能力包架构设计

> 日期：2026-04-29
> 状态：Accepted for planning
> 目标：以最终合理性为准，将 Ditto 从抽象技术平面拆分为面向量化运行职责的多 package 架构。

## 1. 核心决策

Ditto 采用多 package monorepo，不收敛为单包结构。包边界由 `pyproject.toml` 依赖声明、import-linter 和自定义架构检查共同约束。

最终目标不是严格 DDD 三层目录，而是：

```text
轻 DDD
+ 能力模块化量化平台
+ CQRS 编排
+ 插件化外部接入
+ 研究/生产分轨
```

核心判断：

```text
DDD 用来识别边界、保护核心模型；
目录结构按量化系统运行职责划分；
业务数据归业务模块；
市场事实归 data；
技术能力归 platform。
```

当前 `data / analytics / engine / app / infra / interfaces` 的问题不是完全错误，而是包名过于抽象：

- `engine` 同时包含 strategy、portfolio、risk、execution、backtest。
- `analytics` 同时承担 features 与 analysis。
- `data` 仍混入 strategy、trade、derived、research 等业务运行数据。
- `infra` 名称偏技术实现，终态应表达为平台能力。
- `interfaces` 作为入口层终态更适合命名为 `apps`。

因此终态选择完整语义拆包，而不是保守地在旧大包内部继续整理。

## 2. 顶层包结构

```text
packages/
  kernel/
  platform/
  data/
  features/
  strategy/
  portfolio/
  risk/
  execution/
  backtest/
  analysis/
  application/
  apps/
```

每个顶层 package 都必须回答一个问题：这个能力在量化系统中负责什么。

| Package | 定位 |
|---|---|
| `kernel` | 极瘦共享语言，无 I/O，无技术实现 |
| `platform` | 技术横切能力，原 `infra` 的终态命名 |
| `data` | 市场事实、基础数据、PIT、数据治理 |
| `features` | 因子、指标、表达式、物化、因子评估 |
| `strategy` | 策略定义、策略版本、Alpha Pipeline、信号 |
| `portfolio` | 持仓、目标组合、调仓、组合会计 |
| `risk` | 约束、盘前/盘后风控、暴露、风控审计 |
| `execution` | 订单、成交、OMS、券商网关、对账 |
| `backtest` | 回测运行时、模拟 broker、绩效统计 |
| `analysis` | 报告、诊断、实验、筛选、Notebook 支持 |
| `application` | command/query/process 编排与运行时上下文 |
| `apps` | API、CLI、worker、web 等入口与 composition root |

## 3. 命名规则

Python 包和模块名采用小写，必要时使用下划线。单复数按语义统一。

规则：

```text
顶层 package：能力域名，优先单数或不可数名词。
集合型目录：复数。
能力/机制目录：单数。
文件名：角色名，通常单数；聚合文件可复数。
```

顶层包固定为：

```text
kernel
platform
data
features
strategy
portfolio
risk
execution
backtest
analysis
application
apps
```

复数目录示例：

```text
commands/
queries/
processes/
orders/
fills/
signals/
positions/
reports/
diagnostics/
experiments/
screeners/
gateways/
migrations/
```

单数目录示例：

```text
storage/
broker/
reconciliation/
accounting/
calendar/
quality/
runtime/
registry/
observability/
persistence/
serialization/
```

文件命名示例：

```text
models.py          # 多个模型
contracts.py       # 多个 Protocol / Contract
services.py        # 多个轻服务或聚合服务
store.py           # Store 契约
registry.py        # Registry
state_machine.py   # 状态机
```

不使用泛化的 `adapters/` 作为默认一级目录。持久化实现用 `storage/`；券商接入放 `broker/gateways/`；外部数据源接入放 `data/sources/`；平台集成能力放 `platform` 下的具体能力目录。

## 4. 包职责

### 4.1 kernel

`kernel` 只放跨模块稳定语言。

适合：

```text
InstrumentId
Symbol
Exchange
Market
AssetClass
TradeDate
TimeFrame
Money
Price
Quantity
Weight
Bps
ReturnRate
OrderSide
Direction
DittoError
DomainError
```

不适合：

```text
Logger
Metrics
Repository
UnitOfWork
BrokerGateway
DataProvider
SignalStore
FactorStore
CommandBus
QueryBus
Scheduler
```

判断句：如果一个类型只被一个能力包需要，它不属于 `kernel`。

### 4.2 platform

`platform` 是通用技术能力，不承载业务语义。

```text
platform/
  config/
  observability/
  persistence/
    sqlite/
    duckdb/
    parquet/
    questdb/
  cache/
  scheduling/
  messaging/
  locking/
  serialization/
  paths/
  di/
```

`platform` 可以提供连接池、事务、迁移 runner、路径解析、日志、指标、追踪、锁、缓存、序列化等能力。它不能定义订单、信号、风控、组合、因子等业务 schema。

### 4.3 data

`data` 只负责市场事实和数据治理，不是所有数据的仓库。

```text
data/
  sources/
    tushare/
    tdx/
    fred/
  security_master/
  calendar/
  market_data/
  fundamentals/
  constituents/
  corporate_actions/
  macro/
  quality/
  lineage/
  storage/
```

`data` 拥有行情、财务、成分股、交易日历、证券主数据、复权、停复牌、宏观数据、PIT 口径、数据质量、数据血缘。

`data` 不拥有订单、信号、策略运行、组合快照、风控结果、流程状态。

### 4.4 features

`features` 负责因子与特征能力。

```text
features/
  expression/
  factors/
  indicators/
  normalization/
  materialization/
  evaluation/
  models.py
  contracts.py
  registry.py
  storage/
    parquet/
    questdb/
```

它可以依赖 `data` 获取市场输入。因子值与特征快照的 schema 归 `features` 所有，底层 Parquet、QuestDB 能力由 `platform` 提供。

### 4.5 strategy

`strategy` 负责策略定义、策略版本和信号生成。

```text
strategy/
  alpha/
  signals/
    models.py
    services.py
    store.py
  registry.py
  models.py
  contracts.py
  storage/
    sqlite/
    parquet/
```

`strategy` 可以依赖 `features` 和 `data`，但不能依赖 `execution` 或任何 broker 具体实现。策略输出信号、评分、排序、目标意图，不直接下单。

### 4.6 portfolio

`portfolio` 管理组合语义。

```text
portfolio/
  accounting/
  holdings/
  target_portfolios/
  rebalancing/
  positions/
  models.py
  contracts.py
  services.py
  storage/
    sqlite/
    parquet/
```

它拥有持仓、账户视图、目标组合、调仓计划、现金和 NAV 快照。它不直接提交订单。

### 4.7 risk

`risk` 是独立风控模块。

```text
risk/
  pre_trade/
  post_trade/
  constraints/
  exposure/
  drawdown/
  models.py
  contracts.py
  services.py
  storage/
    sqlite/
```

风控检查结果、拒绝原因、暴露快照和审计记录归 `risk` 所有。`risk` 可以被 backtest 和 execution 共用，以保证研究/生产风控一致。

### 4.8 execution

`execution` 是交易执行核心。

```text
execution/
  orders/
    models.py
    store.py
    state_machine.py
  fills/
    models.py
    store.py
  oms/
  broker/
    contracts.py
    gateways/
      miniqmt/
      ibkr/
  reconciliation/
  models.py
  contracts.py
  services.py
  storage/
    sqlite/
      migrations/
```

`execution` 拥有订单、成交、执行回报、订单状态机、OMS、券商网关、对账。它不能依赖 `analysis` 或 `backtest`。

### 4.9 backtest

`backtest` 是回测运行时，不等同于 `execution`。

```text
backtest/
  engine.py
  data_feed.py
  simulated_broker.py
  fill_model.py
  slippage_model.py
  commission_model.py
  performance.py
  statistics.py
  config.py
  manifest.py
  replay.py
  audit/
  steps/
```

共享：

```text
Signal
TargetPortfolio
RiskCheck
Order
Fill
Position
BrokerGateway Protocol
```

分离：

```text
DataFeed 实现
BrokerGateway 实现
Clock 实现
Fill / Slippage / Commission model
```

目标是 backtest-live parity：语义共享，实现替换。

### 4.10 analysis

`analysis` 面向研究和解释，不进入生产依赖路径。

```text
analysis/
  reports/
  diagnostics/
  experiments/
  screeners/
  notebooks/
```

`analysis` 可以读取 `data`、`features`、`strategy`、`portfolio`、`risk`、`backtest` 的结果，用于报告、诊断、实验和筛选。任何生产模块都不能依赖 `analysis`。

### 4.11 application

`application` 是 CQRS 和流程编排层。

```text
application/
  commands/
  queries/
  processes/
  runtime/
  builders/
  contracts.py
```

`commands` 处理写操作；`queries` 聚合只读视图；`processes` 管理长流程；`runtime` 放 clock、mode、context、event loop；`builders` 组装对象图。

`application` 可以依赖所有能力包，但不拥有它们的业务规则。

### 4.12 apps

`apps` 是入口层和 composition root。

```text
apps/
  api/
  cli/
  worker/
  web/
  registry/
  config/
```

`apps` 负责 FastAPI、CLI、worker、web、DI wiring、错误映射和传输 DTO。业务交互通过 `application` 完成，不能绕过 application 直接调用能力包内部实现。

## 5. 依赖规则

总体方向：

```text
apps -> application -> capability packages -> kernel
platform 横向被 apps/application/storage/gateways 使用
```

推荐依赖：

| Package | 可以依赖 |
|---|---|
| `kernel` | 无 |
| `platform` | 标准库和第三方技术依赖 |
| `data` | `kernel`, `platform` |
| `features` | `kernel`, `data` |
| `strategy` | `kernel`, `data`, `features` |
| `portfolio` | `kernel`, `data`, `strategy` |
| `risk` | `kernel`, `portfolio`, `strategy` |
| `execution` | `kernel`, `portfolio`, `risk` |
| `backtest` | `kernel`, `data`, `strategy`, `portfolio`, `risk`, `execution` contracts |
| `analysis` | `kernel`, `data`, `features`, `strategy`, `portfolio`, `risk`, `backtest` |
| `application` | 所有能力包、`platform`, `kernel` |
| `apps` | `application`, `platform`, `kernel` |

硬性禁止：

```text
kernel -> anything                    ❌
platform -> business packages          ❌
data -> strategy/portfolio/execution   ❌
features -> strategy/execution         ❌
strategy -> execution                  ❌
strategy -> execution broker gateways  ❌
portfolio -> execution                 ❌
risk -> execution                      ❌
execution -> backtest/analysis         ❌
backtest -> execution broker gateways  ❌
production packages -> analysis        ❌
apps -> capability internals           ❌
```

`platform` 使用规则：

```text
核心模型层          不依赖 platform
模块服务层          通过构造注入谨慎使用 clock/logger/metrics 抽象
storage/gateways    可以直接使用 platform
application/apps    可以直接使用 platform
```

## 6. 生产链路与研究链路

生产链路：

```text
data
  -> features
  -> strategy
  -> portfolio
  -> risk
  -> execution
```

`application.processes` 将生产链路编排成可重放、可审计、可恢复的流程。

典型调仓流程：

```text
application.processes.rebalance
  -> strategy.signals 生成 signal_batch
  -> portfolio.rebalancing 生成 rebalance_plan
  -> risk.pre_trade 生成 risk_check
  -> execution.orders 生成 order_batch
  -> execution.broker 提交订单
  -> execution.fills 接收成交
  -> execution.reconciliation 对账
  -> portfolio.accounting 更新组合快照
```

研究链路：

```text
analysis
  -> data/features/strategy/portfolio/risk/backtest
```

研究代码可以灵活，生产代码必须稳定。Notebook 和实验逻辑不能直接进入生产路径。

## 7. 数据所有权与存储

核心规则：

```text
业务数据归业务模块；
市场事实归 data；
技术存储能力归 platform。
```

数据归属：

| 数据类型 | 所属模块 |
|---|---|
| 行情、财务、成分股、日历、证券主数据 | `data` |
| 因子值、特征快照、物化元数据 | `features` |
| 策略定义、策略版本、参数、信号批次、信号 | `strategy` |
| 持仓、目标组合、调仓计划、组合快照 | `portfolio` |
| 风控检查、违规、决策、暴露快照 | `risk` |
| 委托、订单事件、成交、执行回报、对账 | `execution` |
| 流程实例、步骤、timer、retry、幂等键 | `application` |
| 报告、诊断、实验产物 | `analysis` |

Store 组织方式：

```text
execution/
  orders/
    models.py
    store.py
  storage/
    sqlite/
      order_store.py
      migrations/
        001_create_execution_orders.sql
```

模块定义 store contract 和业务 schema。`platform.persistence` 只提供通用 DB 能力。

表名使用模块前缀：

```text
data_daily_bars
features_factor_values
strategy_signal_batches
strategy_signals
portfolio_rebalance_plans
risk_checks
execution_orders
execution_fills
application_process_instances
```

`process` 只保存流程状态和业务实体引用，不复制业务详情。

```text
process_id
status
current_step
correlation_id
related_entity_ids
last_error
retry_count
```

## 8. 错误、事件与审计

错误归属：

```text
strategy.errors.SignalGenerationError
portfolio.errors.RebalanceError
risk.errors.RiskRejectedError
execution.errors.OrderStateError
backtest.errors.BacktestRuntimeError
```

`kernel` 只提供根错误类型。`platform` 只处理技术异常。

事件分三类：

| 类型 | 归属 | 示例 |
|---|---|---|
| Domain Event | 各业务模块 | `SignalBatchGenerated`, `OrderFilled` |
| Process Event | `application.processes` | `StepCompleted`, `RetryScheduled` |
| Technical Event | `platform.observability` | DB latency, broker disconnect |

审计按业务所有权存储：

```text
data      -> 数据质量审计
risk      -> 风控审计
execution -> 订单和对账审计
application -> 流程审计
```

可以共享物理 event log 技术，但 schema 和查询接口由各模块拥有。

## 9. 测试与架构门禁

测试按 package ownership 放置：

```text
packages/execution/tests/unit/
packages/execution/tests/integration/
packages/strategy/tests/unit/
packages/application/tests/integration/
packages/apps/tests/e2e/
```

测试职责：

```text
unit         -> 模块内部模型、规则、状态机、纯服务
integration  -> storage、gateway、跨模块 contract
e2e          -> API/CLI/worker 入口的完整流程
```

门禁三层：

```text
ruff / basedpyright / pytest
import-linter capability package contracts
自定义 architecture smell checker
```

import-linter 重点规则：

```text
kernel isolation
platform isolation
production no analysis
strategy no execution
execution no backtest
backtest no real broker gateways
apps no capability internals
capability packages acyclic
```

自定义 smell checker 建议扩展：

```text
禁止 helpers/utils 泛化扩散
禁止顶层跨包 re-export
禁止生产路径 import analysis
禁止 storage 定义业务规则
禁止 platform 出现业务表名
禁止 gateways 被 strategy/portfolio/risk 直接 import
禁止核心模型 import platform
```

## 10. 被拒绝方案

### 10.1 保留当前大包，只做内部重排

例如继续保留 `engine`，内部拆 `strategy / portfolio / risk / execution / backtest`。

拒绝原因：

```text
包边界过粗；
import-linter 难以约束核心交易语义污染；
engine 名称继续需要文档解释；
长期仍会变成大包。
```

### 10.2 只拆明显越界部分

例如只拆 `analytics -> features` 和 `engine/execution -> execution`。

拒绝原因：

```text
适合渐进迁移，不适合作为最终目标；
会留下 strategy/portfolio/risk/backtest 的命名债；
后续还会再次重构。
```

### 10.3 单包 `src/ditto/`

拒绝原因：

```text
当前项目已经是多 package monorepo；
pyproject 依赖声明可以成为边界；
import-linter 对 package 边界更容易表达；
核心交易模块需要强隔离。
```

## 11. 迁移原则

本设计只描述终态合理性，不以迁移成本为约束。实施时仍应分阶段执行，并在每个阶段保持可验证。

建议阶段：

```text
Phase 0: 建立新 package skeleton 和 import-linter 目标规则
Phase 1: infra -> platform，interfaces -> apps
Phase 2: analytics -> features + analysis
Phase 3: engine/alpha -> strategy
Phase 4: engine/portfolio/accounting -> portfolio
Phase 5: engine/risk -> risk
Phase 6: engine/execution + data trade/audit storage -> execution
Phase 7: engine/backtest -> backtest
Phase 8: app -> application，重组 commands/queries/processes/runtime
Phase 9: data 瘦身，只保留市场事实与数据治理
Phase 10: 删除旧包、更新文档、全量门禁
```

每个阶段至少通过：

```text
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
```

最终完成前通过：

```text
pixi run -e dev check
```
