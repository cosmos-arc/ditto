# Ditto 架构重构设计 v2 — Hybrid 平面架构

**日期**: 2026-03-30
**状态**: 设计完成，待实施
**Supersede**: 本文档 supersede `docs/plans/2026-03-26-full-architecture-refactoring-design.md` 和 `docs/reviews/2026-03-27-architecture-refactoring-final-review.md`

---

## 1. 设计背景与动机

Ditto 之前的架构重构计划（2026-03-26）采用纯 DDD 子域优先策略，将系统拆分为 ~10 个顶层 package。经以业界顶尖量化平台为参照的审视，发现以下问题：

1. **过度偏向 DDD 战术模式** — 计划更像 DDD 教科书应用，而非从量化系统核心需求出发
2. **缺少量化系统核心支柱** — 无 Clock 抽象、无 DataProvider 统一接口、无泛化 Pipeline 模型、无状态机
3. **metadata/marketdata 拆分边界模糊** — 在实践中深度纠缠，硬拆增加边界开销
4. **prepared-input-first 作为铁律过激** — 高频 DataFrame 场景下全量预组装代价需正视
5. **10 个顶层 package 过早模块化** — 对当前体量，边界维护成本可能超过收益

本设计采用 **Hybrid 分层架构**：顶层用平面划分，平面内部用 Pipeline 组织，Pipeline Stage 内部用 DDD 战术模式。

---

## 2. 核心组织原则

| 层次 | 组织原则 | 说明 |
|------|---------|------|
| 顶层模块 | **平面划分**（Data / Engine / Analytics） | 量化系统的三大关注点天然分离 |
| 平面内部 | **Pipeline 组合** | 所有计算都是 stage，统一回测/实盘模型 |
| Stage 内部 | **DDD 战术模式** | Entity、Value Object、Domain Service 在这里才有意义 |

### 五大架构支柱

1. **统一时间模型**（Clock）— 回测/实盘共享同一代码路径，只区别于时钟实现
2. **统一数据访问**（DataProvider）— 所有平面通过 Protocol 获取数据，不直接依赖存储实现
3. **统一计算模型**（Stage/Pipeline）— 策略、组合、执行、风控都是 Pipeline Stage
4. **最小事件契约**（DomainEvent）— 跨平面状态变更通过事件通知，同步进程内分发
5. **双通道数据流** — 主数据流通过 Stage typed contract，辅助数据通过 DataProvider on-demand

---

## 3. 目标模块结构

```text
packages/
  kernel/            # 共享类型 + 系统级核心抽象协议（零实现）
  infra/             # 基础设施（配置、日志、存储引擎、并发）
  data/              # 数据平面：统一数据层
  engine/            # 控制平面：交易引擎
  analytics/         # 分析平面：研究 + 评估

apps/
  app/               # 应用编排层（Query + Command + Process）
  api/               # 接口适配层（HTTP / CLI / Jobs）
  web/               # Web 前端（保持不变）
```

从 ~10 个顶层 package 收敛到 **5 个核心 package + kernel**。

---

## 4. Kernel — 系统级抽象协议层

```text
kernel/
  types.py          # 现有：InstrumentId, TradeDate, Currency
  enums.py          # 现有：AssetClass, Exchange, OrderSide, RunStatus, RiskScope
  clock.py          # 新增：Clock Protocol + SimulatedClock + RealtimeClock
  provider.py       # 新增：DataProvider Protocol + 查询契约
  pipeline.py       # 新增：Stage/Pipeline Protocol + Context
  events.py         # 新增：DomainEvent + EventHandler + EventBus Protocol + SimpleEventBus
```

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

### 4.3 Pipeline 抽象

