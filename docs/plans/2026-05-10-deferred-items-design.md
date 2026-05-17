# B8/B9/B10 延后项决策设计

> 创建：2026-05-10
> 基线：`docs/plans/2026-05-10-b8-b9-b10-remediation-plan.md` 延后项清单
> 状态：已确认
> 方法：源码分析 + 业界对标（LEAN / NautilusTrader / vnpy）→ 决策

---

## 决策总览

延后 8 项代码级 + 9 项架构级，经源码调研和业界对标后决策如下：

| 类别 | 执行 | 接受现状 |
|------|------|---------|
| 代码级 | 4 项（含大文件拆分 7 文件） | 4 项 |
| 架构级 | Phase 1 Runtime Spine + Phase 2 OMS Lite（含 Port ISP） | Phase 3 已降级合并入 Phase 2 |

---

## 一、代码级延后项决策

### 1. B9-K.2 `DEFAULT_COMMISSION_RATE` 归属 → 接受 kernel + 清理附带问题

**调研结论**：`DEFAULT_COMMISSION_RATE` 已在正确位置。

kernel 满足全部 5 条准入规则：
1. 跨层使用（execution/risk/backtest/strategy/application 5 包消费）✅
2. 零业务行为（纯 `float` 常量）✅
3. 高稳定性（佣金费率是领域常量）✅
4. 无外部依赖 ✅
5. 纯值语义 ✅

移入任何单一包都会违反架构禁令（如 strategy↛execution）。kernel 是唯一公共祖先。

**附带问题修复**：
- `default_price_limit_pct()`：零生产消费者（仅 execution 测试引用），删除或标注 reserved
- apps 副本 `_DEFAULT_COMMISSION_RATE = 0.0003`：Pydantic + `from __future__ import annotations` 的 linter workaround，添加 sync guard 注释或提取为常量引用

### 2. B9-K.6 DecisionFrame → 删除 kernel 死 Protocol

**调研结论**：存在两个互相矛盾的定义。

| 定义 | 位置 | 类型 | 消费者 |
|------|------|------|--------|
| kernel `DecisionFrame(Protocol)` | `kernel/strategy.py` | 3 property: `instruments`/`signals`/`scores` | **零** |
| strategy `type DecisionFrame = pl.DataFrame` | `strategy/alpha/protocols.py` | 类型别名 | 全部 stage/pipeline |

两者结构不兼容（`pl.DataFrame` 没有 `instruments`/`signals`/`scores` 属性）。kernel Protocol 从未被使用。

strategy 层已有 `validate_frame()`（`alpha/frame.py`），在 pipeline 各 stage 入口做列名存在性检查，是实际契约。

**决策**：删除 kernel 死 Protocol，strategy 的 `pl.DataFrame` + `validate_frame()` 是实际契约。

### 3. B9-EX.4 compute_diff → 引入 DiffContext

**调研结论**：10 个参数，1 个调用点（`SimpleExecutionPlanner.plan()`），已有 `# noqa: PLR0913`。

参数自然分组：

```python
@dataclass(frozen=True, slots=True)
class DiffContext:
    # Portfolio state
    target: TargetPortfolioLike
    account_view: AccountView
    pending_delta: dict[InstrumentId, int]

    # Scope + Market data
    all_instruments: set[InstrumentId]
    instrument_rules: dict[InstrumentId, InstrumentRules]
    market_snapshots: dict[InstrumentId, MarketSnapshot]
    default_lot_size: int

    # Policy
    locked_instruments: set[InstrumentId]
    pre_check_fn: Callable[
        [InstrumentId, int, dict[InstrumentId, MarketSnapshot]],
        BlockedOrder | None,
    ]
```

`compute_diff` 签名从 10 参数降至 3：`(ctx: DiffContext, make_order: MakeOrderFn)` → `tuple[list[Order], list[BlockedOrder]]`。

`make_order` 保持独立参数（factory/callback，不属于 frozen dataclass）。

### 4. B9-DATA.4 + B9-APP.5 大文件拆分 → Facade 模式

**调研结论**：7 个文件 > 600 LOC，全部有清晰自然分段。

**策略**：Facade 模式（项目已有先例——B9-DATA.2 `errors.py` 606 LOC → 4 域文件 + facade）。

优势：
- 公共 API 零破坏（消费端 import 路径不变）
- `arch-check` 不受影响
- 每个文件独立拆分、独立验证

**执行顺序（按难度递增）**：

