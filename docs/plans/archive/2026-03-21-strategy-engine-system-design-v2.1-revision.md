# 策略引擎系统设计 v2.1 修订

**日期**: 2026-03-21
**基于**: v2 (2026-03-20-strategy-engine-system-design-v2.md)
**状态**: Approved — 基于 review 反馈修订
**目标**: 修复 v2 中 7 个阻塞点 + 4 项清理，使文档达到"可按文档直接开工"标准

---

## 修订摘要

| # | Finding | 优先级 | 影响章节 | 修复类型 |
|---|---------|--------|---------|---------|
| 1 | A 股 ETF 手数规则溯源 | 低 | 附录 / 交易规则文档 | 文档补强 |
| 2 | 调仓退出单漏规则 | **高** | §6.1 EngineLoop, §4.2 ExecutionPlanner | 逻辑修正 |
| 3 | 统计层使用成交前快照 | **高** | §6.1 EngineLoop, §8.4 StatsCollector | 逻辑修正 |
| 4 | PostTrade same-day re-entry | **中高** | §7.3 PostTrade, §2.1 Signal 生命周期 | 新增机制 |
| 5 | PreTrade 契约不完整 | **高** | §7.2 PreTrade, §3.5 AccountView | 接口重构 |
| 6 | CashBook 可变性矛盾 + 旧类型残留 | 中 | §3.3 CashBook, §3.5 Account, §5.4 | 类型修正 |
| 7 | RunManifest mode 语义分裂 | 低中 | §12.4 RunManifest | 类型拆分 |
| 8 | 零成交 FillEvent 语义污染 | 中 | §4.3 FillEvent, §5.3 FillModel | 语义修正 |
| 9 | CashProvider 等降级到 Backlog | 低 | §3.7 | 范围收敛 |
| 10 | 策略 control plane 标 greenfield | 低 | §9.3 DataHub | 标注修正 |
| 11 | RuleRefs 进 RunManifest（确定性回放） | **高** | §12.4 RunManifest | 治理面补强 |
| 12 | risk_log 一级 artifact | 中 | §12 Artifact | 治理面补强 |

---

## R1: A 股 ETF 手数规则溯源（Finding 1）

**v2 现状**: §4.2 round_buy_quantity 逻辑正确，但缺乏政策文件溯源。

**v2.1 修订**: 在 A 股交易规则参考文档中补充公告文号。

```markdown
### 3.2 "100+1" 规则

**政策来源**：
- 上交所：《关于优化主板交易制度的通知》（2023-07-21），2023-08-28 起实施
- 深交所：《关于优化交易制度的通知》（2023-07-21），2023-08-28 起实施
- 适用范围：主板股票、ETF、其他在上交所/深交所交易的证券

**规则内容**：
- 买入：最低 100 份起，可以 1 份为单位递增（101、250、1234 均可）
- 卖出零股：不足 100 份的零股必须一次性全部卖出，不得拆分
- 送股/配股产生的零股：可单独一次性申报卖出，或与整手部分一并申报卖出
```

v2 §4.2 的 `round_buy_quantity` 和 `round_sell_quantity` **逻辑无需改动**。

---

## R2: 调仓退出单漏规则（Finding 2）

**v2 现状**: §6.1 _step 只对 `target.instrument_ids` 拉规则，退出标的（当前持有但 target 中没有的）缺规则，导致 ExecutionPlanner 无法对退出标的做涨跌停预检和手数校验。

**v2.1 修订**: rules 加载合并三个来源。

```python
def _step(self, date: str) -> None:
    slice = self.data_feed.get_slice(date)
    account_view = self.brokerage.get_account()

    # 1. PostTrade 扫描
    risk_actions = self.post_trade_guard.scan(account_view, slice)
    if risk_actions:
        self._execute_risk_actions(risk_actions, slice)
        account_view = self.brokerage.get_account()

    # 2. 调仓日 → 执行决策 Pipeline
    if self._is_rebalance_day(date):
        target = self.pipeline.run(self._context, slice)

        # R2 修复：合并 target + 当前持仓 + pending orders
        all_instruments = (
            set(target.instrument_ids)
            | set(account_view.positions.keys())
            | self._pending_order_instrument_ids()
        )
        rules = self.rule_provider.get_rules(date, list(all_instruments))

        plan = self.planner.plan(
            target, account_view, slice, date, rules=rules,
        )
        # ... PreTrade + place_order ...

    # 3. 推进成交
    fills = self.brokerage.process_pending(slice)

    # 4. 刷新快照后统计（R3 修复）
    account_view = self.brokerage.get_account()
    self.stats_collector.record(date, fills, account_view, slice)
```

**辅助方法**（新增）：

```python
def _pending_order_instrument_ids(self) -> set[str]:
    """从 Brokerage 的 OrderBook 提取 pending 订单涉及的 instrument_ids"""
    tickets = self.brokerage.get_account().order_book.get_pending()
    return {t.order.instrument_id for t in tickets}
```