```python
@dataclass(frozen=True)
class Context:
    """Stage 执行上下文"""
    clock: Clock
    provider: DataProvider
    events: EventBus
    metadata: dict[str, Any]

class Stage(Protocol[TInput, TOutput]):
    """所有计算的统一抽象"""
    @property
    def name(self) -> str: ...
    def process(self, input: TInput, ctx: Context) -> TOutput: ...

class Pipeline(Generic[TInput, TOutput]):
    """Stage 的有序组合（不可变）"""
    def __init__(self, stages: Sequence[Stage]): ...
    def execute(self, input: TInput, ctx: Context) -> TOutput:
        result: Any = input
        for stage in self.stages:
            result = stage.process(result, ctx)
        return result
    def add_stage(self, stage: Stage) -> Pipeline:
        return Pipeline([*self.stages, stage])
```

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
    provider.py     # BacktestProvider, LiveProvider（实现 DataProvider）
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
- **query 层实现 DataProvider 协议**：`BacktestProvider` 和 `LiveProvider`
- **sources 和 storage 通过 ingestion 连接**，不直接依赖
- **data.ingestion = 领域关注点**（数据变换、校验、写入）；**app.ingestion = 过程关注点**（调度、重试）

---

## 6. Engine 平面 — Pipeline 驱动的交易引擎

```text
engine/
  alpha/            # 策略/信号生成
    stage.py        # AlphaStage
    signal.py       # 信号/评分/排名
    selection.py    # 标的选择
    specs.py        # 策略规格定义
    builtins/       # 内建策略 stage
    templates/      # 策略模板
  portfolio/        # 组合构建 + 约束
    stage.py        # PortfolioStage
    allocation.py   # 权重分配
    constraints.py  # 约束检查
    targets.py      # 目标持仓生成
  execution/        # 订单管理 + 执行
    stage.py        # ExecutionStage
    planner.py      # 交易规划（目标 → 订单）
    trade_builder.py # 订单构建
    brokerage.py    # Brokerage 抽象
    reality/        # 执行模拟（fill, slippage, fee, market, settlement）
  risk/             # 风控 pipeline
    stage.py        # RiskStage
    pre_trade.py    # 盘前风控
    intraday.py     # 盘中风控
    post_trade.py   # 盘后风控
  accounting/       # 账户/持仓/资金状态机
    account.py      # Account 聚合根
    position.py     # Position
    cash.py         # CashBook
    order_book.py   # OrderBook
    fills.py        # Fill 处理
  backtest/         # 回测引擎核心循环
    engine.py       # 回测主循环（驱动 Clock + Pipeline）
    data_feed.py    # 数据馈送（DataProvider 适配）
    statistics.py   # 统计计算
    audit/          # 审计追踪
```

### 6.1 TradingPipeline

```python
# Stage 间数据契约
@dataclass(frozen=True)
class AlphaOutput:
    signals: pl.DataFrame        # instrument_id, score, rank

@dataclass(frozen=True)
class PortfolioOutput:
    targets: pl.DataFrame        # instrument_id, target_weight

@dataclass(frozen=True)
class ExecutionOutput:
    orders: Sequence[Order]

# Pipeline 组合
trading_pipeline = Pipeline([
    AlphaStage(spec),            # StrategyInputBundle → AlphaOutput
    PortfolioStage(constraints), # AlphaOutput → PortfolioOutput
    RiskStage(guards),           # PortfolioOutput → PortfolioOutput (approved)
    ExecutionStage(brokerage),   # PortfolioOutput → ExecutionOutput
])

# 运行
ctx = Context(clock=simulated_clock, provider=backtest_provider, events=event_bus)
result = trading_pipeline.execute(StrategyInputBundle(universe=target_universe), ctx)
```

### 6.2 双通道数据流

| 数据类型 | 获取方式 | 原因 |
|---------|---------|------|
| 策略信号 → 组合目标 | **显式输入**（AlphaOutput） | 自然流转 |
| 市场行情 DataFrame | **DataProvider**（on-demand） | 数据量大，不复制 |
| 标的基本信息 | **DataProvider** | 查询性质，按需获取 |
| 交易规则/费率 | **DataProvider** | 查询性质 |
| 策略规格/约束条件 | **显式输入** | 天然是输入 |

### 6.3 与现有 core 的映射

| 现有 core 子域 | 目标位置 | 变化 |
|---------------|---------|------|
| `strategy/` | `engine.alpha/` | 重命名 |
| `portfolio/` | `engine.portfolio/` | 直接迁移 |
| `execution/` | `engine.execution/` | 直接迁移 |
| `backtest/` | `engine.backtest/` | 直接迁移 |
| `accounting/` | `engine.accounting/` | 直接迁移 |
| `quality/` | `data.quality/` | 移到 data 平面 |
| `engine/expression/` | `analytics.expression/` | 移到 analytics 平面 |

