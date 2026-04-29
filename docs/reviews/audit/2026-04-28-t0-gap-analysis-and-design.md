# Ditto T0 差距分析与设计方案

> 日期：2026-04-28
> 关联：`2026-04-28-comprehensive-architecture-evaluation.md`
> 目标：从世界级标准出发，识别关键差距并产出可执行的设计方案

---

## 1. T0 评分目标

| 维度 | 当前评分 | T0 目标 | 关键差距 |
|------|---------|---------|---------|
| 架构能力 | A-(7.0) | A+(9.5) | importlinter 模型对齐、Data 包内部治理、Port 归属统一 |
| 工程质量 | B+(7.5) | A(9.0) | 命名一致性、CQRS 纯净度、观测覆盖率、测试金字塔 |
| 业务功能 | D+(3.5) | A-(8.5) | Order 概念、live/backtest 一致、风控、归因 |
| 可演进性 | B+(7.5) | A(9.0) | 插件化、DataPortal、状态机 |
| **综合** | **7.0** | **9.0** | |

---

## 2. 关键差距设计（按优先级排序）

### P1：Order 概念与生命周期（阻塞 live trading）

#### 当前状态

Ditto 的交易流程为 `TargetPortfolio → RebalancePlan → Trade`，直接跳过了 Order 概念。当前 `engine/accounting/order_book.py` 定义了 `OrderType` 和 `OrderStatus` 枚举，但没有 Order 聚合根和状态机。

```
当前: Signal → TargetPortfolio → RebalancePlan → Trade
缺失:                                    Order (submit/ack/fill/cancel)
```

#### T0 参考

| 平台 | Order 状态数 | 关键特征 |
|------|-------------|---------|
| NautilusTrader | 12 | INITIALIZED → PENDING → ACCEPTED → PARTIALLY_FILLED → FILLED → CANCELLED → REJECTED → EXPIRED → TRIGGERED → INVALID → CANCEL_PENDING → MODIFY_PENDING |
| LEAN | 8+ | OrderType (Market/Limit/StopMarket/StopLimit/MarketOnOpen/MarketOnClose) + OrderStatus + OrderEvents |
| FinceptTerminal | ~3 | PtOrder (pending → filled/cancelled)，委托 broker API 管理状态 |

#### 设计方案

**模块位置**：`packages/engine/src/ditto_engine/accounting/`

```python
# engine/accounting/order.py — Order 聚合根
@dataclass(frozen=True)
class Order:
    """Order 聚合根 — 不可变值对象，状态转换产出新实例"""
    order_id: OrderId
    instrument_id: InstrumentId
    side: OrderSide        # BUY / SELL
    order_type: OrderType  # MARKET / LIMIT / STOP_LOSS / STOP_LOSS_LIMIT
    quantity: Decimal
    price: Decimal | None  # None for market orders
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    created_at: datetime | None = None
    updated_at: datetime | None = None

@dataclass(frozen=True)
class OrderId:
    value: str

class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"
```

**状态机**：`engine/accounting/order_state.py`

```python
# crash-only 状态机：无效转换立即异常
class OrderStateMachine:
    """Order 状态转换 — 参考 NautilusTrader crash-only 设计"""

    TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
        OrderStatus.DRAFT: frozenset({OrderStatus.SUBMITTED, OrderStatus.CANCELLED}),
        OrderStatus.SUBMITTED: frozenset({OrderStatus.ACCEPTED, OrderStatus.REJECTED}),
        OrderStatus.ACCEPTED: frozenset({OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCEL_PENDING}),
        OrderStatus.PARTIALLY_FILLED: frozenset({OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCEL_PENDING}),
        OrderStatus.CANCEL_PENDING: frozenset({OrderStatus.CANCELLED}),
    }

    @staticmethod
    def transition(order: Order, target: OrderStatus) -> Order:
        allowed = OrderStateMachine.TRANSITIONS.get(order.status, frozenset())
        if target not in allowed:
            raise StateTransitionError(
                f"Invalid order transition: {order.status} -> {target}"
            )
        return dataclasses.replace(order, status=target, updated_at=utcnow())
```

