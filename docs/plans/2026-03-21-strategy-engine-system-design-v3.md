# 策略引擎完整系统设计 v3

**日期**: 2026-03-21
**状态**: Approved — v3 final，可按文档直接开工
**范围**: `packages/core/src/ditto_core/strategy` / `packages/core/src/ditto_core/portfolio` / `packages/core/src/ditto_core/accounting` / `packages/core/src/ditto_core/execution` / `packages/core/src/ditto_core/backtest`
**前置文档**:
- `docs/plans/2026-03-20-daily-strategy-engine-design.md`（策略决策层设计）
- `docs/reviews/2026-03-20-t1-gap-audit.md`（T1 差距审计）
- `docs/reviews/2026-03-20-industry-benchmark-quant-platforms.md`（业界对标）
- `docs/reviews/2026-03-20-a-share-etf-trading-rules.md`（A 股交易规则）
- `docs/reviews/2026-03-20-quantconnect-lean-architecture-reference.md`（QuantConnect 架构参考）

**本版整合来源**:
- v2 (2026-03-20) — 完整系统设计初版
- v2.1 (2026-03-21) — 12 项修订（R1-R12）
- v2.1 Review — 6 项 Findings + 5 项 Suggested Fixes
- Review 补充 — 3 项额外发现

---

## 2026-03-24 实现状态注记

截至 2026-03-24，这份设计稿对应的主链实现已经不再停留在 Core 层：

- `RunManifest`、artifact 落盘、`strategy_run` 持久化控制面已经接通
- Port 层已有 `StrategyRuntimeBuilder`、`BacktestRuntimeBuilder`、`StrategySliceBuilder`
- Port 层已有统一 `StrategyFacade`，可从 published catalog 直接触发
  `research` / `recommendation` / `backtest`
- CLI 已新增 `ditto strategy research|recommend|backtest` 外层入口

仍未完全收口的设计项：

- ~~`instrument_id` 的全仓统一语义仍未最终定型~~ **已收敛 (2026-03-25)**：
  Core / Port / DataHub 全层统一使用 `InstrumentId = NewType("InstrumentId", int)`，
  详见 [instrument-id-unification-v2](2026-03-25-instrument-id-unification-v2-implementation-plan.md)
- `StrategyComparisonReport` 仍是基础版，统计显著性和更强解释型输出未完成
- 若继续推进 API/job flow 级别产品化入口，建议在本设计稿基础上另起实施文档

---

## v2 → v3 修订追踪

### 必修项（源自 v2.1 R1-R12）

| # | 修订 | 影响章节 |
|---|------|---------|
| R1 | A 股 ETF 手数规则溯源（政策文件补充） | 附录 / 交易规则文档 |
| R2 | 调仓退出单拉规则（all_instruments 合并） | §4.2 ExecutionPlanner, §6.1 EngineLoop |
| R3 | 统计层使用成交后快照 | §6.1 EngineLoop, §8.4 ExecutionAuditCollector |
| R4 | PostTrade same-day re-entry → RiskLock | §6.1 EngineLoop, §7.3 PostTrade |
| R5 | PreTrade 契约补全 → PreTradeContext | §7.2 PreTrade, §3.5 Account |
| R6 | CashBook frozen + InstrumentRule 三层分离 | §3.3 CashBook, §5.1 Reality Model |
| R7 | RunMode / EngineMode 分离 | §12.4 RunManifest |
| R8 | 零成交 → FillOutcome 显式语义 | §4.3 FillOutcome, §5.3 FillModel |
| R9 | 范围收敛（CashProvider 删除、V2+ 降级 Backlog） | §3, §11 Phase 规划 |
| R10 | 策略 control plane 标 Greenfield | §9.3 DataHub |
| R11 | RuleRefs 进 RunManifest（确定性回放） | §12.4 RunManifest |
| R12 | risk_log 一级 artifact | §8.4 ExecutionAuditCollector, §12 Artifact |

### 逻辑修正（源自 Review Findings）

| # | 修订 | 影响章节 |
|---|------|---------|
| F1 | PreTradeContext → 逐单滚动上下文 | §7.2 PreTrade, §6.1 EngineLoop |
| F2 | ExecutionPlanner → pending-aware diff | §4.2 ExecutionPlanner |
| F3 | RuleRefs → 全量冻结（保留所有版本） | §12.4 RunManifest |
| F4 | FillModel → 显式 FillOutcome | §4.3 FillOutcome, §5.3 FillModel |
| F5 | OrderTicket → frozen（只读彻底闭环） | §3.4 OrderBook |
| F6 | 文档合并为单一真相文档 | 本文档 |

### 工程加固（源自 Review Suggested Fixes）

| # | 修订 | 影响章节 |
|---|------|---------|
| S1 | RiskLock → Planner 层锁定（禁止新增买单） | §4.2 ExecutionPlanner, §7.3 PostTrade |
| S2 | RunManifest → rule_resolution_policy | §12.4 RunManifest |
| S3 | StatsCollector → ExecutionAuditCollector（职责分离） | §8.4, §9.1 |
| S4 | test_reproducible 拆为两层 | §10.5 |
| S5 | RiskLock 跨日 cooldown 预留 | §7.3 PostTrade |

### 额外发现

| # | 修订 | 影响章节 |
|---|------|---------|
| A1 | PreTrade resize 后重检（防 resize 跳过后续检查） | §7.2 PreTrade |
| A2 | order_log 补充 pre_trade_decision 审计字段 | §12.2 Artifact 目录 |
| A3 | record_risk_scan 调用位置明确化 | §6.1 EngineLoop |

### v3.1 修订（实现阻塞项 + 审计粒度修复）

| # | 修订 | 类型 | 影响章节 |
|---|------|------|---------|
| B1 | 主流程 accept 路径统一处理 resized_quantity | Blocker | §6.1 EngineLoop |
| B2 | NoFill(can_retry=False) → INVALID 终态 + with_invalid() | Blocker | §3.4 OrderBook, §4.3 FillOutcome |
| B3 | with_order_accepted() 卖出时递减 available_quantity | Blocker | §7.2 PreTrade |
| B4 | Slice.step_time 替代 datetime.now() | Blocker | §6.2 Slice, §4.4 Brokerage |
| F1 | PreTradeDecisionRecord 统一审计记录类型 | 改进 | §8.4 ExecutionAuditCollector |
| F2 | round_sell_quantity 使用 position.available_quantity | 改进 | §4.2 ExecutionPlanner |

### v3 final 收口（治理精度 + 审计解释性）

| # | 修订 | 类型 | 影响章节 |
|---|------|------|---------|
| R1 | RuleRef 去重 key 加入 definition_version | 治理 | §12.4 RunManifest |
| R2 | triggered_checks 完整链路传递 | 审计 | §7.2 PreTrade, §8.4 |
| R3 | BuyingPowerModel 调用签名全文统一（补 direction） | 一致性 | §3.5, §7.2 |
| P1 | 终态说明统一为 FILLED/CANCELED/REJECTED/INVALID | 一致性 | §4.1 |
| P2 | manifest 序列化规范（canonical JSON + 稳定排序） | 治理 | §12.4 |
| P3 | 时间持久化语义统一（内存 datetime / 落盘 RFC3339 UTC） | 一致性 | §4.1, §12.4 |
| P4 | order_log schema 补充 pre_trade_check_sequence | 审计 | §8.5 |
| P5 | 3 个 10 分证明型测试 | 测试 | §10.5 |

### 可后移项（v3+ 远景）

| 内容 | 当前处理 |
|------|---------|
| 事件账本 / AccountSnapshot 全量投影 | 附录 C v3 Phase A |
| StateDiffReport | 附录 C v3 Phase B |
| DecisionTraceService | 附录 C v3 Phase C |
| PIT 全局约束 | 附录 C v3 Phase D |
| 多币种 / OMS / Margin / Futures | §11 Phase 8 Backlog |

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
| 15 | PreTrade 上下文 | 逐单滚动（F1） | 批次内每笔 accept/resize 后更新 reserved_cash/pending_turnover/pending_sell_qty，批内风控正确 |
| 16 | Planner diff | pending-aware（F2） | 计算 position delta 时扣除 pending orders，避免重复卖单 |
| 17 | FillOutcome | 显式联合类型（F4） | Filled/NoFill 替代 FillEvent\|None + side-channel，纯函数语义 |
| 18 | OrderTicket | frozen dataclass（F5） | 状态通过 with_fill() 返回新实例，只读彻底闭环 |
| 19 | 统计收集器 | ExecutionAuditCollector（S3） | 统计与审计职责分离，risk_log 不挂在 StatsCollector 下 |
| 20 | RuleRefs | 全量冻结（F3） | 每instrument+版本都保留，长回测跨规则变更日确定性可证 |
| 21 | 执行层时间源 | Slice.step_time（B4） | 执行层所有时间戳必须来自 Slice.step_time，禁止 datetime.now()，保证回测确定性回放 |
| 22 | 时间持久化语义 | 内存 datetime / 持久化 RFC3339 UTC（P3） | 所有 artifact/manifest 时间字段统一：内存态可用 datetime，落盘统一 RFC3339 显式时区 |

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
│  │    ↓ pending-aware diff (F2)                      │          │
│  │  Orders → PreTradeRiskCheck (rolling ctx, F1)     │          │
│  │    ↓ resize recheck (A1)                          │          │
│  │  Brokerage → FillOutcome (F4)                     │          │
│  │    → Account.update()                             │          │
│  │    → PostTradeRiskGuard.scan() + RiskLock (R4)    │          │
│  └───────────────────────────────────────────────────┘          │
│                        ↓                                        │
│  ┌──────────── 统计与审计层 ─────────────────────────┐          │
│  │  ExecutionAuditCollector (S3)                     │          │
│  │  ├─ TradeBuilder │ NAV │ TradeStats               │          │
│  │  ├─ PortfolioStats │ AlphaStats                   │          │
│  │  ├─ risk_log (R12) │ pre_trade_log (A2)          │          │
│  │  └─ Manifest (RuleRefs full freeze, F3)           │          │
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
3. **执行层**通过 AccountView（只读快照）读取状态，通过 Brokerage（state owner）提交订单并获取 FillOutcome
4. **ExecutionPlanner** 使用 pending-aware diff（F2），将已有 pending orders 折算进 effective position，避免重复下单
5. **PreTrade** 使用逐单滚动上下文（F1），每笔 accept/resize 后更新 reserved_cash/pending_turnover，批内风控正确；resize 后重检（A1）防止跳过后续规则
6. **风控分两层**：PreTradeRiskCheck 在订单提交前逐单校验；PostTradeRiskGuard 在每日 step 后扫描组合状态，通过 RiskLock（R4）防止 same-day re-entry
7. **统计与审计分离**（S3）：ExecutionAuditCollector 统一管理统计收集和审计日志（risk_log、pre_trade_log），不混合职责
8. **FillOutcome** 显式联合类型（F4），FillModel 恢复纯函数语义，无隐式状态
9. **确定性回放**：RunManifest 冻结 RuleRefs 全量版本（F3），同 manifest + 同代码版本 → 结果完全一致
10. **EngineLoop** 只做 BACKTEST/LIVE 两种日历步进模式；RESEARCH/RECOMMENDATION 在 Port 层 service 编排

