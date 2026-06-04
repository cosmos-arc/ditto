# Ditto 模块化量化平台架构设计

> **日期**: 2026-04-29
> **状态**: 设计中
> **前置**: 全库架构重构（2026-03-26 设计）、App 层 CQRS 重构（2026-04-10）
> **目标**: 从严格 DDD 分层架构演进为"轻 DDD + 模块化量化引擎 + CQRS 编排 + 插件化适配器"

---

## 1. 设计哲学

### 1.1 核心判断

> **对个人量化系统，严格 DDD 不是最优解。**
> **DDD 的价值在于识别边界、保护核心模型；但目录结构不一定要按 Domain / Application / Infrastructure 教科书三层来做。**
> **量化系统更适合"能力模块化 + 轻量依赖规则 + 研究/生产分轨"。**

### 1.2 业界对标

| 系统 | 架构模式 | Ditto 采纳 |
|------|---------|-----------|
| QuantConnect LEAN | 五模块 Pipeline (Universe→Alpha→Portfolio→Risk→Execution) + Plugin Handler | Pipeline 流水线 + contracts.py 轻量 Port |
| NautilusTrader | DDD + Ports & Adapters + MessageBus + 单线程确定性内核 | Backtest-Live Parity（共享模型、分离实现） |
| Zipline | DataPortal 门面 + Pipeline 因子系统 | Data 统一门面模式 |
| Hummingbot V2 | Controller-Executor 分离 | Strategy 只产信号，Execution 管订单生命周期 |
| VNTrader | EventEngine 事件总线 + Gateway 统一接口 | 不采纳（Ditto 是日频/周频，不需要高频事件总线） |

### 1.3 三类模块的松紧标准

| 类别 | 模块 | 严格度 | 原因 |
|------|------|--------|------|
| **核心交易语义** | portfolio, risk, execution | 严格 | 真金白银，模型要干净，不依赖外部技术实现 |
| **数据/特征/研究** | data, features, analysis | 实用主义 | Polars/DuckDB/Parquet 是正常工具，不要为 DDD 牺牲研究效率 |
| **技术平台** | kernel, infra | 纯工具 | 不伪装成领域，不承载业务语义 |

---

## 2. 架构全景

### 2.1 12 个独立包

```
ditto/
├── packages/
│   ├── kernel/          # 共享类型（零依赖、零行为）
│   ├── infra/           # 技术横切（config/observability/persistence/cache/scheduling）
│   ├── data/            # 市场数据底座（行情/财务/成分股/日历/PIT/质量/接入）
│   ├── features/        # 因子与特征（表达式编译/因子库/因子评估/物化）
│   ├── strategy/        # 策略与信号（Alpha Pipeline/信号生成/策略 Registry）
│   ├── portfolio/       # 组合管理（持仓/目标组合/再平衡/会计）
│   ├── risk/            # 风控管理（盘前/盘后风控/约束/暴露）
│   ├── execution/       # 交易执行（订单/OMS/券商网关/成交/对账）
│   ├── backtest/        # 回测引擎（模拟券商/滑点/手续费/绩效统计）
│   ├── analysis/        # 研究层（报告/诊断/实验/筛选器）
│   └── application/     # 编排+运行时（command/query/process + 事件循环/时钟/模式切换）
└── interfaces/          # 入口层（API/CLI/Jobs/DI Composition Root）
```

### 2.2 依赖图

```
                    interfaces
                        │
                        ▼
                   application
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   analysis        backtest        execution
        │               │               │
        │          ┌────┴────┐          │
        │          │  risk   │◄─────────┘
        │          └────┬────┘
        │               │
        │          ┌────┴────┐
        │          │portfolio│
        │          └────┬────┘
        │               │
        │          ┌────┴────┐
        │          │strategy │
        │          └────┬────┘
        │               │
   ┌────┴────┐   ┌─────┴─────┐
   │features │◄──┤           │
   └────┬────┘   └───────────┘
        │
   ┌────┴────┐
   │  data   │
   └────┬────┘
        │
   ┌────┴────┐
   │  infra  │
   └────┬────┘
        │
   ┌────┴────┐
   │ kernel  │
   └─────────┘
```

