# Ditto 架构重构设计 v2 — Hybrid 平面架构

**日期**: 2026-03-30（2026-03-31 审查修订）
**状态**: 设计完成，待实施
**审查记录**: `docs/reviews/2026-03-31-hybrid-plane-v2-critical-review.md`
**Supersede**: 本文档 supersede `docs/plans/2026-03-26-full-architecture-refactoring-design.md` 和 `docs/reviews/2026-03-27-architecture-refactoring-final-review.md`

---

## 1. 设计背景与动机

Ditto 之前的架构重构计划（2026-03-26）采用纯 DDD 子域优先策略，将系统拆分为 ~10 个顶层 package。经以业界顶尖量化平台为参照的审视，发现以下问题：

1. **过度偏向 DDD 战术模式** — 计划更像 DDD 教科书应用，而非从量化系统核心需求出发
2. **缺少量化系统核心支柱** — 无 Clock 抽象、无 DataProvider 统一接口、无泛化 Pipeline 模型、无状态机
3. **metadata/marketdata 拆分边界模糊** — 在实践中深度纠缠，硬拆增加边界开销
4. **prepared-input-first 作为铁律过激** — 高频 DataFrame 场景下全量预组装代价需正视
5. **10 个顶层 package 过早模块化** — 对当前体量，边界维护成本可能超过收益

本设计采用 **Hybrid 分层架构**：顶层用平面划分，平面内部用 Stage/Orchestrator 组织，Stage 内部用 DDD 战术模式。

---

## 2. 核心组织原则

| 层次 | 组织原则 | 说明 |
|------|---------|------|
| 顶层模块 | **平面划分**（Data / Engine / Analytics） | 量化系统的三大关注点天然分离 |
| 平面内部 | **Stage + Orchestrator** | Engine 用 Orchestrator 编排状态化流程；Analytics 用 Pipeline 组合纯函数链 |
| Stage 内部 | **DDD 战术模式** | Entity、Value Object、Domain Service 在这里才有意义 |

### 四大架构支柱

1. **统一时间模型**（Clock）— 回测/实盘共享同一代码路径，只区别于时钟实现
2. **统一数据访问**（DataProvider）— 所有平面通过 Protocol 获取数据，不直接依赖存储实现
3. **最小事件契约**（DomainEvent）— 跨平面状态变更通过事件通知，同步进程内分发
4. **双通道数据流** — 主数据流通过 Stage typed contract，辅助数据通过 DataProvider on-demand

> **v2.1 审查修订说明**：
> - Pipeline/Stage/Context 从 Kernel 移出，归属 Engine/Analytics 各自内部（强类型化）
> - Kernel 只保留真正跨层共享的抽象：Clock、DataProvider、EventBus
> - Engine 编排模型从线性 Pipeline 改为 TradingOrchestrator（支持条件分支和状态突变）
> - 状态管理不新增顶层抽象，沿用 Brokerage owner 模式（Account + AccountView 读写分离）
> - 实时流通过 Protocol 继承 + 实现扩展演进，不回头改已冻结的 Kernel 接口

### 架构纪律（源自 v3 设计审查）

以下原则从 `docs/plans/2026-03-31-ditto-future-architecture-design.md` 审查采纳：

1. **唯一语义 owner** — 同一类真相只能有一个 owner。"谁在消费"不等于"谁拥有真相"。data 平面内部通过 query 层统一对外暴露，内部 metadata/market 的 owner 边界用 importlinter 约束。
2. **Runtime Contract 显式化** — 跨平面交互通过显式 contract 表达（输入、组装者、消费者、生命周期）。Snapshot/frozen dataclass 的每个字段必须对应真实消费点，不允许"可能以后会用"的预埋字段。
3. **Query/Command/Process 互斥规则** — Query 不调 Command/Process，Command 不调 Query/Process，Process 可以调 Query/Command，builders 只接收已获取数据并组装 contract。
4. **审计证据四分类** — 每次回测至少可重建：Input Evidence（数据集/规则/参数版本）、Decision Evidence（信号/目标/风控）、Execution Evidence（委托/成交/费用/账户）、Result Evidence（report/attribution/artifact）。
5. **Strangler 迁移优先** — 迁移顺序：先定义新边界 → 建立适配层 → 迁移调用路径 → 最后迁目录。不一刀切。

### 不采纳的 v3 建议

- **8 个顶层包**（metadata/market 拆分）— 对当前体量过度模块化，data 保持统一
- **独立 integration 层** — 等实盘 broker 对接需求出现时再独立
- **8 种 engine 事件** — 事件由实际需求驱动，不提前枚举
- **三级缓存 L1/L2/L3** — 当前只有 compile cache 需要缓存，过度设计

---

## 3. 目标模块结构

```text
packages/
  kernel/            # 跨层共享抽象（Clock, DataProvider, EventBus）— 14 符号
  infra/             # 基础设施（配置、日志、存储引擎、缓存、并发、通知）
  data/              # 数据平面（models + sources + storage + query + quality + ingestion）
  engine/            # 交易引擎（orchestrator + alpha + portfolio + execution + risk + accounting + backtest）
  analytics/         # 分析平面（expression + factors + evaluation + materialization + research）

apps/
  app/               # Use Case 编排（Query + Command + Process + registry）
  interfaces/        # 适配器（HTTP + CLI + Prefect Jobs）
  web/               # Web 前端（保持不变）
```

