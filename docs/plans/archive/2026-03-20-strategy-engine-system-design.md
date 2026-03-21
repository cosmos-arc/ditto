# 策略引擎完整系统设计

**日期**: 2026-03-20
**状态**: Draft — 设计进行中
**范围**: `packages/core/src/ditto_core/strategy` / `packages/core/src/ditto_core/portfolio` / `packages/core/src/ditto_core/backtest` / `packages/core/src/ditto_core/execution`
**前置文档**:
- `docs/plans/2026-03-20-daily-strategy-engine-design.md`（策略决策层设计）
- `docs/reviews/2026-03-20-t1-gap-audit.md`（T1 差距审计）
- `docs/reviews/2026-03-20-industry-benchmark-quant-platforms.md`（业界对标）

---

## 0. 核心设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 架构范式 | 双层混合（研究向量化 + 执行步进式） | 兼顾研究效率与回测真实度，最贴合 Ditto 现有 Polars 生态 |
| 2 | 回测推进 | 日历步进 + 调仓触发 | 每天推进引擎步，非调仓日只更新 NAV/风控；能正确模拟 T+1/停牌 |
| 3 | Order 定位 | Pipeline 后置 | 决策层（TargetPortfolio）纯净无状态，执行层（Order/Brokerage）有状态 |
| 4 | A 股规则 | 扩展 8 条 | 佣金/T+0·T+1/涨跌停/手数/停牌/集合竞价/分类/分时成交 |
| 5 | 资产规则解耦 | InstrumentRule 作为独立数据对象 | BrokerageModel 不感知资产类型，新资产类型只需新增 Provider |
| 6 | 桥接组件命名 | ExecutionPlanner | 语义通用，不暗示特定策略类型 |

---

## 1. 整体架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Port (应用编排层)                         │
│  StrategyRunService │ BacktestService │ ArtifactPersistence     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────── 决策层 (纯计算, 无 I/O) ────────────┐  │
│  │                                                   │          │
│  │  Universe → Signal → Score → Regime → Filter     │          │
│  │    → Select → Allocate → RiskSize → Constraint   │          │
│  │                        ↓                          │          │
│  │              TargetPortfolio                      │          │
│  │              (DecisionFrame)                      │          │
│  └───────────────────────────────────────────────────┘          │
│                        ↓ ExecutionPlanner 转换                  │
│  ┌──────────── 执行层 (有状态模拟) ────────────────┐  │
│  │                                                   │          │
│  │  ExecutionPlanner → Orders                       │          │
│  │    → Brokerage (FillModel/SlippageModel/FeeModel) │          │
│  │    → Fills → PortfolioState.update()              │          │
│  │    → RiskGuard.scan()                             │          │
│  └───────────────────────────────────────────────────┘          │
│                        ↓                                        │
│  ┌──────────── 统计层 ──────────────────────────────┐  │
│  │  NAV │ TradeStats │ PortfolioStats │ AlphaStats  │          │
│  └───────────────────────────────────────────────────┘          │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                     DataHub (数据与持久化层)                      │
│  strategy_catalog │ artifact_service │ InstrumentRuleProvider    │
└─────────────────────────────────────────────────────────────────┘
```

**核心设计思想**：

1. **决策层**完全保持现有 Pipeline 设计——Polars DataFrame 全程向量化计算，无状态、纯函数、可并行
2. **执行层**引入有状态模拟——Order、Brokerage、PortfolioState 状态机。TargetPortfolio（"想要什么"）→ ExecutionPlanner → Order（"怎么交易"）→ Brokerage → Fill
3. **两层通过 ExecutionPlanner 桥接**——读取 TargetPortfolio 和 PortfolioState，计算差异后生成 Order 列表
4. **统计层**消费执行层的 Fills 和 PortfolioState 变化，产出三层统计报告

---

## 2. 决策层细化

在现有 `daily-strategy-engine-design.md` 基础上补充 Gap 审计指出的 6 个改进项。

### 2.1 Signal 生命周期

现有 `SignalSnapshot` 缺少有效期概念。补充 `valid_until` 语义：

- 信号生成时自动标注 `trade_date`（信号日）
- 信号有效期由 `ExecutionSpec.trigger.method` 隐式决定——日频策略信号次日开盘前失效
- 调仓日未被执行的信号自动过期，不累积到下期

### 2.2 约束优先级与冲突解决

现有 `ConstraintSpec` 多约束同时违规时无优先级。补充 `priority: int` 字段：

- 所有约束按 priority 升序执行（数字小优先）
- 同 priority 的约束按声明顺序执行
- 每个约束执行后 `reason_codes` 记录调整原因，确保可解释

### 2.3 StrategyTemplate 参数约束

现有模板缺参数范围声明。补充：

```python
@dataclass(frozen=True)
class ParamConstraint:
    name: str
    dtype: str                           # int / float / str
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    allowed_values: tuple[str, ...] = ()  # 枚举型参数
```

为未来参数扫描 UI 和 Walk-Forward 优化提供元数据基础。

### 2.4 策略实验对比报告

`baseline_run_id` 已有，补充结构化对比输出：

- `StrategyComparisonReport`：指标矩阵 + 统计显著性检验 + 改进方向
- 输出为 artifact，可在 Web 工作台展示

### 2.5 新增第四种模板

| 模板 ID | 名称 | 适用场景 |
|---------|------|---------|
| `etf_rotation` | ETF 轮动 | 行业/主题 ETF 定期轮动 |
| `etf_trend_swing` | ETF 趋势追踪 | 趋势信号驱动的 ETF 交易 |
| `stock_selection_trend` | 选股趋势追踪 | 多因子选股 + 趋势过滤 |
| `stock_sector_rotation` | 选股行业轮动 | 行业配置 + 行业内选股（新增） |

---

## 3. 执行层（全新设计）

执行层引入有状态模拟，与决策层的无状态纯计算形成清晰分界。

### 3.1 Order 模型

```python
class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    MARKET_ON_CLOSE = "market_on_close"