| 序号 | 文件 | LOC | 难度 | 拆分方案 |
|------|------|-----|------|---------|
| 1 | config.py | 615 | 低 | INGESTION_SPECS（纯数据）→ `config/specs.py`，helpers → `config/queries.py` |
| 2 | research.py | 603 | 低 | 底部 154 LOC 纯函数 → `research_helpers.py`，snapshot builders 各保留 |
| 3 | capital.py | 725 | 低 | 按子域分组：valuation/dividend/margin/pledge → capital_market.py，index → index_data.py，corporate → corporate_events.py |
| 4 | runtime_builder.py | 627 | 中 | 反序列化段(174 LOC) → `deserialization.py`，模板配置段(150 LOC) → `template_builders.py` |
| 5 | tushare_source.py | 777 | 中 | 按资产域：stock/etf/index/fundamental/capital/macro/fx 各段委托清晰 |
| 6 | market_service.py | 752 | 中高 | query types → `queries.py`，core engine → `engine.py`，adjustment → `adjustment.py`，convenience API 保留 |
| 7 | coordinator.py | 763 | 高 | instrument-level 路径(180 LOC) → `instrument_ingestion.py`，side effects → `post_ingest.py`。需行为快照测试先行 |

每个拆分后原文件保留为 facade（re-export），确保公共 API 不变。

### 5. 接受现状的项

| 项 | 决策 | 理由 |
|----|------|------|
| B9-PF.5 Constraint priority 移除 | 延后 | P2，待触发动机（如新增 check 时） |
| B9-RK.2 checks.py 拆分 | 延后 | 319 LOC 内聚性高，每个 check 25-45 行，拆分收益有限 |
| B9-DATA.3 apps DI 注入 | 接受 | registry/contexts 是 Composition Root，直接引用具体服务类是标准做法（Mark Seemann DI 模式） |

---

## 二、架构级延后项：3 Phase 依赖链

基于业界对标（LEAN / NautilusTrader / vnpy），确认依赖链和设计方向：

### Phase 1: Runtime Spine

**业界核心洞察**：LEAN 的 backtest/live parity 秘密是**一个接口**：

```
ISynchronizer.StreamData() → IEnumerable<TimeSlice>
```

主循环 `AlgorithmManager.Run()` 永远不知道自己的模式——回测/实盘切换是 Synchronizer 级别的一行代码。

**Ditto 落地方向**：

| 组件 | 行业对标 | Ditto 当前 | 差距 |
|------|---------|-----------|------|
| 时间同步 | LEAN `ISynchronizer` | `Clock`/`SimulatedClock` | 缺数据流前沿驱动的时间抽象 |
| 主循环 | LEAN `AlgorithmManager` | `TradingLoop` Protocol（已定义） | 缺单线程确定性执行保证 |
| 类型化事件 | LEAN `OrderEvent`/`PortfolioEvent` | `DomainEvent` = `str` + `dict` | 需类型化 dataclass + 事件名目录 |
| TimeContext | LEAN `algorithm.UtcTime` | PIT 术语散布各包 | 需共享值对象统一 knowledge_date/as_of 等 |

**启动条件**：B8-B10 代码级修复完成后

### Phase 2: OMS Lite（紧随 Phase 1）

> 更新：2026-05-11 详细设计确认
> 决策依据：源码审计（72 Protocol 完整盘点 + execution/backtest/portfolio 全链路分析）+ 业界对标（LEAN OrderTicket/NautilusTrader 14-state FSM/vnpy EventEngine）

**业界共识**：Order FSM + Append-Only Journal，与执行引擎共置。

```
Order 创建后不可变 → OrderEvent journal 是 source of truth → 状态机确定性
```

**为何紧随 Phase 1**：portfolio 状态重建依赖 execution journal，是后续扩展的前置。

#### 2.0 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| OMS 归属 | execution 包 | Order 生命周期是执行域核心关注点，不属于组合构建域 |
| FSM 方式 | 表驱动 + 方法封装 | 转换表可审计/可测试，方法提供领域语义封装（NautilusTrader 验证） |
| Event 存储 | Protocol + 内存默认 | 回测用内存，Paper/Live 加 SQLite 实现，API 不变 |
| 双 ID 空间 | 现在定义，Live 时填充 | 类型系统一次到位，BacktestBrokerage 不填 BrokerOrderId |
| Phase 3 降级 | 合并入 Phase 2 | 72 Protocol 已行业领先，增量仅 TradeDataPort 拆分 |