§4.2 ExecutionPlanner 补充说明：

> ExecutionPlanner 的 diff 计算范围包括 **current positions 中所有非空仓标的**，不仅仅是 `target.instrument_ids`。退出标的（`position.quantity > 0` 且不在 target 中）应生成全部卖出指令。Planner 依赖 `rules` 字典提供这些标的的交易规则。

---

## R3: 统计层使用成交前快照（Finding 3）

**v2 现状**: §6.1 _step 在 L777 取快照，L811 执行成交，L814 统计用旧快照。导致 NAV/exposure 滞后一个 step。

**v2.1 修订**: 在 `process_pending` 之后重新取快照再统计。

```python
# R3 修复：统计前刷新快照
fills = self.brokerage.process_pending(slice)
account_view = self.brokerage.get_account()  # 刷新为成交后状态
self.stats_collector.record(date, fills, account_view, slice)
```

§8.4 StatsCollector.record 补充注释：

```python
def record(
    self,
    date: str,
    fills: tuple[FillEvent, ...],
    account_view: AccountView,  # 必须是成交后的快照
    slice: Slice,
) -> None:
    for fill in fills:
        self._trade_builder.on_fill(fill, account_view)
    self._nav_series.append((date, account_view.nav))
```

§6.1 补充说明：

> `_execute_risk_actions` 产生的订单通过 `Brokerage.place_order` 提交，与其他订单一起在 `process_pending` 中被统一推进和成交。统计层在 `process_pending` 之后统一刷新快照并记录，确保所有 fills（包括风险动作产生的）都被纳入。

---

## R4: PostTrade same-day re-entry（Finding 4）

**v2 现状**: PostTrade 执行风险动作（如清仓某标的）后，当日调仓 Pipeline 又把标的选回来，风险动作无效。

**v2.1 修订**: 引入 `RiskLock` 机制，当日 step 内阻断被风险动作影响的标的。

### R4.1 StrategyContext 增加 risk_locked

```python
@dataclass
class StrategyContext:
    # ... 现有字段 ...
    risk_locked_instruments: dict[str, str] = field(default_factory=dict)
    # key = instrument_id, value = lock_reason

    def lock_instrument(self, instrument_id: str, reason: str) -> None:
        self.risk_locked_instruments[instrument_id] = reason

    def is_locked(self, instrument_id: str) -> bool:
        return instrument_id in self.risk_locked_instruments

    def clear_locks(self) -> None:
        self.risk_locked_instruments.clear()
```

### R4.2 _execute_risk_actions 标记锁定

```python
def _execute_risk_actions(
    self, actions: list[RiskAction], slice: Slice,
) -> None:
    for action in actions:
        if action.instrument_id and action.action_type != RiskActionType.ALERT:
            self.brokerage.place_order(self._build_risk_order(action))
            # 当日锁定 — Pipeline 不会再选入
            self._context.lock_instrument(action.instrument_id, action.reason)
```

### R4.3 Pipeline Filter 阶段读取锁定

```python
# builtins/filtering.py 新增内置 filter
class RiskLockFilter(DecisionStage):
    """过滤被风险动作锁定的标的 — 由 EngineLoop 自动注入"""
    def process(self, frame: DecisionFrame, context: StrategyContext) -> DecisionFrame:
        locked = context.risk_locked_instruments
        if not locked:
            return frame
        return frame.filter(
            ~pl.col("instrument_id").is_in(list(locked.keys()))
        )
```

### R4.4 锁定生命周期

```python
def _step(self, date: str) -> None:
    # 每个 step 开始时清除上日锁定
    self._context.clear_locks()
    # ... 后续 PostTrade / Pipeline / Execution ...
```

§7.3 PostTradeRiskGuard 补充说明：

> 当 PostTrade 触发非 ALERT 的风险动作时，受影响的标的会被加入当日 `RiskLock`。Pipeline 的 Filter 阶段（`RiskLockFilter`）自动排除被锁定的标的。锁定在每个 step 开始时自动清除，不跨日持久化。
>
> **冷却期**（如连续 N 日锁定）由 PostTradeRiskGuard 的内部状态管理，V1 不实现。V2+ 可通过 `cooldown_until_date` 字段扩展 RiskAction，让 `_execute_risk_actions` 设置跨日锁定。

---

## R5: PreTrade 契约不完整（Finding 5）

**v2 现状**: §7.2 PreTradeRiskCheck 接口只有 order/account/pending_orders，但规则需要 MarketSnapshot（价格合法性）、InstrumentDefinition（手数）、FeeSchedule + BuyingPowerModel（购买力）。AccountView 也不暴露 order book。

**v2.1 修订**: 引入 `PreTradeContext` + AccountView 补充 OrderBook。

### R5.1 PreTradeContext

```python
@dataclass(frozen=True)
class PreTradeContext:
    """PreTrade 校验所需的完整只读上下文 — 在每个 step 开始时组装一次"""
    account_view: AccountView
    slice: Slice
    rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]
    buying_power_model: BuyingPowerModel
    fee_model: FeeModel
    pending_tickets: tuple[OrderTicket, ...]
```