**OrderGateway Protocol**：`engine/execution/order_gateway.py`

```python
# engine/execution/order_gateway.py — Brokerage 抽象
class OrderGateway(Protocol):
    """Order 执行网关 — 由 SimulatedBrokerage 或 LiveBrokerage 实现"""
    def submit(self, order: Order) -> Order: ...
    def cancel(self, order_id: OrderId) -> Order: ...
    def modify(self, order_id: OrderId, quantity: Decimal | None, price: Decimal | None) -> Order: ...
```

**SimulatedBrokerage**：`engine/backtest/simulated_brokerage.py`

```python
# engine/backtest/simulated_brokerage.py
class SimulatedBrokerage:
    """回测模拟券商 — 实现 OrderGateway Protocol"""

    def __init__(self, fill_model: FillModel, fee_model: FeeModel, slippage_model: SlippageModel):
        self._fill_model = fill_model
        self._fee_model = fee_model
        self._slippage_model = slippage_model

    def submit(self, order: Order) -> Order:
        accepted = OrderStateMachine.transition(order, OrderStatus.ACCEPTED)
        fill_price = self._slippage_model.apply(order)
        fill_qty = self._fill_model.simulate(order, fill_price)
        if fill_qty == order.quantity:
            return OrderStateMachine.transition(accepted, OrderStatus.FILLED)
        return OrderStateMachine.transition(accepted, OrderStatus.PARTIALLY_FILLED)
```

**Pipeline 扩展**：StrategyPipeline 输出从直接生成 Trade 改为：

```
Signal → Portfolio Construction → Order Generation → Execution(Fill) → Trade
```

**影响范围**：
- 新增 3 个文件：`order.py`、`order_state.py`、`order_gateway.py`
- 修改 1 个文件：`engine/accounting/order_book.py`（整合 Order 类型）
- 新增 1 个文件：`engine/backtest/simulated_brokerage.py`
- 修改 `engine/backtest/` 的 TradingLoop 以使用 OrderGateway
- kernel 扩展：`OrderId`、`OrderSide` 放入 `ditto_kernel.order`

**依赖方向**：
```
kernel.order → engine.accounting.order → engine.execution.order_gateway
                                         ↑
engine.backtest.simulated_brokerage ─────┘（实现 Protocol）
```

---

### P2：Backtest/Live 单代码路径

#### 当前状态

仅存在 batch backtest（`engine/backtest/`），TradingLoop Protocol 已定义但仅有回测实现。无 live trading loop。

#### T0 参考

| 平台 | 模式 | 关键设计 |
|------|------|---------|
| NautilusTrader | 单一 NautilusKernel | BacktestEngine / SandboxEngine / LiveEngine 共享策略/风控/组合逻辑 |
| LEAN | IAlgorithm 实例 | Backtesting / Benchmarking / LiveTrading 三种模式运行同一算法 |
| FinceptTerminal | UnifiedTrading | "paper" / "live" 路由，IBroker 抽象 |

#### 设计方案

**EnvironmentContext**：`engine/backtest/context.py` → 重命名为 `engine/context.py`

```python
class EnvironmentContext(StrEnum):
    BACKTEST = "backtest"
    SANDBOX = "sandbox"
    LIVE = "live"
```

**DataFeed Protocol 扩展**：`engine/backtest/data_feed.py` → 提升到 `engine/data_feed.py`

```python
class DataFeed(Protocol):
    """统一数据供给 — 由 SimulatedDataFeed 或 LiveDataFeed 实现"""
    def get_history(self, instrument_id: InstrumentId, bars: int, frequency: str) -> pl.DataFrame: ...
    def get_latest(self, instrument_id: InstrumentId) -> pl.DataFrame: ...

class SimulatedDataFeed:
    """回测数据供给 — 从 Parquet 预加载"""
    def __init__(self, data_provider: DataProvider, start: date, end: date): ...

class LiveDataFeed:
    """实时数据供给 — 预留接口"""
    def __init__(self, data_portal: DataPortal): ...
```