从 ~10 个顶层 package 收敛到 **5 个核心 package + kernel**。

---

## 4. Kernel — 跨层共享抽象协议层

```text
kernel/
  types.py          # 现有：InstrumentId, TradeDate, Currency
  enums.py          # 现有：AssetClass, Exchange, OrderSide, RunStatus, RiskScope
  identity.py       # 现有：InstrumentId 相关工具
  clock.py          # ✅ 已实现：Clock Protocol + SimulatedClock + RealtimeClock
  provider.py       # ✅ 已实现：DataProvider Protocol + BarQuery + InstrumentQuery
  events.py         # ✅ 已实现：DomainEvent + EventHandler + EventBus Protocol + SimpleEventBus
```

> **v2.1 变更**：`pipeline.py`（Context、Stage、Pipeline）已从 Kernel 移出。
> Pipeline/Stage 是 Engine/Analytics 的内部编排模式，不是跨层抽象。
> Kernel 只保留真正跨层共享的协议：Clock、DataProvider、EventBus。
> 详见审查文档 Issue #1。

**关键约束：kernel 零实现（除 SimulatedClock、RealtimeClock、SimpleEventBus 这些必要的薄实现）。**

### 4.1 Clock 抽象

```python
class Clock(Protocol):
    """统一时间模型 —— 回测返回模拟时间，实盘返回真实时间"""
    @property
    def now(self) -> datetime: ...
    @property
    def today(self) -> date: ...
    def advance_to(self, target: datetime) -> None: ...

class SimulatedClock:
    """回测时钟：由回测引擎驱动时间前进"""
    def __init__(self, start: datetime): self._current = start
    @property
    def now(self) -> datetime: return self._current
    def advance_to(self, target: datetime) -> None:
        assert target >= self._current; self._current = target

class RealtimeClock:
    """实盘时钟：直接使用系统时间"""
    @property
    def now(self) -> datetime: return datetime.now(tz=UTC)
    def advance_to(self, target: datetime) -> None:
        raise RuntimeError("RealtimeClock cannot be advanced")
```

### 4.2 DataProvider 抽象

```python
@dataclass(frozen=True)
class BarQuery:
    instruments: Sequence[InstrumentId]
    start: date; end: date
    frequency: str  # "daily" | "weekly" | "monthly" | "minute"
    adj: str        # "raw" | "qfq" | "hfq"

@dataclass(frozen=True)
class InstrumentQuery:
    asset_class: AssetClass | None
    exchange: Exchange | None
    universe: str | None

class DataProvider(Protocol):
    """统一数据访问模型 —— 所有平面通过此协议获取数据"""
    def get_bars(self, query: BarQuery) -> pl.DataFrame: ...
    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame: ...
    def get_schedule(self, exchange: Exchange, start: date, end: date) -> TradeSchedule: ...
    def get_factor(self, name: str, instruments: Sequence[InstrumentId],
                   start: date, end: date) -> pl.DataFrame: ...
```

### 4.3 ~~Pipeline 抽象~~（已移至 Engine/Analytics 内部）

> **v2.1 变更**：Pipeline/Stage/Context 从 Kernel 移出，理由：
> 1. Pipeline 的实际消费者只有 Engine 和 Analytics，不是真正的跨层抽象
> 2. Kernel 零外部依赖约束导致 `AnyFrame = Any`、`process(data: Any) -> Any`，类型安全为零
> 3. 移出后可直接使用 `pl.DataFrame` 强类型化 Stage 间数据契约
>
> 各平面的 Pipeline 定义见 Section 6（Engine Orchestrator）和 Section 7（Analytics）。

### 4.4 DomainEvent 基础协议

```python
@dataclass(frozen=True)
class DomainEvent:
    event_type: str; timestamp: datetime; payload: dict[str, Any]

EventHandler = Callable[[DomainEvent], None]

class EventBus(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: str, handler: EventHandler) -> None: ...

class SimpleEventBus:
    """进程内同步事件分发"""
    def __init__(self): self._handlers: dict[str, list[EventHandler]] = {}
    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.event_type, []): handler(event)
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
```

---

## 5. Data 平面 — 统一数据层

```text
data/
  models/           # 数据模型（所有子域共享）
    common.py       # 通用字段、基础类型
    enums.py        # 数据相关枚举
    market.py       # 行情相关模型（bars, quotes, ticks）
    metadata.py     # 元数据相关模型（instrument, calendar, universe）
    ingestion.py    # 摄取相关模型
    factors.py      # 因子相关模型
    ...
  sources/          # 外部 provider ACL
    base.py         # DataSource 协议
    tushare/        # Tushare provider
    fred/           # FRED provider
    tdx/            # 通达信 provider
    schemas/        # SourceSchema 定义
    normalization/  # 标准化逻辑
  storage/          # 内部持久化（CQRS reader/writer）
    base/           # Store 基类 + CQRS 基础设施
    market/         # 行情存储
    metadata/       # 元数据存储
    factors/        # 因子存储
    fundamental/    # 基本面存储
    macro/          # 宏观数据存储
    capital/        # 资金数据存储
    runtime/        # 运行时存储（SQLite）
    schemas/        # StoreSchema 定义
  query/            # 面向消费者的查询契约 + DataProvider 实现
    contracts.py    # BarQuery, InstrumentQuery 等
    metadata.py     # 元数据查询（instrument, calendar, universe）
    market.py       # 行情查询（bars, adj, PIT）
    provider.py     # DataProviderAdapter（实现 kernel.DataProvider Protocol）
  quality/          # 数据质量检查（4 级 checker）
  ingestion/        # 摄取领域逻辑（校验、identity 统一、schema 转换、写入）
```