---

## 2. 决策层细化

> 本章与 v2 一致，无修改。

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

## 3. Accounting 层

### 3.1 设计动机

v1 中 PortfolioState 定义在 backtest/ 下，但 execution 需要读它、RiskGuard 需要扫描它、ExecutionPlanner 需要对比它。状态 owner 不明确导致模块边界卡死。

v3 新增 `accounting/` 作为共享账户契约层，提供 Account（可变状态）和 AccountView（只读快照），所有上层模块通过它交互。**所有数据对象均为 frozen dataclass**（R6, F5），只读闭环。

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

### 3.3 CashBook（R6: frozen）

```python
@dataclass(frozen=True)
class CashBook:
    """现金账户（不可变）— 状态变更通过创建新实例"""
    available: float      # 可用现金（扣除冻结）
    settled: float        # 已交收（可提现）
    frozen: float         # 冻结金额（待交收/待成交）
```

Account 内部通过替换 `_cash` 引用来更新状态：

```python
def apply_fill(self, fill: FillEvent, definition, trading_rule, fee_schedule) -> None:
    new_available = self._cash.available - fill.fee
    self._cash = CashBook(
        available=new_available,
        settled=self._cash.settled,
        frozen=self._cash.frozen,
    )
```

> **设计决策**：V1 不设 CashProvider Protocol（R9）。CashBook 即 V1 现金实现。多币种推迟到 Phase 8（RunManifest 已有 `currency` 字段预留）。

### 3.4 OrderBook（F5: OrderTicket frozen）

```python
class OrderStatus(StrEnum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    INVALID = "invalid"        # B2: 已提交但逻辑上无法成交（can_retry=False）

    @property
    def is_terminal(self) -> bool:
        """终态：FILLED / CANCELED / REJECTED / INVALID"""
        return self in (
            OrderStatus.FILLED, OrderStatus.CANCELED,
            OrderStatus.REJECTED, OrderStatus.INVALID,
        )

@dataclass(frozen=True)
class OrderTicket:
    """订单票据 — frozen，状态变更通过 with_xxx() 返回新实例"""
    order: Order
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: int = 0
    filled_price: float | None = None
    average_fill_price: float | None = None
    order_events: tuple[OrderEvent, ...] = ()

    @property
    def leaves_quantity(self) -> int:
        return self.order.quantity - self.filled_quantity

    def with_fill(
        self, quantity: int, price: float, event: OrderEvent,
    ) -> OrderTicket:
        """成交后返回新的 OrderTicket 实例"""
        new_filled = self.filled_quantity + quantity
        new_status = (
            OrderStatus.FILLED
            if new_filled >= self.order.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        return dataclasses.replace(
            self,
            filled_quantity=new_filled,
            filled_price=price,
            average_fill_price=self._calc_avg(price, quantity),
            status=new_status,
            order_events=(*self.order_events, event),
        )

    def with_cancel(self, event: OrderEvent) -> OrderTicket:
        if self.status.is_terminal:
            raise StateTransitionError(
                f"Cannot cancel order in terminal state: {self.status}"
            )
        return dataclasses.replace(
            self, status=OrderStatus.CANCELED,
            order_events=(*self.order_events, event),
        )

    def with_reject(self, event: OrderEvent) -> OrderTicket:
        return dataclasses.replace(
            self, status=OrderStatus.REJECTED,
            order_events=(*self.order_events, event),
        )

    def with_invalid(self, event: OrderEvent) -> OrderTicket:
        """B2: 已提交但逻辑上无法成交（NoFill.can_retry=False）→ 终态"""
        if self.status.is_terminal:
            raise StateTransitionError(
                f"Cannot invalidate order in terminal state: {self.status}"
            )
        return dataclasses.replace(
            self, status=OrderStatus.INVALID,
            order_events=(*self.order_events, event),
        )

class OrderBook:
    """订单簿 — 持有所有 OrderTicket，只允许通过受控方法修改"""
    _tickets: dict[str, OrderTicket]

    def get(self, order_id: str) -> OrderTicket | None: ...
    def get_pending(self) -> tuple[OrderTicket, ...]: ...
    def submit(self, ticket: OrderTicket) -> None:
        self._tickets[ticket.order.order_id] = ticket
    def update(self, ticket: OrderTicket) -> None:
        """用新的 frozen OrderTicket 替换旧引用"""
        self._tickets[ticket.order.order_id] = ticket
    def cancel(self, order_id: str) -> None:
        ticket = self._tickets[order_id]
        if ticket.status.is_terminal:
            raise StateTransitionError(...)
        event = OrderEvent(order_id=order_id, status=OrderStatus.CANCELED, ...)
        self._tickets[order_id] = ticket.with_cancel(event)

    def readonly_view(self) -> OrderBookReadOnly: ...

class OrderBookReadOnly:
    """OrderBook 的只读视图 — 供 AccountView 暴露，返回 frozen OrderTicket"""
    def get(self, order_id: str) -> OrderTicket | None: ...
    def get_pending(self) -> tuple[OrderTicket, ...]: ...

class StateTransitionError(Exception):
    """非法状态转换，如 FILLED → CANCEL"""
```

> **设计决策（F5）**：OrderTicket 改为 frozen dataclass。状态变更通过 `with_fill()` / `with_cancel()` 返回新实例，OrderBook 内部替换 dict 引用。这与 CashBook frozen 模式一致。`OrderBookReadOnly.get()` 直接返回 frozen OrderTicket——外部无法修改，只读彻底闭环。不需要额外的 `OrderTicketView` 类型。

### 3.5 Account 与 AccountView

```python
@dataclass
class Account:
    """可变账户状态 — state owner (Brokerage) 持有此实例"""
    positions: dict[str, Position]
    _cash: CashBook               # frozen，通过替换引用更新
    order_book: OrderBook

    @property
    def cash(self) -> CashBook:
        return self._cash

    def apply_fill(
        self,
        fill: FillEvent,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
        fee_schedule: FeeSchedule,
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
            order_book=self.order_book.readonly_view(),
        )

@dataclass(frozen=True)
class AccountView:
    """只读账户快照 — execution/risk/pipeline 通过它读取状态"""
    positions: Mapping[str, Position]
    cash: CashBook                       # frozen (R6)
    total_value: float
    nav: float
    exposure: float
    pending_buy_value: float
    order_book: OrderBookReadOnly        # R5, 返回 frozen OrderTicket (F5)
```

**关键设计**：

- `Account` 是可变的，只有 Brokerage 可以持有和修改
- `AccountView` 是 frozen 的，任何模块都可以安全读取
- `AccountView` 返回的所有对象（CashBook、OrderTicket、Position）都是 frozen 的，**只读彻底闭环**（F5）
- EngineLoop 通过 `brokerage.get_account()` 获取 AccountView
- ExecutionPlanner 通过 AccountView 读取当前持仓和权重
- RiskGuard 通过 AccountView 扫描组合状态

### 3.6 BuyingPowerModel

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
```

PreTrade `buying_power` 规则改为消费此模型，不再自行计算。

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
    created_at: datetime              # 内存态 datetime；持久化统一 RFC3339（UTC）
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
    message: str | None = None       # "suspended" / "limit_up_deferred" / ...
    timestamp: datetime
```

**关键设计原则**：

- `Order` 是 frozen dataclass（创建后不可变），所有状态变更记录在 `OrderTicket`（frozen, with_xxx）和 `OrderEvent` 上
- `OrderTicket` 是一等引用——引擎通过它查询订单状态，风控通过它拦截
- 终态（FILLED/CANCELED/REJECTED/INVALID）不可逆，转换函数需校验前置状态，非法转换抛出 `StateTransitionError`
- `Order.with_quantity()` 用于 PreTrade resize，返回新实例而非原地修改

### 4.2 ExecutionPlanner（F2: pending-aware, S1: Planner lock）

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
        account: AccountView,
        slice: Slice,
        trade_date: str,
        rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]],
        locked_instruments: frozenset[str] | None = None,   # S1: RiskLock
    ) -> ExecutionPlan: ...
```

**F2: pending-aware diff** — Planner 计算 position delta 时，必须将 pending orders 折算进 effective position，避免风险卖单和普通调仓卖单重复生成。

**S1: Planner lock** — 锁定标的不得生成新增买单。这补充了 RiskLockFilter（Pipeline 层）的盲区：RiskLockFilter 只作用于 Pipeline 输出的 DecisionFrame，退出标的的卖单由 Planner diff 路径直接生成，绕过 Filter。

ExecutionPlanner 内部处理：

- **Pending-aware diff 计算**（F2）：
  ```python
  def _compute_pending_delta(
      self, order_book: OrderBookReadOnly,
  ) -> dict[str, int]:
      """汇总 pending orders 的净数量变化"""
      delta: dict[str, int] = {}
      for ticket in order_book.get_pending():
          remaining = ticket.leaves_quantity
          iid = ticket.order.instrument_id
          if ticket.order.direction == OrderDirection.BUY:
              delta[iid] = delta.get(iid, 0) + remaining
          else:
              delta[iid] = delta.get(iid, 0) - remaining
      return delta
  ```
- **Diff 计算**：
  ```python
  pending_delta = self._compute_pending_delta(account.order_book)

  for instrument_id in all_instruments:
      current_qty = account.positions.get(instrument_id, empty).quantity
      effective_qty = current_qty + pending_delta.get(instrument_id, 0)
      target_qty = target.get_target_quantity(instrument_id)

      delta = target_qty - effective_qty  # F2: 用 effective 而非 current

      if delta > 0:
          if locked_instruments and instrument_id in locked_instruments:
              # S1: 锁定标的禁止新增买入
              blocked.append(BlockedOrder(..., reason="risk_locked"))
              continue
          orders.append(self._build_buy_order(..., quantity=delta))
      elif delta < 0:
          sell_qty = min(-delta, effective_qty)  # 不超卖 effective position
          if sell_qty > 0:
              orders.append(self._build_sell_order(..., quantity=sell_qty))
  ```
- **Diff 计算范围**（R2）：包括 **current positions 中所有非空仓标的**，不仅仅是 `target.instrument_ids`。退出标的应生成全部卖出指令。
- **数量取整**：买入 `max(100, qty)`（100+1 规则）；卖出分整手 + 零股
- **T+1 检查**：通过 `Position.available_quantity` 判断
- **涨跌停预检**：通过 Slice 中的 `MarketSnapshot.limit_up/limit_down` 判断
- **停牌过滤**：通过 Slice 中的 `MarketSnapshot.is_suspended` 判断

#### 数量取整逻辑

```python
def round_buy_quantity(raw_quantity: int, definition: InstrumentDefinition) -> int:
    """买入：100 份起，之后可 1 份递增（2023-08 起的 100+1 规则）"""
    return max(definition.lot_size, raw_quantity)   # lot_size=100