#### 2.1 Order 模型迁移（execution 包）

**当前状态**（问题）：

| 类型 | 当前位置 | 问题 |
|------|---------|------|
| `Order` / `OrderTicket` / `OrderStatus` / `OrderEvent` / `OrderBook` | `portfolio/accounting/order_book.py` | Order 生命周期不在组合域 |
| `OrderRecord`（扁平 DTO） | `execution/orders/store.py` | 与 portfolio Order 不关联 |
| `OrderSubmitted/Filled/Canceled` | `execution/events.py` | 与 portfolio OrderEvent 双系统不统一 |

**迁移方案**：Account 与 OrderBook 解耦

```
迁移前：
  Account ──owns──> OrderBook ──contains──> OrderTicket ──references──> Order

迁移后：
  Account ──accepts──> FillEvent（纯值对象，已在 kernel）
  ExecutionEngine ──owns──> OrderBook（生命周期管理）
  ExecutionEngine ──calls──> Account.apply_fill()（现金/持仓更新）
```

**Account 失去的能力**（移到 execution/BacktestBrokerage）：
- `submit_order()` → `ExecutionEngine.submit()`
- `get_pending_orders()` → `OrderBook.get_pending()`
- `apply_fill()` → 拆分：execution 做状态转换，调用 `Account.apply_fill()` 做现金/持仓更新

**新 execution 内部结构**：

```
execution/
├── orders/
│   ├── model.py          # Order (frozen), OrderType, OrderDirection
│   ├── status.py         # OrderStatus (enum, 7 状态)
│   ├── trigger.py        # OrderTrigger (enum, 5 触发器)
│   ├── fsm.py            # TRANSITIONS 表 + transition() 函数
│   ├── ticket.py         # OrderTicket (frozen, with_* 方法调用 FSM)
│   ├── book.py           # OrderBook (mutable state owner)
│   ├── journal.py        # OrderEventJournal Protocol + InMemoryJournal
│   ├── ids.py            # ClientOrderId, BrokerOrderId 值对象
│   └── event.py          # OrderEvent (frozen, 含 trigger 字段)
├── events.py             # DomainEvent 子类（已存在，扩展 + OrderRejected/OrderExpired）
└── ...
```

#### 2.2 显式 FSM 转换表

**状态**（保留现有 7 个，对齐 NautilusTrader 核心子集）：

```
NEW → SUBMITTED → PARTIALLY_FILLED → FILLED
                   ↘ CANCELED
                   ↘ REJECTED
                   ↘ INVALID
```

**触发器**（新增 `OrderTrigger` enum）：

| Trigger | 含义 | 产生的 DomainEvent |
|---------|------|-------------------|
| `SUBMIT` | 提交到市场 | `OrderSubmitted` |
| `FILL(qty, price)` | 成交（部分/全部由 qty 决定） | `OrderFilled` |
| `CANCEL` | 撤单 | `OrderCanceled` |
| `REJECT` | 被拒 | `OrderRejected`（新增） |
| `EXPIRE` | 过期 | `OrderExpired`（新增） |

**转换表**（核心逻辑）：

```python
TRANSITIONS: dict[tuple[OrderStatus, OrderTrigger], None] = {
    # 正常路径
    (NEW, SUBMIT):                   None,  # → SUBMITTED
    (SUBMITTED, FILL):               None,  # → PARTIALLY_FILLED or FILLED
    (PARTIALLY_FILLED, FILL):        None,  # → FILLED or still PARTIALLY_FILLED
    # 异常路径
    (NEW, CANCEL):                   None,  # → CANCELED
    (NEW, REJECT):                   None,  # → REJECTED
    (SUBMITTED, CANCEL):             None,
    (SUBMITTED, REJECT):             None,
    (SUBMITTED, EXPIRE):             None,
    (PARTIALLY_FILLED, CANCEL):      None,
    (PARTIALLY_FILLED, EXPIRE):      None,
}

_TRIGGER_TARGET: dict[OrderTrigger, OrderStatus] = {
    OrderTrigger.SUBMIT:  OrderStatus.SUBMITTED,
    OrderTrigger.CANCEL:  OrderStatus.CANCELED,
    OrderTrigger.REJECT:  OrderStatus.REJECTED,
    OrderTrigger.EXPIRE:  OrderStatus.INVALID,
}

def transition(
    current: OrderStatus,
    trigger: OrderTrigger,
    fill_qty: int = 0,
    leaves_qty: int = 0,
) -> OrderStatus:
    if (current, trigger) not in TRANSITIONS:
        raise OrderStateError(current, trigger)
    if trigger == OrderTrigger.FILL:
        return OrderStatus.FILLED if fill_qty >= leaves_qty else OrderStatus.PARTIALLY_FILLED
    return _TRIGGER_TARGET[trigger]
```