**TradingLoop 重构**：

```python
class TradingLoop(Protocol):
    """统一交易循环 — 零修改切换 backtest/live"""
    context: EnvironmentContext
    data_feed: DataFeed
    brokerage: OrderGateway  # P1 的 OrderGateway
    strategy_pipeline: StrategyPipeline

    def run(self) -> RunResult: ...
```

**影响范围**：
- 新增 `engine/context.py`（EnvironmentContext）
- 提升 `engine/backtest/data_feed.py` → `engine/data_feed.py`
- 新增 `engine/live_data_feed.py`（预留）
- 修改 `engine/backtest/protocol.py` 的 TradingLoop 接口
- kernel 扩展：`EnvironmentContext` 放入 `ditto_kernel`

**依赖方向**：
```
kernel → engine.context → engine.data_feed → engine.backtest.data_feed（实现）
                                     → engine.live_data_feed（实现）
                                     → engine.execution.order_gateway
```

---

### P3：Data 包模块化重组

#### 当前状态

Data 包 339 文件 / 42,138 行（43%），storage 子域占 36%（14,877 行）。import-linter 已通过 10 条子域隔离合约实现内部边界。

#### T0 参考

| 平台 | 策略 | 效果 |
|------|------|------|
| OpenBB | per-datatype Fetcher + TET pipeline | 100+ 数据源，独立扩展 |
| Django | app-based modular architecture | 插件化，独立部署 |
| FinceptTerminal | DataHub pub/sub + topic-based | 解耦数据生产和消费 |

#### 设计方案

**策略选择：保持单包 + 强化内部治理**（不建议拆包）

理由：
1. import-linter 子域隔离已到位（10 条合约）
2. 拆包引入跨包依赖管理复杂度
3. Data 包的复杂度源于 CQRS 样板（storage 占 36%），可通过代码生成缓解

**具体改进**：

**3a. DataCatalog 替代 Dataset StrEnum**

```python
# data/catalog/catalog.py
class DataCatalog:
    """数据集目录 — 替代 Dataset StrEnum 的业务逻辑"""
    def __init__(self, entries: frozenset[DatasetEntry]):
        self._entries = {e.name: e for e in entries}

    def get(self, name: str) -> DatasetEntry: ...
    def list_by_asset_class(self, asset_class: AssetClass) -> list[DatasetEntry]: ...
    def list_by_frequency(self) -> list[DatasetEntry]: ...

@dataclass(frozen=True)
class DatasetEntry:
    name: str
    asset_class: AssetClass
    frequency: Frequency | None
    source: str
    date_schedule: DateSchedule | None
```

**3b. Storage Reader/Writer 薄包装合并**

将 `init_schema()` 从 Reader 提取到 `SchemaManager`：

```python
# data/storage/base/schema_manager.py
class SchemaManager:
    """统一 schema 初始化 — 消除 Reader/Writer 中的 DDL 重复"""
    def init_all_schemas(self, data_root: Path) -> None: ...
```

**3c. helpers.py 拆分**

`app/process/materialization/helpers.py`（503 行）→ 按职责拆分：
- `materialization/date_range_resolver.py`
- `materialization/dependency_resolver.py`
- `materialization/plan_builder.py`

**影响范围**：
- 新增 `data/catalog/` 目录（~3 文件）
- 修改 `data/models/common.py`（Dataset → DataCatalog 迁移）
- 修改 interfaces 的 2 个 Dataset 引用（使用 DataCatalog 替代）
- 修改 3 个 Reader（移除 init_schema）
- 修改 2 个 Writer（移除 get_records）
- 拆分 `app/process/materialization/helpers.py`

---

### P4：Port 归属统一

#### 当前状态

`DataProvider`（`data/provider.py`）由实现方（data）定义，消费者（engine）被迫适应其接口语义。这是唯一不符合"消费者定义端口"原则的 Port。