### R5.2 PreTradeRiskCheck 新签名

```python
class PreTradeRiskCheck(Protocol):
    """订单提交前逐单校验 — 在 Brokerage.place_order() 之前"""
    def check_order(
        self, order: Order, context: PreTradeContext,
    ) -> OrderCheckResult: ...
```

每条规则从 PreTradeContext 获取所需数据：

| 规则 | 从 PreTradeContext 获取 |
|------|----------------------|
| `buying_power` | `context.buying_power_model.available_buying_power(...)` + `context.fee_model.estimate(...)` |
| `no_short_sell` | `context.account_view.positions[id].available_quantity` |
| `price_validity` | `context.slice.bars[id].limit_up / limit_down` |
| `lot_size` | `context.rules[id][0].lot_size` (InstrumentDefinition) |
| `concentration_pre` | `context.account_view.total_value` |
| `daily_turnover_pre` | `context.pending_tickets` 累计金额 |

### R5.3 AccountView 补充 OrderBook

```python
class OrderBookReadOnly:
    """OrderBook 的只读视图 — 供 AccountView 暴露"""
    def get(self, order_id: str) -> OrderTicket | None: ...
    def get_pending(self) -> tuple[OrderTicket, ...]: ...

@dataclass(frozen=True)
class AccountView:
    """只读账户快照"""
    positions: Mapping[str, Position]
    cash: CashBook                      # frozen (R6 修正)
    total_value: float
    nav: float
    exposure: float
    pending_buy_value: float
    order_book: OrderBookReadOnly       # R5 新增
```

### R5.4 EngineLoop 组装 PreTradeContext

```python
class EngineLoop:
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
        buying_power_model: BuyingPowerModel,   # R5 新增
        fee_model: FeeModel,                     # R5 新增
    ): ...

    def _build_pre_trade_context(
        self,
        account_view: AccountView,
        slice: Slice,
        rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]],
    ) -> PreTradeContext:
        return PreTradeContext(
            account_view=account_view,
            slice=slice,
            rules=rules,
            buying_power_model=self._buying_power_model,
            fee_model=self._fee_model,
            pending_tickets=account_view.order_book.get_pending(),
        )
```

`_step` 中调用：

```python
if self._is_rebalance_day(date):
    target = self.pipeline.run(self._context, slice)
    rules = self.rule_provider.get_rules(date, list(all_instruments))
    plan = self.planner.plan(target, account_view, slice, date, rules=rules)

    pre_trade_ctx = self._build_pre_trade_context(account_view, slice, rules)

    checked_orders: list[Order] = []
    for order in plan.orders:
        result = self.pre_trade_check.check_order(order, pre_trade_ctx)
        if result.decision == "accept":
            checked_orders.append(order)
        elif result.decision == "resize" and result.resized_quantity:
            checked_orders.append(order.with_quantity(result.resized_quantity))
        # reject → 记录到 blocked，不提交

    for order in checked_orders:
        self.brokerage.place_order(order)
```

### R5.5 CompositePreTradeCheck 更新

```python
class CompositePreTradeCheck(PreTradeRiskCheck):
    """组合多个 PreTrade 规则，按顺序执行，首个 reject/resize 终止"""
    def __init__(self, checks: tuple[PreTradeRiskCheck, ...]): ...

    def check_order(
        self, order: Order, context: PreTradeContext,
    ) -> OrderCheckResult:
        for check in self._checks:
            result = check.check_order(order, context)
            if result.decision != "accept":
                return result
        return OrderCheckResult(decision="accept", order_id=order.order_id)
```

---

## R6: 只读快照/类型清理（Finding 6）

**v2 现状**: CashBook 是可变 dataclass，放在 frozen AccountView 中只做浅冻结；Account.apply_fill 和 ClosingAuctionFillModel 还在用旧 InstrumentRule 类型。

**v2.1 修订**:

### R6.1 CashBook 改为 frozen

```python
@dataclass(frozen=True)
class CashBook:
    """现金账户（不可变）"""
    available: float      # 可用现金（扣除冻结）
    settled: float        # 已交收（可提现）
    frozen: float         # 冻结金额（待交收/待成交）
```

Account 内部替换 cash 引用：