### 2.3 依赖矩阵

| 包 | kernel | infra | data | features | strategy | portfolio | risk | execution | backtest | analysis | application | interfaces |
|---|--------|-------|------|----------|----------|-----------|------|-----------|----------|----------|-------------|-----------|
| kernel | - | | | | | | | | | | | |
| infra | ✅ | - | | | | | | | | | | |
| data | ✅ | ✅ | - | | | | | | | | | |
| features | ✅ | | ✅ | - | | | | | | | | |
| strategy | ✅ | | ✅ | ✅ | - | | | | | | | |
| portfolio | ✅ | | ✅ | | ✅ | - | | | | | | |
| risk | ✅ | | | | ✅ | ✅ | - | | | | | |
| execution | ✅ | | | | | ✅ | ✅ | - | | | | |
| backtest | ✅ | | ✅ | | ✅ | ✅ | ✅ | contracts | - | | | |
| analysis | ✅ | | ✅ | ✅ | | ✅ | | | ✅ | - | | |
| application | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | - | |
| interfaces | ✅ | ✅ | | | | | | | | | ✅ | - |

注：interfaces 通过 DI Composition Root 可以间接访问所有模块，但直接 import 仅限 application + kernel + infra。

---

## 3. 禁止的依赖（硬性规则）

### 3.1 全局禁止

```
kernel           → 任何上游模块              ❌ （零依赖原则）
任何模块          → interfaces              ❌ （接口是入口，不是依赖）
infra            → data/features/...        ❌ （技术层不依赖业务层）
```

### 3.2 业务规则禁止

```
data             → strategy/portfolio/risk/execution    ❌ （底座不依赖上游）
features         → strategy/execution                   ❌ （因子不依赖交易）
strategy         → execution.adapters                   ❌ （策略不接触券商）
portfolio        → execution                            ❌ （组合不直接下单）
risk             → execution                            ❌ （风控独立于执行）
execution        → analysis/backtest                    ❌ （执行不依赖研究）
analysis         → execution.adapters                   ❌ （研究不接触实盘实现）
backtest         → execution.adapters                   ❌ （回测用模拟，不接触券商）
```

### 3.3 三类事件不可混淆

| 事件类型 | 归属 | 存储方式 |
|---------|------|---------|
| Domain Event（SignalGenerated, OrderFilled） | 各业务模块 | 各模块 store |
| Process Event（StepCompleted, RetryScheduled） | application/process | process_store |
| Technical Event（DB query failed, broker disconnected） | infra/observability | log/metrics |

---

## 4. 各包详细设计

### 4.1 kernel — 共享类型

**原则**: 零依赖、零行为、极瘦。只放"跨模块稳定业务语言"。

```python
# 适合放 kernel 的
Sid, Symbol, Exchange, Market, AssetClass
TradeDate, TimeFrame, GrainId
Money, Price, Quantity, Weight, Bps, ReturnRate
OrderSide, Direction
DomainError
Clock Protocol (抽象时钟)
EventBus Protocol (抽象事件)

# 不适合放 kernel 的
Logger, Metrics           → infra
Repository, UnitOfWork    → 各模块 contracts.py
BrokerGateway             → execution/contracts.py
DataProvider              → data/contracts.py
CommandBus, QueryBus      → application
```

**迁移**: 当前 kernel 基本不变，保持 14 个文件。可能需要小幅调整类型归属。

---

### 4.2 infra — 技术横切

**原则**: 通用技术能力，不承载业务语义。保留当前命名。

```
infra/
  foundation/
    cache/              # 缓存（cachebox）
    concurrency/        # 文件锁、并发控制
    config/             # 配置加载、环境变量、路径
    db/                 # SQLite 连接池、事务、迁移工具
    observability/      # logging(loguru)、metrics、tracing(otel)
    util/               # 日期工具、IO 工具、checksum
  services/
    notification/       # Telegram/Email/Webhook 通知
```

**关键约束**:
- `infra` 不定义业务 schema
- 业务 store 的实现放各模块 `adapters/`，底层复用 `infra` 的 DB 工具
- `infra/db/` 只提供 connection、transaction、migration_runner 等通用能力