### 5.1 数据流

```text
外部数据 → sources（标准化 SourceSchema）
  → ingestion（DQ + identity 统一 → StoreSchema）
  → storage（持久化）
  → query（面向消费者的 DataProvider）
```

### 5.2 关键设计决策

- **metadata/marketdata 在 query 层内部组织**，不再独立为 package
- **query 层实现 DataProvider 协议**：统一 `DataProviderAdapter`（组合 MarketService + MetadataService + DerivedQueryService）
- **回测/实盘数据获取无差异**：差异在编排行为（Clock、Orchestrator），不在数据获取。如需缓存，用 composition 而非类继承
- **sources 和 storage 通过 ingestion 连接**，不直接依赖
- **data.ingestion = 领域关注点**（数据变换、校验、写入）；**app.ingestion = 过程关注点**（调度、重试）

> **v2.1 变更**：原设计中的 `BacktestProvider` + `LiveProvider`（逐行代码复制）合并为单一 `DataProviderAdapter`。
> 回测/实盘差异通过构造参数表达，不通过继承。
> 详见审查文档 Issue #4。

---

## 6. Engine 平面 — Orchestrator 驱动的交易引擎

> **v2.1 变更**：Engine 编排模型从线性 Pipeline 改为 TradingOrchestrator。
> 交易引擎是命令式的（读状态 → 决策 → 变更状态 → 读新状态），不是纯函数链。
> 详见审查文档 Issue #2。

```text
engine/
  orchestrator/     # 引擎编排核心（v2.1 新增）
    context.py      # EngineContext（clock + provider + events + metadata）
    stage.py        # Stage Protocol（强类型，直接用 pl.DataFrame）
    pipeline.py     # Pipeline（用于 Analytics 风格的纯函数子链）
    orchestrator.py # TradingOrchestrator（每日循环编排器）
  alpha/            # 策略/信号生成
    signal.py       # 信号/评分/排名
    selection.py    # 标的选择
    specs.py        # 策略规格定义
    builtins/       # 内建策略 stage
    templates/      # 策略模板
  portfolio/        # 组合构建 + 约束
    allocation.py   # 权重分配
    constraints.py  # 约束检查
    targets.py      # 目标持仓生成
  execution/        # 订单管理 + 执行
    planner.py      # 交易规划（目标 → 订单）
    trade_builder.py # 订单构建
    brokerage.py    # Brokerage Protocol + BacktestBrokerage / LiveBrokerage 实现
    reality/        # 执行模拟（fill, slippage, fee, market, settlement）
  risk/             # 风控
    pre_trade.py    # 盘前风控（gate — 可阻断后续 Stage）
    intraday.py     # 盘中风控
    post_trade.py   # 盘后风控
  accounting/       # 账户/持仓/资金（Brokerage owner 模式）
    account.py      # Account（可变）+ AccountView（frozen 只读快照）
    position.py     # Position
    cash.py         # CashBook
    order_book.py   # OrderBook + OrderBookReadOnly
    fills.py        # Fill 处理
  backtest/         # 回测引擎
    engine.py       # 回测主循环（TradingOrchestrator 的回测实现）
    data_feed.py    # 数据馈送（DataProvider 适配）
    statistics.py   # 统计计算
    audit/          # 审计追踪
```

### 6.1 状态管理 — Brokerage Owner 模型

> **v2.1 新增**：基于审查对现有代码的分析，确认 Brokerage owner 模式是正确的状态管理方案。

```text
TradingOrchestrator
    ├── 持有 Brokerage（状态所有者）
    │     ├── Account（可变: positions dict + CashBook 引用替换）
    │     │     └── get_view() → AccountView（frozen 只读快照）
    │     ├── place_order(order) → OrderBook 变更
    │     └── process_pending(input) → Account.apply_fill() → 新 AccountView
    │
    └── 每日循环中生成 AccountView 注入各 Stage（只读消费）
```

**模式特征**：
1. **状态所有者单一** — Brokerage 拥有 Account，其他组件只拿 AccountView
2. **读写分离彻底** — AccountView frozen + MappingProxyType 包装 positions
3. **变更路径唯一** — 只通过 Brokerage.place_order() + process_pending()

**Brokerage Protocol**（Engine 内部定义，Phase 2 实现）：
```python
class Brokerage(Protocol):
    """经纪商抽象 — 回测/实盘各有实现。"""
    def get_account(self) -> AccountView: ...
    def place_order(self, order: Order) -> None: ...
    def process_pending(self, input: ProcessInput) -> tuple[FillEvent, ...]: ...
    def cancel_order(self, order_id: str) -> None: ...
```