#### 设计方案

**新增 engine/ports.py**：

```python
# engine/ports.py — Engine 定义自己需要的数据接口
class DataPortal(Protocol):
    """Engine 需要的数据接口语义 — 由 data 层实现"""
    def get_history(
        self,
        instrument_id: InstrumentId,
        start: date,
        end: date,
        frequency: str,
    ) -> pl.DataFrame: ...

    def get_latest_bar(self, instrument_id: InstrumentId) -> pl.DataFrame: ...
    def get_instruments(self, asset_class: AssetClass | None) -> pl.DataFrame: ...
```

**迁移路径**：

1. 在 `engine/ports.py` 定义 `DataPortal` Protocol
2. `data/provider.py` 的 `DataProvider` 改为实现 `engine.ports.DataPortal`
3. engine 内部所有 DataProvider 引用迁移为 DataPortal
4. 移除 importlinter 中 `engine → data.provider` 的 ignore_imports

**影响范围**：
- 新增 1 个文件：`engine/ports.py`
- 修改 `data/provider.py`（实现 DataPortal）
- 修改 engine 内部 ~5 个文件的 import
- 修改 `.importlinter` 的 engine-no-data-dependency 合约

**依赖方向**：
```
engine.ports（定义 DataPortal Protocol）
  ↑
data.provider（实现 DataPortal Protocol）
```

---

### P5：DataPortal 扩展

#### 当前状态

`DataProvider` 仅 4 个方法（get_history、get_instruments 等），远不够 full data access。

#### T0 参考

| 平台 | DataPortal 方法数 | 关键能力 |
|------|------------------|---------|
| Zipline | 15+ | get_history, get_spot_value, get_splits, get_dividends, get_adjusted_value |
| NautilusTrader | 全类型 | quote, trade, bar, orderbook, ticker |
| LEAN | 订阅制 | DataManager 订阅推送 |

#### 设计方案

在 P4 的 `engine/ports.py` 基础上扩展：

```python
class DataPortal(Protocol):
    """Engine 完整数据接口 — 参考 Zipline DataPortal + NautilusTrader DataEngine"""

    # 历史数据
    def get_history(self, ...) -> pl.DataFrame: ...
    def get_spot_value(self, instrument_id: InstrumentId, field: str) -> float: ...

    # PIT-safe 查询
    def get_pit_history(self, instrument_id: InstrumentId, field: str, as_of: date) -> pl.DataFrame: ...

    # 市场微观结构（预留）
    def get_orderbook(self, instrument_id: InstrumentId) -> pl.DataFrame | None: ...

    # 基础设施
    def get_instruments(self, asset_class: AssetClass | None) -> pl.DataFrame: ...
    def get_trading_calendar(self, exchange: Exchange) -> list[date]: ...
```

**分阶段实现**：
1. **Phase 1**：get_history + get_instruments（当前已有）
2. **Phase 2**：get_pit_history（PIT 安全查询）
3. **Phase 3**：get_spot_value + get_orderbook（微观结构）
4. **Phase 4**：实时推送（LiveDataFeed 集成）

---

### P6：组件状态机与错误恢复

#### 当前状态

backtest 循环使用 `try/except Exception` 吞错误，无显式状态转换。engine 异常体系仅 1 个子类。

#### T0 参考

| 平台 | 组件状态 | 关键特征 |
|------|---------|---------|
| NautilusTrader | 8 状态 | PRE_INITIALIZED → READY → RUNNING → STOPPED → DISPOSED + DEGRADED + FAULTED |
| crash-only | 统一恢复 | 外部化状态、fail-fast on invariant |

#### 设计方案

**EngineLoop 状态机**：`engine/backtest/lifecycle.py`