**迁移**: 当前 infra (48 文件) 基本不变。

---

### 4.3 data — 市场数据底座

**原则**: 只负责外部市场事实数据和数据治理。不是"所有数据的仓库"。

```
data/
  # 保留（市场数据域）
  sources/              # 外部数据源（tushare/tdx/fred）
  storage/
    market/             # 行情存储（bars/adj/status/constituent）
    metadata/           # 元数据（calendar/instrument/universe）
    fundamental/        # 财务数据
    macro/              # 宏观指标
    capital/            # 估值/保证金
  ingestion/            # 数据接入流程
  quality/              # 数据质量引擎
  helpers/              # PIT 帮助、复权帮助
  services/             # 市场数据服务门面
    metadata/           # calendar/instrument/universe 服务
  providers/            # DataProvider 实现
  di/                   # DI 注册

  # 迁出
  storage/execution/    → execution/adapters/
  storage/factors/      → features/adapters/
  storage/features/     → features/adapters/
  services/trade/       → execution/
  services/strategy/    → strategy/
  services/audit/       → execution/
  services/derived/     → features/
  services/research/    → features/ 或 analysis/
```

**data 拥有的数据**:

| 数据类型 | 存储 |
|---------|------|
| 行情（日K/分钟K） | Parquet + QuestDB |
| 财务数据 | Parquet |
| 成分股 | Parquet |
| 交易日历 | SQLite |
| 证券主数据 | SQLite |
| 复权因子 | Parquet |
| 宏观指标 | Parquet |
| 数据质量报告 | SQLite |

**data 不拥有的数据**: 订单、信号、策略状态、流程状态、组合调仓、风控结果。

---

### 4.4 features — 因子与特征

**原则**: 表达式编译 + 因子库 + 因子评估 + 物化。无 I/O，纯计算。

```
features/
  expression/           # 表达式语言（lexer/ast/parser/codegen/compiler）
  factors/              # 内置因子库（technical/fundamental/alpha/...）
  evaluation/           # 因子评估（IC/衰减/正交化/归因/Fama-MacBeth）
  materialization/      # 物化计划（contracts/models/planner）
  models/               # 因子和特征模型
  contracts.py          # FactorCalculator, FactorStore 等 Protocol
  registry.py           # 因子注册表
  adapters/
    parquet/            # 因子值 Parquet 存储
    questdb/            # 因子热数据 QuestDB 存储
```

**迁移来源**: 当前 analytics (53 文件) + data/storage/factors + data/storage/features + data/services/derived。

---

### 4.5 strategy — 策略与信号

**原则**: Alpha Pipeline 产信号，不直接下单。

```
strategy/
  alpha/
    pipeline/           # Alpha Pipeline（过滤/打分/选择/信号/Universe）
    context.py          # 决策上下文
    frame.py            # 决策帧
    seeds.py            # 初始种子
    specs.py            # 策略规格
    builtins/           # 内置 stage（filtering/scoring/selection/signal/...）
    templates/          # 策略模板（etf_rotation/sector_rotation/...）
  signal/
    models.py           # Signal, SignalBatch, SignalDirection
    services.py         # 信号生成服务
    signal_store.py     # 信号存储契约
  registry.py           # 策略注册表
  models.py             # 策略定义模型
  contracts.py          # SignalGenerator, StrategyStore 等 Protocol
  adapters/
    sqlite/             # 策略元数据 SQLite 存储
    parquet/            # 历史信号 Parquet 存储
```

**关键规则**:
- strategy 可以依赖 features（因子）和 data（市场数据）
- strategy **不能**依赖 execution 或 execution.adapters
- strategy 产出结构化信号（Signal），不产出订单

**迁移来源**: engine/alpha (25 文件) + data/services/strategy (30 文件)。

---

### 4.6 portfolio — 组合管理

**原则**: 持仓、目标组合、再平衡、会计。核心交易语义，边界严格。

