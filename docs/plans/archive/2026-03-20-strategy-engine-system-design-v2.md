# 策略引擎完整系统设计 v2

**日期**: 2026-03-20
**状态**: Draft — 基于 v1 review 修订
**范围**: `packages/core/src/ditto_core/strategy` / `packages/core/src/ditto_core/portfolio` / `packages/core/src/ditto_core/accounting` / `packages/core/src/ditto_core/execution` / `packages/core/src/ditto_core/backtest`
**前置文档**:
- `docs/plans/2026-03-20-strategy-engine-system-design.md`（v1 原稿）
- `docs/plans/2026-03-20-daily-strategy-engine-design.md`（策略决策层设计）
- `docs/reviews/2026-03-20-t1-gap-audit.md`（T1 差距审计）
- `docs/reviews/2026-03-20-industry-benchmark-quant-platforms.md`（业界对标）
- `docs/reviews/2026-03-20-a-share-etf-trading-rules.md`（A 股交易规则）

---

## v1 → v2 修订摘要

| # | v1 问题 | v2 修订 | 影响章节 |
|---|---------|---------|---------|
| 1 | ExecutionPlanner 签名缺少 Slice/AccountView，且依赖 backtest 类型的 PortfolioState | 新增 `accounting/` 共享层，提供 AccountView/Account/Position/CashBook/OrderBook；ExecutionPlanner 改为接收 AccountView + Slice | §3, §5, §8 |
| 2 | 状态归属矛盾（"执行层有状态" vs "backtest 是唯一持有状态" vs "即时成交"） | 明确 state owner = Brokerage（持有 Account），event owner = EngineLoop；Brokerage 通过 get_account() 提供只读快照 | §3, §5 |
| 3 | RiskGuard 只能 post-hoc 扫描，BLOCK_ORDER 无法实现 | 拆分为 PreTradeRiskCheck（订单级校验，提交前拦截）+ PostTradeRiskGuard（组合级扫描，每日 step 后） | §6 |
| 4 | FillResult 字段不足，缺少 TradeBuilder，统计链条断 | FillResult → FillEvent（补全 order_id/event_time/cumulative_qty/leaves_qty）；新增 TradeBuilder（FIFO/FlatToFlat）从 fills 构建 trades | §4, §7 |
| 5 | A 股 ETF 手数规则错误（"向下取整到 100" vs "100+1 规则"） | 买入 = max(100, qty)；卖出分整手 + 零股（零股一次性卖出） | §4 |
| 6 | RESEARCH/BACKTEST/RECOMMENDATION 三模式硬塞进 EngineLoop | EngineLoop 收敛为 BACKTEST/LIVE；RESEARCH/RECOMMENDATION 降级为 Port 层 service 编排 | §5 |
| 7 | 测试策略太绝对（"快照测试而非属性测试"） | 四种测试类型：快照测试 + 不变量测试 + 场景矩阵 + 属性测试 | §9 |
| 8 | InstrumentRule 职责过重（静态属性 + 交易规则 + 费用结构一把抓） | 拆分为三层：InstrumentDefinition（静态属性）/ TradingRuleSet（交易规则，PIT）/ FeeSchedule（费用结构，PIT） | §5, 附录 B |
| 9 | BuyingPowerModel 缺失（购买力逻辑散落在 PreTrade 中） | 独立 BuyingPowerModel Protocol，V1 实现 CashAccountBuyingPower | §3 |
| 10 | 规则版本化缺失（交易所规则变更无法回放） | TradingRuleSet / FeeSchedule 复用现有 PIT 基础设施（effective_from / effective_to） | §5, 附录 B |
| 11 | 现有内核硬编码未评估（specs.py / runtime_input.py / query_service.py） | 新增附录 B：逐项评估阻塞等级，策略引擎不走因子编译器，V1 不阻塞 | 附录 B |
| 12 | 现有 evaluation 复用边界不清（数学 vs 语义） | §8.1 细化：`_math.py` 纯数学可复用，因子语义不复用，sharpe/sortino/dd 计算逻辑可抽取共享 | §8 |

---

## 0. 核心设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 架构范式 | 双层混合（研究向量化 + 执行步进式） | 兼顾研究效率与回测真实度，最贴合 Ditto 现有 Polars 生态 |
| 2 | 回测推进 | 日历步进 + 调仓触发 | 每天推进引擎步，非调仓日只更新 NAV/风控；能正确模拟 T+1/停牌 |
| 3 | Order 定位 | Pipeline 后置 | 决策层（TargetPortfolio）纯净无状态，执行层（Order/Brokerage）有状态 |
| 4 | A 股规则 | 扩展 8 条 + 100+1 手数规则 | 佣金/T+0·T+1/涨跌停/100+1手数/停牌/集合竞价/分类/分时成交 |
| 5 | 资产规则解耦 | InstrumentRule 作为独立数据对象 | BrokerageModel 不感知资产类型，新资产类型只需新增 Provider |
| 6 | 桥接组件命名 | ExecutionPlanner | 语义通用，不暗示特定策略类型 |
| 7 | 账户契约 | 独立 accounting 层 | Account/AccountView 作为共享契约，execution 不依赖 backtest |
| 8 | 状态归属 | Brokerage 是 state owner | Brokerage 持有 Account，EngineLoop 是 event owner |
| 9 | 风控分层 | PreTrade + PostTrade | 订单级拦截（提交前）+ 组合级扫描（每日），BLOCK_ORDER 真正可执行 |
| 10 | 交易匹配 | TradeBuilder | FIFO/FlatToFlat 协议，fills → trades 闭环 |
| 11 | 引擎模式 | BACKTEST / LIVE | EngineLoop 只做日历步进，RESEARCH/RECOMMENDATION 在 service 层编排 |
| 12 | 资产规则三层分离 | InstrumentDefinition / TradingRuleSet / FeeSchedule | 静态属性 vs 可变交易规则 vs 可变费用结构分离；规则按日期生效（PIT），支持回放和审计 |
| 13 | 购买力独立建模 | BuyingPowerModel Protocol | V1 现金账户、V2 融资融券、V3 期货保证金，调用接口统一但实现各异 |
| 14 | 内核复用边界 | 因子编译器硬编码不阻塞策略引擎 | 策略 decision pipeline 走独立 Python 路径，不走表达式 AST；evaluation 只复用 `_math.py` |

---

## 1. 整体架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Port (应用编排层)                         │
│  StrategyRunService      │ BacktestService                     │
│  ├─ run_research()       │ ├─ run_backtest()                   │
│  ├─ run_recommendation() │ └─ 调用 EngineLoop                  │
│  └─ 一次性计算，不走日历步进                                     │
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
│  ┌──────────── 执行层 (依赖 accounting 契约) ────────┐  │
│  │                                                   │          │
│  │  ExecutionPlanner(target, account_view, slice)     │          │
│  │    → Orders → PreTradeRiskCheck → Brokerage        │          │
│  │    → FillEvents → Account.update()                  │          │
│  │    → PostTradeRiskGuard.scan(account_view, slice)  │          │
│  └───────────────────────────────────────────────────┘          │
│                        ↓                                        │
│  ┌──────────── 统计层 ──────────────────────────────┐  │
│  │  TradeBuilder │ NAV │ TradeStats │ PortfolioStats │          │
│  │  AlphaStats                                             │          │
│  └───────────────────────────────────────────────────┘          │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                     DataHub (数据与持久化层)                      │
│  strategy_catalog │ artifact_service │ InstrumentRuleProvider    │
└─────────────────────────────────────────────────────────────────┘
```

**核心设计思想**：

1. **决策层**完全保持现有 Pipeline 设计——Polars DataFrame 全程向量化计算，无状态、纯函数、可并行
2. **Accounting 层**定义共享账户契约（Account / AccountView / Position / CashBook / OrderBook），所有上层模块通过它访问状态，不直接依赖具体实现
3. **执行层**通过 AccountView（只读快照）读取状态，通过 Brokerage（state owner）提交订单并获取 FillEvent
4. **风控分两层**：PreTradeRiskCheck 在订单提交前逐单校验（reject/resize/accept）；PostTradeRiskGuard 在每日 step 后扫描组合状态
5. **统计层**通过 TradeBuilder 把 FillEvent 序列聚合成 TradeRecord，产出三层统计报告
6. **EngineLoop**只做 BACKTEST/LIVE 两种日历步进模式；RESEARCH/RECOMMENDATION 在 Port 层 service 编排

---

## 2. 决策层细化

> 本章与 v1 完全一致，无修改。

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

## 3. Accounting 层（v2 新增）

### 3.1 设计动机

v1 中 PortfolioState 定义在 backtest/ 下，但 execution 需要读它、RiskGuard 需要扫描它、ExecutionPlanner 需要对比它。状态 owner 不明确导致模块边界卡死。

v2 新增 `accounting/` 作为共享账户契约层，提供 Account（可变状态）和 AccountView（只读快照），所有上层模块通过它交互。

### 3.2 Position

```python
@dataclass(frozen=True)
class Position:
    """单个标的的持仓状态"""
    instrument_id: str
    quantity: int                    # 总持仓数量
    available_quantity: int          # 可卖数量（扣除 T+1 冻结）
    average_cost: float              # 加权平均成本
    market_value: float              # 当前市值
    unrealized_pnl: float            # 浮动盈亏
    realized_pnl: float              # 已实现盈亏（累计）
    total_fees: float                # 累计交易费用