```python
@dataclass
class Account:
    """可变账户状态 — state owner (Brokerage) 持有此实例"""
    positions: dict[str, Position]
    _cash: CashBook               # 内部持有
    order_book: OrderBook

    @property
    def cash(self) -> CashBook:
        return self._cash

    def apply_fill(
        self,
        fill: FillEvent,
        definition: InstrumentDefinition,    # R6.2 修正
        trading_rule: TradingRuleSet,        # R6.2 修正
        fee_schedule: FeeSchedule,           # R6.2 修正
    ) -> None:
        # 创建新的 CashBook 而非修改原对象
        new_available = self._cash.available - fill.fee
        self._cash = CashBook(
            available=new_available,
            settled=self._cash.settled,
            frozen=self._cash.frozen,
        )
        # ... position 更新逻辑 ...

    def get_view(self) -> AccountView:
        return AccountView(
            positions=MappingProxyType(self.positions),
            cash=self._cash,              # frozen，安全引用
            total_value=self._calc_total_value(),
            nav=self._calc_nav(),
            exposure=self._calc_exposure(),
            pending_buy_value=self._calc_pending_buy_value(),
            order_book=self.order_book.readonly_view(),  # R5.3
        )
```

### R6.2 InstrumentRule → 三层分离

`Account.apply_fill` 和 `ClosingAuctionFillModel` 签名统一改为：

```python
# Account.apply_fill
def apply_fill(
    self,
    fill: FillEvent,
    definition: InstrumentDefinition,
    trading_rule: TradingRuleSet,
    fee_schedule: FeeSchedule,
) -> None: ...

# ClosingAuctionFillModel.fill
def fill(
    self, order: Order, market: MarketSnapshot,
    definition: InstrumentDefinition,
    trading_rule: TradingRuleSet,
) -> FillEvent: ...
```

v2 全文搜索 `InstrumentRule`，除 §5.1.4 的 V1 兼容策略说明外，其余全部替换。V1 兼容说明补充注释：

> Phase 2 简化阶段可使用合并的 `InstrumentRule` dataclass 作为过渡。Phase 3 完整化时拆分为三层。所有新代码必须使用三层分离签名。

---

## R7: RunManifest mode 语义分裂（Finding 7）

**v2 现状**: RESEARCH/RECOMMENDATION 移到 Port 层，但 §12.4 RunManifest.mode 仍用 EngineMode(BACKTEST/LIVE)，导致 RESEARCH/RECOMMENDATION 模式无法产出 manifest。

**v2.1 修订**: 引入 `RunMode`（artifact 管理）与 `EngineMode`（引擎内部）分离。

```python
class RunMode(StrEnum):
    """运行模式 — 面向 artifact 管理和持久化"""
    RESEARCH = "research"
    RECOMMENDATION = "recommendation"
    BACKTEST = "backtest"
    LIVE = "live"

class EngineMode(StrEnum):
    """引擎模式 — 面向 EngineLoop 内部逻辑"""
    BACKTEST = "backtest"
    LIVE = "live"
```

```python
@dataclass(frozen=True)
class RunManifest:
    run_id: str
    strategy_id: str
    strategy_version: int
    mode: RunMode                       # 改为 RunMode
    input_refs: tuple[StrategyInputRef, ...]
    parameter_overrides: dict[str, object]
    artifacts: tuple[ArtifactEntry, ...]
    config_hash: str
    engine_version: str
    created_at: str
```

映射关系：

| RunMode | 编排位置 | EngineMode |
|---------|---------|------------|
| RESEARCH | Port / StrategyRunService | N/A（不经过 EngineLoop） |
| RECOMMENDATION | Port / StrategyRunService | N/A |
| BACKTEST | Port / BacktestService → EngineLoop | BACKTEST |
| LIVE | Port / LiveService → EngineLoop | LIVE |

BacktestService/LiveService 映射：`RunMode(engine_config.mode.value)`。

---

## R8: 零成交 FillEvent 语义修正（Finding 8）

**v2 现状**: §4.3 FillEvent.fill_reason 包含 "suspended" / "deferred" / "insufficient_auction" 等零成交情况，但零成交不应产生 FillEvent——它会污染 TradeBuilder 的统计逻辑。

**v2.1 修订**: FillModel 在不成交时返回 None，不成交原因通过 OrderEvent 记录。

### R8.1 FillModel 返回类型

```python
class FillModel(Protocol):
    def fill(
        self, order: Order, market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillEvent | None:
        """成交返回 FillEvent，不成交返回 None"""
        ...
```

FillEvent 移除 `fill_reason` 字段（不成交语义不再需要）：

```python
@dataclass(frozen=True)
class FillEvent:
    """单次成交事件 — Brokerage 产出（仅在确实成交时产生）"""
    fill_id: str
    order_id: str
    instrument_id: str
    direction: OrderDirection
    filled_quantity: int
    fill_price: float
    fee: float
    slippage: float
    event_time: datetime
    cumulative_quantity: int
    leaves_quantity: int
```

### R8.2 不成交通过 OrderEvent 表达

```python
@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    status: OrderStatus
    fill_price: float | None = None
    fill_quantity: int = 0
    fee: float = 0.0
    message: str | None = None       # "suspended" / "limit_up_deferred" / "limit_down_deferred"
    timestamp: datetime
```

### R8.3 BacktestBrokerage.process_pending 处理