```
portfolio/
  accounting/
    account.py          # 账户抽象
    buying_power.py     # 购买力计算
    cash.py             # 现金管理
    fills.py            # 成交入账
    position.py         # 持仓追踪
    order_book.py       # 订单簿
  target_portfolio/     # 目标组合构建
  rebalance/            # 再平衡计算
    allocation.py       # 配置计算
    comparison.py       # 目标 vs 当前比较
    constraints.py      # 约束检查
  models.py             # PortfolioSnapshot, Position, TargetWeight
  services.py           # PortfolioService
  contracts.py          # PortfolioStore, AccountingService 等 Protocol
  adapters/
    sqlite/             # 组合快照 SQLite 存储
    parquet/            # 历史快照 Parquet 存储
```

**关键规则**:
- portfolio 可以依赖 strategy（信号）和 data（行情数据）
- portfolio **不能**依赖 execution
- accounting 是组合内部概念，不是独立的执行会计

**迁移来源**: engine/portfolio (4 文件) + engine/accounting (6 文件)。

---

### 4.7 risk — 风控管理

**原则**: 盘前/盘后风控，约束检查，暴露分析。风控独立于执行。

```
risk/
  pre_trade/            # 盘前风控
  post_trade/           # 盘后风控
  constraints/          # 约束规则
  exposure/             # 暴露分析
  drawdown/             # 回撤监控
  models.py             # RiskCheck, RiskViolation, RiskDecision
  contracts.py          # RiskChecker, RiskStore 等 Protocol
  adapters/
    sqlite/             # 风控审计 SQLite 存储
```

**关键规则**:
- risk 可以被 backtest 和 execution 共用（研究/生产一致性）
- risk **不能**依赖 execution
- risk 检查结果归 risk 模块所有

**迁移来源**: engine/risk (3 文件) + kernel/quality (部分 DQ 类型可能复用)。

---

### 4.8 execution — 交易执行

**原则**: 最严肃的模块。订单状态机、OMS、券商网关、对账。一旦出错是真金白银。

```
execution/
  orders/
    models.py           # Order, OrderIntent, OrderTicket
    state_machine.py    # 订单状态机
    order_store.py      # 订单存储契约
  fills/
    models.py           # Fill, ExecutionReport
    fill_store.py       # 成交存储契约
  oms/
    order_manager.py    # 订单管理器
  broker/
    contracts.py        # BrokerGateway Protocol
    gateway.py          # 券商网关抽象
  reconciliation/
    reconciler.py       # 对账逻辑
    reconciliation_store.py
  reality/              # 现实模型
    brokerage.py        # 券商模型
    fee.py              # 手续费模型
    fill.py             # 成交模型
    slippage.py         # 滑点模型
    market.py           # 市场模型
    settlement.py       # 结算模型
  services.py           # ExecutionService
  contracts.py          # ExecutionService, OrderRouter 等 Protocol
  adapters/
    miniqmt/            # MiniQMT 券商适配器
      gateway.py
      ...
    ibkr/               # IBKR 券商适配器（未来）
    sqlite/             # 订单/成交 SQLite 存储
      migrations/
  models.py             # BrokerPosition, BrokerCash 等
```

**关键规则**:
- execution 可以依赖 portfolio（目标仓位模型）和 risk（风控结果）
- execution **不能**依赖 analysis 或 backtest
- execution **不能**暴露 MiniQMT/IBKR 细节给 strategy
- execution 拥有: orders, fills, execution_reports, reconciliation 数据

**迁移来源**: engine/execution (10 文件) + engine/execution/reality (7 文件) + data/services/trade (约 8 文件) + data/services/audit (约 5 文件) + data/storage/execution (约 5 文件)。

---

### 4.9 backtest — 回测引擎

**原则**: 共享模型和协议，不共享外部实现。Backtest-Live Parity。

```
backtest/
  engine.py             # 回测主引擎
  data_feed.py          # 回测数据源（实现 data/contracts.py 的 DataFeed Protocol）
  simulated_broker.py   # 模拟券商（实现 execution/contracts.py 的 BrokerGateway Protocol）
  fill_model.py         # 成交模型
  slippage_model.py     # 滑点模型
  commission_model.py   # 手续费模型
  performance.py        # 绩效统计
  statistics.py         # 统计计算
  config.py             # 回测配置
  manifest.py           # 回测清单
  replay.py             # 数据回放
  contracts.py          # BacktestEngine 等 Protocol
  audit/                # 回测审计
    collector.py
    records.py
  steps/                # 回测 Pipeline 步骤
    input_bundle.py
    data_fetch.py
    strategy.py
    planning.py
    pre_trade.py
    execution.py
    risk_scan.py
    audit.py
```