### 6.2 TradingOrchestrator — 每日循环编排

> **v2.1 变更**：替代原来的线性 Pipeline 设计。

TradingOrchestrator 是命令式编排器，不是纯函数 Pipeline。每日循环流程：

```text
for each trading_day:
    1. 获取数据切片（DataFeed / DataProvider）
    2. 获取账户快照（Brokerage.get_account → AccountView）
    3. PostTrade 风控扫描（只读快照 → 可能锁定标的）
    4. [调仓日] 策略 Stage 链执行（AlphaStage → PortfolioStage）
    5. [调仓日] ExecutionPlanner（目标持仓 + 账户快照 → 订单列表）
    6. [调仓日] PreTrade 校验循环（逐单 gate，可阻断/resize）
    7. [调仓日] Brokerage.place_order（提交通过校验的订单）
    8. Brokerage.process_pending（处理成交 → Account 状态突变）
    9. 审计记录（account_view + fills → AuditCollector）
```

**与线性 Pipeline 的关键差异**：
- **条件分支**：步骤 3（PostTrade）可锁定标的，步骤 6（PreTrade）可阻断订单
- **状态突变**：步骤 7-8 改变 Account 状态，步骤 2 在下一交易日读取新状态
- **非每日执行**：步骤 4-7 仅在调仓日执行（daily/weekly/monthly）
- **反馈回路**：步骤 8 的成交结果影响下一交易日的步骤 2

**Stage 间数据契约**（强类型，在 Engine 内部定义）：

```python
@dataclass(frozen=True)
class AlphaOutput:
    signals: pl.DataFrame        # instrument_id, score, rank

@dataclass(frozen=True)
class PortfolioOutput:
    targets: pl.DataFrame        # instrument_id, target_weight
```

策略 Stage 链（步骤 4）内部可以用 Engine 内部的 Pipeline 纯函数组合，
但整个每日循环由 Orchestrator 编排。

### 6.3 双通道数据流

| 数据类型 | 获取方式 | 原因 |
|---------|---------|------|
| 策略信号 → 组合目标 | **显式输入**（AlphaOutput） | 自然流转 |
| 市场行情 DataFrame | **DataProvider**（on-demand） | 数据量大，不复制 |
| 标的基本信息 | **DataProvider** | 查询性质，按需获取 |
| 交易规则/费率 | **DataProvider** | 查询性质 |
| 策略规格/约束条件 | **显式输入** | 天然是输入 |

### 6.4 与现有 core 的映射

| 现有 core 子域 | 目标位置 | 变化 | Phase |
|---------------|---------|------|-------|
| `strategy/` | `engine.alpha/` | 重命名 | 2e |
| `portfolio/` | `engine.portfolio/` | 直接迁移（改名后） | 2c |
| `execution/` | `engine.execution/` | 直接迁移（改名后） | 2c |
| `backtest/` | `engine.backtest/` | 直接迁移（改名后） | 2c |
| `accounting/` | `engine.accounting/` | 直接迁移（改名后） | 2c |
| `quality/` | `data.quality/` | 移到 data 平面 | 2a |
| `engine/expression/` | `analytics.expression/` | 移到 analytics 平面 | 2b |
| `engine/factors/` | `analytics.factors/` | 移到 analytics 平面 | 2b |
| `engine/evaluation/` | `analytics.evaluation/` | 移到 analytics 平面 | 2b |
| `engine/materialization/` | `analytics.materialization/` | 移到 analytics 平面 | 2b |
| `engine/research.py` | `analytics.research/` | 移到 analytics 平面 | 2b |
| `engine/publication_safety.py` | `analytics.publication_safety/` | 提升为子包 | 2b |
| `engine/specs.py` | `analytics/specs.py` | 移到 analytics 平面 | 2b |
| `engine/compile_cache.py` | `analytics/compile_cache.py` | 移到 analytics 顶层（基础设施） | 2b |
| `engine/errors.py` | 删除 | 纯 re-export shim，指向 datahub.errors | 2b |

### 6.5 Engine 域事件

```python
class OrderSubmitted(DomainEvent): ...    # {order_id, instrument_id, side, quantity, price}
class OrderFilled(DomainEvent): ...       # {order_id, fill_price, fill_quantity, commission}
class OrderCanceled(DomainEvent): ...     # {order_id, reason}
class PositionChanged(DomainEvent): ...   # {instrument_id, old_qty, new_qty}
class RiskGuardTriggered(DomainEvent): ... # {guard_name, severity, details}
```

---

## 7. Analytics 平面 — 研究 + 评估 + 因子计算