```python
def process_pending(self, slice: Slice) -> tuple[FillEvent, ...]:
    fills: list[FillEvent] = []
    for ticket in self._account.order_book.get_pending():
        market = slice.bars.get(ticket.order.instrument_id)
        if market is None:
            continue
        definition, trading_rule, fee_schedule = self._get_rules(ticket.order.instrument_id, slice.trade_date)

        fill = self._fill_model.fill(ticket.order, market, definition, trading_rule)
        if fill is not None:
            # 成交 — 产生 FillEvent + 更新 OrderTicket 状态
            self._account.apply_fill(fill, definition, trading_rule, fee_schedule)
            new_status = (
                OrderStatus.PARTIALLY_FILLED
                if fill.leaves_quantity > 0
                else OrderStatus.FILLED
            )
            self._account.order_book.update(OrderEvent(
                order_id=fill.order_id,
                status=new_status,
                fill_price=fill.fill_price,
                fill_quantity=fill.filled_quantity,
                fee=fill.fee,
                timestamp=fill.event_time,
            ))
            fills.append(fill)
        else:
            # 不成交 — 记录原因到 OrderEvent，不产生 FillEvent
            reason = self._fill_model.last_rejection_reason(ticket.order, market)
            self._account.order_book.update(OrderEvent(
                order_id=ticket.order.order_id,
                status=OrderStatus.SUBMITTED,   # 保持待成交
                message=reason,
                timestamp=datetime.now(),
            ))
    return tuple(fills)
```

---

## R9: 范围收敛（Finding 9 — 待补/删除）

### R9.1 删除 CashProvider Protocol

v2 §3.7 的 CashProvider Protocol 删除。V1 只保留 CashBook + CashAccountBuyingPower。

CashBook 即 V1 的现金实现，不需要 Protocol 抽象。多币种支持推迟到 Phase 8（RunManifest 已有 `currency` 字段预留）。

### R9.2 V2+ Backlog 标注

以下内容从 v2 正文移到 Backlog 附录，不阻塞 V1 实现：

| 内容 | 原位置 | 降级为 |
|------|--------|--------|
| CashProvider Protocol | §3.7 | 删除（V1 不需要） |
| MarginAccountBuyingPower | §3.6 注释 | Backlog Phase 8 |
| FuturesBuyingPower | §3.6 注释 | Backlog Phase 8 |
| MultiCurrencyCashProvider | §11.1 Phase 8 | Backlog Phase 8 |
| OMS 模式 | §11.1 Phase 8 | Backlog Phase 8 |

---

## R10: 策略 control plane 标 greenfield（Finding 10）

**v2 现状**: 多处写 strategy_run / strategy_artifact "沿用现有"，但代码中只有 derived artifact 基建，没有策略控制面实现。

**v2.1 修订**: §9.3 DataHub 新增部分标注实际状态。

```markdown
DataHub 新增:
├── services/strategy/
│   ├── strategy_catalog_service.py     # **Greenfield** — 现有 derived artifact 服务不覆盖策略 spec 管理
│   ├── strategy_artifact_service.py    # **Greenfield** — 现有 artifact 基建提供持久化原语，策略 artifact 生命周期需新建
│   └── instrument_rule_provider.py     # 基于现有 InstrumentRegistration + Extension 组装（增量）
├── stores/metadata/
│   └── trading_rule_store.py           # 基于现有 PIT 基建（增量）
└── stores/metadata/
    └── fee_schedule_store.py           # 基于现有 PIT 基建（增量）
```

### 归档旧 README

- `packages/core/src/ditto_core/strategy/README.md` — 描述的 OOP Strategy(DataHub) 体系与 v2 Pipeline 函数式风格冲突 → 归档到 `docs/archive/`
- `packages/core/src/ditto_core/portfolio/README.md` — 描述的 PortfolioManager OOP 体系与 v2 冲突 → 归档到 `docs/archive/`

---

## R11: RuleRefs 进 RunManifest — 确定性回放（战略建议转化）

**来源**: 战略评审——"规则版本化做到比业界更强"+"确定性回放作为一级目标"

**v2 现状**: TradingRuleSet/FeeSchedule 已走 PIT（effective_from / effective_to），但 RunManifest 不记录实际使用的规则版本。相同 manifest + 相同输入理论上应得到相同输出，但缺少规则版本冻结，确定性回放无法保证。

**v2.1 修订**: RunManifest 增加 `rule_refs`，冻结每次 run 使用的规则快照。

### R11.1 RuleRef 数据结构

```python
@dataclass(frozen=True)
class RuleRef:
    """某次 run 中使用的规则版本快照"""
    instrument_id: str
    definition_version: str          # InstrumentDefinition 的 hash
    trading_rule_as_of: str          # TradingRuleSet 的 effective_from
    fee_schedule_as_of: str          # FeeSchedule 的 effective_from
```

### R11.2 RunManifest 新增字段

```python
@dataclass(frozen=True)
class RunManifest:
    run_id: str
    strategy_id: str
    strategy_version: int
    mode: RunMode
    input_refs: tuple[StrategyInputRef, ...]
    parameter_overrides: dict[str, object]
    rule_refs: tuple[RuleRef, ...]   # R11 新增
    artifacts: tuple[ArtifactEntry, ...]
    config_hash: str
    engine_version: str
    created_at: str
```