**与 OrderTicket 的集成**：`with_fill()`/`with_cancel()` 等方法内部调用 `transition()` 做验证 + 状态确定，不再自己实现守卫逻辑。

**对比业界**：

| 特性 | LEAN | NautilusTrader | Ditto Phase 2 |
|------|------|---------------|---------------|
| FSM 状态数 | ~8（隐式） | 14（显式） | 7（显式） |
| 转换表 | 无 | 有 | 有 |
| 守卫检查 | 部分 | 完整 | 完整 |
| 事件溯源 | OrderEvent 累积 | Cache + MessageBus | Journal Protocol |

#### 2.3 Event Journal 与双 ID 空间

**OrderEventJournal Protocol**：

```python
class OrderEventJournal(Protocol):
    def append(self, event: OrderEvent) -> None: ...
    def events_for(self, order_id: ClientOrderId) -> tuple[OrderEvent, ...]: ...
    def all_events(self) -> tuple[OrderEvent, ...]: ...

class InMemoryOrderEventJournal:
    """默认实现：内存 list，回测用"""
```

**OrderEvent 扩展**（当前只有 `status` + `fill_price` + `fill_quantity`）：

```python
@dataclass(frozen=True, slots=True)
class OrderEvent:
    order_id: ClientOrderId
    trigger: OrderTrigger        # 新增：什么触发了状态变化
    status: OrderStatus           # 变化后的状态
    fill_price: float | None = None
    fill_quantity: int | None = None
    fee: float | None = None
    message: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**双 ID 值对象**：

```python
@dataclass(frozen=True, slots=True)
class ClientOrderId:
    """策略/execution 分配的全局唯一 ID"""
    value: str  # UUID 格式

    @classmethod
    def generate(cls) -> ClientOrderId:
        return cls(value=f"ditto-{uuid4().hex[:16]}")

@dataclass(frozen=True, slots=True)
class BrokerOrderId:
    """券商/交易所返回的 ID（回测时为 None）"""
    value: str
```

**Order 模型更新**：

```python
@dataclass(frozen=True, slots=True)
class Order:
    order_id: ClientOrderId          # 替换 str
    broker_id: BrokerOrderId | None  # 新增，Live 时填充
    instrument_id: InstrumentId
    order_type: OrderType
    direction: OrderDirection
    quantity: int
    price: float | None = None
    stop_price: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    strategy_run_id: str | None = None
```

`BrokerOrderId` 在 BacktestBrokerage 中始终为 `None`，Paper/Live 网关实现时自动填充。

#### 2.4 Domain Event 扩展

当前 `execution/events.py` 只有 `OrderSubmitted`/`OrderFilled`/`OrderCanceled`，需补充：

| 新增事件 | 对应 Trigger | 用途 |
|---------|-------------|------|
| `OrderRejected` | `REJECT` | 券商拒单通知 |
| `OrderExpired` | `EXPIRE` | 订单过期（GTC 到期） |

#### 2.5 TradeDataPort ISP 拆分（Phase 3 降级项）

当前 `execution/contracts.py` 的 `TradeDataPort`（10 方法）覆盖 intent/fill/position 三域，违反 ISP。

**拆分方案**：

```python
class OrderIntentPort(Protocol):
    """订单意向存储（execution 内部用）"""
    def save_intent(self, record: SignalRecord) -> None: ...
    def get_intent(self, order_id: str) -> SignalRecord | None: ...
    def list_intents(self, ...) -> list[SignalRecord]: ...
    def update_intent_status(self, order_id: str, status: str) -> None: ...

class TradeFillPort(Protocol):
    """成交记录存储（execution + backtest 消费）"""
    def save_fill(self, record: FillRecord) -> None: ...
    def get_fill(self, order_id: str) -> FillRecord | None: ...
    def list_fills(self, ...) -> list[FillRecord]: ...

class TradePositionPort(Protocol):
    """持仓快照存储（execution + risk 消费）"""
    def save_position(self, ...) -> None: ...
    def list_positions(self, ...) -> list[PositionRecord]: ...