```

### 3.3 CashBook

```python
@dataclass
class CashBook:
    """现金账户"""
    available: float      # 可用现金（扣除冻结）
    settled: float        # 已交收（可提现）
    frozen: float         # 冻结金额（待交收/待成交）
```

### 3.4 OrderBook

```python
class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"

@dataclass
class OrderTicket:
    """订单票据 — 一等引用对象，引擎通过它交互"""
    order: Order
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: int = 0
    filled_price: float | None = None
    average_fill_price: float | None = None
    order_events: list[OrderEvent] = field(default_factory=list)
    # 终态不可逆：FILLED / CANCELED / REJECTED

class OrderBook:
    """订单簿 — 持有所有 OrderTicket，只允许通过受控方法修改"""
    _tickets: dict[str, OrderTicket]

    def get(self, order_id: str) -> OrderTicket | None: ...
    def get_pending(self) -> tuple[OrderTicket, ...]: ...
    def submit(self, ticket: OrderTicket) -> None: ...
    def update(self, event: OrderEvent) -> None: ...
    def cancel(self, order_id: str) -> None: ...

class StateTransitionError(Exception):
    """非法状态转换，如 FILLED → CANCEL"""
    ...
```

### 3.5 Account 与 AccountView

```python
@dataclass
class Account:
    """可变账户状态 — state owner (Brokerage) 持有此实例"""
    positions: dict[str, Position]
    cash: CashBook
    order_book: OrderBook

    def apply_fill(self, fill: FillEvent, rule: InstrumentRule) -> None: ...
    def mark_to_market(self, slice: Slice) -> None: ...
    def get_view(self) -> AccountView: ...

@dataclass(frozen=True)
class AccountView:
    """只读账户快照 — execution/risk/pipeline 通过它读取状态"""
    positions: Mapping[str, Position]
    cash: CashBook
    total_value: float
    nav: float
    exposure: float
    pending_buy_value: float
```

**关键设计**：

- `Account` 是可变的，只有 Brokerage 可以持有和修改
- `AccountView` 是 frozen 的，任何模块都可以安全读取
- EngineLoop 通过 `brokerage.get_account()` 获取 AccountView
- ExecutionPlanner 通过 AccountView 读取当前持仓和权重
- RiskGuard 通过 AccountView 扫描组合状态

### 3.6 BuyingPowerModel（内核升级补充）

购买力计算逻辑随账户类型差异极大，必须独立建模而非散落在 PreTrade 规则中：

```python
class BuyingPowerModel(Protocol):
    """购买力模型 — 策略引擎通过此接口查询可用购买力"""
    def available_buying_power(
        self, account: AccountView, direction: OrderDirection,
    ) -> float: ...

class CashAccountBuyingPower:
    """V1: 现金多头账户

    buying_power = cash.available - frozen - estimated_pending_fees
    """
    def available_buying_power(
        self, account: AccountView, direction: OrderDirection,
    ) -> float:
        if direction == OrderDirection.SELL:
            return 0.0  # 卖出不需要购买力
        return account.cash.available

# 未来扩展（Protocol 已预留，不实现）
# class MarginAccountBuyingPower(BuyingPowerModel): ...   # 融资融券
# class FuturesBuyingPower(BuyingPowerModel): ...          # 期货保证金
```

PreTrade `buying_power` 规则改为消费此模型，不再自行计算。

### 3.7 CashProvider 预留

V1 只跑人民币，但内核不应是单币种死结构。预留 Protocol 供 V2+ 扩展：

```python
class CashProvider(Protocol):
    """现金提供者 — V1 由 CashBook 直接满足，V2+ 可替换为多币种实现"""
    def get_available(self, currency: str = "CNY") -> float: ...
    def get_settled(self, currency: str = "CNY") -> float: ...
```

V1 阶段 CashBook 实现 CashProvider；V2+ 多币种场景替换为 MultiCurrencyCashProvider。

---

## 4. 执行层

### 4.1 Order 模型

```python
class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    MARKET_ON_CLOSE = "market_on_close"

class OrderDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"

@dataclass(frozen=True)
class Order:
    order_id: str
    instrument_id: str
    order_type: OrderType
    direction: OrderDirection
    quantity: int                     # 股数，A股 ≥ 100 份（100+1 规则）
    price: float | None = None        # LIMIT 单价格
    stop_price: float | None = None   # STOP 单触发价
    created_at: datetime
    strategy_run_id: str

    def with_quantity(self, qty: int) -> Order:
        """创建新 Order 实例，用于 PreTrade resize"""
        return dataclasses.replace(self, quantity=qty)

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
- 终态（FILLED/CANCELED/REJECTED）不可逆，转换函数需校验前置状态，非法转换抛出 `StateTransitionError`
- `Order.with_quantity()` 用于 PreTrade resize，返回新实例而非原地修改

### 4.2 ExecutionPlanner（v2 修订签名）

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
    reason: str          # "t_plus1_not_sellable" / "limit_up_no_buy" / "suspended" / ...
    severity: str        # "block" / "defer"

class ExecutionPlanner(Protocol):
    def plan(
        self,
        target: TargetPortfolio,
        account: AccountView,           # v2: 替代 PortfolioState
        slice: Slice,                   # v2: 新增，提供市场快照
        trade_date: str,
        rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]],
    ) -> ExecutionPlan: ...
```

ExecutionPlanner 内部处理：

- **Diff 计算**：从 AccountView 获取 current_weight，对比 target_weight → delta
- **数量取整**：买入 `max(100, qty)`（100+1 规则）；卖出分整手 + 零股
- **T+1 检查**：通过 `Position.available_quantity` 判断，当日买入标的 available=0
- **涨跌停预检**：通过 Slice 中的 `MarketSnapshot.limit_up/limit_down` 判断
- **停牌过滤**：通过 Slice 中的 `MarketSnapshot.is_suspended` 判断

#### 数量取整逻辑（修正 v1 的错误）

```python
def round_buy_quantity(raw_quantity: int, definition: InstrumentDefinition) -> int:
    """买入：100 份起，之后可 1 份递增（2023-08 起的 100+1 规则）"""
    return max(definition.lot_size, raw_quantity)   # lot_size=100