### R11.3 EngineLoop 中收集 RuleRefs

EngineLoop.run() 在所有 step 完成后，汇总本次 run 涉及的所有规则版本：

```python
def run(self) -> EngineResult:
    rule_ref_map: dict[str, RuleRef] = {}  # key = instrument_id

    for date in self._trading_days:
        self._step(date)
        # 收集当天使用的规则版本（去重，保留最新）
        for iid, (defn, rule, fee) in self._current_step_rules.items():
            rule_ref_map[iid] = RuleRef(
                instrument_id=iid,
                definition_version=self._hash_definition(defn),
                trading_rule_as_of=rule.as_of_date,
                fee_schedule_as_of=fee.as_of_date,
            )

    manifest = RunManifest(
        # ...
        rule_refs=tuple(rule_ref_map.values()),
    )
```

### R11.4 确定性回放验证

```python
def assert_reproducible(
    manifest_a: RunManifest, result_a: EngineResult,
    manifest_b: RunManifest, result_b: EngineResult,
) -> None:
    """验证两个 run 在输入 + 规则 + 配置一致时，输出完全一致"""
    assert manifest_a.config_hash == manifest_b.config_hash
    assert manifest_a.input_refs == manifest_b.input_refs
    assert manifest_a.rule_refs == manifest_b.rule_refs
    assert manifest_a.parameter_overrides == manifest_b.parameter_overrides
    # 以上一致 → 以下必须完全相同
    assert result_a.final_nav == result_b.final_nav
    assert result_a.fill_log == result_b.fill_log
    assert result_a.nav_series == result_b.nav_series
```

这个断言应作为回测的**集成测试**，确保引擎升级不破坏确定性。

---

## R12: risk_log 一级 artifact（战略建议转化）

**来源**: 战略评审——"fill_log/order_log/risk_log/decision_log 视为一级 artifact，不是调试附件"

**v2 现状**: `fill_log` 和 `order_log` 已是一级 artifact，但 PostTrade 风控扫描结果没有持久化。风控只产生即时 RiskAction，不留审计痕迹。

**v2.1 修订**: 新增 `risk_log.parquet` 一级 artifact。

### R12.1 数据结构

```python
@dataclass(frozen=True)
class RiskScanRecord:
    """单次 PostTrade 扫描记录"""
    trade_date: str
    rule_id: str
    instrument_id: str | None       # None 表示组合级规则（如 max_drawdown）
    severity: RiskSeverity
    action_taken: RiskActionType | None  # None 表示仅告警，未执行动作
    detail: str                     # 人类可读描述
    current_value: float | None     # 触发时的实际值（如当前回撤 = -12.3%）
    threshold: float | None         # 规则阈值（如 max_drawdown = -15%）
```

### R12.2 StatsCollector 扩展

```python
class StatsCollector:
    def record_risk_scan(
        self, date: str, results: tuple[RiskScanRecord, ...],
    ) -> None:
        self._risk_log.extend(results)

    def build_report(self) -> BacktestReport:
        # ...
        risk_log = self._risk_log  # 写入 artifact
```

### R12.3 Artifact 目录新增

```
├── risk_log.parquet           # [PostTrade] 风控扫描记录（一级 artifact）
│   schema: trade_date, rule_id, instrument_id, severity, action_taken, detail,
│           current_value, threshold
```

ArtifactKind 枚举新增：

```python
class ArtifactKind(StrEnum):
    # ... 现有 ...
    RISK_LOG = "risk_log"
```

---

## v3 远景规划：量化语义系统 + 可审计执行系统

以下内容不阻塞 v2.1 和 Phase 0-5，作为 v3 架构升级的方向性规划。

### v3 核心升级目标

> 不是"能跑回测的策略引擎"，而是：
> **一个以 PIT 正确性、事件可回放、决策可解释、规则可审计 为核心的策略操作系统。**

### v3.1 事件账本架构（替代可变 Account）

**现状（v2.1）**：Account 是可变对象（Brokerage 持有），AccountView 是 frozen snapshot。状态变更直接发生，不记录变更原因。

**v3 目标**：Account 变成 `AccountSnapshot`，由事件流 projection 得出。

```python
# 事件基类
class AccountEvent:
    event_id: str
    timestamp: datetime
    run_id: str

# 状态变更事件
class OrderAccepted(AccountEvent): order_id: str; instrument_id: str; direction: OrderDirection; quantity: int
class OrderRejected(AccountEvent): order_id: str; reason: str
class FillReceived(AccountEvent): fill: FillEvent
class CashDebited(AccountEvent): amount: float; reason: str
class CashSettled(AccountEvent): amount: float; settle_date: str
class PositionUnlocked(AccountEvent): instrument_id: str; quantity: int; unlock_date: str
class RiskTriggered(AccountEvent): action: RiskAction
class RiskLockApplied(AccountEvent): instrument_id: str; reason: str; cooldown_until: str | None
```