```

**消费者映射**：

| 消费者 | 需要的 Port |
|--------|------------|
| BacktestBrokerage | `TradeFillPort` |
| AuditService | `TradeFillPort` |
| Risk scan | `TradePositionPort` |
| Strategy Run | `OrderIntentPort` + `TradeFillPort` |

**DataProvider 不动**：4 方法、2 消费者（backtest + application），窄化收益低。

#### 2.6 迁移序列

**7 步增量迁移**（每步可独立验证）：

| 步骤 | 内容 | 涉及包 | 验证方式 |
|------|------|--------|---------|
| **S1** | 定义新类型（ids/model/status/trigger/fsm/journal/event） | execution | 单元测试 FSM 转换表 |
| **S2** | 实现 OrderTicket（调用 FSM）+ OrderBook（使用 Journal） | execution | 单元测试状态转换 |
| **S3** | Account 解耦 OrderBook：移除 `_order_book` 字段，`apply_fill()` 保留 | portfolio | 现有测试通过 |
| **S4** | BacktestBrokerage 适配新 execution OMS | backtest + execution | 回测集成测试 |
| **S5** | TradeDataPort 拆分为 3 窄 Port | execution | `arch-check` 通过 |
| **S6** | 清理 portfolio 旧类型 + execution OrderRecord | portfolio + execution | 全量测试通过 |
| **S7** | B9-K.6 删除 kernel DecisionFrame + B9-EX.4 DiffContext | kernel + execution | `pixi run -e dev check` |

**关键约束**：
- S1-S2 不改动现有代码，只新增
- S3 是最关键的一步（Account 解耦），需先确保所有 Account 消费者已适配
- S4 完成后回测应可正常运行（功能不变，内部重构）
- S5-S7 是清理和优化，可独立执行

#### 2.7 与 Phase 1 的衔接

Phase 1（Runtime Spine）已建立 `Synchronizer`/`Clock`/`TimeContext` 抽象。Phase 2 在此基础上：
- `BacktestSynchronizer` 产出的 `TimeSlice` 不变
- `EngineLoop._step()` 中 PreTradeStep → ExecutionStep 调用链不变
- 内部 Order 生命周期从 portfolio 隐式 → execution 显式 FSM
- Phase 1 的 `Synchronizer` 抽象使 Backtest/Paper 共享 seam 天然存在

### Phase 3: Consumer-Owned Ports 深化（已降级）

> 2026-05-11 决策：降级为 Phase 2 附带任务（S5 TradeDataPort 拆分）。
> 理由：72 Protocol 审计表明覆盖度已行业领先，DataProvider 4 方法 / 2 消费者无需窄化。

**已完成项**（合并入 Phase 2 S5）：
- `TradeDataPort` 拆分为 `OrderIntentPort` / `TradeFillPort` / `TradePositionPort`

**延后项**（触发条件）：
- `DataProvider` 窄化 → 第 3+ 消费者出现或 Live DataFeed 有不同需求时
- application 层窄编排 Port → ResearchCatalog/ArtifactPort → 研究功能扩展时
- DataCatalog Runtime Store → Dataset 降权 → 多数据源接入时

---

## 三、B10 遗留项

| 项 | 触发条件 |
|----|---------|
| B10.1 Platform 死代码清理 | 随代码级修复同步 |
| B10.2 barrel/`__all__` 统一 | 随代码级修复同步 |
| B10.3 CLAUDE.md 同步 | 随代码级修复同步 |
| B10.4 Golden E2E | Phase 1 完成后作为验收手段 |
| B10.5 Data errors facade 验证 | B9-DATA.4 拆分时同步 |
| B10.6 Data services DI 验证 | 接受现状，无需单独验证 |

---

## 四、业界对标参考

| 来源 | 关键参考 |
|------|---------|
| LEAN Engine.cs | 配置驱动 Handler 工厂方法 |
| LEAN AlgorithmManager.cs | 确定性单线程主循环 |
| LEAN ISynchronizer.cs | 回测/实盘时间抽象 |
| LEAN OrderTicket | 隐式 FSM + OrderEvent 累积 |
| NautilusTrader | Actor 模型 + 纯六边形架构 + 14 状态显式 FSM |
| NautilusTrader Adapter | 5 固定组件 + 窄 async 方法 + Cache-then-Publish |
| vnpy EventEngine | 反应器模式（120 LOC） |
| Martin Fowler Event Sourcing | 交易系统轻量级事件溯源 |
| Mikhail Shilkov DIP | Consumer-Owned Ports 理论基础 |
| Alistair Cockburn | 六边形架构原始定义 |