```text
analytics/
  expression/           # 表达式编译器（纯计算链，零 I/O）
    lexer.py            # 词法分析
    parser.py           # 语法分析（Pratt parser）
    ast.py              # AST 节点定义
    analyzer.py         # 语义分析
    codegen.py          # Polars 代码生成
    compiler.py         # 编译器入口（tokenize → parse → analyze → codegen）
    registry.py         # 算子规格注册
    diagnostics.py      # 编译诊断
  factors/              # 因子定义（纯数据声明）
    spec.py             # FactorSpec, FactorContext
    primitives.py       # 基础特征（returns_1, prev_close）
    technical.py        # 技术因子（MA, RSI, MACD）
    fundamental.py      # 基本面因子（PE, PB）
    alpha.py            # 策略因子（momentum）
  evaluation/           # 绩效评估 + 归因（纯 Polars 向量化计算）
    evaluator.py        # 评估编排器
    report.py           # 评估报告模型（frozen dataclass）
    metrics/            # 指标计算
      _math.py          # 共享数值工具
      ic.py             # IC 指标（pearson, rank, decay, autocorrelation）
      factor_analysis.py # 因子分析（exposure, orthogonalize, Fama-MacBeth）
      portfolio.py      # 组合分析（quantile, long-short, turnover）
      tail_risk.py      # 尾部风险（MaxDD, VaR, CVaR）
  materialization/      # 衍生数据物化模型
    contracts.py        # 编译契约（Analysis, CompiledDerivedExpression）
    models.py           # 运行时状态（DerivedRun, DerivedVersion, DerivedState）
    planner.py          # 执行计划器
  research/             # 研究数据集
    (from core.engine.research.py)
  publication_safety/   # 发布安全控制
    (from core.engine.publication_safety.py，提升为子包)
  compile_cache.py      # 编译缓存基础设施（L1 LRU + L2 SQLite）
  specs.py              # 衍生规格（DerivedSpec, TimeSpec, ExecutionPolicy）
```

### 7.1 Analytics 设计约束

- **纯计算包**：不依赖 DataProvider，所有数据由调用方（app 层）传入
- **零 I/O 子包**：expression/ 和 evaluation/ 内部纯函数，无外部 I/O
- **compile_cache.py 是唯一引入 I/O 的模块**（SQLite + cachebox），放在顶层而非 expression/ 内部
- **依赖**：`analytics → kernel + polars + cachebox`
- **DataFrame 是一等载体**：所有计算函数接受 `pl.DataFrame`，返回 `pl.DataFrame` 或标量

### 7.2 从 datahub 迁入的代码

| 模块 | 来源 | 迁入原因 |
|------|------|---------|
| `forward_return_service.py` | `datahub.services.forward_return_service` | 计算逻辑（`close[t+T]/close[t]-1`），不是数据 CRUD |

---

## 8. Application 层 — Use Case 编排

```text
app/
  # ── Query（只读，薄 passthrough + DTO 转换）──
  market/           # 行情查询（query_bars, query_instruments）
  metadata/         # 元数据查询（query_calendar, query_universe）
  sources/          # 数据源诊断（list_sources, preview_data, diagnostics）
  analytics/        # 因子/评估查询（从 port/services/derived/ 的 facade 迁入）

  # ── Command（单次写）──
  ingestion/        # 数据写入（write_batch）
  strategy/         # 策略配置（save_strategy）

  # ── Process（长流程，多步骤，可重试/补偿）──
  backtest/         # 运行回测（从 port/services/strategy/ 迁入）
  live/             # 运行实时/实盘会话
  ingestion/        # 完整摄取流程（run_ingestion, backfill）
  materialization/  # 因子物化（从 port/services/derived/ 的 orchestrator 迁入）

  # ── 共享 ──
  shared/           # DTO（use case request/response）、builders（纯装配）
  registry/         # Dishka DI 容器（Composition Root）
```

## 8b. Interfaces 层 — 适配器

```text
interfaces/
  http/             # FastAPI 适配器（从 port/api/routes/ 迁入）
    routes/         # 10 个路由模块（market, metadata, capital, ...）
    middleware.py    # 中间件
    errors.py        # 错误处理
  cli/              # Typer CLI 适配器（从 port/cli/ 迁入）
    commands/       # 5 个命令组（init, ingest, backfill, query, strategy）
  jobs/             # Prefect 适配器（从 port/jobs/ 迁入）
    flows/          # 17 个 Prefect flows
    tasks/          # 3 个 task 工厂
  config/           # 接口层配置（从 port/config/ 迁入）
  testing.py        # 测试工具
```

### 8.1 interfaces 永远只调 app

```text
interfaces → app → data | engine | analytics
```

app 作为统一的反腐败层。即使是简单查询也通过 app，确保依赖方向一致。

### 8.2 app vs 各平面的职责划分

| 类型 | app 做什么 | 平面做什么 |
|------|-----------|-----------|
| Query | 调用 data.query，转换结果为 DTO | 执行查询逻辑 |
| Command | 编排单次写入 | 执行写入逻辑 |
| Process | 构建 Orchestrator、注入 Provider、管理重试 | 各 Stage 执行业务逻辑 |

### 8.4 app 内部互斥规则

> 源自 v3 设计审查，可用 importlinter 强制执行。

```text
Query    -X-> Command / Process    # Query 只读，不得触发写操作
Command  -X-> Query / Process      # Command 只做单次写，不得查询或编排
Process  ->  Query / Command        # Process 可以协调 Query 和 Command
builders -X-> query / write         # builders 只接收已获取数据并组装 contract
```

### 8.3 DI 容器 — Composition Root 模式

**各包暴露 Provider（组件自治） + app 做唯一组装入口**：