def round_sell_quantity(
    quantity: int, definition: InstrumentDefinition, position: Position,
) -> tuple[int, int]:
    """
    卖出分两部分，以可卖数量为上界：
    - 整手：(effective_qty // lot_size) * lot_size，可分批
    - 零股：effective_qty % lot_size，必须一次性全部卖出

    F2: effective_qty = min(quantity, position.available_quantity)
    如果 effective_qty == 0，调用方不应生成卖单。
    """
    effective_qty = min(quantity, position.available_quantity)
    round_lot = (effective_qty // definition.lot_size) * definition.lot_size
    odd_lot = effective_qty % definition.lot_size
    return round_lot, odd_lot
```

**A 股 ETF 手数规则政策来源**（R1）：

- 上交所：《关于优化主板交易制度的通知》（2023-07-21），2023-08-28 起实施
- 深交所：《关于优化交易制度的通知》（2023-07-21），2023-08-28 起实施
- 买入：最低 100 份起，可以 1 份为单位递增（101、250、1234 均可）
- 卖出零股：不足 100 份的零股必须一次性全部卖出，不得拆分

### 4.3 FillOutcome（F4: 显式联合类型）

替代 v2 的 `FillEvent | None + last_rejection_reason()` side-channel。FillModel 恢复纯函数语义。

```python
class FillOutcome:
    """FillModel 的显式返回值基类"""
    pass

@dataclass(frozen=True)
class Filled(FillOutcome):
    """成交"""
    fill_event: FillEvent

@dataclass(frozen=True)
class NoFill(FillOutcome):
    """不成交 — 明确原因，无隐式状态"""
    reason: str           # "suspended" / "limit_up_deferred" / "limit_down_deferred" / "insufficient_auction"
    can_retry: bool       # True = 下一 step 可能成交，False = 该订单逻辑上无效
```

`can_retry` 区分两种语义：
- `suspended` → `can_retry=True`（复牌后可能成交）
- `limit_up_deferred` → `can_retry=True`（涨停打开后可能成交）
- `insufficient_auction` → `can_retry=False`（集合竞价流动性不足，当日不会再成交）

**FillEvent**（R8: 移除 fill_reason，零成交不再产生 FillEvent）：

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
    cumulative_quantity: int      # 该订单累计已成交量
    leaves_quantity: int          # 该订单剩余未成交量
```

### 4.4 Brokerage 抽象

```python
class Brokerage(Protocol):
    """Brokerage 是 state owner，持有 Account 实例"""
    def connect(self) -> None: ...
    def get_account(self) -> AccountView: ...       # 只读快照（所有对象 frozen）
    def place_order(self, order: Order) -> OrderTicket: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def process_pending(self, slice: Slice) -> tuple[FillEvent, ...]: ...

class BacktestBrokerage:
    """回测 Broker — 确定性成交模拟
    注意：不是"即时成交"，而是根据 FillModel 规则模拟成交。
    """
    def __init__(
        self,
        account: Account,
        fill_model: FillModel,
        fee_model: FeeModel,
        slippage_model: SlippageModel,
        settlement_model: SettlementModel,
    ): ...

    def process_pending(self, slice: Slice) -> tuple[FillEvent, ...]:
        fills: list[FillEvent] = []
        for ticket in self._account.order_book.get_pending():
            market = slice.bars.get(ticket.order.instrument_id)
            if market is None:
                continue
            defn, trading_rule, fee_schedule = self._get_rules(
                ticket.order.instrument_id, slice.trade_date,
            )

            outcome = self._fill_model.try_fill(
                ticket.order, market, defn, trading_rule,
            )
            if isinstance(outcome, Filled):
                self._account.apply_fill(outcome.fill_event, defn, trading_rule, fee_schedule)
                event = OrderEvent(
                    order_id=outcome.fill_event.order_id,
                    status=(
                        OrderStatus.PARTIALLY_FILLED
                        if outcome.fill_event.leaves_quantity > 0
                        else OrderStatus.FILLED
                    ),
                    fill_price=outcome.fill_event.fill_price,
                    fill_quantity=outcome.fill_event.filled_quantity,
                    fee=outcome.fill_event.fee,
                    timestamp=outcome.fill_event.event_time,
                )
                self._account.order_book.update(ticket.with_fill(
                    quantity=outcome.fill_event.filled_quantity,
                    price=outcome.fill_event.fill_price,
                    event=event,
                ))
                fills.append(outcome.fill_event)
            elif isinstance(outcome, NoFill):
                # B4: 使用 slice.step_time（确定性时间源）
                # B2: can_retry=False → INVALID 终态，不再留在 pending
                if outcome.can_retry:
                    event = OrderEvent(
                        order_id=ticket.order.order_id,
                        status=OrderStatus.SUBMITTED,
                        message=outcome.reason,
                        timestamp=slice.step_time,
                    )
                    self._account.order_book.update(
                        dataclasses.replace(ticket, order_events=(*ticket.order_events, event))
                    )
                else:
                    event = OrderEvent(
                        order_id=ticket.order.order_id,
                        status=OrderStatus.INVALID,
                        message=f"[invalid] {outcome.reason}",
                        timestamp=slice.step_time,
                    )
                    self._account.order_book.update(ticket.with_invalid(event))
        return tuple(fills)
```

---

## 5. Reality Model（A 股交易规则建模）

### 5.1 资产交易规则 — 三层分离架构（R6）

v2 中 InstrumentRule 职责过重。内核升级将其拆为三层，并接入现有 PIT 基础设施实现规则版本化。

#### 5.1.1 InstrumentDefinition — 静态资产属性

```python
@dataclass(frozen=True)
class InstrumentDefinition:
    """资产的静态定义 — 很少变化，不按日期生效"""
    instrument_id: str
    asset_class: str                 # stock / etf / index / future / ...
    exchange: str                    # XSHE / XSHG / XBSE
    currency: str                    # CNY（V1），未来多币种
    tick_size: float                 # 最小价格变动（A股=0.01）
    lot_size: int                    # 最小手数（A股=100）
    multiplier: float                # 合约乘数（股票/ETF=1）
    board_segment: str               # main / gem / star / bse（影响涨跌停规则）
    lifecycle_state: str             # normal / st / st_star / delisting / ipo
```

**设计原则**：

- 复用现有 `InstrumentRegistration` + `InstrumentExtension`（metadata.py）的注册数据
- `board_segment` 和 `lifecycle_state` 直接影响 `TradingRuleSet` 中的涨跌停计算
- 由 `InstrumentRuleProvider` 在 DataHub 层从 instrument 表 + extension 表组装

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
    order_types_supported: tuple[str, ...]
    call_auction_sessions: tuple[str, ...]
```

**规则版本化机制**：复用 Ditto 现有 PIT 基础设施（effective_from / effective_to），零新基建。

**规则变更实例**：

| 日期 | 变更 | 影响字段 |
|------|------|---------|
| 2023-08-28 | 100+1 规则实施 | lot_size 语义变化 |
| 2023-08-28 | 印花税减半（1‰→0.5‰） | FeeSchedule.stamp_duty_rate |
| 2025-06-27 | ST 涨跌幅限制调整 | price_limit_pct |

#### 5.1.3 FeeSchedule — 可变费用结构（PIT 版本化）

```python
@dataclass(frozen=True)
class FeeSchedule:
    """某个标的在某个时间点的费用结构 — 按日期生效"""
    instrument_id: str
    as_of_date: str
    commission_rate: float
    min_commission: float            # A股=5元
    stamp_duty_rate: float           # ETF=0, 股票=0.0005 卖出
    transfer_fee_rate: float         # ETF=0, 股票=0.00001
```

#### 5.1.4 InstrumentRuleProvider — 组装层

```python
class InstrumentRuleProvider(Protocol):
    """由 DataHub 实现，组装三层规则并缓存"""

    def get_definition(self, instrument_id: str) -> InstrumentDefinition: ...
    def get_trading_rule(self, instrument_id: str, as_of_date: str) -> TradingRuleSet: ...
    def get_fee_schedule(self, instrument_id: str, as_of_date: str) -> FeeSchedule: ...
    def get_rules(
        self, as_of_date: str, instrument_ids: list[str],
    ) -> dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]: ...
```

**所有 BrokerageModel 方法签名使用三层分离**：

```python
def fill(
    self, order: Order, market: MarketSnapshot,
    definition: InstrumentDefinition,
    trading_rule: TradingRuleSet,
    fee_schedule: FeeSchedule,
) -> FillOutcome: ...
```

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
    limit_up: float | None
    limit_down: float | None
    avg_volume_20d: float | None
```

### 5.3 四大可插拔模型