**关键规则**:
- backtest 实现各模块的 contracts（DataFeed、BrokerGateway）
- backtest **不能**依赖 execution.adapters（回测用 simulated_broker，不接触券商）
- backtest 共享: Order, Fill, Position, Signal, TargetWeight（来自各模块 models）
- backtest 分离: BrokerGateway 实现、DataFeed 实现、Clock 实现

**迁移来源**: engine/backtest (20 文件)。

---

### 4.10 analysis — 研究层

**原则**: 面向人和研究迭代的解释、诊断、报告、探索层。不被任何生产模块依赖。

```
analysis/
  reports/
    backtest_report.py  # 回测报告
    factor_report.py    # 因子报告
    strategy_report.py  # 策略报告
  diagnostics/
    signal_diagnostics.py   # 信号诊断
    turnover_diagnostics.py # 换手率诊断
    drawdown_diagnostics.py # 回撤诊断
  experiments/
    notebooks/          # Jupyter notebook 支持
    prototypes/         # 原型代码
  screeners/
    etf_screener.py     # ETF 筛选器
```

**关键规则**:
- analysis 可以依赖: data, features, portfolio, backtest
- analysis **不能**被任何生产路径依赖
- analysis **不能**依赖 execution.adapters（不接触实盘实现）

**迁移来源**: 新建 + app/query 中报告类查询迁移。

---

### 4.11 application — 编排 + 运行时

**原则**: command/query/process 编排 + 运行时基础设施（事件循环、时钟、模式切换）。

```
application/
  commands/             # 写操作 DTO + Handler
    ingestion.py
    quality_check.py
    backtest.py
    strategy.py
    rebalance.py
    execution.py
  queries/              # 读操作（不含报告类，报告归 analysis）
    metadata.py
    market.py
    fundamental.py
    macro.py
    source.py
    ingestion_status.py
    lineage.py
    run.py
    universe.py
  processes/            # 长流程 Process Manager
    ingestion/          # 数据接入流程
    materialization/    # 因子物化流程
    execution/          # 策略运行/回测执行流程
    quality/            # 质量巡逻
    rebalance/          # 调仓工作流
  runtime/              # 运行时基础设施（原 engine 运行时部分）
    event_loop.py       # 事件循环
    clock.py            # 时钟（模拟/实时）
    modes.py            # 模式管理（backtest/live）
    context.py          # 运行时上下文
  builders/             # 运行时组装
    runtime_builder.py
    slice_builder.py
    service_factory.py
  contracts.py          # 跨 CQRS 共享契约
  providers.py          # DI Provider 聚合
```

**关键规则**:
- application 是唯一可以依赖所有能力模块的层
- application **不做业务逻辑**，只做编排
- runtime/ 替代了独立 engine 模块，负责事件循环和模式切换

**迁移来源**: app (101 文件) 瘦身 + engine 运行时部分提取。

---

### 4.12 interfaces — 入口层

**原则**: 唯一应用入口。API/CLI/Jobs + DI Composition Root。

```
interfaces/
  api/                  # FastAPI 路由
    routes/
    deps.py
    params.py
    errors.py
  cli/                  # CLI 命令
    commands/
    utils/
  jobs/                 # Prefect 任务
    flows/
    tasks/
  models/               # API Pydantic 模型
  registry/             # DI Container (Dishka Composition Root)
    contexts/
    infra/
  config/               # 环境配置加载
  main.py               # FastAPI 入口
```

**关键规则**:
- interfaces 只依赖 application + kernel + infra（DI 组装需要）
- interfaces **不能**直接 import data/features/strategy/... 的内部实现
- 所有业务交互通过 application 的 command/query/process

**迁移来源**: interfaces (108 文件) 基本不变。

---

## 5. 数据所有权规则

### 5.1 核心原则

> **业务数据的"所有权"归模块；物理存储能力由 infra 提供；data 层只负责市场数据。**

### 5.2 数据归属表