```python
class ComponentState(StrEnum):
    PRE_INITIALIZED = "pre_initialized"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    DISPOSED = "disposed"
    FAULTED = "faulted"

class EngineLifecycle:
    """Engine 组件生命周期 — crash-only 设计"""
    TRANSITIONS: dict[ComponentState, frozenset[ComponentState]] = {
        ComponentState.PRE_INITIALIZED: frozenset({ComponentState.READY}),
        ComponentState.READY: frozenset({ComponentState.RUNNING, ComponentState.DISPOSED}),
        ComponentState.RUNNING: frozenset({ComponentState.STOPPED, ComponentState.FAULTED}),
        ComponentState.STOPPED: frozenset({ComponentState.READY, ComponentState.DISPOSED}),
        ComponentState.FAULTED: frozenset({ComponentState.DISPOSED}),  # crash-only: fault → dispose
    }

    def transition(self, current: ComponentState, target: ComponentState) -> None:
        allowed = self.TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise StateTransitionError(f"Invalid lifecycle transition: {current} -> {target}")
```

**Crash-only 不变量检查**：

```python
# 在回测循环中替换 except Exception
def _validate_bar_invariants(self, bar: pl.DataFrame) -> None:
    """fail-fast: NaN/负时间戳/算术溢出立即终止"""
    if bar["close"].null_count() > 0:
        raise DataIntegrityError("NaN in close price")
    if (bar["timestamp"] < 0).any():
        raise DataIntegrityError("Negative timestamp")
```

**Engine 异常体系扩展**：

```python
# engine/exceptions.py — 扩展
class EngineError(DittoError): ...

class StateTransitionError(EngineError): ...        # 已有
class InsufficientBuyingPowerError(EngineError): ...  # 新增
class InvalidOrderError(EngineError): ...             # 新增
class BacktestConfigError(EngineError): ...           # 新增
class DataIntegrityError(EngineError): ...            # 新增
class PortfolioConstraintError(EngineError): ...      # 新增
```

**影响范围**：
- 新增 1 个文件：`engine/backtest/lifecycle.py`
- 修改 `engine/exceptions.py`（扩展异常体系）
- 修改回测循环（替换 except Exception）
- 新增 1 个文件：`engine/backtest/invariants.py`（不变量检查）

---

## 3. 改进路线图

### Sprint A：Quick Wins（1 周）→ 目标 8.0 分

| 任务 | 关联 | 工作量 |
|------|------|--------|
| ConfigValidationProvider f-string 日志修复 | 工程实践 | 0.5h |
| DQSettings CWD 相对路径修复 | 工程实践 | 1h |
| Analysis/AnalysisWarning 下沉到 expression/contracts.py | F07 | 2h |
| 新增 importlinter analytics expression→materialization 禁止合约 | F07 | 0.5h |
| PartitionStrategy(ABC) → Protocol 转换 | Python 实践 | 1h |
| ETF/Fx 缩写统一（Etf→Etf, FX→Fx） | F06 | 2h |
| engine/exceptions.py 扩展（5 个领域异常） | F08 | 1h |

### Sprint B：命名收敛（1 周）→ 目标 8.2 分

| 任务 | 关联 | 工作量 |
|------|------|--------|
| Exchange 枚举统一到 kernel | F03 | 3h |
| StrategyRunService 重命名（data 版 → StrategyRunStorageService） | F04 | 2h |
| _CatalogReader ×3 合并到 derived/protocols.py | F04 | 2h |
| helpers.py 拆分（3 个模块） | 评估报告 §3.4 | 4h |
| 命名词典补充（Client/Processor/Transformer） | 评估报告 §3.1 | 1h |
| errors.py → exceptions.py 统一命名 | F08 附带 | 2h |
| factor_analysis.py 拆分 | F14 | 3h |

### Sprint C：Order 概念（2 周）→ 目标 8.5 分

| 任务 | 关联 | 工作量 |
|------|------|--------|
| Order 聚合根 + OrderId 值对象 | P1 | 1 天 |
| OrderStateMachine（crash-only） | P1 | 1 天 |
| OrderGateway Protocol | P1 | 0.5 天 |
| SimulatedBrokerage 实现 | P1 | 2 天 |
| StrategyPipeline 扩展（Signal→Order→Fill） | P1 | 2 天 |
| engine/backtest/lifecycle.py 组件状态机 | P6 | 1 天 |
| 回测循环 crash-only 改造 | P6 | 1 天 |
| 单元测试 + 集成测试 | P1+P6 | 2 天 |