```python
class EventStore:
    """事件账本 — 真正的 source of truth"""
    def append(self, event: AccountEvent) -> None: ...
    def get_events(self, run_id: str) -> tuple[AccountEvent, ...]: ...
    def get_events(self, run_id: str, date: str) -> tuple[AccountEvent, ...]: ...

class AccountProjector:
    """从事件流重建 AccountSnapshot"""
    def project(self, events: tuple[AccountEvent, ...]) -> AccountSnapshot: ...
```

**迁移路径**：
1. v2.1 阶段：所有状态变更方法保持"输入 → 输出"签名风格（apply_fill 接收 FillEvent，mark_to_market 接收 Slice），不原地修改返回值
2. v3 阶段：Account.apply_fill → EventStore.append(FillReceived(...)) + AccountProjector.project()
3. AccountView → AccountSnapshot（语义更准确，但类型结构不变）

**收益**：
- 完美可审计：每个状态变更都有对应事件，可追溯"为什么变成这样"
- 完美可回放：重放事件流 = 重建任意时刻的账户状态
- 完美可 diff：两个 run 的事件流 diff = 精确的状态差异定位

### v3.2 StateDiffReport — 研究-治理闭环

**目标**：两个 run 之间的全维度差异报告。

```python
@dataclass(frozen=True)
class StateDiffReport:
    """两个 run 的全维度差异 — 研究治理核心工具"""
    run_id_a: str
    run_id_b: str

    # 输入差异
    input_diff: InputDiff               # 数据版本 / 时间范围 / 数据缺失

    # 规则差异
    rule_diff: RuleDiff                 # TradingRuleSet / FeeSchedule 版本变化

    # 信号差异
    signal_diff: SignalDiff             # SignalSnapshot diff（按标的）

    # 目标仓位差异
    target_diff: TargetDiff             # TargetPortfolio diff（权重/标的变化）

    # 执行差异
    execution_diff: ExecutionDiff       # order_log diff（rejected/resized/deferred）

    # 风控差异
    risk_diff: RiskDiff                 # risk_log diff（触发规则/动作变化）

    # 绩效差异
    performance_diff: PerformanceDiff   # NAV / Sharpe / Drawdown / Turnover 变化
```

**使用场景**：
- 参数调优：改了一个参数 → 看哪些标的的信号/权重变了
- 引擎升级：升级了 FillModel → 看哪些成交结果变了
- 规则变更：交易所改了涨跌停规则 → 看影响范围

### v3.3 解释链路查询

**目标**：输入 run_id + instrument_id，输出该标的在这次 run 中的完整决策链路。

```python
@dataclass(frozen=True)
class DecisionTrace:
    """单个标的在单次 run 中的完整决策链路"""
    run_id: str
    instrument_id: str

    # 为什么进入 universe
    universe_reason: str | None                # "passed liquidity filter (avg_vol_20d > 1e8)"

    # 为什么被选中
    signal_value: float | None
    score_value: float | None
    rank: int | None

    # 为什么给这个权重
    weight_assigned: float | None
    weight_reason: str | None                  # "equal_weight after constraint clipping"

    # 约束裁剪
    constraint_adjustments: tuple[str, ...]    # ("max_weight clipped from 0.25 to 0.20",)

    # 执行
    order_quantity: int | None
    pre_trade_result: OrderCheckResult | None  # accept / reject / resize

    # 成交
    fills: tuple[FillEvent, ...]
    no_fill_reasons: tuple[str, ...]           # ("suspended on 2024-03-15",)

    # 风控
    risk_events: tuple[RiskScanRecord, ...]    # ("max_drawdown triggered at -15.2%",)

    # 绩效
    entry_price: float | None
    current_price: float | None
    unrealized_pnl: float | None
    realized_pnl: float | None
```

**实现方式**：DecisionTrace 是一个**聚合查询**，不新增采集点——数据来自 decision_frame / execution_plan / pre_trade log / fill_log / risk_log 等现有 artifact。V1 只需确保这些 artifact 都记录 `run_id` + `instrument_id`。

### v3.4 三平面架构显式化

**v2.1 隐含的三平面**：

| 平面 | v2.1 对应 | v3 显式化 |
|------|----------|----------|
| 语义平面 | StrategySpec → TargetPortfolio → ExecutionPlan → Order | 命名为"Semantic Plane"，作为架构组织原则 |
| 运行时平面 | Slice → AccountView → OrderTicket → FillEvent → RiskAction | 命名为"Runtime Plane"，事件账本落地 |
| 治理平面 | RunManifest → InputRefs → RuleRefs → Artifacts → StateDiff | 命名为"Governance Plane"，StateDiffReport + Certification |

**v3 不改类型名**——`TargetPortfolio` / `ExecutionPlan` / `AccountView` 等命名保持不变，只在设计文档中显式标注它们属于哪个平面。