class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"

class OrderDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"

@dataclass(frozen=True)
class Order:
    order_id: str
    instrument_id: str
    order_type: OrderType
    direction: OrderDirection
    quantity: int                     # 股数，A股 ETF ≥ 100 份
    price: float | None = None        # LIMIT 单价格
    stop_price: float | None = None   # STOP 单触发价
    created_at: datetime
    strategy_run_id: str

@dataclass
class OrderTicket:
    """订单票据 — 一等引用对象，策略/引擎通过它交互"""
    order: Order
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: int = 0
    filled_price: float | None = None
    average_fill_price: float | None = None
    order_events: list[OrderEvent] = field(default_factory=list)
    # 终态不可逆：FILLED / CANCELED / REJECTED

@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    status: OrderStatus
    fill_price: float | None = None
    fill_quantity: int = 0
    fee: float = 0.0
    message: str | None = None
    timestamp: datetime
```

**关键设计原则**：

- `Order` 是 frozen dataclass（创建后不可变），所有状态变更记录在 `OrderTicket` 和 `OrderEvent` 上
- `OrderTicket` 是一等引用——引擎通过它查询订单状态，风控通过它拦截/修改
- 终态（FILLED/CANCELED/REJECTED）不可逆，转换函数需校验前置状态

### 3.2 ExecutionPlanner

```python
@dataclass(frozen=True)
class ExecutionPlan:
    """TargetPortfolio → Order 列表的转换结果"""
    plan_id: str
    trade_date: str
    orders: tuple[Order, ...]
    estimated_turnover: float
    estimated_cost: float
    blocked_orders: tuple[BlockedOrder, ...]

@dataclass(frozen=True)
class BlockedOrder:
    instrument_id: str
    direction: OrderDirection
    intended_quantity: int
    reason: str          # "t_plus1_not_sellable" / "limit_up_no_buy" / ...
    severity: str        # "block" / "defer_to_next_day"

class ExecutionPlanner(Protocol):
    def plan(
        self,
        target: TargetPortfolio,
        current: PortfolioState,
        trade_date: str,
        rules: dict[str, InstrumentRule],
    ) -> ExecutionPlan: ...
```

ExecutionPlanner 内部处理：

- **Diff 计算**：current_weight vs target_weight → delta
- **数量取整**：按 100 份手数向下取整（A股规则）
- **T+1 检查**：当日买入的标的标记为不可卖
- **涨跌停预检**：涨停标的买单标记为 `defer_to_next_day`，跌停标的卖单标记为 `block`
- **停牌过滤**：停牌标的所有订单标记为 `block`

### 3.3 Brokerage 抽象

```python
class Brokerage(Protocol):
    def connect(self) -> None: ...
    def place_order(self, order: Order) -> OrderTicket: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def update_order(self, order_id: str, **updates) -> OrderTicket: ...
    def get_positions(self) -> dict[str, Holding]: ...
    def get_cash(self) -> CashBook: ...

class BacktestBrokerage:
    """回测 Broker — 同步、确定性、即时成交"""
    def __init__(self, fill_model: FillModel, fee_model: FeeModel,
                 slippage_model: SlippageModel, settlement_model: SettlementModel): ...

# 未来扩展（接口已预留，不实现）
# class LiveBrokerage:  # QMT / PTrade adapter
```

**核心设计**：`Brokerage` 是 Protocol，回测和实盘是两个实现。策略代码和引擎只依赖 Protocol，不依赖具体实现。

---

## 4. Reality Model（A 股交易规则建模）

### 4.1 InstrumentRule — 资产交易规则（独立数据对象）

```python
@dataclass(frozen=True)
class InstrumentRule:
    """某个标的的交易规则 — 由 DataHub 从配置/数据中组装"""
    instrument_id: str
    settlement_cycle: int            # T+N 的 N（1=次日可卖, 0=当日可卖）
    fund_settlement_cycle: int       # 资金交收 T+N
    price_limit_pct: float | None    # 涨跌停限制（10.0/20.0/None）
    lot_size: int                    # 最小手数
    min_commission: float            # 最低佣金
    stamp_duty_rate: float           # 印花税率（ETF=0, 股票=0.0005 卖出）
    transfer_fee_rate: float         # 过户费率（ETF=0, 股票=0.00001）
    commission_rate: float           # 佣金费率
```

- `InstrumentRule` 由 DataHub 层的 `InstrumentRuleProvider` 组装
- `BrokerageModel` 的所有方法签名接收 `rule: InstrumentRule`，不持有分类逻辑
- `ETFClassifier` / `StockClassifier` 降级为 DataHub 内部实现细节
- 未来加期货、可转债等只需新增 Provider 实现

**业界对标**：
- QuantConnect LEAN：规则存在 `Security.SymbolProperties` 上，`BrokerageModel.GetXxxModel(Security)` 读取它
- NautilusTrader：规则存在 `Instrument` 属性上，引擎完全不知道资产类型
- Ditto 方案：与 NautilusTrader 对齐，更干净

### 4.2 MarketSnapshot

```python
@dataclass(frozen=True)
class MarketSnapshot:
    """某个交易日某个标的的市场快照"""
    trade_date: str
    instrument_id: str
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: float
    amount: float
    is_suspended: bool
    limit_up: float | None       # 涨停价（None = 无限制）
    limit_down: float | None     # 跌停价（None = 无限制）
    avg_volume_20d: float | None # 20日均量（流动性参考）