### 6.4 Engine 域事件

```python
class OrderSubmitted(DomainEvent): ...    # {order_id, instrument_id, side, quantity, price}
class OrderFilled(DomainEvent): ...       # {order_id, fill_price, fill_quantity, commission}
class OrderCanceled(DomainEvent): ...     # {order_id, reason}
class PositionChanged(DomainEvent): ...   # {instrument_id, old_qty, new_qty}
class RiskGuardTriggered(DomainEvent): ... # {guard_name, severity, details}
```

---

## 7. Analytics 平面 — 研究 + 评估

```text
analytics/
  expression/       # 表达式编译器（lexer → parser → AST → codegen → compiler）
  factors/          # 因子计算（alpha, fundamental, technical, primitives）
  research/         # 研究数据集构建 + catalog
  evaluation/       # 绩效评估 + 归因（IC, IR, Sharpe, MaxDD 等）
  simulation/       # 蒙特卡洛 + 压力测试
  materialization/  # 因子/衍生数据物化（planner, models, contracts）
```

Analytics 是 DataFrame 的天然主场，不追求实体化建模。

---

## 8. Application 层 — Query + Command + Process

```text
app/
  # ── Query（只读，薄 passthrough + DTO 转换）──
  market/           # 行情查询（query_bars, query_instruments）
  metadata/         # 元数据查询（query_calendar, query_universe）
  sources/          # 数据源诊断（list_sources, preview_data, diagnostics）
  analytics/        # 因子/评估查询

  # ── Command（单次写）──
  ingestion/        # 数据写入（write_batch）
  strategy/         # 策略配置（save_strategy）

  # ── Process（长流程，多步骤，可重试/补偿）──
  backtest/         # 运行回测
  live/             # 运行实时/实盘会话
  ingestion/        # 完整摄取流程（run_ingestion, backfill）
  materialization/  # 因子物化

  # ── 共享 ──
  shared/           # DTO（use case request/response）、builders（纯装配）
  registry/         # Dishka DI 容器
```

### 8.1 api 永远只调 app

```text
api → app → data | engine | analytics
```

app 作为统一的反腐败层。即使是简单查询也通过 app，确保依赖方向一致。

### 8.2 app vs 各平面的职责划分

| 类型 | app 做什么 | 平面做什么 |
|------|-----------|-----------|
| Query | 调用 data.query，转换结果为 API DTO | 执行查询逻辑 |
| Command | 编排单次写入 | 执行写入逻辑 |
| Process | 构建 Pipeline、注入 Provider、管理重试 | 各 Stage 执行业务逻辑 |

---

## 9. 依赖规则

### 顶层依赖矩阵

```text
api       → app
app       → data, engine, analytics
engine    → kernel
analytics → kernel
data      → kernel
infra     → none
kernel    → none
```

### 禁止依赖

```text
engine    -X-> data           # 通过 DataProvider Protocol 解耦
engine    -X-> app
analytics -X-> data           # 通过 DataProvider Protocol 解耦
analytics -X-> app
analytics -X-> engine
api       -X-> data           # 通过 app 解耦
api       -X-> engine
api       -X-> analytics
data      -X-> engine
data      -X-> analytics
data.sources -X-> data.storage
data.storage -X-> data.query
```

### Engine/Analytics 获取数据的方式