### v3.5 PitCorrectness 作为一等架构约束

**现状（v2.1）**：PIT 用于 TradingRuleSet / FeeSchedule 的版本化查询。

**v3 目标**：PIT 扩展为全局约束——**引擎中的每个值都关联到一个"它是世界什么样子时计算出来的"时间戳**。

| 数据 | PIT 约束 |
|------|---------|
| TradingRuleSet | as_of_date（已有） |
| FeeSchedule | as_of_date（已有） |
| MarketSnapshot (Slice) | trade_date（已有） |
| AccountSnapshot | projection_as_of（v3 新增——事件流投影到哪个时间点） |
| NAV | calculated_at（v3 新增——NAV 是哪个时刻的快照） |
| SignalSnapshot | generated_at = trade_date（已有） |
| InstrumentDefinition | version_hash（v3 新增——静态定义也要可 diff） |

这不是给每个字段加时间戳——而是确保**引擎无法在不知道"世界是什么样"的情况下做出决策**。

### v3 Phase 规划（概要）

```
v3 Phase A: 事件账本基础设施
  ├─ AccountEvent 体系 + EventStore + AccountProjector
  ├─ Account → AccountSnapshot 迁移
  └─ 事件流可回放验证

v3 Phase B: 治理面完善
  ├─ StateDiffReport
  ├─ Run Certification（自动标记 run 质量）
  └─ RuleRefs diff 工具

v3 Phase C: 解释链路
  ├─ DecisionTraceService
  ├─ 标的级决策链路查询 API
  └─ Web 工作台集成

v3 Phase D: PIT 全局约束
  ├─ 所有数据对象的时间溯源
  ├─ PIT 违规检测（静态分析）
  └─ 治理平面文档化
```

---

## 战略方向采纳判定

| 战略建议 | v2.1 采纳情况 | v3 计划 |
|---------|-------------|---------|
| 三个平面架构 | 隐式对齐（类型已有） | v3 显式化为组织原则 |
| 事件账本 | **不采纳**（V1 保持可变 Account） | v3 Phase A 核心升级 |
| RuleRefs / 确定性回放 | **R11 采纳** | v3 Phase B 扩展 diff 能力 |
| risk_log 一级 artifact | **R12 采纳** | v3 Phase B Certification 输入 |
| StateDiffReport | 不采纳（V1 不做） | v3 Phase B |
| 解释链路 | 不采纳（V1 确保数据关联即可） | v3 Phase C |
| PIT 全局约束 | PIT 仅用于规则版本化 | v3 Phase D |
| 研究-回测-实盘同构 | 已对齐（无需改动） | — |
| 控制面先强后广 | R9/R10 已覆盖 | — |
| ExecutionPlanner 重命名 | 不采纳（R2/R5 已解决输入完整性） | — |
| 策略/portfolio 旧 README 归档 | R10 已覆盖 | — |

---

## 影响评估

### 对 Phase 规划的影响

| Phase | 影响 | 说明 |
|-------|------|------|
| Phase 0 | R5 (PreTradeContext), R6 (CashBook frozen), R7 (RunMode), R10 (greenfield), **R11 (RuleRefs)** | 数据结构定义阶段就要落地，不影响工期 |
| Phase 1 | R4 (RiskLockFilter) | Pipeline 内置 filter 增加一个，影响极小 |
| Phase 2 | R2 (退出单 rules), R3 (统计快照), R5 (PreTradeContext 使用), **R11 (RuleRefs 收集)** | EngineLoop 逻辑修正，是 Phase 2 的核心内容 |
| Phase 3 | R6 (类型统一), R8 (零成交语义) | Reality Model 阶段自然收敛 |
| Phase 4 | R4 (PostTrade cooldown), **R12 (risk_log artifact)** | PostTrade 规则实现时顺带完成 |

**结论**: 所有修订可在对应 Phase 内消化，不引入新的 Phase，不改变关键路径。

### 不变量测试补充

| 测试 | 说明 |
|------|------|
| `test_exit_order_has_rules` | 退出标的的 rules 加载正确 |
| `test_stats_use_post_fill_snapshot` | 统计 NAV = 成交后 NAV |
| `test_risk_lock_prevents_reentry` | 清仓标的在当日 Pipeline 中不被选入 |
| `test_risk_lock_clears_next_day` | 次日锁定自动清除 |
| `test_cash_book_immutability` | frozen CashBook 不可修改 |
| `test_no_fill_event_on_suspended` | 停牌标的不产生 FillEvent |
| `test_no_fill_event_on_limit_up` | 涨停买入不产生 FillEvent |
| `test_rule_refs_frozen_in_manifest` | manifest.rule_refs 包含所有使用过的规则版本 |
| `test_reproducible_with_same_manifest` | 相同 manifest → 相同 NAV / fill_log |
| `test_risk_log_persisted` | PostTrade 扫描结果写入 risk_log artifact |