```text
packages/data/src/ditto_datahub/di.py       → get_providers() → tuple[Provider, ...]
packages/engine/src/ditto_engine/di.py      → get_providers() → tuple[Provider, ...]
packages/analytics/src/ditto_analytics/di.py → get_providers() → tuple[Provider, ...]

apps/app/src/ditto_app/registry/
  container.py  ← 唯一入口，调用各包 get_providers() 组装
```

```python
# apps/app/src/ditto_app/registry/container.py
def make_app_container() -> Container:
    return make_container(
        *get_infra_providers(),
        *ditto_datahub.di.get_providers(),
        *ditto_engine.di.get_providers(),
        *ditto_analytics.di.get_providers(),
        *get_app_providers(),
    )
```

**迁移节奏**：Phase 4 中逐步把 `port/registry/datahub/*` 推入各包的 `di.py`，
最终 app 只调用各包的 `get_providers()`，不深入包内部。

---

## 9. 依赖规则

### 顶层依赖矩阵

```text
interfaces → app
app         → data, engine, analytics
engine      → kernel
analytics   → kernel
data        → kernel
infra       → none
kernel      → none
```

### 禁止依赖

```text
engine      -X-> data           # 通过 DataProvider Protocol 解耦
engine      -X-> app
analytics   -X-> data           # 数据由 app 层传入，analytics 不主动获取
analytics   -X-> app
analytics   -X-> engine
interfaces  -X-> data           # 通过 app 解耦
interfaces  -X-> engine
interfaces  -X-> analytics
data        -X-> engine
data        -X-> analytics
data.sources -X-> data.storage
data.storage -X-> data.query

### app 内部约束

```text
app.*Query    -X-> app.*Command / app.*Process
app.*Command  -X-> app.*Query / app.*Process
app.*Process  ->  app.*Query / app.*Command（允许）
app.builders  -X-> query / write（只装配，不查询，不写入）
```

app 层在运行时通过 DI 注入具体实现。

---

## 10. DomainEvent 最小设计

### 事件定义归属

- **kernel**：`DomainEvent` 基类 + `EventBus` Protocol + `SimpleEventBus`
- **engine**：`OrderSubmitted`, `OrderFilled`, `OrderCanceled`, `PositionChanged`, `RiskGuardTriggered`
- **data**：`DataIngested`, `QualityCheckCompleted`

### 消费场景分层

| 场景 | 复杂度 | 实现 |
|------|-------|------|
| 回测审计追踪 | 低 | `AuditTrail` 收集事件 |
| 实盘通知 | 中 | handler 调用 NotificationManager |
| 跨域投影 | 高 | 暂不实现（需异步分发） |

### 不做的事

- 不做异步事件分发、不持久化事件、不跨进程、不引入消息队列

---

## 11. 迁移策略

### 总体原则

- 每个 Phase 独立可验证（`pixi run -e dev check` 全通过）
- 先加后改再删（新增抽象 → 迁移代码 → 删除旧代码）
- importlinter 先宽后严

### Phase 0：Kernel 扩展（✅ 已完成）

| PR | 内容 | 状态 |
|----|------|------|
| 0a | Clock Protocol + SimulatedClock + RealtimeClock | ✅ |
| 0b | DataProvider Protocol + BarQuery + InstrumentQuery | ✅ |
| 0c | ~~Stage/Pipeline Protocol + Context~~ | ❌ 已移除（移至 Engine 内部） |
| 0d | DomainEvent + EventHandler + SimpleEventBus | ✅ |

**产出**：`packages/kernel/` 新增 3 个协议文件（pipeline.py 待迁移出）

### Phase 0.5：Kernel Pipeline 移出 + DataProvider 清理（v2.1 新增，~3 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 0.5a | 将 `kernel/pipeline.py`（Context、Stage、Pipeline）移至 `ditto_core.pipeline` | 低 |
| 0.5b | 合并 BacktestProvider/LiveProvider 为单一 `DataProviderAdapter` | 低 |
| 0.5c | 更新 kernel `__init__.py`，移除 Pipeline/Context/Stage 导出 | 低 |

**验证**：`pixi run -e dev check` 全通过

### Phase 1：Data 平面收拢（⚠️ 部分完成，待补充）

| PR | 内容 | 状态 |
|----|------|------|
| 1a | 新建 `datahub/query/` 子模块 + contracts | ✅ |
| 1b | `BacktestProvider` 实现（组合现有 services） | ✅（将被 0.5b 合并替换） |
| 1c | core/data_feed.py 消费 DataProvider | ⚠️ ProviderBackedDataFeed 并行新增，旧路径未清理 |
| 1d | ~~`LiveProvider` + 缓存~~ | ❌ 已废弃（合并入 0.5b） |

**待补充**：
- [ ] 清理 `ParquetDataFeed`（旧路径），统一为 `ProviderBackedDataFeed`
- [ ] Core 依赖收敛：`core/CLAUDE.md` 从 `core → kernel, datahub, infra` 改为 `core → kernel only`
- [ ] DI 注册验证：`port/registry/` 中 DataProviderAdapter 注册
- [ ] Golden test：验证回测流程行为不变

### Phase 2：Engine 平面成型（~8 PR，Strangler 模式）

> **v2.1 变更**：先迁子域，后改名。Phase 2b 采用 Strangler 模式（先适配，后迁目录）。

| PR | 内容 | 风险 | 说明 |
|----|------|------|------|
| 2a | `core.quality` → `datahub.quality` | 低 | ~15 文件 import 改动 |
| 2b-1 | 创建 `packages/analytics/` 空包 + pyproject.toml | 低 | 新包骨架 |
| 2b-2 | 在 `ditto_core.engine.__init__` 中建立 re-export 兼容层 → `ditto_analytics` | 低 | Strangler 适配：旧路径不中断 |
| 2b-3 | 逐步迁移 import：`ditto_core.engine.xxx` → `ditto_analytics.xxx` | 中 | 33 文件引用迁移 |
| 2b-4 | 删除 `ditto_core.engine/` 和兼容层 | 低 | 所有引用迁移完后清理 |
| 2c | `core` → `engine` 包名重命名 | 中 | 此时 core 只剩交易引擎 4 子域 |
| 2d | engine 内部新增 `orchestrator/`（context, stage, pipeline） | 低 | 从 kernel.pipeline 移入 + 强类型化 |
| 2e | engine 内部子域重命名（strategy → alpha） | 低 | 内部重命名 |
| 2f | 定义 Brokerage Protocol + 整理 accounting | 中 | Engine 内部 Protocol |
| 2g | `datahub.forward_return_service` → `analytics` | 低 | 计算逻辑归位 |

**Phase 2b 细节**（analytics 包迁入清单）：

| 源文件 | 目标 | 说明 |
|--------|------|------|
| `core.engine.expression/` (8 files) | `analytics.expression/` | 纯计算链 |
| `core.engine.factors/` (6 files) | `analytics.factors/` | 因子定义 |
| `core.engine.evaluation/` (8 files) | `analytics.evaluation/` | 评估指标 |
| `core.engine.materialization/` (4 files) | `analytics.materialization/` | 物化模型 |
| `core.engine.research.py` | `analytics/research.py` | 研究模型 |
| `core.engine.publication_safety.py` | `analytics/publication_safety/__init__.py` | 提升为子包 |
| `core.engine.specs.py` | `analytics/specs.py` | 衍生规格 |
| `core.engine.compile_cache.py` | `analytics/compile_cache.py` | 顶层基础设施 |
| `core.engine.errors.py` | 删除 | 纯 re-export shim |

**验证**：回测、策略、因子计算、评估功能不受影响

### Phase 3：Analytics 平面收尾（~3 PR）

> Phase 2b 创建了 analytics 包并迁入代码，Phase 3 做收尾。

| PR | 内容 | 风险 |
|----|------|------|
| 3a | analytics 包内部整理（__init__.py 重导出、di.py Provider 注册） | 低 |
| 3b | datahub 错位模型清理（portfolio.py、trading.py 评估废弃或删除） | 低 |
| 3c | analytics 内部纯函数 Pipeline（如需链式因子计算） | 低 |

**验证**：`pixi run -e dev check` 全通过 + 因子/评估集成测试

### Phase 4：Application 层提炼（port → app + interfaces，~7 PR）

> **v2.1 变更**：api 改名 interfaces；DI 采用 Composition Root 模式。

| PR | 内容 | 风险 | 说明 |
|----|------|------|------|
| 4a | app 包骨架 + Composition Root 容器 | 高 | DI 是全系统神经中枢 |
| 4b | port/services/ → app/ use case 迁移 | 中 | ingestion + strategy |
| 4c | port/services/derived/ 拆分 → app/analytics/ + app/materialization/ | 中 | facade → analytics，orchestrator → materialization |
| 4d | interfaces 包骨架 + HTTP routes 迁入 | 中 | 从 port/api/routes/ |
| 4e | interfaces/cli/ + interfaces/jobs/ 迁入 | 中 | 从 port/cli/ + port/jobs/ |
| 4f | port/models/ → app/shared/ DTO 迁入 | 低 | request/response 模型 |
| 4g | 删除旧 port 包 | 低 | 所有引用已迁移 |

**DI 迁移策略**：
1. 先在 app/registry/container.py 建立新的 Composition Root
2. 逐步把 port/registry/datahub/*、port/registry/core/* 推入各包的 di.py
3. 最终 port/registry/ 只剩 app 自身 Provider

**验证**：所有 HTTP 端点 + CLI 命令 + Prefect Jobs 功能不变

### Phase 5：固化（~4 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 5a | 更新 importlinter 为最终规则 | 低 |
| 5b | 更新所有 CLAUDE.md | 低 |
| 5c | 更新根 CLAUDE.md 架构描述 | 低 |
| 5d | 清理废弃代码和临时兼容层 | 低 |

**验证**：`pixi run -e dev ci` + `pixi run -e dev arch-check`

### 迁移总览

| Phase | PR 数 | 风险等级 | 依赖 | 状态 |
|-------|-------|---------|------|------|
| Phase 0 | 3 | 低 | 无 | ✅ 已完成 |
| Phase 0.5 | 3 | 低 | Phase 0 | 待开始 |
| Phase 1 补完 | 2-3 | 低-中 | Phase 0 | ⚠️ 部分完成 |
| Phase 2 | 8 | 中 | Phase 0.5, 1 | 待开始 |
| Phase 3 | 3 | 低 | Phase 2 | 待开始 |
| Phase 4 | 7 | 中-高 | Phase 2, 3 | 待开始 |
| Phase 5 | 4 | 低 | Phase 4 | 待开始 |
| **总计** | **~30-31 PR** | | | |

### 目标模块结构（最终态）

```text
packages/
  kernel/            # Clock + DataProvider + EventBus（14 符号）
  infra/             # 基础设施（配置、日志、存储引擎、缓存、并发、通知）
  data/              # 数据平面（models + sources + storage + query + quality + ingestion）
  engine/            # 交易引擎（orchestrator + alpha + portfolio + execution + risk + accounting + backtest）
  analytics/         # 分析平面（expression + factors + evaluation + materialization + research）

