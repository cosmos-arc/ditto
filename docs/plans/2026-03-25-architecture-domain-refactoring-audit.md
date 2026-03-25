# 架构审计：领域子域重构与异常体系规范

**日期**: 2026-03-25
**范围**: 全库架构审视（分层、模块划分、命名、领域归属、异常体系）
**状态**: 已决策，待实施

---

## 1. 审计背景与目标

对 Ditto 全库进行架构审计，审视：
- 各模块的分层、划分、命名、边界归属
- 层次-模块-类-方法的领域归属是否合理
- 是否符合量化领域专业术语
- 异常体系是否遵循分层架构规范

**参考**：QuantConnect LEAN、DDD（[InfoQ](https://www.infoq.com/news/2015/03/ddd-trading-example/)、[DevIQ](https://deviq.com/domain-driven-design/shared-kernel/)）、Clean Architecture（[Medium](https://medium.com/@venmanassery.vivek/clean-architecture-in-python-how-do-i-clean-43469db8dc62)）

---

## 2. 当前架构优点

在指出问题之前，值得肯定当前设计的优秀之处：

| 优点 | 说明 |
|------|------|
| 四层分离 | Infra → DataHub → Core → Port 通过 importlinter 强制约束 |
| frozen dataclass + Protocol | 不可变值对象 + 依赖倒置，量化系统最佳实践 |
| Kernel 准入标准 | 严格防止"万能包"退化 |
| Pipeline/Stage 架构 | DecisionStage Protocol + builtins/templates 分层，扩展性极强 |
| CQRS Reader/Writer | DataHub 层读写分离执行到位 |
| 可变状态最小化 | 仅 Account 和 BacktestBrokerage 是可变状态持有者 |

---

## 3. P0 — 跨层模型重复与命名不统一

### 3.1 问题：Order / OrderStatus / OrderSide 重复定义

DataHub 和 Core 对同一领域概念存在**重复定义且语义不一致**。

| 概念 | DataHub (`models/trading.py`) | Core (`accounting/order_book.py`) | Kernel (`enums.py`) |
|------|------|------|------|
| 方向 | `OrderSide` (BUY/SELL) | `OrderDirection` = `OrderSide` 别名 | `OrderSide` (权威源) |
| 状态 | `OrderStatus` (PENDING/FILLED/...) | `OrderStatus` (NEW/SUBMITTED/...) | — |
| 订单 | `Order` (存储模型) | `Order` (领域模型) | — |

**决策**：
- Kernel 扩展为 Rich Domain Model，吸收 Core 的核心领域模型（含行为）
- DataHub 的 Order → `OrderRecord`，Position → `PositionRecord`（存储模型命名规范）
- 消除 `OrderDirection` 别名，统一使用 `OrderSide`
- OrderStatus 以 Core 版本为权威定义（更完整的状态流），迁移至 Kernel

### 3.2 问题：Position / Portfolio 同名歧义

DataHub `models/portfolio.py` 的 `Position` 和 Core `accounting/position.py` 的 `Position` 同名不同结构。

**决策**：DataHub 的 Position → `PositionRecord`，消除同名歧义。

---

## 4. Kernel 扩展：Rich Domain Model

### 4.1 业界参考

**QuantConnect LEAN** 的 `Common/` 是直接参照：

```
Common/
├── Orders/       ← 订单领域模型（含状态机行为）
├── Securities/   ← 标的领域模型（含价格更新行为）
├── Interfaces/   ← 跨域 Protocol
├── Data/         ← 数据类型
└── Brokerages/   ← 经纪商 Protocol
```

LEAN 的 `Order` 类包含完整状态转换行为，`Security` 类包含价格更新逻辑——**Rich Domain Model**，不是 anemic model。

**DDD Shared Kernel 原则**：保持**尽可能小**的共享子集，只放跨 Bounded Context 必须一致的类型。

### 4.2 扩展原则

- Kernel 包含完整的领域模型（含行为）：self-contained 的纯方法
- Core 包含领域服务：协调多个 Kernel 对象的业务逻辑
- 不采用"纯结构 + service wrapper"模式，也不采用"hybrid wrapper"模式
- 类型上限保持 20 个红线

**行为归属**：

| 归属 | 示例 | 判断标准 |
|------|------|---------|
| Kernel | `OrderStatus.is_terminal`, `Order.with_quantity()`, `OrderTicket.with_fill()` | self-contained，不依赖外部状态 |
| Core | `Account.apply_fill()`, `OrderBook.submit()`, `Brokerage.place_order()` | 协调多个对象，需要外部依赖 |

### 4.3 按领域子域组织（消除技术类型命名）

```
ditto_kernel/
├── __init__.py          # 顶层重导出
├── instrument.py        # 标的子域
│   ├── InstrumentId (NewType)
│   ├── AssetClass (StrEnum)
│   └── Exchange (StrEnum)
├── order.py             # 订单子域
│   ├── OrderSide (StrEnum)
│   ├── OrderType (StrEnum)
│   ├── OrderStatus (StrEnum, 含 is_terminal)
│   ├── Order (frozen dataclass, 含 with_quantity)
│   ├── OrderEvent (frozen dataclass)
│   ├── OrderTicket (frozen dataclass, 含 with_fill/with_cancel/with_reject/with_invalid)
│   └── StateTransitionError
├── trade.py             # 成交子域
│   ├── FillEvent (frozen dataclass)
│   ├── FillOutcome (联合类型: Filled | NoFill)
│   ├── Filled (frozen dataclass)
│   ├── NoFill (frozen dataclass)
│   ├── Position (frozen dataclass)
│   └── CashBook (frozen dataclass)
├── market.py            # 行情子域
│   └── MarketSnapshot (frozen dataclass)
└── strategy.py          # 策略子域
    └── RunStatus (StrEnum)
```

**类型总数**：从 5 个增长到约 18 个，在 20 个红线内。

---

## 5. Core 层按领域子域重新组织

### 5.1 量化系统标准子域划分

业界共识将量化系统拆为以下子域：

| 子域 | 英文 | DDD 类型 | 对应 Ditto |
|------|------|---------|-----------|
| **标的/参考数据** | Instrument / Reference Data | 通用域 | InstrumentId, AssetClass, Exchange, InstrumentDefinition |
| **订单管理** | Order Management | 核心域 | Order, OrderStatus, OrderType, OrderTicket, OrderBook |
| **交易执行** | Execution | 核心域 | Brokerage, Planner, Fill/Slippage/Fee/Settlement Model |
| **持仓/账户** | Position & Account | 核心域 | Account, Position, CashBook, BuyingPower |
| **组合构建** | Portfolio Construction | 核心域 | Allocator, ConstraintChecker |
| **风控** | Risk Management | 支撑域 | PreTrade Check, PostTrade Guard |
| **策略/信号** | Strategy & Signal | 核心域 | Pipeline, Stages, Specs, Templates |
| **行情数据** | Market Data | 通用域 | Bar, MarketSnapshot, DataFeed |
| **回测** | Backtesting | 支撑域 | EngineLoop, Manifest, Statistics |
| **数据质量** | Data Quality | 通用域 | DQ Engine, Checkers |

### 5.2 Core 重构后的模块结构

```
ditto_core/
├── instrument/          # 标的子域（从 execution/rules.py 拆出）
│   ├── definition.py    # InstrumentDefinition（静态资产属性）
│   ├── trading_rules.py # TradingRuleSet, FeeSchedule
│   └── provider.py      # InstrumentRuleProvider Protocol + InMemory 实现
│
├── order/               # 订单子域（从 accounting/order_book.py 迁出）
│   └── book.py          # OrderBook, OrderBookReadOnly（状态管理服务）
│
├── execution/           # 执行子域（精简，不再"拥有"规则和订单定义）
│   ├── brokerage.py     # Brokerage Protocol + BacktestBrokerage
│   ├── planner.py       # ExecutionPlanner Protocol + SimpleExecutionPlanner
│   ├── trade_matching.py# TradeBuilder Protocol + FIFO/FlatToFlat
│   ├── fill.py          # FillModel Protocol + 实现
│   ├── slippage.py      # SlippageModel Protocol + 实现
│   ├── fee.py           # FeeModel Protocol + 实现
│   ├── settlement.py    # SettlementModel Protocol + 实现
│   └── model.py         # BrokerageModel（聚合 reality 子模型）
│
├── account/             # 账户子域（从 accounting/ 重命名）
│   ├── account.py       # Account (mutable), AccountView (frozen snapshot)
│   └── buying_power.py  # BuyingPowerModel Protocol + CashAccountBuyingPower
│
├── portfolio/           # 组合构建子域（精简）
│   ├── allocation.py    # WeightAllocator + 适配器
│   └── constraints.py   # ConstraintChecker + 适配器
│
├── risk/                # 风控子域（从 backtest/risk/ 提升）
│   ├── pre_trade.py     # PreTradeRiskCheck Protocol + 6 规则
│   └── post_trade.py    # PostTradeRiskGuard Protocol + 4 Guard
│
├── strategy/            # 策略子域（不变）
│   ├── pipeline.py, context.py, specs.py, models.py, validation.py
│   ├── builtins/        # 8 个原子 Stage
│   └── templates/       # 4 个策略模板
│
├── backtest/            # 回测编排（不再"拥有"风控和比较）
│   ├── engine.py        # EngineLoop, EngineConfig, EngineOptions
│   ├── data_feed.py     # DataFeed Protocol + ParquetDataFeed
│   ├── statistics.py    # BacktestReport + 统计计算
│   ├── manifest.py      # RunManifest + RuleRefCollector
│   ├── comparison.py    # StrategyComparisonReport（从 portfolio/ 移入）
│   └── audit/           # ExecutionAuditCollector, records
│
├── derived/             # 派生因子引擎（原 engine/ 拆分，详见 §9）
│   ├── expression/      # DSL 编译器（lexer → parser → analyzer → codegen）
│   ├── specs.py         # DerivedSpec, DerivedRole, MaterializationProfile
│   ├── factors/         # 因子定义注册表（FactorSpec + 4 类因子库）
│   ├── compile.py       # ExpressionCompiler + CompileIdentity（门面）
│   └── materialization/ # 物化 DTO（contracts, models, planner）
│
├── evaluation/          # 因子评估统计（原 engine/evaluation/，提升为独立子域）
│   ├── evaluator.py
│   ├── report.py
│   └── metrics/         # ic, factor_analysis, portfolio, tail_risk, _math
│
├── research/            # 研究数据集与发布安全（原 engine/ 散落模块整合）
│   ├── spine.py         # SpineSpec, SpineSnapshot
│   ├── dataset.py       # ResearchDatasetSpec, DatasetSnapshot, LateArrival*
│   └── publication.py   # CertificationPack, ShadowDiffReport, CompatibilityManifest
│
└── quality/             # 数据质量（隔离，不变）
```

### 5.3 关键变更对照表

| 变更 | 当前 | 目标 | 理由 |
|------|------|------|------|
| `accounting/` → `account/` | 会计（技术概念） | 账户（领域概念） | 量化领域用"Account"而非"Accounting" |
| 新增 `instrument/` | 规则在 execution/ | 独立子域 | InstrumentDefinition 是标的属性，不是执行概念 |
| 新增 `order/` | 订单在 accounting/ | 独立子域 | OrderBook 状态管理是订单子域的服务 |
| `execution/rules.py` 拆分 | 7 类型混一文件 | instrument/ 子域 | 三层规则按关注点分离 |
| `execution/reality/` 扁平化 | 子目录 5 文件 | 平铺 5 文件 | reality 不是领域概念 |
| `backtest/risk/` → `risk/` | 风控在回测下 | 独立顶层子域 | 风控不限于回测，实盘同样需要 |
| `portfolio/comparison.py` → `backtest/` | 在 portfolio/ | 在 backtest/ | 输入是 BacktestReport，语义更匹配 |

---

## 6. DataHub 层变更

### 6.1 Record 模型命名规范

| Kernel/Core 领域模型 | DataHub 存储模型 | 转换收口位置 |
|---|---|---|
| `Order` | `OrderRecord` | DataHub stores |
| `Position` | `PositionRecord` | DataHub stores |
| `FillEvent` | `TradeRecord` | DataHub stores |
| `OrderStatus` | 字符串列 | Store Writer |
| `MarketSnapshot` | DataFrame Schema | DataHub stores |

### 6.2 DataFrame 流转边界

| 数据特征 | 模型形式 | 所在层 |
|---------|---------|--------|
| 有状态机/业务行为 | 强类型 domain model | Kernel 定义结构 + Core 实现行为 |
| 批量时序数据（bars, factors, signals） | polars DataFrame + Schema | Core/DataHub 用 Schema 约束 |
| 持久化/外部交互 | Record 模型 + DataFrame | DataHub 收口 |

### 6.3 models/ 清理

| 动作 | 文件 | 说明 |
|------|------|------|
| 删除 | `enums.py` | 纯重导出壳，消费者直接 import kernel |
| 重命名 | `trading.py` | Order → OrderRecord, OrderStatus → OrderStatusRecord |
| 重命名 | `portfolio.py` | Position → PositionRecord |
| 重命名 | `source_codes.py` → `instrument_code_mapping.py` | 硬编码映射不是"模型" |
| 合并 | `strategy_audit.py` → `strategy.py` | 仅 2 个 Payload 类，量太少 |

---

## 7. 异常体系规范

### 7.1 业界最佳实践

参考 [StackOverflow DDD](https://stackoverflow.com/questions/51942769/should-my-domain-exceptions-be-thrown-from-application-layer)、[Enterprise Python Error Handling](https://www.augmentcode.com/guides/python-error-handling-10-enterprise-grade-tactics)、[FastAPI Exception Best Practices](https://medium.com/delivus/exception-handling-best-practices-in-python-a-fastapi-perspective-98ede2256870)：

**核心原则**：
1. **内层不依赖外层异常** — Kernel/Core 不能 catch infra 异常
2. **外层包装内层异常** — Infra 层包装底层存储/网络异常，提供统一抽象
3. **领域异常由领域层定义和抛出** — Core 层定义和抛出业务规则违反异常
4. **应用层做翻译** — Port 层捕获所有异常，翻译为 HTTP 响应或 CLI 输出

**分层异常所有权**：

| 层 | 异常类型 | 职责 | 示例 |
|----|---------|------|------|
| Infra | `InfraError` + 子类 | 包装底层存储/网络/配置异常 | `StorageError`, `ConnectionError` |
| Kernel | `DomainError` + 子类 | 纯业务规则违反（无 I/O） | `StateTransitionError` |
| Core | `DomainError` + 子类 | 领域服务业务规则违反 | `InsufficientBuyingPowerError` |
| DataHub | 无自有异常 | 使用 Infra 异常 + Core 异常 | — |
| Port | 翻译层 | 捕获所有异常，翻译为响应 | HTTP status / CLI message |

### 7.2 当前异常分布问题

| 问题 | 详情 |
|------|------|
| Port 两套并行体系 | `exceptions.py`（DittoException 层）与 `errors.py`（DittoPortError 层）并存 |
| 同名异常跨层重复 | `DataSourceError`、`ValidationError`、`SourceFetchError` 在 DataHub 和 Port 各有一份 |
| DataHub 25 个异常类过多 | `DerivedError`（7 个）、`DataHubError`（11 个）、`DataSourceError`（6 个）三大层级 |
| Port 散落异常 | `CascadeDepthExceededError`、`MissingDependencyError` 直接继承 Exception |
| Core re-export DataHub 异常 | `ditto_core.engine.errors` re-export 7 个 DerivedError，违反 Core 不依赖 DataHub 原则 |
| DataHub ingestion 异常 | `NotTradingDayError`、`DataChangedError`、`LateArrivalRejectedError` 定义在 models/ 中 |

### 7.3 目标异常体系

#### Infra 层：统一基础设施异常

```python
# ditto_infra/errors.py

class InfraError(Exception):
    """基础设施层异常基类。"""
    def __init__(self, message: str, *, cause: Exception | None = None):
        self.cause = cause
        super().__init__(message)


class StorageError(InfraError):
    """存储操作异常（SQLite / Parquet / 文件系统）。"""


class ConnectionError(InfraError):
    """外部连接异常（HTTP / 数据库连接池）。"""


class ConcurrencyError(InfraError):
    """并发控制异常（锁超时 / 写冲突）。"""


class ConfigurationError(InfraError):
    """配置/启动阶段异常。"""
```

**迁移映射**：

| 当前（散落各处） | 目标 | 说明 |
|---|---|---|
| `ConfigInitError` (infra config) | `ConfigurationError` | 合并 |
| `LockAcquisitionError` (infra concurrency) | `ConcurrencyError` | 合并 |
| `LegacySchemaError` (infra sqlite) | `StorageError` | 合并 |
| `DataSourceError` (datahub sources) | `ConnectionError` | 外部数据源连接失败 |
| `SourceAuthenticationError` | `ConnectionError` | 认证失败是连接问题 |
| `SourceRateLimitError` | `ConnectionError` | 限流是连接问题 |
| `SourceFetchError` | `ConnectionError` | 网络获取失败 |
| `SourceTransformationError` | `StorageError` | 数据转换/写入问题 |
| `SourceConfigurationError` | `ConfigurationError` | 配置问题 |

#### Kernel 层：纯领域异常

```python
# ditto_kernel/order.py（随领域模型一起定义）

class StateTransitionError(Exception):
    """订单状态非法转换（如 FILLED → CANCEL）。"""
```

Kernel 的异常极少——只有领域模型自身的不变量违反。大部分业务异常由 Core 层定义。

#### Core 层：领域业务异常

```python
# ditto_core/account/errors.py

class AccountError(Exception):
    """账户子域异常基类。"""

class InsufficientBuyingPowerError(AccountError):
    """购买力不足。"""

class InvalidOrderError(AccountError):
    """订单校验失败。"""


# ditto_core/risk/errors.py

class RiskError(Exception):
    """风控子域异常基类。"""

class PreTradeRejectError(RiskError):
    """前置风控拒绝订单。"""

class PostTradeRiskAlert(RiskError):
    """后置风控触发警报。"""


# ditto_core/execution/errors.py

class ExecutionError(Exception):
    """执行子域异常基类。"""
```

**迁移映射**：

| 当前 | 目标 | 说明 |
|------|------|------|
| `StateTransitionError` (accounting) | `ditto_kernel.order.StateTransitionError` | 迁入 Kernel |
| `ExpressionCompileError` (engine) | 保留在 `derived/` | 表达式编译是派生子域的领域概念 |
| `LateArrivalError` (engine/research) | 保留在 `research/` | 研究数据集是独立子域 |

#### DataHub 层：零自有异常

DataHub **不定义任何异常类**。所有基础设施异常使用 `ditto_infra.errors`，所有领域异常使用 `ditto_core.*.errors`。

**迁移映射**：

| 当前 DataHub 异常 | 目标 |
|---|---|
| `DerivedError` 系列 (7 个) | `Core/engine/errors.py`（DerivedError 是领域概念）或评估是否需要 |
| `DataHubError` 系列 (11 个) | 逐个评估：存储类 → `InfraError`，领域类 → Core 异常 |
| `DataSourceError` 系列 (6 个) | `InfraError` 子类 |
| `NotTradingDayError` | Core 异常或 Port 层校验 |
| `DataChangedError` | Infra `StorageError` |
| `LateArrivalRejectedError` | Core 异常 |

**详细 DataHub 异常归类**：

| DataHub 异常 | 归类 | 目标 | 理由 |
|---|---|---|---|
| `CalendarError` / `TradingDateNotFoundError` | 领域 | Core 或保留 DataHub | 交易日历是领域概念 |
| `InstrumentIdNotFoundError` / `IdentifierNotFoundError` / `AmbiguousTickerError` | 领域 | Core instrument/ | 标的查找是领域概念 |
| `DatasetNotFoundError` / `PartitionNotFoundError` | 基础设施 | `InfraError(StorageError)` | 文件/分区不存在是存储问题 |
| `ValidationError` / `SchemaValidationError` | 基础设施 | `InfraError(StorageError)` | Schema 校验是存储写入时的技术校验 |
| `DerivedNotFoundError` / `DerivedVersionError` | 领域 | Core derived/ | 衍生实体管理是领域概念 |
| `DerivedMaterializationError` / `DerivedDependencyError` | 领域 | Core derived/ | 物化依赖是领域概念 |
| `DerivedValidationError` / `DerivedNotImplementedError` | 领域 | Core derived/ | 衍生校验是领域概念 |

#### Port 层：统一翻译层

Port 层**不定义业务异常**，只做异常翻译：

```python
# ditto_port/errors.py（统一为单一文件）

class DittoPortError(Exception):
    """Port 层异常翻译基类。"""


class APIError(DittoPortError):
    """HTTP API 异常，携带 status_code 和 error_code。"""

class CLIError(DittoPortError):
    """CLI 异常，携带用户友好消息。"""
```

Port 层通过 FastAPI middleware / CLI handler 捕获 `InfraError` / `DomainError`，翻译为 HTTP 404/400/500 或 CLI 错误消息。

**迁移映射**：

| 当前 | 目标 |
|---|---|
| `exceptions.py`（DittoException 层，5 个） | 删除，合并入 `errors.py` |
| `errors.py`（DittoPortError 层，9 个） | 精简为 API 翻译 |
| `api/errors.py`（APIError 层，3 个） | 保留，继承自新的 DittoPortError |
| `CascadeDepthExceededError`（散落） | Core risk/ 异常或 Port 内部异常 |

### 7.4 异常依赖规则

```
┌─────────────────────────────────────────────┐
│  Kernel/Core 可以抛出 Infra 异常吗？         │
│  ❌ 不可以。内层不能依赖外层。               │
│  Kernel/Core 只抛出自己的 DomainError。      │
│  Infra 异常由 Store/Source 适配层抛出，      │
│  Port 层统一捕获和翻译。                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  DataHub Store 可以抛出 InfraError 吗？     │
│  ✅ 可以。DataHub 依赖 Infra。              │
│  Store 写入失败时抛出 InfraError(StorageError)。│
│  Port 层捕获并翻译为 HTTP 500。              │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Core re-export DataHub 异常？              │
│  ❌ 不可以。违反 Core 不依赖 DataHub。      │
│  当前 ditto_core.engine.errors re-export    │
│  7 个 DerivedError 需要消除。               │
│  方案：将领域异常迁移到 Core，或消除 re-export。│
└─────────────────────────────────────────────┘
```

### 7.5 异常体系统计

| 层 | 当前 | 目标 | 变化 |
|----|------|------|------|
| Infra | 3 | ~5 | StorageError, ConnectionError, ConcurrencyError, ConfigurationError |
| Kernel | 0 | 1 | StateTransitionError |
| Core | 3（+ 7 re-export） | ~8 | AccountError, RiskError, ExecutionError, DerivedError + 子类 |
| DataHub | 25 | 0 | 全部迁移或消除 |
| Port | 16 | ~5 | APIError + CLIError + 翻译逻辑 |
| **总计** | **47** | **~19** | 大幅精简 |

---

## 8. engine/ 模块拆分方案

### 8.1 问题诊断

`engine/` 名字语义过载，实际包含 5 个弱耦合的子域，且存在多个架构问题：

| 问题 | 详情 |
|------|------|
| 语义过载 | "engine" 不传达具体领域含义，5 个子域（编译器、因子、物化、评估、研究）共用一个名字 |
| 反向依赖 | `expression/analyzer.py` 导入 `materialization.contracts.Analysis`，编译器不应依赖物化层 |
| 架构违规 | `errors.py` 从 `ditto_datahub.errors` 纯重导出 7 个 DerivedError，违反 Core↔DataHub 规则 |
| I/O 混入 Core | `compile_cache.py` 包含 SQLite L2 缓存，Core 层应零 I/O |
| `evaluation/` 完全独立 | 不依赖 expression/factors/materialization 中任何一个，挂在一起不合理 |

### 8.2 DerivedSpec 与 FactorSpec 的关系

两者**不应合并**，是故意区分的设计：

- `DerivedSpec`：统一的派生数据语义规约，覆盖 4 种角色（FACTOR/FEATURE/SIGNAL/LABEL），面向物化管道
- `FactorSpec`：因子专用的轻量声明（id + expression + dependencies），给因子注册表内部使用
- `DerivedSpec` 需要完整的物化属性（version, role, grain, calendar, execution_policy 等），`FactorSpec` 不需要

### 8.3 消费者分析

| 消费者 | 导入数量 | 说明 |
|--------|---------|------|
| **Port 源码** (`apps/port/src/`) | ~20 处 | **主要消费者**，编排层直接依赖 engine |
| **DataHub 源码** (`packages/datahub/src/`) | 0 处 | DataHub 不直接依赖 engine |
| **DataHub 测试** | ~8 处 | 仅测试中构造 DTO 使用 |
| **Core 自身** | ~30 处 | 内部互依赖 |

**结论**：Port 层是 engine 的实际消费者，分层合理（Core 提供领域逻辑 → Port 编排调用 → DataHub 不直接依赖）。

### 8.4 拆分方案

将 `engine/` 拆分为 3 个独立顶层子域：

```
ditto_core/
├── derived/               # 派生因子引擎（原 engine 核心部分）
│   ├── expression/        # DSL 编译器（lexer → parser → analyzer → codegen）
│   ├── specs.py           # DerivedSpec, DerivedRole, MaterializationProfile
│   ├── factors/           # 因子定义注册表（FactorSpec + primitives/technical/fundamental/alpha）
│   ├── compile.py         # ExpressionCompiler + CompileIdentity（顶层门面）
│   ├── materialization/   # 物化 DTO（contracts, models, planner）
│   └── errors.py          # DerivedError 层次（领域异常，不再从 DataHub 重导出）
│
├── evaluation/            # 因子评估统计（完全独立子域）
│   ├── evaluator.py
│   ├── report.py
│   └── metrics/           # ic, factor_analysis, portfolio, tail_risk, _math
│
└── research/              # 研究数据集与发布安全
    ├── spine.py           # SpineSpec, SpineSnapshot
    ├── dataset.py         # ResearchDatasetSpec, DatasetSnapshot, LateArrival*
    └── publication.py     # CertificationPack, ShadowDiffReport, CompatibilityManifest
```

### 8.5 拆分对照表

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `engine/expression/` | `derived/expression/` | 编译器子包不变 |
| `engine/specs.py` | `derived/specs.py` | DerivedSpec 保留 |
| `engine/factors/` | `derived/factors/` | FactorSpec 保留，与 DerivedSpec 不合并 |
| `engine/materialization/` | `derived/materialization/` | 物化 DTO 保留 |
| `engine/compile_cache.py` | 移至 DataHub Store | SQLite I/O 不属于 Core |
| `engine/errors.py` | `derived/errors.py` | DerivedError 迁移到 Core，消除 DataHub 重导出 |
| `engine/evaluation/` | `evaluation/`（顶层） | 独立子域 |
| `engine/research.py` | `research/dataset.py` | 研究数据集 |
| `engine/publication_safety.py` | `research/publication.py` | 发布安全 |

### 8.6 需修复的依赖问题

| 问题 | 修复方案 |
|------|---------|
| `expression/analyzer.py` → `materialization.contracts.Analysis` | 将 `Analysis`/`AnalysisWarning` 提取为共享类型，放入 `derived/expression/analysis.py` |
| `errors.py` re-export `ditto_datahub.errors` | DerivedError 系列定义为 `derived/errors.py` 的自有异常，DataHub 改为导入 Core |
| `compile_cache.py` SQLite I/O | 移至 `ditto_datahub/stores/runtime/compile_cache.py` |

---

## 9. 完整行动清单

### P0 — 应尽快修复

| # | 行动 | 影响范围 | 复杂度 |
|---|------|---------|--------|
| 1 | Kernel 扩展（order.py, trade.py, market.py, strategy.py） | kernel + core + datahub | 中 |
| 2 | 消除 OrderDirection 别名，统一 OrderSide | core 全局 | 低 |
| 3 | DataHub Order → OrderRecord, Position → PositionRecord | datahub models + stores | 低 |
| 4 | DataHub enums.py 删除 | datahub | 低 |

### P1 — 中期重构

| # | 行动 | 影响范围 | 复杂度 |
|---|------|---------|--------|
| 5 | Core 按子域重组（accounting→account, 新增 instrument/order/risk） | core 全局 | 高 |
| 6 | execution/rules.py 拆分到 instrument/ | core execution | 中 |
| 7 | backtest/risk/ → risk/ 提升 | core | 中 |
| 8 | engine/ 拆分为 derived/ + evaluation/ + research/ | core 全局 | 高 |
| 9 | expression/analyzer.py 反向依赖修复（Analysis 提取到 derived/expression/） | core derived | 中 |
| 10 | compile_cache.py 从 Core 移至 DataHub Store | core + datahub | 中 |
| 11 | 异常体系重构（Infra 统一 + DataHub 清零 + Port 精简） | 全局 | 高 |
| 12 | Core re-export DataHub 异常消除（DerivedError 迁移到 Core derived/） | core + datahub | 中 |
| 13 | DataHub strategy_audit.py 合并入 strategy.py | datahub | 低 |

### P2 — 长期演进

| # | 行动 | 影响范围 | 复杂度 |
|---|------|---------|--------|
| 11 | portfolio/comparison.py → backtest/comparison.py | core | 低 |
| 12 | execution/reality/ 扁平化 | core | 低 |
| 13 | backtest/serialization.py I/O 迁移到 Port | core + port | 中 |
| 14 | Port errors.py + exceptions.py 合并 | port | 低 |

---

## 附录 A：参考资源

- [QuantConnect LEAN — Common/](https://github.com/quantconnect/lean/tree/master/Common)
- [InfoQ — Clarifying DDD Using a Trading Application](https://www.infoq.com/news/2015/03/ddd-trading-example/)
- [DevIQ — Shared Kernel](https://deviq.com/domain-driven-design/shared-kernel/)
- [StackOverflow — Domain Exceptions and Application Layer](https://stackoverflow.com/questions/51942769/should-my-domain-exceptions-be-thrown-from-application-layer)
- [Augment Code — Python Error Handling: 10 Enterprise-Grade Tactics](https://www.augmentcode.com/guides/python-error-handling-10-enterprise-grade-tactics)
- [Medium — FastAPI Exception Handling Best Practices](https://medium.com/delivus/exception-handling-best-practices-in-python-a-fastapi-perspective-98ede2256870)
- [Medium — Clean Architecture in Python](https://medium.com/@venmanassery.vivek/clean-architecture-in-python-how-do-i-clean-43469db8dc62)
- [Medium — Trading System Design using MicroServices](https://medium.com/@datajedi/trading-system-design-using-microservices-256cda0dc60a)