def round_sell_quantity(
    quantity: int, definition: InstrumentDefinition, position: Position,
) -> tuple[int, int]:
    """
    卖出分两部分：
    - 整手：(quantity // lot_size) * lot_size，可分批
    - 零股：quantity % lot_size，必须一次性全部卖出
    返回 (round_lot_qty, odd_lot_qty)
    """
    round_lot = (quantity // definition.lot_size) * definition.lot_size
    odd_lot = quantity % definition.lot_size
    return round_lot, odd_lot
```

### 4.3 FillEvent（v2 新增，替代 FillResult）

```python
@dataclass(frozen=True)
class FillEvent:
    """单次成交事件 — Brokerage 产出"""
    fill_id: str
    order_id: str
    instrument_id: str
    direction: OrderDirection
    filled_quantity: int
    fill_price: float
    fee: float
    slippage: float
    fill_reason: str | None       # "normal" / "closing_auction" / "deferred"
    event_time: datetime          # 成交时间点
    cumulative_quantity: int      # 该订单累计已成交量
    leaves_quantity: int          # 该订单剩余未成交量
```

### 4.4 Brokerage 抽象（v2 修订）

```python
class Brokerage(Protocol):
    """Brokerage 是 state owner，持有 Account 实例"""
    def connect(self) -> None: ...
    def get_account(self) -> AccountView: ...       # 只读快照
    def place_order(self, order: Order) -> OrderTicket: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def process_pending(self, slice: Slice) -> tuple[FillEvent, ...]: ...

class BacktestBrokerage:
    """回测 Broker — 确定性成交模拟

    注意：不是"即时成交"，而是根据 FillModel 规则模拟成交。
    涨跌停/停牌/集合竞价等场景由 FillModel 决定是否成交。
    """
    def __init__(
        self,
        account: Account,
        fill_model: FillModel,
        fee_model: FeeModel,
        slippage_model: SlippageModel,
        settlement_model: SettlementModel,
    ): ...

# 未来扩展（接口已预留，不实现）
# class LiveBrokerage:  # QMT / PTrade adapter
```

**v2 关键变化**：

- 新增 `get_account()` 返回 AccountView（只读快照），替代原来的 `get_positions()/get_cash()`
- 新增 `process_pending(slice)` 返回 `tuple[FillEvent, ...]`，替代隐式的订单推进
- BacktestBrokerage 构造时接收 Account 实例（state owner 职责）
- 移除"即时成交"语义——成交规则由 FillModel 决定

---

## 5. Reality Model（A 股交易规则建模）

### 5.1 资产交易规则 — 三层分离架构（内核升级修订）

v2 中 InstrumentRule 职责过重（静态属性 + 交易规则 + 费用结构一把抓），且没有版本化概念。内核升级将其拆为三层，并接入现有 PIT 基础设施实现规则版本化。

#### 5.1.1 InstrumentDefinition — 静态资产属性

```python
@dataclass(frozen=True)
class InstrumentDefinition:
    """资产的静态定义 — 很少变化，不按日期生效"""
    instrument_id: str
    asset_class: str                 # stock / etf / index / future / ...
    exchange: str                    # XSHE / XSHG / XBSE
    currency: str                    # CNY（V1），未来多币种
    tick_size: float                 # 最小价格变动（A股=0.01，期货不同）
    lot_size: int                    # 最小手数（A股=100）
    multiplier: float                # 合约乘数（股票/ETF=1，期货需要）
    board_segment: str               # main / gem / star / bse（影响涨跌停规则）
    lifecycle_state: str             # normal / st / st_star / delisting / ipo
```

**设计原则**：

- 复用现有 `InstrumentRegistration` + `InstrumentExtension`（metadata.py）的注册数据
- 由 `InstrumentRuleProvider` 在 DataHub 层从 instrument 表 + extension 表组装
- `board_segment` 和 `lifecycle_state` 直接影响 `TradingRuleSet` 中的涨跌停计算
- `ETFClassifier` / `StockClassifier` 降级为 DataHub 内部组装细节

#### 5.1.2 TradingRuleSet — 可变交易规则（PIT 版本化）

```python
@dataclass(frozen=True)
class TradingRuleSet:
    """某个标的在某个时间点的交易规则 — 按日期生效，可回放"""
    instrument_id: str
    as_of_date: str                  # 规则生效日期
    settlement_cycle: int            # T+N 的 N（1=次日可卖, 0=当日可卖）
    fund_settlement_cycle: int       # 资金交收 T+N
    price_limit_pct: float | None    # 涨跌停限制（None=无限制，如新股前5日）
    order_types_supported: tuple[str, ...]  # 支持的订单类型
    call_auction_sessions: tuple[str, ...]  # 集合竞价时段
```

**规则版本化机制**：复用 Ditto 现有 PIT 基础设施（effective_from / effective_to），零新基建：

```python
# PIT 查询 — 获取 trade_date 当天有效的交易规则
def get_trading_rule(instrument_id: str, as_of_date: str) -> TradingRuleSet:
    rules = trading_rule_store.query(instrument_id)
    return rules.filter(
        (pl.col("effective_from") <= as_of_date) &
        ((pl.col("effective_to").is_null()) | (pl.col("effective_to") > as_of_date))
    )
```

**规则变更实例**：

| 日期 | 变更 | 影响字段 |
|------|------|---------|
| 2025-06-27（征求意见） | 主板风险警示股票涨跌幅限制调整 | `price_limit_pct` |
| 2026-01-14 | 融资保证金比例调整 | `settlement_cycle` 相关 |
| ST 标记生效日 | 个股涨跌幅 10% → 5% | `price_limit_pct` |
| 新股上市前 5 日 | 无涨跌幅限制 | `price_limit_pct = None` |

#### 5.1.3 FeeSchedule — 可变费用结构（PIT 版本化）

```python
@dataclass(frozen=True)
class FeeSchedule:
    """某个标的在某个时间点的费用结构 — 按日期生效"""
    instrument_id: str
    as_of_date: str
    commission_rate: float           # 佣金费率
    min_commission: float            # 最低佣金（A股=5元）
    stamp_duty_rate: float           # 印花税率（ETF=0, 股票=0.0005 卖出）
    transfer_fee_rate: float         # 过户费率（ETF=0, 股票=0.00001）
```

同样走 PIT 查询。不同资产类别的费率差异（ETF 免印花税、股票收印花税）通过 DataHub 内部的 `ETFClassifier` / `StockClassifier` 在组装时决定。

#### 5.1.4 InstrumentRuleProvider — 组装层

```python
class InstrumentRuleProvider(Protocol):
    """由 DataHub 实现，组装三层规则并缓存"""

    def get_definition(self, instrument_id: str) -> InstrumentDefinition: ...

    def get_trading_rule(
        self, instrument_id: str, as_of_date: str,
    ) -> TradingRuleSet: ...

    def get_fee_schedule(
        self, instrument_id: str, as_of_date: str,
    ) -> FeeSchedule: ...

    def get_rules(
        self, as_of_date: str, instrument_ids: list[str],
    ) -> dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]: ...
```

**BrokerageModel 所有方法签名改为接收三个独立参数**：

```python
# 旧签名（v2 早期）
def fill(self, order: Order, market: MarketSnapshot, rule: InstrumentRule) -> FillEvent: ...

# 新签名（内核升级后）
def fill(
    self, order: Order, market: MarketSnapshot,
    definition: InstrumentDefinition,
    trading_rule: TradingRuleSet,
    fee_schedule: FeeSchedule,
) -> FillEvent: ...
```

**V1 兼容策略**：`InstrumentRuleProvider.get_rules()` 返回一个 convenience tuple，各模型内部拆包使用。Phase 2-3 的简化实现可以先用一个合并的 `InstrumentRule` dataclass，Phase 3 完整化时拆分为三层。

### 5.2 MarketSnapshot

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

### 5.3 四大可插拔模型

```python
# 签名采用三层分离。V1 简化阶段可用 InstrumentRule 合并体，
# Phase 3 完整化时拆为 definition / trading_rule / fee_schedule 三个参数。