apps/
  app/               # Use Case 编排（Query + Command + Process + registry）
  interfaces/        # 适配器（HTTP + CLI + Prefect Jobs）
  web/               # Web 前端（保持不变）
```

---

## 12. 验证策略

### 每个 PR 必须通过

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

### 每个 Phase 结束后额外验证

- Phase 0：新抽象有完整单元测试
- Phase 1：现有回测流程行为不变（golden test）
- Phase 2：回测 + 策略功能完整可用
- Phase 3：因子计算 + 评估功能完整可用
- Phase 4：所有 HTTP 端点 + CLI 命令 + Prefect jobs 功能不变
- Phase 5：`pixi run -e dev ci` + `pixi run -e dev arch-check`

### 最终验收

- [ ] `pixi run -e dev ci` 全通过
- [ ] `pixi run -e dev arch-check` 全通过
- [ ] 分支覆盖率 ≥ 80%
- [ ] 所有 CLAUDE.md 已更新
- [ ] importlinter 反映最终依赖规则

### 审计证据验证（源自 v3 审查）

每次回测至少应可重建以下四类证据：

| 证据类型 | 当前覆盖 | Phase 2 验收要求 |
|---------|---------|----------------|
| **Input Evidence** — 数据集/规则/参数版本 | ⚠️ RunManifest 部分覆盖 | RunManifest 补全：规则版本、费率版本、数据版本引用 |
| **Decision Evidence** — 信号/目标/风控调整 | ⚠️ EngineLoop 部分记录 | AuditCollector 增加目标持仓快照 |
| **Execution Evidence** — 委托/成交/费用/账户变化 | ✅ AuditCollector + TradeBuilder | 确认无回归 |
| **Result Evidence** — report/attribution/artifact URI | ❌ 无系统性覆盖 | BacktestResult 增加 artifact 引用列表 |

---

## 13. 与 2026-03-26 计划的关键差异

| 维度 | 2026-03-26 计划 | 本设计（v2） | v2.1 审查修订 |
|------|----------------|-------------|-------------|
| 组织原则 | 子域优先（纯 DDD） | Hybrid 分层（平面 + Pipeline + DDD） | 平面 + Stage/Orchestrator + DDD |
| 顶层 package 数 | ~10 | 5 + kernel | 不变 |
| kernel 范围 | 极小类型仓库 | 类型 + 系统级 Protocol（含 Pipeline） | **Pipeline 移出**，只留 Clock/DataProvider/EventBus |
| Engine 编排 | 未设计 | 线性 Pipeline | **TradingOrchestrator**（命令式编排） |
| 状态管理 | 未设计 | 未设计 | **Brokerage owner 模式**（Engine 内部） |
| 实时流 | 未设计 | 未设计 | Protocol 继承 + 实现扩展演进 |
| DataProvider 实现 | 未设计 | BacktestProvider + LiveProvider | **单一 DataProviderAdapter** |
| Phase 2 顺序 | — | 先改名后迁移 | **先迁移子域后改名** |

### 保留的 v1/v2 设计决策

- kernel 保持极小（不采纳 rich kernel）
- sources/datahub 分离方向正确（在 data 平面内部分离）
- application 是唯一跨域编排者（app 层）
- DataFrame 是一等业务载体
- Input Contract 归属行为域
- builders.py 纯装配
- 渐进式迁移（非 Big Bang）

### v3 设计审查采纳记录

审查对象：`docs/plans/2026-03-31-ditto-future-architecture-design.md`

| v3 建议 | 采纳 | 说明 |
|---------|------|------|
| 唯一语义 owner 原则 | ✅ 原则 | 写入架构纪律，但 data 平面保持统一不拆 metadata/market |
| Runtime Contract 显式化 | ✅ | Snapshot 字段必须对应真实消费点 |
| Query/Command/Process 互斥规则 | ✅ | importlinter 强制执行 |
| 审计证据四分类 | ✅ 部分 | RunManifest 补全 Input Evidence |
| Strangler 迁移模式 | ✅ | Phase 2b 采用适配层迁移，不一刀切 |
| 独立 integration ACL 层 | 🔶 Backlog | 等实盘 broker 对接时再独立 |
| CQRS 三形态文档 | 🔶 文档 | data CLAUDE.md 中用此模型解释数据流 |
| 8 个顶层包 | ❌ | 对当前体量过度模块化 |
| 8 种 engine 事件 | ❌ | 事件由需求驱动，不提前枚举 |
| 三级缓存 | ❌ | 过度设计 |