### Phase 2：Data 重组（3 周）→ 目标 8.8 分

| 任务 | 关联 | 工作量 |
|------|------|--------|
| DataCatalog 替代 Dataset StrEnum | P3 | 3 天 |
| SchemaManager 提取 init_schema | P3 | 2 天 |
| Reader/Writer CQRS 纯净度修复 | F05 | 3 天 |
| Data Portal → engine/ports.py | P4 | 2 天 |
| DataPortal 扩展 Phase 1-2 | P5 | 3 天 |
| importlinter 模型对齐（线性→diamond 注释） | F01 | 0.5 天 |
| @traced 覆盖 engine + analytics（目标 50%） | F09 | 3 天 |
| E2E 测试补充（目标 10 个） | F10 | 2 天 |

### Phase 3：Live Parity（4 周）→ 目标 9.1 分

| 任务 | 关联 | 工作量 |
|------|------|--------|
| EnvironmentContext 实现 | P2 | 1 天 |
| SimulatedDataFeed / LiveDataFeed | P2 | 3 天 |
| TradingLoop 重构（统一 backtest/live） | P2 | 3 天 |
| Brokerage Protocol（参考 FinceptTerminal IBroker） | P2 | 2 天 |
| InstrumentEventHandler 扩展 | P2 | 2 天 |
| 集成测试 + E2E 测试 | P2 | 3 天 |

### Phase 4：T0 平台化（6 周）→ 目标 9.5 分

| 任务 | 关联 | 工作量 |
|------|------|--------|
| DataPortal 扩展 Phase 3-4 | P5 | 2 周 |
| 生产运维（健康检查、告警、日志聚合） | — | 1 周 |
| OMS（订单管理系统） | — | 1 周 |
| API 产品化（OpenAPI 文档、版本管理） | — | 1 周 |
| Web 工作台（可选） | — | 1 周 |

---

## 4. 14 平台对标矩阵

| # | 平台 | 语言 | 定位 | Ditto 对标维度 | 关键参考 |
|---|------|------|------|---------------|---------|
| 1 | QuantConnect LEAN | C#/Python | 全栈量化平台 | 策略生命周期、组合模型、brokerage | IAlgorithm, OrderType, DataManager |
| 2 | NautilusTrader | Rust/Python | 高性能交易 | DDD、事件驱动、backtest/live 一致、状态机 | 12 态 Order, 组件状态机, 单一 Kernel |
| 3 | Microsoft Qlib | Python | AI 量化研究 | 因子研究、ML 集成 | DataHandler, Dataset |
| 4 | Zipline | Python | 回测框架 | DataPortal、Pipeline API | 15+ DataPortal 方法 |
| 5 | VectorBT | Python | 向量化回测 | 性能优化 | NumPy 集成 |
| 6 | Backtrader | Python | 回测框架 | Strategy/Cerebro 模式 | 策略模式 |
| 7 | OpenBB | Python | 金融数据终端 | 数据源架构 | per-datatype Fetcher |
| 8 | Databento | C++/Python | 市场数据 | 高性能数据处理 | 零拷贝解析 |
| 9 | Panda QuantFlow | Python | 因子平台 | 因子管理 | 表达式语言 |
| 10 | Panda Factor | Python | 因子平台 | 因子计算 | 组合优化 |
| 11 | **FinceptTerminal** | **C++/Python** | **金融终端** | **DataHub pub/sub、Broker 抽象、MCP** | **TopicPolicy, IBroker, MCP 工具路由** |
| 12 | Django | Python | Web 框架 | 分层架构、插件系统 | app-based 模块化 |
| 13 | FastAPI | Python | API 框架 | 依赖注入、类型安全 | DI 系统 |
| 14 | pytest | Python | 测试框架 | 插件架构、fixture 系统 | entry_points 发现 |