```

`limit_up` / `limit_down` 由 DataHub 根据 `InstrumentRule.price_limit_pct + prev_close` 预计算填入。

### 4.3 四大可插拔模型

```python
@dataclass(frozen=True)
class FillResult:
    filled: bool
    filled_quantity: int
    fill_price: float
    reason: str | None = None

class FillModel(Protocol):
    def fill(self, order: Order, market: MarketSnapshot, rule: InstrumentRule) -> FillResult: ...

class SlippageModel(Protocol):
    def estimate(self, order: Order, market: MarketSnapshot, rule: InstrumentRule) -> float: ...

class FeeModel(Protocol):
    def calculate(self, order: Order, fill: FillResult, rule: InstrumentRule) -> float: ...

class SettlementModel(Protocol):
    def is_tradable(self, instrument_id: str, trade_date: str,
                    direction: OrderDirection, holdings: dict[str, Holding],
                    rule: InstrumentRule) -> bool: ...
    def settle_date(self, trade_date: str, rule: InstrumentRule) -> str: ...
```

#### FillModel — 成交模拟

内置 `AShareFillModel` 的规则矩阵：

| 条件 | 行为 |
|------|------|
| 停牌 | 不成交，标记 `suspended` |
| 涨停 + 买入 | 不成交（排队），标记 `defer_to_next_day` |
| 跌停 + 卖出 | 不成交（无法卖出），标记 `defer_to_next_day` |
| 涨停 + 卖出 | 全部成交（涨停板上卖方充足），价格 = 涨停价 |
| 跌停 + 买入 | 全部成交（跌停板上买方充足），价格 = 跌停价 |
| MarketOnClose | 收盘集合竞价模拟 |
| LIMIT 单 | 价格在涨跌停范围内则成交，否则不成交 |
| 正常 | 以 close ± slippage 成交 |

#### SlippageModel — 滑点模拟

内置实现：
- `FixedBpsSlippage`：固定 bps（默认 2bp）
- `VolumeShareSlippage`：按成交额占日均量比例线性递增

#### FeeModel — 费用计算

内置 `AShareFeeModel`：

| 费用项 | 规则 |
|--------|------|
| 佣金 | `max(5.0, trade_amount × commission_rate)` |
| 印花税 | 由 `rule.stamp_duty_rate` 决定（ETF=0, 股票=0.0005 卖出） |
| 过户费 | 由 `rule.transfer_fee_rate` 决定（ETF=0, 股票=0.00001） |
| 最低佣金 | 由 `rule.min_commission` 决定 |

#### SettlementModel — 交收规则

内置 `AShareSettlementModel`：

| 参数 | ETF 股票型 | ETF 跨境型 | ETF 债券型 | ETF 商品型 |
|------|-----------|-----------|-----------|-----------|
| settlement_cycle | 1 (T+1) | 0 (T+0) | 0 (T+0) | 0 (T+0) |
| fund_settlement_cycle | 1 | 1 | 1 | 0 |

### 4.4 收盘集合竞价模拟

A股收盘价由 14:57-15:00 集合竞价确定。回测中简化为：

```python
class ClosingAuctionFillModel(FillModel):
    """用于 MarketOnClose 订单"""
    def fill(self, order: Order, market: MarketSnapshot, rule: InstrumentRule) -> FillResult:
        fill_ratio = self._estimate_closing_auction_participation(
            order.quantity, market.avg_volume_20d
        )
        filled_quantity = (int(order.quantity * fill_ratio) // rule.lot_size) * rule.lot_size
        return FillResult(filled=filled_quantity > 0, ...)
```

尾盘 3 分钟（14:57-15:00）通常占全天成交量的 10-20%，用于估算大额订单的隐性滑点。

### 4.5 BrokerageModel — 规则打包

```python
class BrokerageModel:
    """将所有 Reality Model 打包为一个整体，供 Brokerage 使用"""
    def __init__(
        self,
        fill_model: FillModel,
        slippage_model: SlippageModel,
        fee_model: FeeModel,
        settlement_model: SettlementModel,
    ): ...
```

不持有资产分类逻辑，所有模型方法均接收 `InstrumentRule` 参数。

---

## 5. 回测引擎与状态管理

### 5.1 EngineLoop — 日历步进式主循环

```python
@dataclass(frozen=True)
class EngineConfig:
    start_date: str
    end_date: str
    initial_cash: float
    benchmark_id: str | None = None
    mode: StrategyRunMode = StrategyRunMode.BACKTEST

class EngineLoop:
    """回测引擎主循环 — 日历步进 + 调仓触发"""

    def __init__(
        self,
        config: EngineConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        risk_guard: RiskGuard,
        rule_provider: InstrumentRuleProvider,
        data_feed: DataFeed,
        stats_collector: StatsCollector,
    ): ...

    def run(self) -> EngineResult: ...

    def _step(self, date: str) -> None:
        """每个交易日执行一步"""
        slice = self.data_feed.get_slice(date)

        # 1. 风控扫描（per-step，每天执行）
        risk_actions = self.risk_guard.scan(self._portfolio_state, slice)
        self._apply_risk_actions(risk_actions, slice)

        # 2. 调仓日判断 → 执行决策 Pipeline
        if self._is_rebalance_day(date):
            target = self.pipeline.run(self._context, slice)
            plan = self.planner.plan(
                target, self._portfolio_state, date,
                rules=self.rule_provider.get_rules(date, list(target.instrument_ids))
            )
            self._submit_orders(plan)

        # 3. 推进订单 → 模拟成交
        self._process_pending_orders(slice)

        # 4. 更新持仓 → 标记市值
        self._portfolio_state.mark_to_market(slice)

        # 5. 记录统计
        self.stats_collector.record(date, self._portfolio_state, slice)
```

### 5.2 DataFeed — 数据源抽象

```python
class DataFeed(Protocol):
    def trading_days(self) -> list[str]: ...
    def get_slice(self, date: str) -> Slice: ...

@dataclass(frozen=True)
class Slice:
    """某个交易日所有标的的市场快照"""
    trade_date: str
    bars: dict[str, MarketSnapshot]
    benchmark_close: float | None = None
```

回测场景下 `DataFeed` 从 Parquet artifact 加载历史数据；实盘场景下替换为实时数据源（预留接口，不实现）。

### 5.3 PortfolioState — 持仓状态机

```python
@dataclass
class PortfolioState:
    """组合状态 — 引擎步进间的可变状态"""
    holdings: dict[str, Holding]
    cash: CashBook
    orders: dict[str, OrderTicket]
    pending_buy_ids: set[str] = field(default_factory=set)

    def mark_to_market(self, slice: Slice) -> None: ...
    def apply_fill(self, fill: FillResult, fee: float, rule: InstrumentRule) -> None: ...
    def total_value(self, slice: Slice) -> float: ...
    def nav(self) -> float: ...

@dataclass(frozen=True)
class Holding:
    instrument_id: str
    quantity: int
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_fees: float

@dataclass
class CashBook:
    available: float     # 可用现金
    settled: float       # 已交收（可提现）
    frozen: float        # 冻结（待交收）
```

### 5.4 三种运行模式的引擎行为差异

| 阶段 | RESEARCH | BACKTEST | RECOMMENDATION |
|------|----------|----------|----------------|
| 数据范围 | 指定区间 | 全历史 | 最新截面 |
| Pipeline | 执行 | 执行 | 执行（仅最新日） |
| ExecutionPlanner | 不执行 | 执行（含成本模拟） | 执行（生成调仓计划） |
| Brokerage | 不启动 | BacktestBrokerage | 不启动（仅计划） |
| RiskGuard | 不执行 | 执行 | 执行 |
| 统计 | 信号分析 | 三层统计 | 最新状态快照 |
| 输出 | SignalSnapshot + DecisionFrame | NAV + Metrics + Reports | TargetPortfolio + RebalancePlan |

---

## 6. 风控体系

### 6.1 双层风控架构

```
Pipeline 内 — ConstraintCheck（已有设计）
  职责：对 TargetPortfolio 做后置检查与确定性削减
  时机：Pipeline 最后一步，每轮调仓执行一次
  特征：无状态、纯函数、结果可解释

引擎内 — RiskGuard（新增）
  职责：对 PortfolioState 做实时扫描，可主动触发订单
  时机：每个交易日执行一次（per-step）
  特征：有状态、可主动干预、支持紧急动作
```

### 6.2 RiskGuard

```python
class RiskGuard(Protocol):
    def scan(self, state: PortfolioState, slice: Slice) -> list[RiskAction]: ...

class RiskActionType(StrEnum):
    REDUCE_POSITION = "reduce_position"
    LIQUIDATE = "liquidate"
    BLOCK_ORDER = "block_order"
    ALERT = "alert"

class RiskSeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

@dataclass(frozen=True)
class RiskAction:
    action_type: RiskActionType
    instrument_id: str | None
    target_quantity: int | None
    reason: str
    severity: RiskSeverity
    rule_id: str
```

### 6.3 V1 内置风控规则

| rule_id | 规则 | 动作 | 时机 |
|---------|------|------|------|
| `max_drawdown` | 组合回撤超阈值 | ALERT 或 LIQUIDATE | per-step |
| `single_loss_limit` | 单标的亏损超阈值 | REDUCE_POSITION | per-step |
| `concentration_limit` | 单标的持仓占比超限 | REDUCE_POSITION | per-step |
| `daily_turnover_limit` | 单日换手率超限 | BLOCK_ORDER | per-step |
| `market_anomaly` | 市场/标的异常波动 | ALERT | per-step |

```python
@dataclass(frozen=True)
class RiskRuleSpec:
    rule_id: str
    enabled: bool = True
    params: dict[str, object] = field(default_factory=dict)
    action_on_breach: RiskActionType = RiskActionType.ALERT
    severity: RiskSeverity = RiskSeverity.WARNING
```

风控规则作为 `StrategySpec` 的一部分声明：

```python
@dataclass(frozen=True)
class StrategySpec:
    # ... 现有字段 ...
    risk_rules: tuple[RiskRuleSpec, ...] = ()
```

### 6.4 RiskGuard 与 Pipeline Constraint 的分工

| 维度 | ConstraintCheck（Pipeline 内） | RiskGuard（引擎内） |
|------|-----|------|
| 输入 | TargetPortfolio（意图） | PortfolioState（现实） |
| 输出 | 修改后的 TargetPortfolio | RiskAction（可触发订单） |
| 时机 | 调仓日 Pipeline 末尾 | 每个交易日 |
| 能力 | 削减权重、标记违规 | 减仓、清仓、阻止、告警 |
| 状态 | 无状态 | 有状态（追踪历史回撤等） |
| 举例 | max_weight_per_instrument=20% | max_drawdown=-15% 触发清仓 |

设计原则：**Constraint 管"不该做什么"，RiskGuard 管"已经出事了怎么办"**。

---

## 7. 统计与报告层

### 7.1 与现有评估体系的关系

策略统计与因子评估服务于不同目的，保持独立但复用共享数学公式：

```
engine/evaluation/ (已有，因子研究视角)
├── IC / rank correlation / quantile returns / Fama-MacBeth
├── 因子衰减 / 正交化 / 绩效归因
└── 回答："这个因子预测力如何？"

backtest/stats/ (新增，策略执行视角)
├── 交易级 PnL / 持仓分析 / NAV 曲线
├── 换手成本归因 / 信号实现度
└── 回答："这个策略实际赚了多少钱，怎么赚的？"

共享数学：sharpe / sortino / max_drawdown / annualization
└── 复用 engine/evaluation/metrics/_math.py 中已有实现
```

不合并，不互相依赖。策略统计独立模块，数学公式复用。

### 7.2 三层统计体系

```python
# ── Layer 1: TradeStats（交易级） ──

@dataclass(frozen=True)
class TradeRecord:
    """单笔交易记录 — 由 StatsCollector 从 Fills 中提取"""
    instrument_id: str
    direction: OrderDirection
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    fees: float
    net_pnl: float
    holding_days: int
    return_pct: float
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class TradeStatistics:
    """交易级统计"""
    total_trades: int
    long_trades: int
    short_trades: int
    win_trades: int
    loss_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_win_loss_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    avg_holding_days: float
    median_holding_days: float
    best_trade: float
    worst_trade: float
    avg_trade_return_pct: float


# ── Layer 2: PortfolioStats（组合级） ──

@dataclass(frozen=True)
class PortfolioStatistics:
    """组合级统计 — 基于 NAV 曲线计算"""
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    calmar_ratio: float
    information_ratio: float
    tracking_error: float
    beta: float
    alpha_annualized: float
    total_turnover: float
    avg_turnover_per_rebalance: float
    total_fees: float
    net_return_after_cost: float
    cost_drag: float


# ── Layer 3: AlphaStats（信号级） ──

@dataclass(frozen=True)
class AlphaStatistics:
    """信号质量统计 — 衡量"信号方向对了多少" """
    n_signals: int
    signal_accuracy: float
    avg_signal_return: float
    avg_magnitude_realized: float
    signal_decay_days: float
    top_quintile_return: float
    bottom_quintile_return: float
    long_short_spread: float
    rebalance_effectiveness: float
```

### 7.3 StatsCollector

```python
class StatsCollector:
    """统计收集器 — 在 EngineLoop._step() 中被调用"""
    def record(self, date: str, state: PortfolioState, slice: Slice) -> None: ...
    def build_report(self) -> BacktestReport: ...

@dataclass(frozen=True)
class BacktestReport:
    """完整回测报告 — 三层统计的聚合"""
    run_id: str
    period: tuple[str, str]
    initial_cash: float
    final_nav: float
    trade_stats: TradeStatistics
    portfolio_stats: PortfolioStatistics
    alpha_stats: AlphaStatistics
    trade_log: list[TradeRecord]
    nav_series: list[tuple[str, float]]
```

### 7.4 NAV Artifact 格式

```
strategy/runs/{strategy_id}/v{version}/{run_id}/
├── nav.parquet                         # NAV 曲线
│   schema: trade_date, nav, benchmark_nav, drawdown, cash, exposure
├── trade_log.parquet                   # 交易明细
│   schema: 与 TradeRecord 字段对齐
├── backtest_report.json                # 三层统计摘要
│   schema: BacktestReport 的 JSON 序列化
└── fill_log.parquet                    # 逐笔成交记录（调试用）
    schema: trade_date, order_id, instrument_id, direction,
            filled_quantity, fill_price, fee, slippage, fill_reason
```

---

## 8. 模块布局

### 8.1 Core 层新增模块

现有模块布局（`packages/core/CLAUDE.md`）：

```
ditto_core/
├── quality/      # 数据质量（已实现）
├── engine/       # 核心引擎（因子/表达式/评估，已实现）
├── portfolio/    # 组合管理（待实现）
└── strategy/     # 策略框架（待实现）
```

需要新增两个模块，同时调整现有 `portfolio/` 的定位：

```
ditto_core/
├── quality/              # [已有] 数据质量引擎
├── engine/               # [已有] 表达式编译器 / 因子定义 / 因子评估 / 物化模型
│
├── strategy/             # [Phase 0-1] 策略决策层（纯计算，无 I/O）
│   ├── specs.py          #   StrategySpec / StrategyTemplate / StrategyVersion
│   ├── context.py        #   StrategyContext / StrategyInputBundle
│   ├── models.py         #   StrategyRun / SignalSnapshot / TargetPortfolio / RebalancePlan
│   ├── protocols.py      #   DecisionStage Protocol
│   ├── pipeline.py       #   Pipeline Runner（编排各阶段）
│   ├── validation.py     #   Spec 校验（参数范围 / 约束优先级 / 模式权限）
│   └── builtins/         #   内置阶段实现
│       ├── universe.py
│       ├── signal.py
│       ├── scoring.py
│       ├── regime.py
│       ├── filtering.py
│       ├── selection.py
│       └── templates/    #   策略模板
│           ├── etf_rotation.py
│           ├── etf_trend_swing.py
│           ├── stock_selection_trend.py
│           └── stock_sector_rotation.py
│
├── portfolio/            # [Phase 1] 组合构建层（纯计算，无 I/O）
│   ├── allocation.py     #   WeightAllocator 实现（equal/score/inverse_vol）
│   ├── sizing.py         #   RiskSizer 实现（full_invest/vol_target/drawdown_scale）
│   ├── constraints.py    #   ConstraintChecker 实现 + ConstraintSpec
│   └── comparison.py     #   StrategyComparisonReport / baseline 对比
│
├── execution/            # [Phase 2-3] 执行层（纯计算，无 I/O）
│   ├── orders.py         #   Order / OrderTicket / OrderEvent / OrderStatus
│   ├── planner.py        #   ExecutionPlanner 实现 / ExecutionPlan / BlockedOrder
│   ├── brokerage.py      #   Brokerage Protocol / BacktestBrokerage
│   ├── reality/          #   Reality Model（可插拔）
│   │   ├── fill.py       #     FillModel / AShareFillModel / ClosingAuctionFillModel
│   │   ├── slippage.py   #     SlippageModel / FixedBpsSlippage / VolumeShareSlippage
│   │   ├── fee.py        #     FeeModel / AShareFeeModel
│   │   └── settlement.py #     SettlementModel / AShareSettlementModel
│   └── rules.py          #   InstrumentRule（数据对象）
│
├── backtest/             # [Phase 3-4] 回测引擎（编排层，依赖 execution）
│   ├── engine.py         #   EngineLoop / EngineConfig / EngineResult
│   ├── data_feed.py      #   DataFeed Protocol / ParquetDataFeed
│   ├── state.py          #   PortfolioState / Holding / CashBook
│   ├── risk_guard.py     #   RiskGuard Protocol / 内置规则实现
│   └── stats/            #   统计体系
│       ├── collector.py  #     StatsCollector / BacktestReport
│       ├── trade.py      #     TradeRecord / TradeStatistics
│       ├── portfolio.py  #     PortfolioStatistics
│       └── alpha.py      #     AlphaStatistics
```

### 8.2 模块间依赖关系

```
strategy ←── 无外部 Core 依赖（最底层，纯决策逻辑）
portfolio ←── strategy（消费 TargetPortfolio）
execution ←── portfolio（消费 PortfolioState 的接口）
backtest  ←── strategy + execution（编排层，唯一可持有状态的模块）
```

关键依赖规则：

- `strategy` 不依赖 `portfolio` / `execution` / `backtest`（决策层最纯净）
- `portfolio` 只依赖 `strategy`（组合构建消费决策结果）
- `execution` 只依赖 `portfolio`（执行层消费组合状态接口，不消费具体实现）
- `backtest` 是唯一的编排层，可以同时依赖上面三层
- 四个模块都共享 `engine/evaluation/metrics/_math.py` 中的数学公式

### 8.3 DataHub / Port 新增

```
DataHub 新增:
├── services/strategy/
│   ├── strategy_catalog_service.py     # 策略 spec/version 元数据
│   ├── strategy_artifact_service.py    # artifact 持久化
│   └── instrument_rule_provider.py     # InstrumentRule 组装
│
Port 新增:
├── services/strategy/
│   ├── strategy_run_service.py         # 策略运行编排
│   ├── backtest_service.py             # 回测运行编排
│   └── strategy_input_assembler.py     # StrategyInputBundle 组装
```

---

## 9. 测试策略

### 9.1 测试分层

```
tests/
├── unit/                   # 单元测试（纯函数，无 I/O）
│   ├── strategy/           #   Pipeline 各阶段 / Spec 校验 / 模板
│   ├── portfolio/          #   Allocator / Sizer / Constraint
│   ├── execution/          #   Order 状态机 / FillModel / FeeModel / SettlementModel
│   └── backtest/           #   RiskGuard 规则 / Stats 计算公式
│
├── integration/            # 集成测试（需要 Parquet 数据）
│   ├── strategy/           #   端到端 Pipeline（输入 bundle → 输出 TargetPortfolio）
│   └── backtest/           #   完整引擎步进（3-5 个交易日的快照测试）
│
└── snapshot/               # 快照测试（输出稳定性）
    └── backtest/           #   回测引擎输出 artifact 不变
```

### 9.2 各模块测试重点

**strategy/ — 纯函数测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| 每个 builtin stage | 参数化 + edge case | `top_k(k=0)`, `top_k(k>N)`, 空输入 |
| Scorer | 固定输入 → 期望输出 | `rank_then_combine` 的排名一致性 |
| ConstraintCheck | 优先级冲突 | 两约束同时违规时 priority 小的先执行 |
| Spec 校验 | 非法参数拒绝 | `param_constraint.min > max` 应报错 |
| StrategyTemplate | 实例化 → 合法 StrategySpec | 4 个模板各自输出合法 spec |
| DRAFT/PUBLISHED 权限 | `StrategyRunMode × StrategyVersionStatus` 矩阵 | DRAFT+RECOMMENDATION 应拒绝 |

**execution/ — 规则测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| FillModel | 8 种场景矩阵 | 涨停买/卖 × LIMIT/MARKET × 正常/停牌 |
| FeeModel | 边界值 | 佣金 < 5 元时应取 5 元 |
| SettlementModel | T+0/T+1 判断 | 股票 ETF 当日买入次日可卖 |
| ExecutionPlanner | T+1 拦截 | 当日买入标的生成 SELL order 应被 block |
| OrderTicket 状态机 | 合法转换 + 非法转换 | NEW→FILLED ✅, FILLED→CANCELED ❌ |
| 数量取整 | 手数规则 | 买入 350 份 → 取整为 300 份 |

**backtest/ — 快照测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| EngineLoop | 3-5 日快照 | 固定输入数据 → 期望 NAV 序列和 TradeRecord |
| RiskGuard | 单规则触发 | 注入特定 PortfolioState → 期望 RiskAction |
| StatsCollector | 已知交易序列 | 固定 Fills → 期望 TradeStatistics 指标值 |
| BacktestBrokerage | 订单成交确定性 | 相同输入 → 相同输出（幂等性） |

### 9.3 回测引擎的测试策略

回测引擎测试采用**快照测试（Snapshot Test）**而非属性测试：

```python
# 快照测试：固定输入 → 固定输出，用 inline-snapshot 管理
def test_engine_3day_etf_rotation(snapshot):
    """
    3 个交易日的 ETF 轮动策略快照：
    Day 1: 建仓（买入 3 只 ETF）
    Day 2: 非调仓日（仅 mark-to-market）
    Day 3: 调仓日（换入 1 只新 ETF，卖出 1 只）
    """
    config = EngineConfig(...)
    result = engine.run(config)
    assert result.final_nav == snapshot
    assert result.trade_stats.win_rate == snapshot
    assert result.portfolio_stats.sharpe_ratio == snapshot
```

选择快照测试的原因：
- 回测引擎是确定性系统，相同输入必须产出相同结果
- 属性测试（如"NAV > 0"）太弱，无法捕获逻辑回归
- 快照测试配合 `pixi run -e dev test --snapshot` 自动管理基线更新

### 9.4 Reality Model 测试方法

A 股规则测试采用**场景矩阵**：

```python
@pytest.mark.parametrize("scenario", A_SHARE_FILL_SCENARIOS)
def test_fill_model_scenario(scenario):
    """场景矩阵覆盖 8 条 A 股规则的所有组合"""
    result = fill_model.fill(scenario.order, scenario.market, scenario.rule)
    assert result == scenario.expected
```

场景矩阵包括：
- 涨停 × 买/卖 × Market/Limit = 4 种
- 跌停 × 买/卖 × Market/Limit = 4 种
- 停牌 × 买/卖 = 2 种
- 正常 × Market/Limit/MarketOnClose = 3 种
- 集合竞价 × 正常/涨停/大额 = 3 种

---

## 10. Phase 规划

### 10.1 重组后的 Phase 规划

```
Phase 0:  基础语义与数据契约
  ┌─ StrategySpec / StrategyRun / StrategyTemplate / StrategyVersion
  ├─ DecisionFrame schema 定义
  ├─ InstrumentRule 数据对象
  ├─ ParamConstraint 参数约束
  ├─ DataHub 控制面表（strategy_version / strategy_run / strategy_artifact）
  └─ DataHub InstrumentRuleProvider（ETF 分类规则配置）
  📋 交付物：策略可以定义、版本化、存储，但无法执行
  🎯 里程碑：策略 spec CRUD + DRAFT/PUBLISHED 治理

Phase 1:  决策 Pipeline 闭环
  ┌─ Pipeline Runner（编排 Universe → Signal → Score → Filter → Select）
  ├─ 内置 stage 实现（universe / signal / scoring / filtering / selection）
  ├─ WeightAllocator（equal_weight / score_weight）
  ├─ ConstraintCheck（max_weight / max_turnover / cash_floor）+ priority
  ├─ etf_rotation 模板端到端验证
  └─ StrategyInputBundle 组装 + SignalSnapshot / TargetPortfolio 输出
  📋 交付物：输入 bundle → 运行 Pipeline → 输出 TargetPortfolio
  🎯 里程碑：ETF 轮动策略 RECOMMENDATION 闭环

Phase 2:  日频回测 V1（简化版）
  ┌─ 简化 ExecutionPlanner（diff → 数量取整，不含 T+1/涨跌停）
  ├─ 简化 BacktestBrokerage（线性佣金 + 固定滑点）
  ├─ PortfolioState / Holding / CashBook（基础 mark-to-market）
  ├─ EngineLoop（日历步进 + 调仓触发，不含 RiskGuard）
  ├─ ParquetDataFeed（从 artifact 加载历史数据）
  ├─ StatsCollector V1（NAV / PortfolioStats / TradeStatistics）
  └─ etf_rotation 回测集成测试（快照测试）
  📋 交付物：完整回测闭环，但成本模型简化（不含涨跌停/T+1）
  🎯 里程碑：ETF 轮动策略 BACKTEST 闭环 + 基础统计报告

Phase 3:  Reality Model 完整化
  ┌─ AShareFillModel（涨跌停 / 停牌 / LIMIT / 集合竞价）
  ├─ AShareFeeModel（最低 5 元 / 印花税 / 过户费，按 InstrumentRule 区分）
  ├─ AShareSettlementModel（T+0/T+1 交收，按 InstrumentRule 区分）
  ├─ VolumeShareSlippage
  ├─ ExecutionPlanner 完整化（T+1 预检 / 涨跌停预检 / 停牌过滤）
  └─ 现有回测快照测试升级（Phase 2 的测试数据替换为含涨跌停场景）
  📋 交付物：回测引擎对 A 股 ETF 规则完整建模
  🎯 里程碑：涨跌停/T+1 场景的回测结果可信

Phase 4:  风控 + 统计完善
  ┌─ RiskGuard + 内置 5 条规则
  ├─ AlphaStats（信号级统计）
  ├─ StrategyComparisonReport（baseline 对比）
  ├─ fill_log artifact（逐笔成交调试）
  └─ RiskGuard 集成测试
  📋 交付物：per-step 风控 + 完整三层统计 + 策略对比
  🎯 里程碑：回测报告可直接用于策略决策

Phase 5:  多策略模板扩展
  ┌─ etf_trend_swing 模板（regime overlay / vol_target / drawdown_scale）
  ├─ stock_selection_trend 模板（股票过滤链 / 停牌/ST/退市）
  ├─ stock_sector_rotation 模板（行业配置 + 行业内选股）
  ├─ inverse_vol allocator
  └─ 每个模板的回测快照测试
  📋 交付物：4 个策略模板全部可用
  🎯 里程碑：选股类策略回测闭环

─── 以下为 T1 延续（不在初期目标内） ───

Phase 6:  实盘执行适配
  ┌─ LiveBrokerage Protocol → QMT/PTrade adapter
  ├─ BrokerAdapter 抽象
  ├─ 实盘→回测一致性验证
  └─ 断线重连 / 幂等性 / 限流处理

Phase 7:  API 产品化
  ┌─ Order / Position / Holding / Strategy API
  ├─ 策略工作台 Web
  └─ 回测详情 + 调仓中心 + 交易记录

Phase 8:  高级能力
  ┌─ Mean-Variance / Risk Parity 组合构建
  ├─ Walk-Forward 参数优化
  └─ 多策略资金预算
```

### 10.2 关键路径

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5
                                                         ↕
                                              (Phase 4 依赖 Phase 3)
                                              (Phase 5 可与 Phase 4 并行)
```

Phase 0-2 是主线（打通从 spec 定义到回测结果的完整链路）。
Phase 3-4 是补强（A 股规则 + 风控，让回测结果可信）。
Phase 5 是扩展（更多策略模板）。

每个 Phase 都有独立可交付的闭环。

---

## 11. Artifact 与持久化

### 11.1 新增 Artifact 类型

在现有 `daily-strategy-engine-design.md` 的 artifact_kind 基础上，新增执行层和回测层 artifact：

| artifact_kind | 来源 | 格式 | 说明 |
|--------------|------|------|------|
| `decision_frame` | Pipeline | Parquet | 完整中间态（已有设计） |
| `signal_snapshot` | Pipeline | Parquet | 信号快照（已有设计） |
| `target_portfolio` | Pipeline | Parquet | 目标组合（已有设计） |
| `rebalance_plan` | ExecutionPlanner | Parquet | 调仓计划（已有设计） |
| `nav` | StatsCollector | Parquet | 每日 NAV 曲线（新增） |
| `trade_log` | StatsCollector | Parquet | 交易明细（新增） |
| `fill_log` | Brokerage | Parquet | 逐笔成交记录（新增） |
| `backtest_report` | StatsCollector | JSON | 三层统计摘要（新增） |
| `order_log` | Brokerage | Parquet | 订单生命周期日志（新增） |

### 11.2 Artifact 目录结构

```
strategy/runs/{strategy_id}/v{version}/{run_id}/
├── manifest.json                # 输入引用 + artifact 清单 + hash
│
├── decision_frame.parquet       # [Pipeline] 完整中间态
├── signal_snapshot.parquet      # [Pipeline] 信号快照
├── target_portfolio.parquet     # [Pipeline] 目标组合
├── rebalance_plan.parquet       # [Planner] 调仓计划
│
├── order_log.parquet            # [Brokerage] 订单生命周期
│   schema: trade_date, order_id, instrument_id, direction,
│           order_type, quantity, status, fill_price, fee, reason
│
├── fill_log.parquet             # [Brokerage] 逐笔成交
│   schema: trade_date, order_id, instrument_id, direction,
│           filled_qty, fill_price, slippage, fee, fill_reason
│
├── nav.parquet                  # [Stats] NAV 曲线
│   schema: trade_date, nav, benchmark_nav, drawdown, cash, exposure
│
├── trade_log.parquet            # [Stats] 交易明细
│   schema: 同 TradeRecord 字段
│
└── backtest_report.json         # [Stats] 三层统计摘要
    schema: BacktestReport 的 JSON 序列化
```

### 11.3 控制面表

沿用现有 `strategy_artifact` 表设计，`artifact_kind` 枚举扩展为：

```python
class ArtifactKind(StrEnum):
    # Pipeline 输出
    DECISION_FRAME = "decision_frame"
    SIGNAL_SNAPSHOT = "signal_snapshot"
    TARGET_PORTFOLIO = "target_portfolio"
    REBALANCE_PLAN = "rebalance_plan"
    # 执行层输出
    ORDER_LOG = "order_log"
    FILL_LOG = "fill_log"
    # 统计层输出
    NAV = "nav"
    TRADE_LOG = "trade_log"
    BACKTEST_REPORT = "backtest_report"
    # 诊断
    DIAGNOSTICS = "diagnostics"
```

### 11.4 Manifest 结构

```python
@dataclass(frozen=True)
class RunManifest:
    run_id: str
    strategy_id: str
    strategy_version: int
    mode: StrategyRunMode
    input_refs: tuple[StrategyInputRef, ...]
    parameter_overrides: dict[str, object]
    artifacts: tuple[ArtifactEntry, ...]
    config_hash: str
    engine_version: str
    created_at: str

@dataclass(frozen=True)
class ArtifactEntry:
    artifact_kind: ArtifactKind
    path: str
    row_count: int
    manifest_hash: str
```

### 11.5 与现有 DataHub 的集成

执行层和统计层的 artifact 走同一条持久化路径——通过 `StrategyArtifactService` 落盘，通过 `strategy_artifact` 表索引。不新建独立的 artifact 管理。

新增的 artifact 只是 `artifact_kind` 枚举的新值，不需要新建表或新的 service 接口。

---

## 附录 A：业界对标参考

### A.1 QuantConnect LEAN 关键设计

- `BrokerageModel` 是策略中心，通过 `GetFillModel(Security)` / `GetFeeModel(Security)` 按资产类型分发
- `SecurityInitializer` 将 BrokerageModel 策略绑定到每个 Security
- 交易规则（手数、涨跌停等）存在 `Security.SymbolProperties`，不在 BrokerageModel 上
- 参考：https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/key-concepts
- 源码：https://github.com/QuantConnect/Lean/blob/master/Common/Brokerages/DefaultBrokerageModel.cs

### A.2 NautilusTrader 关键设计

- `Instrument` 是纯数据对象，引擎完全不感知资产类型
- Rust 核心提供确定性事件驱动运行时
- 参考：https://nautilustrader.io/docs/latest/concepts/instruments/
- 源码：https://github.com/nautechsystems/nautilus_trader

### A.3 其他参考平台

| 平台 | 参考价值 |
|------|---------|
| VectorBT Pro | 向量化参数扫描、PyPortfolioOpt 组合优化 |
| Qlib (Microsoft) | Recorder + MLflow 实验管理、Alpha 表达式 |
| Zipline-Reloaded | 事件驱动架构、Pipeline API |
| Panda QuantFlow | A 股规则建模最佳参考、六阶段风控钩子 |
| Panda Factor | 技术指标库、IC 衰减分析 |