class FillModel(Protocol):
    def fill(
        self, order: Order, market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillEvent: ...

class SlippageModel(Protocol):
    def estimate(
        self, order: Order, market: MarketSnapshot,
        definition: InstrumentDefinition,
    ) -> float: ...

class FeeModel(Protocol):
    def calculate(
        self, order: Order, fill: FillEvent,
        fee_schedule: FeeSchedule,
    ) -> float: ...
    def estimate(
        self, order: Order, estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float: ...

class SettlementModel(Protocol):
    def is_tradable(
        self,
        instrument_id: str,
        trade_date: str,
        direction: OrderDirection,
        position: Position | None,
        trading_rule: TradingRuleSet,
    ) -> bool: ...
    def settle_date(self, trade_date: str, trading_rule: TradingRuleSet) -> str: ...
```

#### FillModel — 成交模拟

内置 `AShareFillModel` 的规则矩阵：

| 条件 | 行为 |
|------|------|
| 停牌 | 不成交，fill_reason="suspended" |
| 涨停 + 买入 | 不成交（排队），fill_reason="deferred" |
| 跌停 + 卖出 | 不成交（无法卖出），fill_reason="deferred" |
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
| 佣金 | `max(fee_schedule.min_commission, trade_amount × fee_schedule.commission_rate)` |
| 印花税 | 由 `fee_schedule.stamp_duty_rate` 决定（ETF=0, 股票=0.0005 卖出） |
| 过户费 | 由 `fee_schedule.transfer_fee_rate` 决定（ETF=0, 股票=0.00001） |

FeeModel 新增 `estimate()` 方法用于 PreTrade buying power 校验（在下单前预估费用）。

#### SettlementModel — 交收规则

内置 `AShareSettlementModel`：

| 参数 | ETF 股票型 | ETF 跨境型 | ETF 债券型 | ETF 商品型 |
|------|-----------|-----------|-----------|-----------|
| settlement_cycle | 1 (T+1) | 0 (T+0) | 0 (T+0) | 0 (T+0) |
| fund_settlement_cycle | 1 | 1 | 1 | 0 |

### 5.4 收盘集合竞价模拟

A股收盘价由 14:57-15:00 集合竞价确定。回测中简化为：

```python
class ClosingAuctionFillModel(FillModel):
    """用于 MarketOnClose 订单"""
    def fill(self, order: Order, market: MarketSnapshot, rule: InstrumentRule) -> FillEvent:
        fill_ratio = self._estimate_closing_auction_participation(
            order.quantity, market.avg_volume_20d
        )
        filled_quantity = (int(order.quantity * fill_ratio) // rule.lot_size) * rule.lot_size
        if filled_quantity <= 0:
            return FillEvent(filled_quantity=0, fill_price=0.0, fill_reason="insufficient_auction", ...)
        return FillEvent(filled_quantity=filled_quantity, fill_price=market.close, ...)
```

### 5.5 BrokerageModel — 规则打包

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

---

## 6. 回测引擎与状态管理

### 6.1 EngineLoop — 日历步进式主循环

```python
class EngineMode(StrEnum):
    BACKTEST = "backtest"
    LIVE = "live"

@dataclass(frozen=True)
class EngineConfig:
    start_date: str
    end_date: str
    initial_cash: float
    benchmark_id: str | None = None
    mode: EngineMode = EngineMode.BACKTEST
    trade_matching: TradeMatchingMethod = TradeMatchingMethod.FIFO

class EngineLoop:
    """回测/实盘引擎主循环 — 日历步进 + 调仓触发"""

    def __init__(
        self,
        config: EngineConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: PreTradeRiskCheck,
        post_trade_guard: PostTradeRiskGuard,
        rule_provider: InstrumentRuleProvider,
        data_feed: DataFeed,
        stats_collector: StatsCollector,
    ): ...

    def run(self) -> EngineResult: ...

    def _step(self, date: str) -> None:
        """每个交易日执行一步"""
        slice = self.data_feed.get_slice(date)
        account_view = self.brokerage.get_account()

        # 1. PostTrade 扫描 — 检查组合健康度，可能触发紧急退出
        risk_actions = self.post_trade_guard.scan(account_view, slice)
        if risk_actions:
            self._execute_risk_actions(risk_actions, slice)
            account_view = self.brokerage.get_account()  # 刷新快照

        # 2. 调仓日 → 执行决策 Pipeline
        if self._is_rebalance_day(date):
            target = self.pipeline.run(self._context, slice)
            plan = self.planner.plan(
                target, account_view, slice, date,
                rules=self.rule_provider.get_rules(date, list(target.instrument_ids)),
            )

            # 3. PreTrade 逐单校验
            checked_orders: list[Order] = []
            pending = account_view_order_ids(account_view)
            for order in plan.orders:
                result = self.pre_trade_check.check_order(
                    order, account_view, pending,
                )
                if result.decision == "accept":
                    checked_orders.append(order)
                elif result.decision == "resize" and result.resized_quantity:
                    checked_orders.append(order.with_quantity(result.resized_quantity))
                # reject → 记录到 blocked，不提交

            # 4. 提交通过的订单
            for order in checked_orders:
                self.brokerage.place_order(order)

        # 5. 推进未完成订单 → 模拟成交
        fills = self.brokerage.process_pending(slice)

        # 6. 记录统计
        self.stats_collector.record(date, fills, account_view, slice)
```

### 6.2 DataFeed — 数据源抽象

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

### 6.3 RESEARCH / RECOMMENDATION 模式（v2 修订）

v1 将三种模式硬塞进 EngineLoop。v2 将 EngineLoop 收敛为 BACKTEST/LIVE，RESEARCH/RECOMMENDATION 降级为 Port 层 service 编排。

```python
# Port 层 — StrategyRunService
class StrategyRunService:
    """策略运行编排 — 在 Port 层，不走日历步进"""

    def run_research(
        self, spec: StrategySpec, input_bundle: StrategyInputBundle,
    ) -> ResearchOutput:
        """一次性计算：input → pipeline → 信号分析 → artifact

        流程：
        1. 组装 StrategyInputBundle（从 DataHub 加载数据）
        2. 执行 Pipeline（Universe → Signal → Score → ... → TargetPortfolio）
        3. 输出 SignalSnapshot + DecisionFrame + TargetPortfolio
        4. 持久化为 artifact
        """
        ...

    def run_recommendation(
        self, spec: StrategySpec, input_bundle: StrategyInputBundle,
    ) -> RecommendationOutput:
        """最新截面计算：input → pipeline → target portfolio → artifact

        与 run_research 的区别：
        - 数据范围：只取最新一个交易日
        - 输出重点：TargetPortfolio + RebalancePlan
        """
        ...
```

**模式对应表**：

| 模式 | 编排位置 | 是否需要 Brokerage | 是否需要 EngineLoop |
|------|---------|-------------------|-------------------|
| RESEARCH | Port / StrategyRunService | 否 | 否 |
| RECOMMENDATION | Port / StrategyRunService | 否 | 否 |
| BACKTEST | Port / BacktestService → EngineLoop | 是 | 是 |
| LIVE | Port / LiveService → EngineLoop | 是 | 是 |

---

## 7. 风控体系

### 7.1 三层风控架构（v2 修订）

```
Pipeline 内 — ConstraintCheck（已有设计）
  职责：对 TargetPortfolio 做后置检查与确定性削减
  时机：Pipeline 最后一步，每轮调仓执行一次
  特征：无状态、纯函数、结果可解释

订单提交前 — PreTradeRiskCheck（v2 新增）
  职责：对单个订单做提交前校验
  时机：每个订单提交前逐单执行
  特征：无状态、返回 accept/reject/resize
  能力：购买力校验、超卖检查、价格合法性、手数校验、集中度校验、换手率校验

每日 step 后 — PostTradeRiskGuard（v2 重命名自 RiskGuard）
  职责：对组合状态做实时扫描，可主动触发订单
  时机：每个交易日执行一次（per-step）
  特征：有状态、可主动干预、支持紧急动作
  能力：回撤止损、单标的亏损止损、异常波动告警
```

### 7.2 PreTradeRiskCheck（v2 新增）

```python
@dataclass(frozen=True)
class OrderCheckResult:
    decision: Literal["accept", "reject", "resize"]
    order_id: str
    resized_quantity: int | None = None
    reason: str | None = None

class PreTradeRiskCheck(Protocol):
    """订单提交前逐单校验 — 在 Brokerage.place_order() 之前"""
    def check_order(
        self,
        order: Order,
        account: AccountView,
        pending_orders: tuple[Order, ...],
    ) -> OrderCheckResult: ...
```

#### V1 内置 PreTrade 规则

| rule_id | 校验内容 | 行为 |
|---------|---------|------|
| `buying_power` | 可用现金 >= 买入金额 + 预估费用 | reject |
| `no_short_sell` | 卖出数量 <= 可卖数量（含 T+1 冻结） | reject |
| `price_validity` | LIMIT 单价格在涨跌停范围内 | reject |
| `lot_size` | 数量符合手数规则（买入 >= 100，卖出可含零股） | resize |
| `concentration_pre` | 单标的买入后占比 <= 阈值 | reject |
| `daily_turnover_pre` | 累计换手率 <= 阈值 | reject |

```python
class CompositePreTradeCheck(PreTradeRiskCheck):
    """组合多个 PreTrade 规则，按顺序执行，首个 reject/resize 终止"""
    def __init__(self, checks: tuple[PreTradeRiskCheck, ...]): ...

    def check_order(
        self, order: Order, account: AccountView,
        pending_orders: tuple[Order, ...],
    ) -> OrderCheckResult:
        for check in self._checks:
            result = check.check_order(order, account, pending_orders)
            if result.decision != "accept":
                return result
        return OrderCheckResult(decision="accept", order_id=order.order_id)
```

### 7.3 PostTradeRiskGuard

```python
class PostTradeRiskGuard(Protocol):
    """每日 step 后扫描组合状态 — 可主动触发退出动作"""
    def scan(
        self,
        account: AccountView,
        slice: Slice,
    ) -> list[RiskAction]: ...

class RiskActionType(StrEnum):
    REDUCE_POSITION = "reduce_position"
    LIQUIDATE = "liquidate"
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

#### V1 内置 PostTrade 规则

| rule_id | 规则 | 动作 | 时机 |
|---------|------|------|------|
| `max_drawdown` | 组合回撤超阈值 | ALERT 或 LIQUIDATE | per-step |
| `single_loss_limit` | 单标的亏损超阈值 | REDUCE_POSITION | per-step |
| `concentration_limit` | 单标的持仓占比超限 | REDUCE_POSITION | per-step |
| `market_anomaly` | 市场/标的异常波动 | ALERT | per-step |

注意：v1 的 `daily_turnover_limit` 从 PostTrade 移到了 PreTrade（它本质上是"在提交前检查累计换手率"）。

```python
@dataclass(frozen=True)
class RiskRuleSpec:
    rule_id: str
    enabled: bool = True
    params: dict[str, object] = field(default_factory=dict)
    action_on_breach: RiskActionType = RiskActionType.ALERT
    severity: RiskSeverity = RiskSeverity.WARNING
```

### 7.4 三层风控分工总览

| 维度 | ConstraintCheck（Pipeline 内） | PreTradeRiskCheck（订单前） | PostTradeRiskGuard（每日） |
|------|-----|------|------|
| 输入 | TargetPortfolio（意图） | Order + AccountView | AccountView + Slice |
| 输出 | 修改后的 TargetPortfolio | accept/reject/resize | RiskAction（可触发订单） |
| 时机 | 调仓日 Pipeline 末尾 | 每个订单提交前 | 每个交易日 step 后 |
| 状态 | 无状态 | 无状态 | 有状态（追踪回撤等） |
| 能力 | 削减权重 | 拒单、缩单 | 减仓、清仓、告警 |
| 举例 | max_weight=20% | buying_power 不够 | max_drawdown=-15% 清仓 |

设计原则：**Constraint 管"组合意图"，PreTrade 管"单笔合规"，PostTrade 管"紧急干预"**。

---

## 8. 统计与报告层

### 8.1 与现有评估体系的关系

策略统计与因子评估服务于不同目的，保持独立但复用共享数学公式：

```
engine/evaluation/ (已有，因子研究视角)
├── IC / rank correlation / quantile returns / Fama-MacBeth
├── 因子衰减 / 正交化 / 绩效归因
└── 回答："这个因子预测力如何？"

backtest/stats/ (新增，策略执行视角)
├── TradeBuilder → TradeRecord → TradeStatistics
├── NAV 曲线 → PortfolioStatistics
├── 信号实现度 → AlphaStatistics
└── 回答："这个策略实际赚了多少钱，怎么赚的？"
```

**复用边界**：

| 分类 | engine/evaluation 内容 | 策略统计复用方式 |
|------|----------------------|-----------------|
| **纯数学工具** | `scalar_to_float`, `two_sided_p_value`, `regularized_incomplete_beta`, `log_gamma`, `fit_ic_half_life` | 直接 import 复用 |
| **可抽取的计算逻辑** | `long_short_returns()` 中 sharpe/sortino/max_dd/calmar 的计算过程（L119-196） | 抽取为独立函数后复用 |
| **因子专用语义** | `pearson_ic`, `rank_ic`, `ic_decay`, `fama_macbeth`, `orthogonalize`, `factor_exposure`, `performance_attribution`, `regime_adjusted_ic`, `sub_period_ic`, `grinold_kahn_ir` | **不复用** — 因子 cross-section vs 策略 time-series 是不同语义 |
| **因子 portfolio 辅助** | `quantile_returns()`, `turnover()`, `net_returns()`, `turnover_adjusted_ir()` | **不复用** — 输入输出形状不同 |

**关键区分**：因子评估是 per-factor cross-section（每个截面日计算 IC/分位收益），策略统计是 per-portfolio time-series（NAV 曲线的时间序列统计）。两者即使指标名相同（如 sharpe），输入数据和计算上下文也不同。

不合并，不互相依赖。策略统计独立模块，只复用 `_math.py` 纯数学工具。

### 8.2 TradeBuilder（v2 新增）

```python
class TradeMatchingMethod(StrEnum):
    FIFO = "fifo"                # 先进先出
    FLAT_TO_FLAT = "flat_to_flat"  # 平仓对平仓

@dataclass(frozen=True)
class TradeRecord:
    """一笔完整交易 — 从 entry fill(s) 到 exit fill(s)"""
    trade_id: str
    instrument_id: str
    direction: OrderDirection
    entry_date: str
    exit_date: str | None        # None 表示未平仓（open trade）
    entry_price: float           # 加权平均入场价
    exit_price: float | None     # None 表示未平仓
    quantity: int
    gross_pnl: float | None      # None 表示未平仓
    fees: float                  # entry + exit 所有费用
    net_pnl: float | None        # None 表示未平仓
    holding_days: int | None
    return_pct: float | None
    entry_order_ids: tuple[str, ...]
    exit_order_ids: tuple[str, ...]

class TradeBuilder(Protocol):
    """从 fills 序列构建 trades"""
    def on_fill(self, fill: FillEvent, account: AccountView) -> None: ...
    def get_open_trades(self) -> tuple[TradeRecord, ...]: ...
    def get_closed_trades(self) -> tuple[TradeRecord, ...]: ...
    def flush(self) -> tuple[TradeRecord, ...]: ...
```

**V1 实现策略**：只做 FIFO，因为 A 股现金多头场景下 FIFO 和 FlatToFlat 结果几乎一样。Protocol 层面先支持两种方法选择。

### 8.3 三层统计体系

```python
# ── Layer 1: TradeStats（交易级） ──

@dataclass(frozen=True)
class TradeStatistics:
    """交易级统计 — 由 TradeRecord 列表计算"""
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
    """组合级统计 — 基于 NAV 曲线计算（复用 _math.py）"""
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

### 8.4 StatsCollector（v2 修订）

```python
class StatsCollector:
    """统计收集器 — 在 EngineLoop._step() 中被调用"""

    def __init__(self, trade_builder: TradeBuilder): ...

    def record(
        self,
        date: str,
        fills: tuple[FillEvent, ...],
        account_view: AccountView,
        slice: Slice,
    ) -> None:
        for fill in fills:
            self._trade_builder.on_fill(fill, account_view)
        self._nav_series.append((date, account_view.nav))

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
    alpha_stats: AlphaStatistics | None
    trade_log: list[TradeRecord]
    nav_series: list[tuple[str, float]]
    fill_log: list[FillEvent]
```

### 8.5 NAV Artifact 格式

```
strategy/runs/{strategy_id}/v{version}/{run_id}/
├── nav.parquet                         # NAV 曲线
│   schema: trade_date, nav, benchmark_nav, drawdown, cash, exposure
├── trade_log.parquet                   # 交易明细
│   schema: 与 TradeRecord 字段对齐
├── backtest_report.json                # 三层统计摘要
│   schema: BacktestReport 的 JSON 序列化
└── fill_log.parquet                    # 逐笔成交记录
    schema: trade_date, fill_id, order_id, instrument_id, direction,
            filled_quantity, fill_price, fee, slippage, fill_reason,
            event_time, cumulative_quantity, leaves_quantity
```

---

## 9. 模块布局

### 9.1 Core 层新增模块

```
ditto_core/
├── quality/              # [已有] 数据质量引擎
├── engine/               # [已有] 表达式编译器 / 因子定义 / 因子评估 / 物化模型
│
├── accounting/           # [Phase 0] 共享账户契约层（纯数据结构，无 I/O）
│   ├── __init__.py
│   ├── position.py       #   Position
│   ├── cash.py           #   CashBook / CashProvider Protocol
│   ├── order_book.py     #   OrderBook / OrderTicket / OrderEvent / StateTransitionError
│   ├── account.py        #   Account / AccountView
│   └── buying_power.py   #   BuyingPowerModel Protocol / CashAccountBuyingPower
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
│       └── templates/
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
│   ├── orders.py         #   Order / OrderType / OrderDirection
│   ├── fills.py          #   FillEvent
│   ├── planner.py        #   ExecutionPlanner 实现 / ExecutionPlan / BlockedOrder
│   ├── brokerage.py      #   Brokerage Protocol / BacktestBrokerage
│   ├── trade_builder.py  #   TradeBuilder Protocol / FifoTradeBuilder / TradeRecord
│   ├── reality/          #   Reality Model（可插拔）
│   │   ├── fill.py       #     FillModel / AShareFillModel / ClosingAuctionFillModel
│   │   ├── slippage.py   #     SlippageModel / FixedBpsSlippage / VolumeShareSlippage
│   │   ├── fee.py        #     FeeModel / AShareFeeModel
│   │   └── settlement.py #     SettlementModel / AShareSettlementModel
│   └── rules.py          #   InstrumentDefinition / TradingRuleSet / FeeSchedule（数据对象）
│
├── backtest/             # [Phase 3-4] 回测引擎（编排层，持有 Account 实例）
│   ├── engine.py         #   EngineLoop / EngineConfig / EngineResult
│   ├── data_feed.py      #   DataFeed Protocol / ParquetDataFeed
│   ├── risk/
│   │   ├── pre_trade.py  #   PreTradeRiskCheck / CompositePreTradeCheck / 内置规则
│   │   └── post_trade.py #   PostTradeRiskGuard / 内置规则
│   └── stats/            #   统计体系
│       ├── collector.py  #     StatsCollector / BacktestReport
│       ├── trade.py      #     TradeStatistics
│       ├── portfolio.py  #     PortfolioStatistics
│       └── alpha.py      #     AlphaStatistics
```

### 9.2 模块间依赖关系（v2 修订）

```
accounting  ←── 无 Core 依赖（最底层，纯数据结构）
strategy    ←── 无外部 Core 依赖（纯决策逻辑）
portfolio   ←── strategy（消费 TargetPortfolio）
execution   ←── accounting + portfolio（通过 AccountView，不依赖 backtest）
backtest    ←── strategy + execution + accounting（持有 Account 实例，state owner）
```

关键依赖规则：

- `accounting` 是最底层契约，不依赖任何其他 Core 模块
- `strategy` 不依赖 `portfolio` / `execution` / `backtest`（决策层最纯净）
- `portfolio` 只依赖 `strategy`（组合构建消费决策结果）
- `execution` 只依赖 `accounting` + `portfolio`（不依赖 backtest）
- `backtest` 是编排层，持有 Account 实例，依赖 strategy + execution + accounting
- 所有模块共享 `engine/evaluation/metrics/_math.py` 中的数学公式

### 9.3 DataHub / Port 新增

```
DataHub 新增:
├── services/strategy/
│   ├── strategy_catalog_service.py     # 策略 spec/version 元数据
│   ├── strategy_artifact_service.py    # artifact 持久化
│   └── instrument_rule_provider.py     # InstrumentDefinition / TradingRuleSet / FeeSchedule 组装
├── stores/metadata/
│   └── trading_rule_store.py           # PIT 版本化的交易规则存储
└── stores/metadata/
    └── fee_schedule_store.py           # PIT 版本化的费率存储

Port 新增:
├── services/strategy/
│   ├── strategy_run_service.py         # RESEARCH/RECOMMENDATION 编排
│   ├── backtest_service.py             # BACKTEST 编排（调用 EngineLoop）
│   └── strategy_input_assembler.py     # StrategyInputBundle 组装
```

---

## 10. 测试策略

### 10.1 测试类型总览

| 测试类型 | 适用对象 | 方法 | 示例 |
|---------|---------|------|------|
| 快照测试 | EngineLoop、Stats | 固定输入 → 固定输出 | 3 日快照 NAV = 1,003,210.50 |
| 不变量测试 | Account、CashBook、OrderBook | 状态机合法性 | 不超卖、现金守恒、终态不可逆 |
| 场景矩阵 | FillModel、FeeModel、Settlement | 参数化组合 | 涨跌停 × 买卖 × Market/Limit |
| 属性测试 | PortfolioStatistics | 数值范围 | NAV > 0, max_drawdown <= 0 |

### 10.2 测试分层

```
tests/
├── unit/                   # 单元测试（纯函数，无 I/O）
│   ├── accounting/         #   Position / CashBook / OrderBook 状态机
│   ├── strategy/           #   Pipeline 各阶段 / Spec 校验 / 模板
│   ├── portfolio/          #   Allocator / Sizer / Constraint
│   ├── execution/          #   Order / FillEvent / FillModel / FeeModel / SettlementModel
│   └── backtest/           #   PreTrade / PostTrade / Stats 计算公式
│
├── integration/            # 集成测试（需要 Parquet 数据）
│   ├── strategy/           #   端到端 Pipeline（输入 bundle → 输出 TargetPortfolio）
│   └── backtest/           #   完整引擎步进（3-5 个交易日的快照测试）
│
└── snapshot/               # 快照测试（输出稳定性）
    └── backtest/           #   回测引擎输出 artifact 不变
```

### 10.3 各模块测试重点

**accounting/ — 不变量测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| CashBook | 现金守恒 | fill 前后净值差异 = 费用 |
| OrderBook | 终态不可逆 | FILLED → CANCEL 抛 StateTransitionError |
| OrderBook | Fill 幂等性 | 同一 fill 重复 apply 不改变状态 |
| Account | 不超卖 | 卖出数量 <= available_quantity |
| Account | T+1 冻结 | 买入当日 available_quantity 不变 |

```python
def test_cash_conservation():
    """现金守恒：fill 前后净值差异等于费用"""
    account = Account(...)
    nav_before = account.get_view().total_value
    for fill in fills:
        account.apply_fill(fill, rule)
    nav_after = account.get_view().total_value
    total_fees = sum(f.fee for f in fills)
    assert abs((nav_before - nav_after) - total_fees) < 0.01

def test_no_oversell():
    """不能超卖"""
    account = Account(...)
    sell_qty = 1000
    available = account.positions["159915.SZ"].available_quantity
    assert sell_qty <= available

def test_terminal_state_irreversible():
    """FILLED 订单不能被 CANCEL"""
    order_book = OrderBook()
    # ... fill order to FILLED state ...
    with pytest.raises(StateTransitionError):
        order_book.cancel(order_id)
```

**strategy/ — 纯函数测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| 每个 builtin stage | 参数化 + edge case | `top_k(k=0)`, `top_k(k>N)`, 空输入 |
| Scorer | 固定输入 → 期望输出 | `rank_then_combine` 的排名一致性 |
| ConstraintCheck | 优先级冲突 | 两约束同时违规时 priority 小的先执行 |
| Spec 校验 | 非法参数拒绝 | `param_constraint.min > max` 应报错 |
| StrategyTemplate | 实例化 → 合法 StrategySpec | 4 个模板各自输出合法 spec |

**execution/ — 场景矩阵测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| FillModel | 16 种场景矩阵 | 涨停/跌停/正常 × 买/卖 × Market/Limit × T+0/T+1 |
| FeeModel | 边界值 | 佣金 < 5 元时应取 5 元 |
| SettlementModel | T+0/T+1 判断 | 股票 ETF 当日买入次日可卖 |
| ExecutionPlanner | T+1 拦截 | 当日买入标的生成 SELL order 应被 block |
| 数量取整 | 100+1 规则 | 买入 50 → 100，买入 350 → 350（非 300） |
| 卖出零股 | 零股拆分 | 持仓 350 卖出 → 整手 300 + 零股 50 两笔订单 |
| OrderTicket 状态机 | 合法 + 非法转换 | NEW→FILLED ✅, FILLED→CANCELED ❌ |

**backtest/ — 快照测试 + 属性测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| EngineLoop | 3-5 日快照 | 固定输入 → 期望 NAV 序列和 TradeRecord |
| PreTrade | 拒单场景 | 购买力不足 → reject |
| PostTrade | 单规则触发 | 注入特定 AccountView → 期望 RiskAction |
| StatsCollector | 已知交易序列 | 固定 Fills → 期望 TradeStatistics |
| PortfolioStatistics | 属性测试 | NAV > 0, max_drawdown <= 0, annualized_return 合理 |

### 10.4 Reality Model 测试方法

A 股规则测试采用**场景矩阵**：

```python
@pytest.mark.parametrize("scenario", A_SHARE_FILL_SCENARIOS)
def test_fill_model_scenario(scenario):
    """场景矩阵覆盖 A 股规则的所有组合"""
    result = fill_model.fill(scenario.order, scenario.market, scenario.rule)
    assert result == scenario.expected
```

场景矩阵：
- 涨停 × 买/卖 × Market/Limit = 4 种
- 跌停 × 买/卖 × Market/Limit = 4 种
- 停牌 × 买/卖 = 2 种
- 正常 × Market/Limit/MarketOnClose = 3 种
- 集合竞价 × 正常/涨停/大额 = 3 种

---

## 11. Phase 规划

### 11.1 重组后的 Phase 规划

```
Phase 0:  基础语义与数据契约
  ┌─ accounting/（Account / AccountView / Position / CashBook / OrderBook）
  │   └─ BuyingPowerModel Protocol / CashProvider Protocol（预留）
  ├─ StrategySpec / StrategyRun / StrategyTemplate / StrategyVersion
  ├─ DecisionFrame schema 定义
  ├─ InstrumentDefinition / TradingRuleSet / FeeSchedule（三层规则数据对象）
  ├─ ParamConstraint 参数约束
  ├─ DataHub 控制面表（strategy_version / strategy_run / strategy_artifact）
  ├─ DataHub InstrumentRuleProvider（三层规则组装）
  └─ DataHub trading_rule_store + fee_schedule_store（PIT 版本化存储）
  📋 交付物：账户契约 + 三层规则 + 策略可定义/版本化/存储
  🎯 里程碑：accounting 层可测试 + 策略 spec CRUD + DRAFT/PUBLISHED 治理

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
  ├─ 简化 BacktestBrokerage（线性佣金 + 固定滑点，使用 Account）
  ├─ CashAccountBuyingPower 实现（V1 购买力模型）
  ├─ EngineLoop（日历步进 + 调仓触发，不含风控）
  ├─ ParquetDataFeed（从 artifact 加载历史数据）
  ├─ FillEvent / StatsCollector V1（NAV / PortfolioStats）
  ├─ FifoTradeBuilder V1（基础 FIFO 匹配）
  └─ etf_rotation 回测集成测试（快照测试 + 不变量测试）
  📋 交付物：完整回测闭环，但成本模型简化（不含涨跌停/T+1）
  🎯 里程碑：ETF 轮动策略 BACKTEST 闭环 + 基础统计报告

Phase 3:  Reality Model 完整化
  ┌─ AShareFillModel（涨跌停 / 停牌 / LIMIT / 集合竞价）
  ├─ AShareFeeModel（最低 5 元 / 印花税 / 过户费，按 FeeSchedule 区分）
  ├─ AShareSettlementModel（T+0/T+1 交收，按 TradingRuleSet 区分）
  ├─ VolumeShareSlippage
  ├─ ExecutionPlanner 完整化（T+1 预检 / 涨跌停预检 / 停牌过滤 / 100+1 规则）
  ├─ 规则版本化接入（trading_rule_store + fee_schedule_store PIT 查询）
  ├─ InstrumentLifecycle 基础（ST/*ST → price_limit_pct 动态变化）
  └─ 现有回测快照测试升级（Phase 2 的测试数据替换为含涨跌停/ST 场景）
  📋 交付物：回测引擎对 A 股规则完整建模（含规则版本化）
  🎯 里程碑：涨跌停/T+1/100+1/ST 场景的回测结果可信

Phase 4:  风控 + 统计完善
  ┌─ PreTradeRiskCheck + 6 条内置规则
  ├─ PostTradeRiskGuard + 4 条内置规则
  ├─ TradeStatistics + AlphaStats
  ├─ StrategyComparisonReport（baseline 对比）
  ├─ fill_log artifact（逐笔成交调试）
  └─ 风控集成测试
  📋 交付物：三层风控 + 完整三层统计 + 策略对比
  🎯 里程碑：回测报告可直接用于策略决策

Phase 5:  多策略模板扩展
  ┌─ etf_trend_swing 模板（regime overlay / vol_target / drawdown_scale）
  ├─ stock_selection_trend 模板（股票过滤链 / 停牌/ST/退市/lifecycle）
  ├─ stock_sector_rotation 模板（行业配置 + 行业内选股）
  ├─ inverse_vol allocator
  ├─ InstrumentDefinition 扩展（新股前 N 日 / 退市整理期）
  └─ 每个模板的回测快照测试
  📋 交付物：4 个策略模板全部可用，股票 lifecycle 完整建模
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
  ├─ 多策略资金预算
  ├─ MarginAccountBuyingPower（融资融券）
  ├─ PositionLot 多批次持仓（TradeBuilder 升级）
  └─ MultiCurrencyCashProvider（多币种）
  ┌─ OMS 模式（netting / hedging 持仓归并）
  └─ specs.py CalendarId 注册化（因子引擎+策略引擎共享日历服务）
```

### 11.2 关键路径

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5
                                                         ↕
                                              (Phase 4 依赖 Phase 3)
                                              (Phase 5 可与 Phase 4 并行)
```

Phase 0-2 是主线（打通从 spec 定义到回测结果的完整链路）。
Phase 3-4 是补强（A 股规则 + 风控，让回测结果可信）。
Phase 5 是扩展（更多策略模板）。

---

## 12. Artifact 与持久化

### 12.1 新增 Artifact 类型

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

### 12.2 Artifact 目录结构

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
│   schema: trade_date, fill_id, order_id, instrument_id, direction,
│           filled_quantity, fill_price, slippage, fee, fill_reason,
│           event_time, cumulative_quantity, leaves_quantity
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

### 12.3 控制面表

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

### 12.4 Manifest 结构

```python
@dataclass(frozen=True)
class RunManifest:
    run_id: str
    strategy_id: str
    strategy_version: int
    mode: EngineMode                     # v2: BACKTEST / LIVE（不再含 RESEARCH/RECOMMENDATION）
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

### 12.5 与现有 DataHub 的集成

执行层和统计层的 artifact 走同一条持久化路径——通过 `StrategyArtifactService` 落盘，通过 `strategy_artifact` 表索引。不新建独立的 artifact 管理。

新增的 artifact 只是 `artifact_kind` 枚举的新值，不需要新建表或新的 service 接口。

---

## 附录 A：业界对标参考

### A.1 QuantConnect LEAN 关键设计

- `BrokerageModel` 是策略中心，通过 `GetFillModel(Security)` / `GetFeeModel(Security)` 按资产类型分发
- `SecurityInitializer` 将 BrokerageModel 策略绑定到每个 Security
- 交易规则（手数、涨跌停等）存在 `Security.SymbolProperties`，不在 BrokerageModel 上
- `TradeBuilder` 支持 FIFO / FIFOV / LIFO / FlatToFlat 多种匹配方法
- 参考：https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/key-concepts
- 源码：https://github.com/QuantConnect/Lean/blob/master/Common/Brokerages/DefaultBrokerageModel.cs

### A.2 NautilusTrader 关键设计

- `Instrument` 是纯数据对象，引擎完全不感知资产类型
- Rust 核心提供确定性事件驱动运行时
- `RiskEngine` 提供 pre-trade 和 post-trade 双层风控
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

---

## 附录 B：现有内核评估与升级路线

### B.1 评估总览

| 模块 | 完成度 | 策略引擎可复用性 | V1 阻塞 |
|------|--------|-----------------|---------|
| 表达式编译器 (expression/) | 95% | 因子计算可复用 | 不阻塞（策略 pipeline 走独立路径） |
| 因子评估 (evaluation/metrics/) | 95% | `_math.py` 纯数学可复用 | 不阻塞 |
| 物化模型 (materialization/) | 85% | artifact-first 模式直接复用 | 不阻塞 |
| DataHub PIT 基础设施 | 90% | 规则版本化的天然基座 | 不阻塞 |
| InstrumentId 分配 (8 大资产类别) | 90% | ID 空间已预留 | 不阻塞 |
| 四级标识符体系 | 85% | source/standard/instrument/ticker | 不阻塞 |
| InstrumentRegistration + Extension | 70% | InstrumentDefinition 的数据源 | 不阻塞（需补充字段） |
| specs.py (CalendarId/GrainId) | 60% | CalendarId="cn_stock" 硬编码 | **P2 不阻塞**（策略不走因子编译） |

### B.2 specs.py 硬编码清单

文件：`packages/core/src/ditto_core/engine/specs.py`

| # | 硬编码 | 行号 | 影响范围 | V1 阻塞 | 升级时机 |
|---|--------|------|---------|---------|---------|
| 1 | `CalendarId = Literal["cn_stock"]` | L11 | 日历服务假设单市场 | 不阻塞 | Phase 8（多市场/多币种） |
| 2 | `GrainId = Literal["1d", "1m"]`，1m 未实现 | L12 | 策略引擎只用 1d | 不阻塞 | Phase 8（分钟级） |
| 3 | `entity_keys` 单键硬校验 | L111-115 | 复合键被 reject | 不阻塞 | 按需 |
| 4 | `CALENDAR_TO_TIMEZONE` 只有一条 | L50-52 | 只支持 cn_stock | 不阻塞 | Phase 8 |

**关键判断**：策略引擎的 decision pipeline **不走 DerivedSpec/表达式编译器**。策略的 Universe/Signal/Score 是独立的 Python pipeline，不是表达式 AST。specs.py 的硬编码不会阻塞策略引擎 V1。

### B.3 runtime_input.py 硬编码评估

文件：`apps/port/src/ditto_port/services/derived/runtime_input.py`

硬编码路径：`market.stock_daily`, `market.adj_factor`, `market.stock_status`, `etf.daily`

**V1 阻塞**：**不阻塞**。策略引擎通过 `DataFeed` Protocol 从 artifact 加载数据，不经过 runtime_input.py。DataFeed 实现由 ParquetDataFeed 从 artifact 目录读取。

### B.4 query_service.py 硬编码评估

文件：`packages/data/src/ditto_data/services/derived/query_service.py`

硬编码假设：`instrument_id.cast(pl.Int64)`, schema = `instrument_id + trade_date + value`

**V1 阻塞**：**不阻塞**。query_service 是 derived（因子计算）的查询层。策略引擎的统计层（NAV / TradeStats）输出为独立的 Parquet artifact，不走 query_service。

### B.5 evaluation/metrics/ 复用清单

文件：`packages/core/src/ditto_core/engine/evaluation/metrics/`

| 文件 | 内容 | 复用方式 |
|------|------|---------|
| `_math.py` | `scalar_to_float`, `two_sided_p_value`, `regularized_incomplete_beta`, `log_gamma`, `fit_ic_half_life` | **直接 import** |
| `portfolio.py` | sharpe/sortino/max_dd/calmar 计算逻辑（L119-196） | **抽取为独立函数后复用** |
| `portfolio.py` | `quantile_returns`, `long_short_returns`, `turnover`, `net_returns`, `turnover_adjusted_ir` | 不复用（因子语义） |
| `ic.py` | `pearson_ic`, `rank_ic`, `ic_summary`, `ic_decay`, `ic_autocorrelation` | 不复用（因子专用） |
| `factor_analysis.py` | `fama_macbeth`, `orthogonalize`, `performance_attribution` | 不复用（因子专用） |
| `tail_risk.py` | `tail_risk_metrics` | 可选复用（统计辅助） |
| `evaluator.py` | `FactorEvaluator`, `EvaluationConfig` | 不复用（编排层） |

### B.6 内核升级路线图

```
Phase 0 (策略引擎基础):
  ├── specs.py — 不动（策略引擎不走因子编译器）
  ├── evaluation — 复用 _math.py，不复用因子语义
  ├── InstrumentRegistration → InstrumentDefinition（补充 tick_size / currency / board_segment / lifecycle_state）
  └─ TradingRuleSet + FeeSchedule 的 PIT 表结构（复用现有 PIT 管道，零新基建）

Phase 2 (回测 V1):
  ├── BuyingPowerModel Protocol + CashAccountBuyingPower 实现
  └── CashProvider Protocol 预留（V1 CashBook 直接满足）

Phase 3 (Reality Model):
  ├── TradingRuleSet 接入 instrument_lifecycle 表（ST/*ST → price_limit_pct 动态变化）
  └── FeeSchedule 接入费率变更历史

Phase 5 (多策略模板):
  └── InstrumentDefinition 扩展（新股前 N 日 / 退市整理期）

Phase 8 (高级能力):
  ├── specs.py CalendarId 注册化（因子引擎+策略引擎共享日历服务）
  ├── MarginAccountBuyingPower（融资融券）
  ├── PositionLot 多批次持仓（TradeBuilder 升级）
  ├── MultiCurrencyCashProvider（多币种）
  └── OMS 模式（netting / hedging 持仓归并）
```

### B.7 现有内核资产可直接消费

以下内核资产**不需要任何修改**即可被策略引擎消费：

| 资产 | 位置 | 策略引擎用法 |
|------|------|------------|
| PIT 基础设施 | `.claude/rules/pit.md` | TradingRuleSet / FeeSchedule 版本化查询 |
| artifact-first 模式 | `engine/materialization/` | 策略 run artifact 持久化 |
| InstrumentIdRange | `datahub/models/common.py:262-398` | 8 大资产类别 ID 空间，已预留 futures/option |
| 四级标识符体系 | `datahub/sources/exchange_transformers.py` | standard_ticker ↔ source_ticker 双向转换 |
| resolve_source_ticker | `datahub/services/metadata/instrument.py:593-715` | PR #57 引入，支持多格式输入 |
| InstrumentRegistration | `datahub/models/metadata.py:113-143` | InstrumentDefinition 的数据来源 |
| InstrumentExtension | `datahub/models/metadata.py:67-106` | StockExtension.list_status → lifecycle_state |

**结论**：不需要另起炉灶。内核的硬编码（specs.py 等）集中在因子编译器路径，策略引擎走独立的 Python pipeline，不受影响。需要升级的是**数据模型**（三层规则 + BuyingPowerModel），是增量添加而非重构。