| 数据类型 | 所属模块 | 物理存储 |
|---------|---------|---------|
| 市场行情/财务/成分股/日历 | data | Parquet / QuestDB / SQLite |
| 因子值/特征快照 | features | Parquet / QuestDB |
| 策略定义/版本/信号 | strategy | SQLite + Parquet |
| 组合快照/调仓计划 | portfolio | SQLite + Parquet |
| 风控检查/审计 | risk | SQLite |
| 订单/成交/对账 | execution | SQLite |
| 流程状态 | application/process | SQLite |
| log/metrics/tracing | infra/observability | Log files / OTel |

### 5.3 Store 实现策略

```
contract (Protocol)  → 各模块 contracts.py
通用 DB 工具          → infra/db/
业务 store 实现       → 各模块 adapters/sqlite/ 或 adapters/parquet/
migration SQL        → 各模块提供，infra 负责运行
```

### 5.4 表命名规范

```sql
data_daily_bars              -- data 模块
data_constituents             -- data 模块
features_factor_values        -- features 模块
strategy_signal_batches       -- strategy 模块
strategy_signals              -- strategy 模块
portfolio_snapshots           -- portfolio 模块
portfolio_rebalance_plans     -- portfolio 模块
risk_checks                   -- risk 模块
execution_orders              -- execution 模块
execution_fills               -- execution 模块
process_instances             -- application 模块
```

---

## 6. 依赖规则详细说明

### 6.1 三层依赖许可

| 层级 | 可以依赖 infra | 示例 |
|------|---------------|------|
| **核心模型层** (models.py) | ❌ 不依赖 | portfolio/models.py 不 import logger |
| **服务层** (services.py) | ⚠️ 谨慎 | execution/oms.py 可注入 logger 抽象 |
| **适配器/应用层** (adapters/, application/) | ✅ 可以 | execution/adapters/sqlite 直接用 infra/db/ |

### 6.2 跨模块引用规则

```
# 模块间只通过 contracts.py 定义的 Protocol 交互
# 具体实现在 DI Composition Root (interfaces/registry/) 中绑定

# 正确
from ditto_execution.contracts import BrokerGateway

# 错误
from ditto_execution.adapters.miniqmt.gateway import MiniQmtBrokerGateway
```

### 6.3 backtest 与 execution 的关系

```
共享:  Order (execution/models)
       Fill (execution/models)
       Position (portfolio/models)
       BrokerGateway Protocol (execution/contracts)
       Signal (strategy/models)

分离:
  backtest/implements BrokerGateway → SimulatedBrokerGateway
  execution/adapters/miniqmt/ → MiniQmtBrokerGateway

  backtest/implements DataFeed → HistoricalDataFeed
  data/sources/ → LiveTradingDataFeed（未来）
```

---

## 7. 研究/生产分轨

### 7.1 Research Path（松）

```
analysis/       → 报告、诊断、实验
notebooks/      → Jupyter notebook
experiments/    → 快速原型
```

特点: 快速、方便、允许不完美抽象。

### 7.2 Production Path（硬）

```
data pipeline   → 数据接入、质量检查
features pipeline → 因子物化
strategy        → 信号生成
portfolio       → 组合构建
risk            → 风控检查
execution       → 订单执行、对账
application     → 流程编排
```

特点: 稳定、可审计、可重放、可观测。

---

## 8. LEAN Algorithm Framework 映射

| LEAN 概念 | Ditto 对应 |
|-----------|-----------|
| IUniverseSelectionModel | strategy/alpha/builtins/universe |
| IAlphaModel | strategy/alpha/builtins/signal |
| IPortfolioConstructionModel | portfolio/rebalance/ |
| IRiskManagementModel | risk/pre_trade/ |
| IExecutionModel | execution/oms/ |
| IDataFeed | data/contracts.py DataProvider / backtest/data_feed.py |
| ITransactionHandler | execution/contracts.py BrokerGateway |
| IResultHandler | analysis/reports/ + infra/observability/ |
| Insight | strategy/signal/models.py Signal |
| PortfolioTarget | portfolio/models.py TargetWeight |

---

## 9. 迁移策略（概要）

### 9.1 迁移顺序（由底向上，风险递增）