```text
data.query.provider.BacktestProvider --implements--> kernel.provider.DataProvider
                                                    ↑
engine.backtest.data_feed           --consumes------┘ (只依赖 Protocol)
analytics.research.dataset          --consumes------┘ (只依赖 Protocol)
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

### Phase 0：Kernel 扩展（纯增量，~4 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 0a | Clock Protocol + SimulatedClock + RealtimeClock | 低 |
| 0b | DataProvider Protocol + BarQuery + InstrumentQuery | 低 |
| 0c | Stage/Pipeline Protocol + Context | 低 |
| 0d | DomainEvent + EventHandler + SimpleEventBus | 低 |

**产出**：`packages/kernel/` 新增 4 个文件 + 测试

### Phase 1：Data 平面收拢（datahub 内部操作，~4 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 1a | 新建 `datahub/query/` 子模块 + contracts | 低 |
| 1b | `BacktestProvider` 实现（组合现有 services） | 低 |
| 1c | core/data_feed.py 改为消费 DataProvider | 中 |
| 1d | `LiveProvider` + 缓存 | 低 |

**验证**：现有回测流程不改行为

### Phase 2：Engine 平面成型（core → engine，~5 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 2a | `core` → `engine` 包名重命名（纯机械） | 中（影响面大） |
| 2b | `core.quality` → `datahub.quality` | 低 |
| 2c | `core.engine.expression` → `analytics` 包 | 中 |
| 2d | engine 内部子域重命名（strategy → alpha） | 低 |
| 2e | 所有 Stage 实现 kernel Stage Protocol | 中 |

**验证**：回测、策略功能不受影响

### Phase 3：Analytics 平面独立（~4 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 3a | analytics 包骨架 + expression 迁入 | 中 |
| 3b | factors 迁入 | 低 |
| 3c | evaluation 迁入 | 低 |
| 3d | research + materialization 从 port 整合 | 中 |

**验证**：因子计算、评估功能不受影响

### Phase 4：Application 层提炼（port → app + api，~6 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 4a | app 包骨架 + registry 迁移 | 中 |
| 4b | Process 类 use case 迁移 | 中 |
| 4c | Query/Command 类 use case 迁移 | 中 |
| 4d | api 包骨架 + HTTP routes 迁移 | 中 |
| 4e | api CLI + Jobs 迁移 | 中 |
| 4f | 删除旧 port 包 | 低 |

**风险**：DI 容器迁移需特别小心

**验证**：所有 API 端点、CLI 命令、Jobs 功能不变

### Phase 5：固化（~4 PR）

| PR | 内容 | 风险 |
|----|------|------|
| 5a | 更新 importlinter 为最终规则 | 低 |
| 5b | 更新所有 CLAUDE.md | 低 |
| 5c | 更新根 CLAUDE.md 架构描述 | 低 |
| 5d | 清理废弃代码和临时兼容层 | 低 |

**验证**：`pixi run -e dev ci` + `pixi run -e dev arch-check`

### 迁移总览

| Phase | PR 数 | 风险等级 | 依赖 |
|-------|-------|---------|------|
| Phase 0 | 4 | 低 | 无 |
| Phase 1 | 4 | 低-中 | Phase 0 |
| Phase 2 | 5 | 中 | Phase 0, 1 |
| Phase 3 | 4 | 中 | Phase 2 |
| Phase 4 | 6 | 中-高 | Phase 2, 3 |
| Phase 5 | 4 | 低 | Phase 4 |
| **总计** | **~27 PR** | | |

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

---

## 13. 与 2026-03-26 计划的关键差异

| 维度 | 2026-03-26 计划 | 本设计（v2） |
|------|----------------|-------------|
| 组织原则 | 子域优先（纯 DDD） | Hybrid 分层（平面 + Pipeline + DDD） |
| 顶层 package 数 | ~10 | 5 + kernel |
| 依赖规则数 | ~45 条 | ~10 条 |
| metadata/marketdata | 独立 package | data 平面 query 层内部组织 |
| 行为域数据访问 | prepared-input-first 铁律 | 双通道：显式输入 + DataProvider on-demand |
| 回测/实盘统一 | 未设计 | Clock + DataProvider + Stage 注入 |
| kernel 范围 | 极小类型仓库 | 类型 + 系统级 Protocol |
| domain event | 未设计 | 最小事件契约 + 同步进程内分发 |
| 迁移方式 | 渐进模块化单体 | 5 Phase + ~27 PR |

### 保留的 v1 设计决策

- kernel 保持极小（不采纳 rich kernel）
- sources/datahub 分离方向正确（在 data 平面内部分离）
- application 是唯一跨域编排者（app 层）
- DataFrame 是一等业务载体
- Input Contract 归属行为域
- builders.py 纯装配
- 渐进式迁移（非 Big Bang）