---

## 5. FinceptTerminal 深度对标

### 5.1 能力对标总览

| 能力 | FinceptTerminal | Ditto | 差距方向 |
|------|-----------------|-------|---------|
| 进程内 pub/sub | 成熟（10 期 DataHub） | 概念阶段 | ← 需学习 |
| Broker 抽象 | 16 broker（IBroker） | 未实现 | ← 需补齐 |
| AI Agent 集成 | 完整 MCP 协议 | 不适用 | 暂无需求 |
| 数据源广度 | 100+ 连接器 | A 股 ETF 专注 | 各有侧重 |
| 量化回测 | 基础（Python 脚本级） | 核心差异化（engine 层） | → 优势 |
| 领域建模 | 服务导向 | DDD 分层架构 | → 优势 |
| 类型安全 | QVariant | 类型化 kernel + strict | → 优势 |

### 5.2 值得借鉴的设计

| 模式 | FinceptTerminal 实现 | Ditto 应用场景 |
|------|---------------------|---------------|
| DataHub TopicPolicy | per-topic TTL + min_interval + coalesce + push_only | DataPortal 数据新鲜度管理 |
| Producer rate limiting | `max_requests_per_sec()` + hub 调度器 | 数据源限流统一管理 |
| IBroker + BrokerRegistry | 16 broker adapter，统一接口 | P1 OrderGateway + P2 LiveBrokerage |
| MCP 工具路由 | 内部工具 + 外部 MCP server + 统一路由 | 未来 AI Agent 集成预留 |

### 5.3 Ditto 的差异化优势

| 能力 | Ditto | FinceptTerminal |
|------|-------|-----------------|
| 量化回测引擎 | 完整（alpha/portfolio/execution/accounting/orchestrator） | 基础（Python 脚本级） |
| 领域建模 | DDD 分层（kernel/data/engine/app/interfaces） | 服务导向（无 DDD） |
| 类型安全 | typed kernel + basedpyright strict | QVariant（动态类型） |
| 架构门禁 | 30+ import-linter 合约 | 无（Qt 应用内聚） |
| CQRS 分离 | Reader/Writer 模式 | 无 |
| 因子表达式 | 自研表达式编译器 + AST | 无 |

---

## T0 Architecture Clarity Downstream Notes

P1-P6 均为 T0 architecture clarity plan 的下游依赖：

| 差距 | 下游依赖说明 |
|------|-------------|
| P1: Order 概念 | 依赖 engine 异常体系稳定（T0 F08 已评估为可接受基线），依赖 @traced 覆盖（T0 Task 10 已完成关键路径） |
| P2: Backtest/Live 单路径 | 依赖 P1 Order 概念，依赖 engine 内部隔离已清洁（T0 F07 已验证） |
| P3: Data 包模块化 | 依赖 Dataset StrEnum 泄露问题收敛（T0 F02 仍 open），依赖 CQRS 纯净度（T0 F05 部分解决） |
| P4: DataProvider 归属 | 依赖 Port 归属规则统一（T0 Task 7 命名词典已更新） |
| P5: 异常体系完善 | 依赖各包异常基线评估（T0 F08 已完成 engine 评估），命名统一为后续任务 |
| P6: 约定可执行化 | 依赖 CQRS guard test 模式（T0 Task 4 已建立），架构 smell checker 已上线（T0 Task 12） |

---

## 附录：验证清单

- [x] T0 差距分析覆盖 P1-P6，每个差距有完整设计方案
- [x] FinceptTerminal 已纳入对标矩阵
- [x] 改进路线图有明确的时间估算和优先级排序
- [x] 所有设计方案有模块位置、Protocol 定义、依赖方向
- [x] 运行 `pixi run -e dev check` 确认审计过程未引入变更 — **已验证**：5855 tests passed, 0 type errors, 34 import-linter contracts kept