```
Phase 0: 准备
  - 创建新的包目录结构
  - 更新 pyproject.toml 配置

Phase 1: 基础层（低风险）
  - kernel → 基本不变
  - infra → 基本不变（保留命名）

Phase 2: 数据层拆分（中风险）
  - features 从 analytics + data 提取
  - data 瘦身（迁出 execution/strategy/trade 存储）

Phase 3: 业务层拆分（高风险）
  - strategy 从 engine/alpha + data/services/strategy 提取
  - portfolio 从 engine/portfolio + engine/accounting 提取
  - risk 从 engine/risk 提取
  - execution 从 engine/execution + data/services/trade 提取

Phase 4: 回测与编排（中风险）
  - backtest 从 engine/backtest 提取
  - application 吸收 app + engine 运行时
  - analysis 新建

Phase 5: 入口层（低风险）
  - interfaces 调整引用

Phase 6: 清理
  - 删除旧包结构
  - 更新 importlinter 配置
  - 更新所有 CLAUDE.md
  - 全量测试验证
```

### 9.2 每个 Phase 的验证标准

```
pixi run -e dev check     # lint + fmt + type + test --fast
pixi run -e dev arch-check # importlinter 依赖检查
```

---

## 10. 待后续设计细化的问题

1. **各模块 pyproject.toml 的精确依赖声明**
2. **importlinter 配置的具体 rules**
3. **DI Container (Dishka) Provider 重组方案**
4. **各模块 adapters/ 的存储实现细节**
5. **application/runtime 的具体 API 设计**
6. **现有测试的迁移和重组**
7. **CLI/API 路由的调整**
8. **backtest 与 execution 的 contracts 共享机制**

---

## A. 附录：当前 → 新架构文件迁移映射（概要）

| 当前位置 | 新位置 | 文件数(约) |
|---------|--------|-----------|
| kernel/ | kernel/ | 14 (不变) |
| infra/ | infra/ | 48 (不变) |
| data/sources/ | data/sources/ | ~30 (保留) |
| data/storage/market/ | data/storage/market/ | ~40 (保留) |
| data/storage/metadata/ | data/storage/metadata/ | ~25 (保留) |
| data/storage/fundamental/ | data/storage/fundamental/ | ~15 (保留) |
| data/storage/macro/ | data/storage/macro/ | ~10 (保留) |
| data/storage/capital/ | data/storage/capital/ | ~10 (保留) |
| data/storage/execution/ | execution/adapters/ | ~5 (迁出) |
| data/storage/factors/ | features/adapters/ | ~5 (迁出) |
| data/storage/features/ | features/adapters/ | ~5 (迁出) |
| data/services/trade/ | execution/ | ~8 (迁出) |
| data/services/strategy/ | strategy/ | ~30 (迁出) |
| data/services/audit/ | execution/ | ~5 (迁出) |
| data/services/derived/ | features/ | ~15 (迁出) |
| data/quality/ | data/quality/ | ~20 (保留) |
| data/ingestion/ | data/ingestion/ | ~6 (保留) |
| data/helpers/ | data/helpers/ | ~5 (保留) |
| analytics/expression/ | features/expression/ | ~9 (迁出) |
| analytics/factors/ | features/factors/ | ~15 (迁出) |
| analytics/evaluation/ | features/evaluation/ | ~10 (迁出) |
| analytics/materialization/ | features/materialization/ | ~3 (迁出) |
| engine/alpha/ | strategy/alpha/ | ~25 (迁出) |
| engine/portfolio/ | portfolio/ | ~4 (迁出) |
| engine/accounting/ | portfolio/accounting/ | ~6 (迁出) |
| engine/risk/ | risk/ | ~3 (迁出) |
| engine/execution/ | execution/ | ~10 (迁出) |
| engine/backtest/ | backtest/ | ~20 (迁出) |
| app/command/ | application/commands/ | ~7 (迁移) |
| app/query/ | application/queries/ + analysis/ | ~25 (拆分) |
| app/process/ | application/processes/ | ~45 (迁移) |
| app/builders/ | application/runtime/ | ~5 (迁移) |
| interfaces/ | interfaces/ | ~108 (调整引用) |