```python
class FillModel(Protocol):
    """成交模拟 — 纯函数，无隐式状态（F4）"""
    def try_fill(
        self, order: Order, market: MarketSnapshot,
        definition: InstrumentDefinition,
        trading_rule: TradingRuleSet,
    ) -> FillOutcome: ...

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

#### FillModel — 成交模拟（R8: 返回 FillOutcome）

内置 `AShareFillModel` 的规则矩阵：

| 条件 | 行为 | FillOutcome |
|------|------|-------------|
| 停牌 | 不成交 | `NoFill("suspended", can_retry=True)` |
| 涨停 + 买入 | 不成交（排队） | `NoFill("limit_up_deferred", can_retry=True)` |
| 跌停 + 卖出 | 不成交（无法卖出） | `NoFill("limit_down_deferred", can_retry=True)` |
| 涨停 + 卖出 | 全部成交（涨停板上卖方充足） | `Filled(fill_event)` |
| 跌停 + 买入 | 全部成交（跌停板上买方充足） | `Filled(fill_event)` |
| MarketOnClose | 收盘集合竞价模拟 | `Filled` 或 `NoFill("insufficient_auction", can_retry=False)` |
| LIMIT 单 | 价格在涨跌停范围内则成交，否则不成交 | `Filled` 或 `NoFill("price_out_of_range", can_retry=False)` |
| 正常 | 以 close ± slippage 成交 | `Filled(fill_event)` |

#### SlippageModel — 滑点模拟

- `FixedBpsSlippage`：固定 bps（默认 2bp）
- `VolumeShareSlippage`：按成交额占日均量比例线性递增

#### FeeModel — 费用计算

内置 `AShareFeeModel`：

| 费用项 | 规则 |
|--------|------|
| 佣金 | `max(fee_schedule.min_commission, trade_amount × fee_schedule.commission_rate)` |
| 印花税 | `fee_schedule.stamp_duty_rate`（ETF=0, 股票=0.0005 卖出） |
| 过户费 | `fee_schedule.transfer_fee_rate`（ETF=0, 股票=0.00001） |

#### SettlementModel — 交收规则

内置 `AShareSettlementModel`：

| 参数 | ETF 股票型 | ETF 跨境型 | ETF 债券型 | ETF 商品型 |
|------|-----------|-----------|-----------|-----------|
| settlement_cycle | 1 (T+1) | 0 (T+0) | 0 (T+0) | 0 (T+0) |
| fund_settlement_cycle | 1 | 1 | 1 | 0 |

### 5.4 收盘集合竞价模拟

```python
class ClosingAuctionFillModel(FillModel):
    """用于 MarketOnClose 订单"""
    def try_fill(
        self, order: Order, market: MarketSnapshot,
        definition: InstrumentDefinition, trading_rule: TradingRuleSet,
    ) -> FillOutcome:
        fill_ratio = self._estimate_closing_auction_participation(
            order.quantity, market.avg_volume_20d
        )
        filled_quantity = (int(order.quantity * fill_ratio) // definition.lot_size) * definition.lot_size
        if filled_quantity <= 0:
            return NoFill(reason="insufficient_auction", can_retry=False)
        fill_price = market.close
        return Filled(fill_event=FillEvent(
            filled_quantity=filled_quantity, fill_price=fill_price, ...
        ))
```

### 5.5 BrokerageModel

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
```

```python
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
        audit_collector: ExecutionAuditCollector,     # S3: 重命名
        buying_power_model: BuyingPowerModel,
        fee_model: FeeModel,
    ): ...

    def run(self) -> EngineResult: ...

    def _step(self, date: str) -> None:
        """每个交易日执行一步"""
        slice = self.data_feed.get_slice(date)
        account_view = self.brokerage.get_account()

        # 每个 step 开始时清除上日锁定 (R4)
        self._context.clear_locks()

        # 1. PostTrade 扫描 — 检查组合健康度，可能触发紧急退出
        risk_actions = self.post_trade_guard.scan(account_view, slice)
        risk_records = self._to_risk_scan_records(risk_actions, date)
        if risk_records:
            self.audit_collector.record_risk_scan(date, risk_records)   # A3
        if risk_actions:
            self._execute_risk_actions(risk_actions, slice)
            account_view = self.brokerage.get_account()  # 刷新快照

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

            # F2 + S1: 传入 locked_instruments
            plan = self.planner.plan(
                target, account_view, slice, date, rules=rules,
                locked_instruments=frozenset(self._context.risk_locked_instruments.keys()),
            )

            # F1: 构建逐单滚动 PreTradeContext
            pre_trade_ctx = self._build_pre_trade_context(
                account_view, slice, rules,
            )

            # A1: PreTrade 逐单校验（resize 后重检）
            # B1: accept 路径统一处理 resized_quantity
            # F1: 收集完整 PreTrade 决策记录
            checked_orders: list[Order] = []
            pre_trade_decisions: list[PreTradeDecisionRecord] = []
            for order in plan.orders:
                result = self.pre_trade_check.check_order(order, pre_trade_ctx)
                if result.decision == "accept":
                    # B1: CompositePreTradeCheck 内部 resolve resize → accept 时
                    # 附带 resized_quantity，外层必须用缩后数量
                    final_order = (
                        order.with_quantity(result.resized_quantity)
                        if result.resized_quantity
                        else order
                    )
                    checked_orders.append(final_order)
                    pre_trade_ctx = pre_trade_ctx.with_order_accepted(final_order)
                    pre_trade_decisions.append(PreTradeDecisionRecord(
                        trade_date=date,
                        order_id=order.order_id,
                        instrument_id=order.instrument_id,
                        direction=order.direction,
                        original_quantity=order.quantity,
                        final_quantity=(
                            final_order.quantity
                            if result.resized_quantity else None
                        ),
                        decision="resized" if result.resized_quantity else "accepted",
                        reason=result.reason,
                        check_sequence=result.triggered_checks,
                    ))
                else:  # reject
                    pre_trade_decisions.append(PreTradeDecisionRecord(
                        trade_date=date,
                        order_id=order.order_id,
                        instrument_id=order.instrument_id,
                        direction=order.direction,
                        original_quantity=order.quantity,
                        final_quantity=None,
                        decision="rejected",
                        reason=result.reason,
                        check_sequence=result.triggered_checks,
                    ))

            # 记录 PreTrade 审计日志 (A2 + F1)
            self.audit_collector.record_pre_trade_decisions(
                date, tuple(pre_trade_decisions),
            )

            # 提交通过的订单
            for order in checked_orders:
                self.brokerage.place_order(order)

        # 3. 推进未完成订单 → 模拟成交
        fills = self.brokerage.process_pending(slice)

        # 4. 刷新快照后统计（R3 修复：统计用成交后快照）
        account_view = self.brokerage.get_account()
        self.audit_collector.record(date, fills, account_view, slice)

    def _pending_order_instrument_ids(self) -> set[str]:
        """从 Brokerage 的 OrderBook 提取 pending 订单涉及的 instrument_ids"""
        tickets = self.brokerage.get_account().order_book.get_pending()
        return {t.order.instrument_id for t in tickets}
```

#### F1: PreTradeContext — 逐单滚动上下文

```python
@dataclass(frozen=True)
class PreTradeContext:
    """PreTrade 校验所需的完整只读上下文 — 每笔订单通过后滚动更新"""
    account_view: AccountView
    slice: Slice
    rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]
    buying_power_model: BuyingPowerModel
    fee_model: FeeModel
    pending_tickets: tuple[OrderTicket, ...]

    def with_order_accepted(self, order: Order) -> PreTradeContext:
        """返回包含此订单影响的新上下文 — 保持 frozen 语义"""
        estimated_cost = self._estimate_order_cost(order)
        market = self.slice.bars.get(order.instrument_id)
        if market is None:
            return self  # 无市场数据时不更新

        if order.direction == OrderDirection.BUY:
            new_cash = self.account_view.cash.__class__(
                available=self.account_view.cash.available - estimated_cost,
                settled=self.account_view.cash.settled,
                frozen=self.account_view.cash.frozen + estimated_cost,
            )
            new_view = dataclasses.replace(
                self.account_view,
                cash=new_cash,
                pending_buy_value=self.account_view.pending_buy_value + estimated_cost,
            )
        else:
            # B3: 卖出时递减 available_quantity — 防止批内超卖
            position = self.account_view.positions.get(order.instrument_id)
            if position is not None:
                new_available = max(0, position.available_quantity - order.quantity)
                new_position = dataclasses.replace(
                    position, available_quantity=new_available,
                )
                new_positions = dict(self.account_view.positions)
                new_positions[order.instrument_id] = new_position
                new_view = dataclasses.replace(
                    self.account_view, positions=new_positions,
                )
            else:
                new_view = self.account_view

        return PreTradeContext(
            account_view=new_view,
            slice=self.slice,
            rules=self.rules,
            buying_power_model=self.buying_power_model,
            fee_model=self.fee_model,
            pending_tickets=(*self.pending_tickets, self._ticket_from_order(order)),
        )

    def _estimate_order_cost(self, order: Order) -> float:
        market = self.slice.bars.get(order.instrument_id)
        if market is None:
            return 0.0
        price = order.price if order.price else market.close
        cost = order.quantity * price
        fee_schedule = self.rules.get(order.instrument_id, (None, None, None))[2]
        if fee_schedule:
            cost += self.fee_model.estimate(order, price, fee_schedule)
        return cost

    @staticmethod
    def _ticket_from_order(order: Order) -> OrderTicket:
        return OrderTicket(order=order)
```

#### R4: RiskLock — 防止 same-day re-entry

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

def _execute_risk_actions(
    self, actions: list[RiskAction], slice: Slice,
) -> None:
    for action in actions:
        if action.instrument_id and action.action_type != RiskActionType.ALERT:
            self.brokerage.place_order(self._build_risk_order(action))
            # 当日锁定 — Pipeline 不再选入 + Planner 不再生成买单
            self._context.lock_instrument(action.instrument_id, action.reason)
```

**RiskLockFilter**（Pipeline Filter 阶段自动注入）：

```python
class RiskLockFilter(DecisionStage):
    """过滤被风险动作锁定的标的"""
    def process(self, frame: DecisionFrame, context: StrategyContext) -> DecisionFrame:
        locked = context.risk_locked_instruments
        if not locked:
            return frame
        return frame.filter(
            ~pl.col("instrument_id").is_in(list(locked.keys()))
        )
```

**锁定生命周期**：

- 每个 step 开始时自动清除（`clear_locks()`），不跨日持久化
- S5: 跨日 cooldown 由 `cooldown_until_date` 字段扩展（V2+ 实现，V1 不做）

> **冷却期**（S5）：V1 只做当日锁定。V2+ 可通过 `RiskAction.cooldown_until_date` 字段扩展，让 `_execute_risk_actions` 设置跨日锁定。`clear_locks()` 改为只清除非 cooldown 的锁定。

### 6.2 DataFeed

```python
class DataFeed(Protocol):
    def trading_days(self) -> list[str]: ...
    def get_slice(self, date: str) -> Slice: ...

@dataclass(frozen=True)
class Slice:
    """某个交易日所有标的的市场快照"""
    trade_date: str
    step_time: datetime              # B4: 确定性时间源（由 EngineLoop 设置）
    bars: dict[str, MarketSnapshot]
    benchmark_close: float | None = None
```

### 6.3 RESEARCH / RECOMMENDATION 模式（R7: RunMode 分离）

EngineLoop 收敛为 BACKTEST/LIVE。RESEARCH/RECOMMENDATION 在 Port 层 service 编排。

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

| RunMode | 编排位置 | EngineMode |
|---------|---------|------------|
| RESEARCH | Port / StrategyRunService | N/A（不经过 EngineLoop） |
| RECOMMENDATION | Port / StrategyRunService | N/A |
| BACKTEST | Port / BacktestService → EngineLoop | BACKTEST |
| LIVE | Port / LiveService → EngineLoop | LIVE |

---

## 7. 风控体系

### 7.1 三层风控架构

```
Pipeline 内 — ConstraintCheck（已有设计）
  职责：对 TargetPortfolio 做后置检查与确定性削减
  时机：Pipeline 最后一步，每轮调仓执行一次
  特征：无状态、纯函数、结果可解释

订单提交前 — PreTradeRiskCheck（逐单滚动，F1+A1）
  职责：对单个订单做提交前校验
  时机：每个订单提交前逐单执行，resize 后重检
  特征：无状态（上下文由 EngineLoop 管理）、返回 accept/reject/resize
  能力：购买力校验、超卖检查、价格合法性、手数校验、集中度校验、换手率校验

每日 step 后 — PostTradeRiskGuard（R4: RiskLock）
  职责：对组合状态做实时扫描，可主动触发订单
  时机：每个交易日执行一次（per-step）
  特征：有状态、可主动干预、支持紧急动作
  能力：回撤止损、单标的亏损止损、异常波动告警
```

### 7.2 PreTradeRiskCheck（F1: 滚动上下文, A1: resize 重检）

```python
@dataclass(frozen=True)
class OrderCheckResult:
    decision: Literal["accept", "reject", "resize"]
    order_id: str
    resized_quantity: int | None = None
    reason: str | None = None
    triggered_checks: tuple[str, ...] = ()   # R2: 完整命中 check id 链路

class PreTradeRiskCheck(Protocol):
    """订单提交前逐单校验 — 在 Brokerage.place_order() 之前"""
    def check_order(
        self, order: Order, context: PreTradeContext,
    ) -> OrderCheckResult: ...
```

每条规则从 PreTradeContext 获取所需数据：

| 规则 | 从 PreTradeContext 获取 |
|------|----------------------|
| `buying_power` | `context.buying_power_model.available_buying_power(context.account_view, order.direction)` + `context.fee_model.estimate(...)` |
| `no_short_sell` | `context.account_view.positions[id].available_quantity` |
| `price_validity` | `context.slice.bars[id].limit_up / limit_down` |
| `lot_size` | `context.rules[id][0].lot_size` |
| `concentration_pre` | `context.account_view.total_value` |
| `daily_turnover_pre` | `context.pending_tickets` 累计金额 |

#### A1: CompositePreTradeCheck — resize 后重检

```python
class CompositePreTradeCheck(PreTradeRiskCheck):
    """组合多个 PreTrade 规则，resize 后用新数量重新进入检查链"""

    MAX_RESIZE_ITERATIONS: int = 3

    def __init__(self, checks: tuple[PreTradeRiskCheck, ...]): ...

    def check_order(
        self, order: Order, context: PreTradeContext,
    ) -> OrderCheckResult:
        current_order = order
        triggered_checks: list[str] = []   # R2: 记录触发的 check id
        for iteration in range(self.MAX_RESIZE_ITERATIONS + 1):
            for check in self._checks:
                result = check.check_order(current_order, context)
                if result.decision == "reject":
                    return result
                if result.decision == "resize" and result.resized_quantity:
                    triggered_checks.extend(result.triggered_checks)
                    current_order = current_order.with_quantity(result.resized_quantity)
                    break  # 用新数量重新开始 check 链
            else:
                # 所有 check 通过
                return OrderCheckResult(
                    decision="accept",
                    order_id=current_order.order_id,
                    resized_quantity=(
                        current_order.quantity
                        if current_order.quantity != order.quantity
                        else None
                    ),
                    triggered_checks=tuple(triggered_checks),
                )
        # 超过最大重试次数
        return OrderCheckResult(
            decision="reject",
            order_id=order.order_id,
            reason="resize loop detected",
        )
```

**resize 重检逻辑说明**：

当一个 check 返回 resize 时，用新数量重新从第一个 check 开始检查。这防止了以下场景：
- `lot_size`: 350 → resize 400（凑整手）
- `buying_power`: 400 × 价格 > available → reject（如果不重检就会漏掉）

最大重试次数（3 次）防止理论上不应存在的 resize 循环。

### 7.3 PostTradeRiskGuard

```python
class PostTradeRiskGuard(Protocol):
    """每日 step 后扫描组合状态 — 可主动触发退出动作"""
    def scan(
        self,
        account_view: AccountView,
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
    cooldown_until: str | None = None    # S5: 跨日冷却预留
```

#### V1 内置 PostTrade 规则

| rule_id | 规则 | 动作 | 时机 |
|---------|------|------|------|
| `max_drawdown` | 组合回撤超阈值 | ALERT 或 LIQUIDATE | per-step |
| `single_loss_limit` | 单标的亏损超阈值 | REDUCE_POSITION | per-step |
| `concentration_limit` | 单标的持仓占比超限 | REDUCE_POSITION | per-step |
| `market_anomaly` | 市场/标的异常波动 | ALERT | per-step |

> **S5 冷却期（V2+）**：V1 的 RiskLock 只做当日锁定。V2+ 通过 `RiskAction.cooldown_until_date` 字段扩展，`clear_locks()` 改为只清除 `cooldown_until <= today` 的锁定。

### 7.4 三层风控分工总览

| 维度 | ConstraintCheck（Pipeline 内） | PreTradeRiskCheck（订单前） | PostTradeRiskGuard（每日） |
|------|-----|------|------|
| 输入 | TargetPortfolio（意图） | Order + PreTradeContext（滚动） | AccountView + Slice |
| 输出 | 修改后的 TargetPortfolio | accept/reject/resize | RiskAction（可触发订单） |
| 时机 | 调仓日 Pipeline 末尾 | 每个订单提交前（逐单滚动） | 每个交易日 step 后 |
| 状态 | 无状态 | 无状态（上下文由 EngineLoop 管理） | 有状态（追踪回撤等） |
| 能力 | 削减权重 | 拒单、缩单（resize 后重检） | 减仓、清仓、告警 |
| 举例 | max_weight=20% | buying_power 不够 | max_drawdown=-15% 清仓 |

设计原则：**Constraint 管"组合意图"，PreTrade 管"单笔合规"（滚动上下文），PostTrade 管"紧急干预"（RiskLock 防重入）**。

---

## 8. 统计与审计层

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
├── AlphaStatistics
└── 回答："这个策略实际赚了多少钱，怎么赚的？"
```

**复用边界**：

| 分类 | engine/evaluation 内容 | 策略统计复用方式 |
|------|----------------------|-----------------|
| **纯数学工具** | `scalar_to_float`, `two_sided_p_value`, ... | 直接 import 复用 |
| **可抽取的计算逻辑** | sharpe/sortino/max_dd/calmar 过程 | 抽取为独立函数后复用 |
| **因子专用语义** | `pearson_ic`, `rank_ic`, `fama_macbeth`, ... | **不复用** |
| **因子 portfolio 辅助** | `quantile_returns`, `turnover`, ... | **不复用** |

### 8.2 TradeBuilder

```python
class TradeMatchingMethod(StrEnum):
    FIFO = "fifo"
    FLAT_TO_FLAT = "flat_to_flat"

@dataclass(frozen=True)
class TradeRecord:
    """一笔完整交易 — 从 entry fill(s) 到 exit fill(s)"""
    trade_id: str
    instrument_id: str
    direction: OrderDirection
    entry_date: str
    exit_date: str | None
    entry_price: float
    exit_price: float | None
    quantity: int
    gross_pnl: float | None
    fees: float
    net_pnl: float | None
    holding_days: int | None
    return_pct: float | None
    entry_order_ids: tuple[str, ...]
    exit_order_ids: tuple[str, ...]

class TradeBuilder(Protocol):
    def on_fill(self, fill: FillEvent, account: AccountView) -> None: ...
    def get_open_trades(self) -> tuple[TradeRecord, ...]: ...
    def get_closed_trades(self) -> tuple[TradeRecord, ...]: ...
    def flush(self) -> tuple[TradeRecord, ...]: ...
```

### 8.3 三层统计体系

```python
@dataclass(frozen=True)
class TradeStatistics:
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

@dataclass(frozen=True)
class PortfolioStatistics:
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

@dataclass(frozen=True)
class AlphaStatistics:
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

### 8.4 ExecutionAuditCollector（S3: 统计与审计职责分离）

v2 的 `StatsCollector` 同时负责统计收集和风险日志，职责混合。v3 拆为 `ExecutionAuditCollector`，统一管理统计和审计日志。

```python
class ExecutionAuditCollector:
    """执行审计收集器 — 统计收集 + 审计日志的统一入口

    职责：
    - 统计：NAV / TradeRecord / PortfolioStats / AlphaStats
    - 审计：risk_log / pre_trade_log
    不负责业务逻辑判断（如风控规则评估），只负责收集和持久化。
    """

    def __init__(self, trade_builder: TradeBuilder): ...

    # ── 统计收集 ──

    def record(
        self,
        date: str,
        fills: tuple[FillEvent, ...],
        account_view: AccountView,  # 必须是成交后的快照 (R3)
        slice: Slice,
    ) -> None:
        for fill in fills:
            self._trade_builder.on_fill(fill, account_view)
        self._nav_series.append((date, account_view.nav))

    # ── 审计日志 ──

    def record_risk_scan(
        self, date: str, results: tuple[RiskScanRecord, ...],
    ) -> None:
        """R12: PostTrade 风控扫描记录"""
        self._risk_log.extend(results)

    def record_pre_trade_decisions(
        self,
        date: str,
        decisions: tuple[PreTradeDecisionRecord, ...],
    ) -> None:
        """A2 + F1: PreTrade 校验结果记录 — 统一记录 accept/reject/resize"""
        self._pre_trade_log.extend(decisions)

    # ── 报告构建 ──

    def build_report(self) -> BacktestReport:
        # ... 构建 BacktestReport ...
        return BacktestReport(
            ...,
            risk_log=tuple(self._risk_log),
            pre_trade_log=tuple(self._pre_trade_log),
        )
```

```python
@dataclass(frozen=True)
class RiskScanRecord:
    """单次 PostTrade 扫描记录 (R12)"""
    trade_date: str
    rule_id: str
    instrument_id: str | None
    severity: RiskSeverity
    action_taken: RiskActionType | None
    detail: str
    current_value: float | None
    threshold: float | None

@dataclass(frozen=True)
class PreTradeDecisionRecord:
    """PreTrade 单笔校验结果 — 覆盖 accept/reject/resize (A2 + F1)"""
    trade_date: str
    order_id: str
    instrument_id: str
    direction: OrderDirection
    original_quantity: int
    final_quantity: int | None     # resized 时的最终数量；None = 未修改（accept 原量）或被拒
    decision: str                  # "accepted" / "rejected" / "resized"
    reason: str | None = None
    check_sequence: tuple[str, ...] = ()  # 命中的 check id 列表
```

```python
@dataclass(frozen=True)
class BacktestReport:
    """完整回测报告 — 三层统计 + 审计日志"""
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
    risk_log: tuple[RiskScanRecord, ...]        # R12
    pre_trade_log: tuple[PreTradeDecisionRecord, ...]  # A2 + F1
```

### 8.5 Artifact 格式

```
strategy/runs/{strategy_id}/v{version}/{run_id}/
├── manifest.json                # 输入引用 + rule_refs + artifact 清单 + hash
│
├── decision_frame.parquet       # [Pipeline] 完整中间态
├── signal_snapshot.parquet      # [Pipeline] 信号快照
├── target_portfolio.parquet     # [Pipeline] 目标组合
├── rebalance_plan.parquet       # [Planner] 调仓计划
│
├── order_log.parquet            # [Brokerage] 订单生命周期
│   schema: trade_date, order_id, instrument_id, direction,
│           order_type, quantity, status, fill_price, fee,
│           pre_trade_decision, pre_trade_reason,   # A2
│           resized_from_quantity,                  # A2
│           pre_trade_check_sequence                # P4: 完整命中 check 链路
│
├── fill_log.parquet             # [Brokerage] 逐笔成交
│   schema: trade_date, fill_id, order_id, instrument_id, direction,
│           filled_quantity, fill_price, slippage, fee,
│           event_time, cumulative_quantity, leaves_quantity
│
├── nav.parquet                  # [AuditCollector] NAV 曲线
│   schema: trade_date, nav, benchmark_nav, drawdown, cash, exposure
│
├── trade_log.parquet            # [AuditCollector] 交易明细
│   schema: 同 TradeRecord 字段
│
├── risk_log.parquet             # [AuditCollector] 风控扫描记录 (R12)
│   schema: trade_date, rule_id, instrument_id, severity, action_taken,
│           detail, current_value, threshold
│
├── pre_trade_log.parquet        # [AuditCollector] PreTrade 决策记录 (A2, F1)
│   schema: trade_date, order_id, instrument_id, direction, quantity,
│           decision, reason
│
└── backtest_report.json         # [AuditCollector] 三层统计摘要 + 审计汇总
    schema: BacktestReport 的 JSON 序列化
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
│   ├── position.py       #   Position (frozen)
│   ├── cash.py           #   CashBook (frozen, R6)
│   ├── order_book.py     #   OrderBook / OrderTicket (frozen, F5) / OrderEvent / OrderBookReadOnly
│   ├── account.py        #   Account / AccountView
│   └── buying_power.py   #   BuyingPowerModel Protocol / CashAccountBuyingPower
│
├── strategy/             # [Phase 0-1] 策略决策层（纯计算，无 I/O）
│   ├── specs.py          #   StrategySpec / StrategyTemplate / StrategyVersion
│   ├── context.py        #   StrategyContext (含 risk_locked_instruments)
│   ├── models.py         #   StrategyRun / SignalSnapshot / TargetPortfolio / RebalancePlan
│   ├── protocols.py      #   DecisionStage Protocol
│   ├── pipeline.py       #   Pipeline Runner
│   ├── validation.py     #   Spec 校验
│   └── builtins/
│       ├── universe.py
│       ├── signal.py
│       ├── scoring.py
│       ├── regime.py
│       ├── filtering.py  #     含 RiskLockFilter (R4)
│       ├── selection.py
│       └── templates/
│           ├── etf_rotation.py
│           ├── etf_trend_swing.py
│           ├── stock_selection_trend.py
│           └── stock_sector_rotation.py
│
├── portfolio/            # [Phase 1] 组合构建层（纯计算，无 I/O）
│   ├── allocation.py     #   WeightAllocator
│   ├── sizing.py         #   RiskSizer
│   ├── constraints.py    #   ConstraintChecker
│   └── comparison.py     #   StrategyComparisonReport
│
├── execution/            # [Phase 2-3] 执行层（纯计算，无 I/O）
│   ├── orders.py         #   Order / OrderType / OrderDirection
│   ├── fills.py          #   FillOutcome (F4) / FillEvent
│   ├── planner.py        #   ExecutionPlanner (pending-aware, F2) / ExecutionPlan / BlockedOrder
│   ├── brokerage.py      #   Brokerage Protocol / BacktestBrokerage
│   ├── trade_builder.py  #   TradeBuilder / FifoTradeBuilder / TradeRecord
│   ├── reality/
│   │   ├── fill.py       #     FillModel / AShareFillModel / ClosingAuctionFillModel
│   │   ├── slippage.py   #     SlippageModel
│   │   ├── fee.py        #     FeeModel / AShareFeeModel
│   │   └── settlement.py #     SettlementModel / AShareSettlementModel
│   └── rules.py          #   InstrumentDefinition / TradingRuleSet / FeeSchedule
│
├── backtest/             # [Phase 3-4] 回测引擎（编排层）
│   ├── engine.py         #   EngineLoop / EngineConfig / EngineResult / PreTradeContext (F1)
│   ├── data_feed.py      #   DataFeed Protocol / ParquetDataFeed
│   ├── risk/
│   │   ├── pre_trade.py  #   PreTradeRiskCheck / CompositePreTradeCheck (A1: resize recheck)
│   │   └── post_trade.py #   PostTradeRiskGuard / RiskLock (R4)
│   └── audit/            # S3: 重命名 stats/ → audit/
│       ├── collector.py  #     ExecutionAuditCollector (S3)
│       ├── models.py     #     RiskScanRecord / PreTradeDecisionRecord (R12, A2, F1)
│       ├── trade.py      #     TradeStatistics
│       ├── portfolio.py  #     PortfolioStatistics
│       └── alpha.py      #     AlphaStatistics
```

### 9.2 模块间依赖关系

```
accounting  ←── 无 Core 依赖（最底层，纯数据结构）
strategy    ←── 无外部 Core 依赖（纯决策逻辑）
portfolio   ←── strategy（消费 TargetPortfolio）
execution   ←── accounting + portfolio（通过 AccountView，不依赖 backtest）
backtest    ←── strategy + execution + accounting（持有 Account 实例，state owner）
```

关键依赖规则：

- `accounting` 是最底层契约，不依赖任何其他 Core 模块
- `strategy` 不依赖 `portfolio` / `execution` / `backtest`
- `portfolio` 只依赖 `strategy`
- `execution` 只依赖 `accounting` + `portfolio`（不依赖 backtest）
- `backtest` 是编排层，持有 Account 实例，依赖 strategy + execution + accounting
- 所有模块共享 `engine/evaluation/metrics/_math.py` 中的数学公式

### 9.3 DataHub / Port 新增（R10: 标 Greenfield）

```
DataHub 新增:
├── services/strategy/
│   ├── strategy_catalog_service.py     # **Greenfield** — 策略 spec 管理
│   ├── strategy_artifact_service.py    # **Greenfield** — 策略 artifact 生命周期
│   └── instrument_rule_provider.py     # 基于现有 InstrumentRegistration + Extension（增量）
├── stores/metadata/
│   ├── trading_rule_store.py           # PIT 版本化（基于现有 PIT 基建）
│   └── fee_schedule_store.py           # PIT 版本化
└── services/audit/                     # S3: 新增审计服务层
    └── execution_audit_service.py      # risk_log / pre_trade_log 持久化

Port 新增:
├── services/strategy/
│   ├── strategy_run_service.py         # RESEARCH/RECOMMENDATION 编排
│   ├── backtest_service.py             # BACKTEST 编排
│   └── strategy_input_assembler.py     # StrategyInputBundle 组装
```

> **R10 归档**：
> - `packages/core/src/ditto_core/strategy/README.md` → `docs/archive/`（与 v2 Pipeline 冲突）
> - `packages/core/src/ditto_core/portfolio/README.md` → `docs/archive/`（与 v2 冲突）

---

## 10. 测试策略

### 10.1 测试类型总览

| 测试类型 | 适用对象 | 方法 | 示例 |
|---------|---------|------|------|
| 快照测试 | EngineLoop、AuditCollector | 固定输入 → 固定输出 | 3 日快照 NAV = 1,003,210.50 |
| 不变量测试 | Account、CashBook、OrderBook | 状态机合法性 | 不超卖、现金守恒、终态不可逆 |
| 场景矩阵 | FillModel、FeeModel、Settlement | 参数化组合 | 涨跌停 × 买卖 × Market/Limit |
| 属性测试 | PortfolioStatistics | 数值范围 | NAV > 0, max_drawdown <= 0 |

### 10.2 测试分层

```
tests/
├── unit/
│   ├── accounting/         #   Position / CashBook / OrderBook 状态机
│   ├── strategy/           #   Pipeline 各阶段 / Spec 校验
│   ├── portfolio/          #   Allocator / Sizer / Constraint
│   ├── execution/          #   Order / FillOutcome / FillModel / FeeModel
│   └── backtest/           #   PreTrade / PostTrade / AuditCollector
│
├── integration/
│   ├── strategy/           #   端到端 Pipeline
│   └── backtest/           #   完整引擎步进（3-5 日快照测试）
│
└── snapshot/
    └── backtest/           #   回测引擎输出 artifact 不变
```

### 10.3 各模块测试重点

**accounting/ — 不变量测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| CashBook | 现金守恒 | fill 前后净值差异 = 费用 |
| CashBook | frozen 不可变 | 修改属性抛 FrozenInstanceError |
| OrderBook | 终态不可逆 | FILLED → CANCEL 抛 StateTransitionError |
| OrderBook | Fill 幂等性 | 同一 fill 重复 apply 不改变状态 |
| OrderTicket | frozen 不可变 | with_fill 返回新实例 |
| Account | 不超卖 | 卖出数量 <= effective_position |
| Account | T+1 冻结 | 买入当日 available_quantity 不变 |

**strategy/ — 纯函数测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| 每个 builtin stage | 参数化 + edge case | `top_k(k=0)`, 空输入 |
| Scorer | 固定输入 → 期望输出 | 排名一致性 |
| ConstraintCheck | 优先级冲突 | priority 小的先执行 |
| Spec 校验 | 非法参数拒绝 | `min > max` 应报错 |
| RiskLockFilter | 锁定标的不选入 | 过滤正确 |

**execution/ — 场景矩阵测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| FillModel | 场景矩阵 | 涨跌停 × 买卖 × Market/Limit → Filled/NoFill |
| FeeModel | 边界值 | 佣金 < 5 元 → 5 元 |
| SettlementModel | T+0/T+1 | ETF 股票型次日可卖 |
| ExecutionPlanner | pending-aware | 有 pending 卖单时不重复生成卖单 (F2) |
| ExecutionPlanner | planner lock | 锁定标的禁止新增买单 (S1) |
| 数量取整 | 100+1 | 买入 50 → 100，买入 350 → 350 |
| 卖出零股 | 拆分 | 持仓 350 → 整手 300 + 零股 50 |
| OrderTicket | frozen | with_fill 返回新实例，原实例不变 |

**backtest/ — 快照测试 + 属性测试**

| 测试对象 | 测试方法 | 说明 |
|---------|---------|------|
| EngineLoop | 3-5 日快照 | 固定输入 → 期望 NAV 序列 |
| PreTrade rolling | 批内累积 | 第二笔买单看到第一笔的 reserved_cash (F1) |
| PreTrade resize | 重检 | lot_size resize 后 buying_power 仍检查 (A1) |
| PostTrade | 锁定 + 清除 | 当日锁定、次日清除 (R4) |
| AuditCollector | 已知序列 | 固定 Fills → 期望统计 |
| PortfolioStatistics | 属性测试 | NAV > 0, max_drawdown <= 0 |

### 10.4 Reality Model 测试方法

```python
@pytest.mark.parametrize("scenario", A_SHARE_FILL_SCENARIOS)
def test_fill_model_scenario(scenario):
    """场景矩阵覆盖 A 股规则的所有组合 — 返回 FillOutcome"""
    outcome = fill_model.try_fill(scenario.order, scenario.market, scenario.rule)
    if scenario.should_fill:
        assert isinstance(outcome, Filled)
        assert outcome.fill_event.filled_quantity == scenario.expected_quantity
    else:
        assert isinstance(outcome, NoFill)
        assert outcome.reason == scenario.expected_reason
```

### 10.5 确定性回放测试（S4: 拆为两层）

```python
# Layer 1: 同 manifest + 同代码版本 → 结果完全一致
def test_reproducible_with_same_manifest():
    """同 manifest + 同代码 → 输出完全一致"""
    manifest_a, result_a = run_backtest(config)
    manifest_b, result_b = run_backtest(config)
    assert manifest_a.rule_refs == manifest_b.rule_refs
    assert result_a.final_nav == result_b.final_nav
    assert result_a.fill_log == result_b.fill_log
    assert result_a.nav_series == result_b.nav_series

# Layer 2: 代码版本变化时 → diff report 精确指出差异
def test_version_change_diff_report():
    """代码升级后，diff report 能定位差异来源"""
    manifest_v1, result_v1 = run_backtest(config, engine_version="1.0.0")
    manifest_v2, result_v2 = run_backtest(config, engine_version="1.1.0")
    diff = compute_run_diff(manifest_v1, result_v1, manifest_v2, result_v2)
    # diff 应指出具体哪些标的/哪些 step 的结果变了
    assert len(diff.affected_instruments) >= 0  # 可以为空（无差异）
    assert len(diff.affected_dates) >= 0
```

### 10.6 完整不变量测试清单

| 测试 | 来源 | 说明 |
|------|------|------|
| `test_cash_conservation` | v2 | 现金守恒 |
| `test_no_oversell` | v2 | 不超卖 |
| `test_terminal_state_irreversible` | v2 | 终态不可逆 |
| `test_cash_book_immutability` | R6 | frozen CashBook 不可修改 |
| `test_order_ticket_immutability` | F5 | frozen OrderTicket |
| `test_exit_order_has_rules` | R2 | 退出标的 rules 加载正确 |
| `test_stats_use_post_fill_snapshot` | R3 | 统计 NAV = 成交后 NAV |
| `test_no_fill_event_on_suspended` | R8 | 停牌 → NoFill，不产生 FillEvent |
| `test_no_fill_event_on_limit_up` | R8 | 涨停买入 → NoFill |
| `test_risk_lock_prevents_reentry` | R4 | 清仓标的不被 Pipeline 选入 |
| `test_risk_lock_clears_next_day` | R4 | 次日锁定自动清除 |
| `test_rule_refs_frozen_in_manifest` | R11 | manifest 包含规则版本 |
| `test_rule_refs_all_versions_preserved` | F3 | 跨规则变更日的版本不被覆盖 |
| `test_risk_log_persisted` | R12 | 风控扫描写入 risk_log |
| `test_pre_trade_decision_logged` | A2, F1 | PreTrade 决策（accept/reject/resize）写入 pre_trade_log |
| `test_rolling_pre_trade_context` | F1 | 批内第二笔买单看到第一笔的 reserved_cash |
| `test_pending_aware_planner_no_duplicate_sell` | F2 | 有 pending 卖单时不重复生成 |
| `test_planner_lock_prevents_buy` | S1 | 锁定标的不生成买单 |
| `test_resize_triggers_recheck` | A1 | resize 后 buying_power 仍检查 |
| `test_reproducible_with_same_manifest` | S4 L1 | 同 manifest 结果一致 |
| `test_version_change_diff_report` | S4 L2 | 版本升级 diff 可定位 |
| `test_manifest_canonical_json_stable` | P2 | 同输入二次生成 manifest.json 字节级一致 |
| `test_rule_refs_sorted_and_diffable` | P2 | rule_refs 按稳定 key 排序，diff 可定位变更 |
| `test_order_log_resize_check_chain` | P4 | order_log.pre_trade_check_sequence 能完整还原 resize 链路 |

---

## 11. Phase 规划

### 11.1 重组后的 Phase 规划

```
Phase 0:  基础语义与数据契约
  ┌─ accounting/（Account / AccountView / Position / CashBook frozen / OrderTicket frozen）
  │   └─ BuyingPowerModel Protocol
  ├─ StrategySpec / StrategyRun / StrategyTemplate / StrategyVersion
  ├─ DecisionFrame schema 定义
  ├─ InstrumentDefinition / TradingRuleSet / FeeSchedule（三层规则数据对象）
  ├─ ParamConstraint 参数约束
  ├─ FillOutcome / Filled / NoFill（F4）
  ├─ DataHub 控制面表（strategy_version / strategy_run / strategy_artifact）
  ├─ DataHub InstrumentRuleProvider（三层规则组装）
  ├─ DataHub trading_rule_store + fee_schedule_store（PIT 版本化存储）
  └─ DataHub execution_audit_service（审计日志持久化，S3）
  📋 交付物：账户契约 + 三层规则 + FillOutcome + 策略可定义/版本化/存储
  🎯 里程碑：accounting 层可测试 + 策略 spec CRUD + DRAFT/PUBLISHED 治理

Phase 1:  决策 Pipeline 闭环
  ┌─ Pipeline Runner（编排 Universe → Signal → Score → Filter → Select）
  ├─ 内置 stage 实现（含 RiskLockFilter, R4）
  ├─ WeightAllocator（equal_weight / score_weight）
  ├─ ConstraintCheck + priority
  ├─ etf_rotation 模板端到端验证
  └─ StrategyInputBundle 组装 + SignalSnapshot / TargetPortfolio 输出
  📋 交付物：输入 bundle → Pipeline → TargetPortfolio
  🎯 里程碑：ETF 轮动策略 RECOMMENDATION 闭环

Phase 2:  日频回测 V1（简化版）
  ┌─ 简化 ExecutionPlanner（pending-aware diff, F2；不含 T+1/涨跌停）
  ├─ 简化 BacktestBrokerage（线性佣金 + 固定滑点，使用 FillOutcome）
  ├─ CashAccountBuyingPower 实现
  ├─ EngineLoop（日历步进 + 调仓触发 + rolling PreTrade, F1）
  ├─ CompositePreTradeCheck（含 resize recheck, A1）
  ├─ ParquetDataFeed
  ├─ FillEvent / ExecutionAuditCollector V1（NAV / PortfolioStats）
  ├─ FifoTradeBuilder V1
  ├─ PreTrade 审计日志（A2）
  ├─ order_log / fill_log artifact
  └─ etf_rotation 回测集成测试（快照测试 + 不变量测试）
  📋 交付物：完整回测闭环，含 pending-aware planner + rolling pre-trade + 审计日志
  🎯 里程碑：ETF 轮动策略 BACKTEST 闭环 + 基础统计报告

Phase 3:  Reality Model 完整化
  ┌─ AShareFillModel（涨跌停 / 停牌 / LIMIT / 集合竞价）→ FillOutcome
  ├─ AShareFeeModel（最低 5 元 / 印花税 / 过户费）
  ├─ AShareSettlementModel（T+0/T+1）
  ├─ VolumeShareSlippage
  ├─ ExecutionPlanner 完整化（T+1 / 涨跌停 / 停牌 / 100+1）
  ├─ 规则版本化接入（trading_rule_store + fee_schedule_store PIT 查询）
  ├─ InstrumentLifecycle 基础（ST/*ST → price_limit_pct）
  └─ 快照测试升级（含涨跌停/ST 场景）
  📋 交付物：回测引擎对 A 股规则完整建模（含规则版本化）
  🎯 里程碑：涨跌停/T+1/100+1/ST 场景的回测结果可信

Phase 4:  风控 + 统计完善
  ┌─ PreTradeRiskCheck + 6 条内置规则（含 rolling context）
  ├─ PostTradeRiskGuard + 4 条内置规则（含 RiskLock）
  ├─ RuleRefs 进 RunManifest（F3: 全量冻结）
  ├─ TradeStatistics + AlphaStats
  ├─ risk_log / pre_trade_log artifact（R12, A2）
  ├─ StrategyComparisonReport
  ├─ 确定性回放测试（S4）
  └─ 风控集成测试
  📋 交付物：三层风控 + 完整统计 + 审计日志 + 确定性回放
  🎯 里程碑：回测报告可直接用于策略决策

Phase 5:  多策略模板扩展
  ┌─ etf_trend_swing 模板
  ├─ stock_selection_trend 模板
  ├─ stock_sector_rotation 模板
  ├─ inverse_vol allocator
  ├─ InstrumentDefinition 扩展（新股前 N 日 / 退市整理期）
  ├─ RiskLock 跨日 cooldown（S5）
  └─ 每个模板的回测快照测试
  📋 交付物：4 个策略模板全部可用
  🎯 里程碑：选股类策略回测闭环

─── 以下为 T1 延续（不在初期目标内） ───

Phase 6:  实盘执行适配
Phase 7:  API 产品化
Phase 8:  高级能力
  ┌─ Mean-Variance / Risk Parity
  ├─ Walk-Forward 参数优化
  ├─ 多策略资金预算
  ├─ MarginAccountBuyingPower（融资融券）
  ├─ PositionLot 多批次持仓
  └─ MultiCurrencyCashProvider / OMS / Specs CalendarId 注册化
```

### 11.2 关键路径

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5
                                                         ↕
                                              (Phase 4 依赖 Phase 3)
                                              (Phase 5 可与 Phase 4 并行)
```

### 11.3 Phase 0-4 变更影响

| Phase | 新增/变更 | 说明 |
|-------|----------|------|
| Phase 0 | F4 (FillOutcome), F5 (OrderTicket frozen), R6 (CashBook frozen), S3 (ExecutionAuditCollector) | 数据结构定义阶段就落地 |
| Phase 1 | R4 (RiskLockFilter) | Pipeline 内置 filter 增加一个 |
| Phase 2 | F1 (rolling PreTrade), F2 (pending-aware Planner), A1 (resize recheck), A2 (pre_trade audit) | EngineLoop 核心逻辑，Phase 2 主线 |
| Phase 3 | R6 (三层分离签名), R8 (FillOutcome 集成) | Reality Model 自然收敛 |
| Phase 4 | R4 (PostTrade + RiskLock), F3 (RuleRefs 全量冻结), R12 (risk_log), S4 (确定性测试), S5 (cooldown 预留) | 风控 + 治理面 |

**结论**：所有修订可在对应 Phase 内消化，不引入新的 Phase，不改变关键路径。

---

## 12. Artifact 与持久化

### 12.1 新增 Artifact 类型

| artifact_kind | 来源 | 格式 | 来源标注 |
|--------------|------|------|---------|
| `decision_frame` | Pipeline | Parquet | 已有 |
| `signal_snapshot` | Pipeline | Parquet | 已有 |
| `target_portfolio` | Pipeline | Parquet | 已有 |
| `rebalance_plan` | ExecutionPlanner | Parquet | 已有 |
| `order_log` | Brokerage | Parquet | 已有，A2 补字段 |
| `fill_log` | Brokerage | Parquet | 已有 |
| `nav` | ExecutionAuditCollector | Parquet | 已有 |
| `trade_log` | ExecutionAuditCollector | Parquet | 已有 |
| `backtest_report` | ExecutionAuditCollector | JSON | 已有 |
| `risk_log` | ExecutionAuditCollector | Parquet | R12 新增 |
| `pre_trade_log` | ExecutionAuditCollector | Parquet | A2 新增 |

### 12.2 Artifact 目录结构

详见 §8.5。

### 12.3 控制面表

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
    # 审计日志 (R12, A2)
    RISK_LOG = "risk_log"
    PRE_TRADE_LOG = "pre_trade_log"
    # 诊断
    DIAGNOSTICS = "diagnostics"
```

### 12.4 RunManifest（R7: RunMode, F3: RuleRefs 全量冻结, S2: rule_resolution_policy）

```python
@dataclass(frozen=True)
class RuleRef:
    """某次 run 中使用的规则版本快照 — 全量保留，不去重覆盖（F3）"""
    instrument_id: str
    definition_version: str          # InstrumentDefinition 的 hash
    trading_rule_as_of: str          # TradingRuleSet 的 effective_from
    fee_schedule_as_of: str          # FeeSchedule 的 effective_from
    trading_rule_effective_to: str | None   # F3: 生效区间上界
    fee_schedule_effective_to: str | None   # F3: 生效区间上界

@dataclass(frozen=True)
class RunManifest:
    run_id: str
    strategy_id: str
    strategy_version: int
    mode: RunMode                       # R7: RunMode（非 EngineMode）
    input_refs: tuple[StrategyInputRef, ...]
    parameter_overrides: dict[str, object]
    rule_refs: tuple[RuleRef, ...]     # R11 + F3: 全量冻结
    artifacts: tuple[ArtifactEntry, ...]
    config_hash: str
    engine_version: str
    rule_resolution_policy: str        # S2: "as_of_date" / "effective_range"
    created_at: str                  # RFC3339（UTC），内存态用 datetime
```

**F3: 全量冻结收集方式**：

```python
def run(self) -> EngineResult:
    # key = (instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of)
    # 保留首次出现，不去重覆盖（definition_version 防止 InstrumentDefinition 变更被折叠）
    rule_ref_map: dict[tuple[str, str, str, str], RuleRef] = {}

    for date in self._trading_days:
        self._step(date)
        for iid, (defn, rule, fee) in self._current_step_rules.items():
            def_ver = self._hash_definition(defn)
            key = (iid, def_ver, rule.as_of_date, fee.as_of_date)
            if key not in rule_ref_map:
                rule_ref_map[key] = RuleRef(
                    instrument_id=iid,
                    definition_version=self._hash_definition(defn),
                    trading_rule_as_of=rule.as_of_date,
                    fee_schedule_as_of=fee.as_of_date,
                    trading_rule_effective_to=rule.effective_to,
                    fee_schedule_effective_to=fee.effective_to,
                )

    manifest = RunManifest(
        ...,
        rule_refs=tuple(sorted(rule_ref_map.values(), key=lambda r: (
            r.instrument_id, r.definition_version,
            r.trading_rule_as_of, r.fee_schedule_as_of,
        ))),
    )
```

> **S2: rule_resolution_policy** — `"as_of_date"` 表示"取 as_of_date 当天有效的规则"，`"effective_range"` 表示"取包含该日期的生效区间"。V1 使用 `"as_of_date"`。这个字段让确定性回放的语义边界更明确。
>
> **P2: manifest 序列化规范** — `manifest.json` 必须使用 canonical JSON（key 排序、无多余空白）序列化。`rule_refs` 按 `(instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of)` 稳定排序，保证同 manifest 二次生成字节级一致。

### 12.5 与现有 DataHub 的集成

执行层和统计层的 artifact 走同一条持久化路径——通过 `StrategyArtifactService` 落盘。审计日志（risk_log、pre_trade_log）通过 `ExecutionAuditService`（S3）持久化，同样走 `strategy_artifact` 表索引。

新增的 artifact 只是 `artifact_kind` 枚举的新值，不需要新建表或新的 service 接口。

---

## 附录 A：业界对标参考

### A.1 QuantConnect LEAN 关键设计

- `BrokerageModel` 是策略中心，通过 `GetFillModel(Security)` / `GetFeeModel(Security)` 按资产类型分发
- `SecurityInitializer` 将 BrokerageModel 策略绑定到每个 Security
- 交易规则存在 `Security.SymbolProperties`，不在 BrokerageModel 上
- `TradeBuilder` 支持 FIFO / FIFOV / LIFO / FlatToFlat
- 参考：https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/key-concepts

### A.2 NautilusTrader 关键设计

- `Instrument` 是纯数据对象，引擎完全不感知资产类型
- Rust 核心提供确定性事件驱动运行时
- `RiskEngine` 提供 pre-trade 和 post-trade 双层风控
- 参考：https://nautilustrader.io/docs/latest/concepts/instruments/

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
| 表达式编译器 (expression/) | 95% | 因子计算可复用 | 不阻塞 |
| 因子评估 (evaluation/metrics/) | 95% | `_math.py` 纯数学可复用 | 不阻塞 |
| 物化模型 (materialization/) | 85% | artifact-first 模式直接复用 | 不阻塞 |
| DataHub PIT 基础设施 | 90% | 规则版本化的天然基座 | 不阻塞 |
| InstrumentId 分配 (8 大资产类别) | 90% | ID 空间已预留 | 不阻塞 |
| 四级标识符体系 | 85% | source/standard/instrument/ticker | 不阻塞 |
| InstrumentRegistration + Extension | 70% | InstrumentDefinition 数据源 | 不阻塞 |
| specs.py (CalendarId/GrainId) | 60% | CalendarId 硬编码 | 不阻塞 |

### B.2 specs.py 硬编码清单

文件：`packages/core/src/ditto_core/engine/specs.py`

| # | 硬编码 | V1 阻塞 | 升级时机 |
|---|--------|---------|---------|
| 1 | `CalendarId = Literal["cn_stock"]` | 不阻塞 | Phase 8 |
| 2 | `GrainId = Literal["1d", "1m"]`，1m 未实现 | 不阻塞 | Phase 8 |
| 3 | `entity_keys` 单键硬校验 | 不阻塞 | 按需 |
| 4 | `CALENDAR_TO_TIMEZONE` 只有一条 | 不阻塞 | Phase 8 |

### B.3 evaluation/metrics/ 复用清单

| 文件 | 复用方式 |
|------|---------|
| `_math.py` | **直接 import** |
| `portfolio.py` sharpe/sortino/dd | **抽取为独立函数后复用** |
| `ic.py` / `factor_analysis.py` | 不复用（因子专用语义） |
| `tail_risk.py` | 可选复用 |

### B.4 现有内核资产可直接消费

| 资产 | 策略引擎用法 |
|------|------------|
| PIT 基础设施 | TradingRuleSet / FeeSchedule 版本化查询 |
| artifact-first 模式 | 策略 run artifact 持久化 |
| InstrumentIdRange | 8 大资产类别 ID 空间 |
| 四级标识符体系 | standard_ticker ↔ source_ticker 双向转换 |
| InstrumentRegistration | InstrumentDefinition 数据来源 |
| InstrumentExtension | StockExtension.list_status → lifecycle_state |

---

## 附录 C：v3+ 远景规划

> 以下内容不阻塞 v3 Phase 0-5，作为后续架构升级的方向性规划。

### C.1 核心升级目标

> 不是"能跑回测的策略引擎"，而是：
> **一个以 PIT 正确性、事件可回放、决策可解释、规则可审计 为核心的策略操作系统。**

### C.2 事件账本架构（替代可变 Account）

**v3 现状**：Account 是可变对象（Brokerage 持有），AccountView 是 frozen snapshot。状态变更直接发生，不记录变更原因。

**v4 目标**：Account 变成 `AccountSnapshot`，由事件流 projection 得出。

```python
class AccountEvent:
    event_id: str
    timestamp: datetime
    run_id: str

class OrderAccepted(AccountEvent): order_id: str; instrument_id: str; direction: OrderDirection; quantity: int
class OrderRejected(AccountEvent): order_id: str; reason: str
class FillReceived(AccountEvent): fill: FillEvent
class CashDebited(AccountEvent): amount: float; reason: str
class RiskTriggered(AccountEvent): action: RiskAction
class RiskLockApplied(AccountEvent): instrument_id: str; reason: str; cooldown_until: str | None

class EventStore:
    def append(self, event: AccountEvent) -> None: ...
    def get_events(self, run_id: str, date: str | None = None) -> tuple[AccountEvent, ...]: ...

class AccountProjector:
    def project(self, events: tuple[AccountEvent, ...]) -> AccountSnapshot: ...
```

**收益**：完美可审计、完美可回放、完美可 diff。

**迁移路径**：
1. v3 阶段：所有状态变更方法保持"输入 → 输出"签名风格
2. v4 阶段：Account.apply_fill → EventStore.append(FillReceived(...)) + AccountProjector.project()

### C.3 StateDiffReport — 研究-治理闭环

```python
@dataclass(frozen=True)
class StateDiffReport:
    run_id_a: str
    run_id_b: str
    input_diff: InputDiff
    rule_diff: RuleDiff
    signal_diff: SignalDiff
    target_diff: TargetDiff
    execution_diff: ExecutionDiff
    risk_diff: RiskDiff
    performance_diff: PerformanceDiff
```

**使用场景**：参数调优、引擎升级、规则变更 → 精确定位影响范围。

### C.4 DecisionTraceService — 解释链路查询

```python
@dataclass(frozen=True)
class DecisionTrace:
    run_id: str
    instrument_id: str
    universe_reason: str | None
    signal_value: float | None
    weight_assigned: float | None
    order_quantity: int | None
    pre_trade_result: OrderCheckResult | None
    fills: tuple[FillEvent, ...]
    no_fill_reasons: tuple[str, ...]
    risk_events: tuple[RiskScanRecord, ...]
```

**实现方式**：聚合查询，数据来自现有 artifact（decision_frame / execution_plan / fill_log / risk_log）。V1 只需确保这些 artifact 都记录 `run_id` + `instrument_id`。

### C.5 三平面架构显式化

| 平面 | v3 对应 | v4 显式化 |
|------|--------|----------|
| 语义平面 | StrategySpec → TargetPortfolio → ExecutionPlan → Order | 命名为 Semantic Plane |
| 运行时平面 | Slice → AccountView → OrderTicket → FillEvent → RiskAction | 命名为 Runtime Plane，事件账本落地 |
| 治理平面 | RunManifest → InputRefs → RuleRefs → Artifacts | 命名为 Governance Plane，StateDiff + Certification |

**v4 不改类型名**——只在设计文档中显式标注所属平面。

### C.6 PIT 全局约束

**v3 现状**：PIT 用于 TradingRuleSet / FeeSchedule 的版本化查询。

**v4 目标**：PIT 扩展为全局约束——引擎中的每个值都关联到一个时间戳。

| 数据 | PIT 约束 |
|------|---------|
| TradingRuleSet | as_of_date（已有） |
| FeeSchedule | as_of_date（已有） |
| MarketSnapshot | trade_date（已有） |
| AccountSnapshot | projection_as_of（v4 新增） |
| NAV | calculated_at（v4 新增） |
| InstrumentDefinition | version_hash（v4 新增） |

### C.7 v4 Phase 规划

```
v4 Phase A: 事件账本基础设施
  ├─ AccountEvent 体系 + EventStore + AccountProjector
  ├─ Account → AccountSnapshot 迁移
  └─ 事件流可回放验证

v4 Phase B: 治理面完善
  ├─ StateDiffReport
  ├─ Run Certification
  └─ RuleRefs diff 工具

v4 Phase C: 解释链路
  ├─ DecisionTraceService
  └─ Web 工作台集成

v4 Phase D: PIT 全局约束
  ├─ 所有数据对象的时间溯源
  └─ PIT 违规检测（静态分析）
```

### C.8 战略方向采纳判定

| 战略建议 | v3 采纳情况 | v4 计划 |
|---------|------------|---------|
| 三个平面架构 | 隐式对齐 | v4 显式化为组织原则 |
| 事件账本 | 不采纳（保持可变 Account） | v4 Phase A 核心升级 |
| RuleRefs / 确定性回放 | F3 全量冻结采纳 | v4 Phase B 扩展 diff |
| risk_log 一级 artifact | R12 采纳 | v4 Phase B Certification |
| pre_trade_log 审计 | A2 采纳 | — |
| StateDiffReport | 不采纳 | v4 Phase B |
| 解释链路 | 不采纳（V1 确保数据关联） | v4 Phase C |
| PIT 全局约束 | 仅规则版本化 | v4 Phase D |
| 控制面先强后广 | R9/R10 已覆盖 | — |
