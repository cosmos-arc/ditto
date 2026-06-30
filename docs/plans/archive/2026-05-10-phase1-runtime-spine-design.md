# Phase 1: Runtime Spine 设计

> 创建：2026-05-10
> 基线：`docs/plans/2026-05-10-deferred-items-design.md` §二
> 前置：B8-B10 代码级修复完成
> 目标：建立回测/实盘切换的核心抽象 — Synchronizer + TimeContext + 事件增强
> 方法：源码分析 + 业界对标（LEAN ISynchronizer / NautilusTrader Actor）

---

## 1. 目标与范围

### 1.1 问题陈述

当前 `EngineLoop`（376 LOC）将「时间推进 + 数据拉取 + 策略执行 + 订单管理」紧密耦合在回测引擎内部：

```
EngineLoop.run()
  ├── data_feed.trading_days()     ← 数据源（回测专用）
  ├── for date in trading_days:    ← 时间驱动（日历迭代）
  │   ├── clock.advance_to()       ← 时钟推进（在 DataFetchStep 内）
  │   ├── data_feed.get_slice()    ← 数据拉取（pull 模式）
  │   └── step_chain.execute()     ← 业务逻辑（可复用）
  └── assemble_result()
```

实盘/Paper Trading 无法复用主循环逻辑——时间推进方式不同（等待实时数据 vs 日历迭代）、数据源不同（实时行情流 vs 历史数据）。

### 1.2 设计目标

| 目标 | 验收标准 |
|------|---------|
| 模式无关主循环 | `EngineLoop` 不包含 `backtest`/`live`/`paper` 条件分支 |
| 回测/实盘 parity | 切换模式只需替换 `Synchronizer` 实现 + 步骤链组合 |
| PIT 语义统一 | 所有 PIT 查询可通过 `TimeContext` 入口 |
| 事件可追溯 | 每个状态变更产生类型化事件，为 Phase 2 Journal 打基础 |
| Paper Trading 就绪 | Phase 1 完成后可立即启动 Paper Trading |

### 1.3 范围

**包含**：

| 组件 | 包 | 优先级 |
|------|-----|--------|
| `TimeContext` 值对象 | kernel | P0 |
| `TimeSlice` 值对象 | kernel | P0 |
| `Synchronizer` Protocol | kernel | P0 |
| `BacktestSynchronizer` 实现 | backtest | P0 |
| `EngineLoop` 重构（Synchronizer 驱动） | backtest | P0 |
| 事件增强（PositionChanged 发布 + EventName 补全） | portfolio/kernel | P1 |
| `PaperSynchronizer` 骨架 | application | P1 |

**不包含**：

- OMS Lite / Journal（Phase 2）
- Consumer-Owned Ports 深化（Phase 3）
- 分钟级行情推送（后续扩展，Synchronizer 抽象支持但不实现）
- 具体券商网关实现
- `DataFeed` Protocol 废弃（保持向后兼容）

---

## 2. 核心抽象

### 2.1 TimeContext

**文件**：`kernel/time_context.py`（新文件）

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

__all__ = ["TimeContext"]


@dataclass(frozen=True)
class TimeContext:
    """
    时间上下文 — PIT 语义的统一值对象.

    是 Synchronizer 与各包沟通「当前时间」的唯一入口。
    替代散布在 data/helpers/pit/、backtest/data_feed.py 中的分散 PIT 模式。

    Attributes:
        decision_time: 决策时刻（Clock.now() 的语义等价物）
        knowledge_date: 数据可见边界（knowledge_date 之前的行才可见）
        trade_date: 当前交易日（YYYY-MM-DD）
    """

    decision_time: datetime
    knowledge_date: date
    trade_date: str

    @property
    def pit_cutoff(self) -> datetime:
        """PIT 查询的严格上界（不含 knowledge_date 当日数据）。"""
        return datetime.combine(self.knowledge_date, time.min)
```

**kernel 准入验证**：

| # | 标准 | 结果 |
|---|------|------|
| 1 | 跨层使用 | ✅ data/strategy/backtest/application ≥ 4 包消费 |
| 2 | 零业务行为 | ✅ 纯值对象 + 计算型 `@property` |
| 3 | 高稳定性 | ✅ 时间语义是领域常量 |
| 4 | 无外部依赖 | ✅ 仅 stdlib |
| 5 | 纯值语义 | ✅ frozen dataclass |

**Barrel 决策**：不加入 `__init__.py` barrel（已满 30/30），消费者从叶模块导入：
```python
from ditto_kernel.time_context import TimeContext
```

### 2.2 TimeSlice

**文件**：`kernel/synchronizer.py`（新文件，与 Synchronizer Protocol 共置）

```python
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from ditto_kernel.clock import Clock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_kernel.trading import MarketSnapshot

__all__ = ["Synchronizer", "TimeSlice"]


@dataclass(frozen=True)
class TimeSlice:
    """
    单步时间切片 — Synchronizer 每次产出的最小数据单元.

    包含该时刻的所有可用市场数据。
    不包含账户/策略/订单状态（这些由 step chain 内部管理）。

    Attributes:
        time_context: 时间上下文（PIT 语义）
        bars: instrument_id → MarketSnapshot
    """

    time_context: TimeContext
    bars: dict[InstrumentId, MarketSnapshot]


class Synchronizer(Protocol):
    """
    时间同步器 — 回测/实盘切换的唯一 seam.

    封装「何时推进时间」+「该时刻有什么数据」为一元化抽象。
    主循环永远不知道自己的模式。

    对标 LEAN ISynchronizer.StreamData() → IEnumerable<TimeSlice>。
    """

    def stream(self) -> Iterator[TimeSlice]:
        """产生时间切片流 — 回测时有限，实盘时无限。"""
        ...

    def clock(self) -> Clock:
        """返回与此同步器关联的时钟。"""
        ...
```

**kernel 准入验证**：

| # | 标准 | 结果 |
|---|------|------|
| 1 | 跨层使用 | ✅ backtest + application ≥ 2 包消费 |
| 2 | 零业务逻辑 | ✅ 纯 Protocol + 值对象 |
| 3 | 无外部依赖 | ✅ 仅 stdlib + kernel 内部类型 |
| 4 | 高稳定性 | ✅ 核心抽象不随业务迭代 |
| 5 | 零 I/O | ✅ Protocol 定义无 I/O |

**Barrel 决策**：不加入 barrel。消费者从叶模块导入：
```python
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
```

---

## 3. 实现设计

### 3.1 BacktestSynchronizer

**文件**：`backtest/synchronizer.py`（新文件）

封装现有 `DataFeed` + `SimulatedClock`，日历驱动迭代。

```python
from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from ditto_backtest.data_feed import DataFeed
from ditto_kernel.clock import Clock, SimulatedClock
from ditto_kernel.synchronizer import TimeSlice, Synchronizer as SynchronizerProto
from ditto_kernel.time_context import TimeContext

__all__ = ["BacktestSynchronizer"]


class BacktestSynchronizer:
    """
    回测时间同步器.

    日历驱动迭代：DataFeed.trading_days() → get_slice(date) → TimeSlice。
    时钟为 SimulatedClock，可向前推进。
    """

    def __init__(
        self,
        data_feed: DataFeed,
        clock: SimulatedClock,
        start_date: str,
        knowledge_lag_days: int = 1,
    ) -> None:
        self._feed = data_feed
        self._clock = clock
        self._start_date = start_date
        self._knowledge_lag_days = knowledge_lag_days

    def stream(self) -> Iterator[TimeSlice]:
        for date_str in self._feed.trading_days():
            if date_str < self._start_date:
                continue
            slice_ = self._feed.get_slice(date_str)
            tc = TimeContext(
                decision_time=slice_.step_time,
                knowledge_date=slice_.step_time.date()
                    - timedelta(days=self._knowledge_lag_days),
                trade_date=slice_.trade_date,
            )
            yield TimeSlice(time_context=tc, bars=slice_.bars)

    def clock(self) -> Clock:
        return self._clock
```

### 3.2 PaperSynchronizer（骨架）

**文件**：`application/runtime/synchronizer.py`（新文件）

```python
class PaperSynchronizer:
    """
    Paper Trading 时间同步器 — 日线级别.

    每日收盘后通过 DataProvider 拉取当日 bar，构造 TimeSlice。
    使用 RealtimeClock（advance_to 不可调用）。

    详细实现随 Paper Trading 项目展开，此处为骨架。
    """
```

骨架职责：
1. 检测当日是否已收盘（A股 15:05 后）
2. 通过 `DataProvider.get_bars()` 拉取当日行情
3. 构造 `TimeSlice` 并 yield
4. 等待下一交易日

### 3.3 EngineLoop 重构

**核心变更**：`EngineLoop` 改为接受 `Synchronizer` 替代 `DataFeed` + `Clock` 的直接持有。

**变更前后对比**：

```python
# 变更前
class EngineLoop:
    def __init__(self, ..., data_feed: DataFeed, options: EngineOptions):
        self._data_feed = data_feed
        self._clock = options.clock

    def run(self):
        trading_days = self._data_feed.trading_days()
        for date in trading_days:
            self._step(date)

# 变更后
class EngineLoop:
    def __init__(self, ..., synchronizer: Synchronizer, options: EngineOptions):
        self._synchronizer = synchronizer
        # clock 从 synchronizer.clock() 获取，不再直接持有

    def run(self):
        for time_slice in self._synchronizer.stream():
            self._synchronizer.clock().advance_to(
                time_slice.time_context.decision_time
            )
            self._step(time_slice)
```

**StepContext 适配**：

```python
# 变更前
@dataclass
class StepContext:
    date: str
    is_rebalance_day: bool
    slice_: Slice | None = None  # 由 DataFetchStep 填充

# 变更后
@dataclass
class StepContext:
    time_context: TimeContext  # 替代裸 date
    is_rebalance_day: bool
    bars: dict[InstrumentId, MarketSnapshot]  # 由 Synchronizer 提供
    slice_: Slice | None = None  # 保留，由 DataFetchStep 补充 benchmark_close 等
```

**DataFetchStep 简化**：

变更前职责：获取 Slice + 账户快照 + 推进时钟 + 清除冻结量
变更后职责：获取账户快照 + 清除冻结量（Slice 数据已由 Synchronizer 提供）

**is_rebalance_day 适配**：

当前基于 `date: str` 和 `trading_days` 列表计算。改为基于 `time_context.trade_date`。

---

## 4. 事件增强

### 4.1 PositionChanged 发布

**文件**：`portfolio/accounting/account.py`

在 `Account.apply_fill()` 末尾发布 `PositionChanged` 事件：

```python
def apply_fill(self, fill: FillEvent, *, settle_date: str, ...) -> None:
    # ... 现有逻辑（先计算后赋值）...

    # 新增：发布 PositionChanged 事件
    if self._event_bus is not None:
        self._event_bus.publish(
            PositionChanged(
                event_type=EventName.POSITION_CHANGED,
                timestamp=self._event_bus_timestamp or datetime.now(UTC),
                instrument_id=fill.instrument_id,
                direction=fill.direction,
                quantity=fill.filled_quantity,
                price=fill.fill_price,
            )
        )
```

**依赖注入**：`Account.__init__` 接受可选 `event_bus: EventBus` 参数。

### 4.2 EventName 目录补全

**文件**：`kernel/events.py`

```python
class EventName:
    # 现有
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    RISK_GUARD_TRIGGERED = "risk_guard_triggered"
    POSITION_CHANGED = "position_changed"  # 已有，当前 reserved

    # 新增
    ACCOUNT_UPDATED = "account_updated"              # cash 变动
    STRATEGY_SIGNAL_GENERATED = "strategy_signal_generated"  # 策略信号产出
```

### 4.3 Portfolio events 激活验证

在 `portfolio/events.py` 中验证 `PositionChanged` 事件结构完整性：
- 确认 frozen dataclass 字段覆盖关键状态
- 确认 `event_type` 引用 `EventName.POSITION_CHANGED`

---

## 5. 迁移计划

### 5.1 执行顺序与依赖

```
Step 1: 定义抽象（kernel 层增量）
  │
  ├── TimeContext + TimeSlice + Synchronizer Protocol
  │
  └→ Step 2: BacktestSynchronizer（backtest 层）
       │
       ├── 封装 DataFeed + SimulatedClock
       │
       └→ Step 3: EngineLoop 重构（backtest 层）
            │
            ├── 接受 Synchronizer 替代 DataFeed + Clock
            ├── StepContext 适配
            ├── DataFetchStep 简化
            │
            └→ Step 4: 事件增强（portfolio + kernel）
                 │
                 ├── PositionChanged 发布
                 ├── EventName 补全
                 │
                 └→ Step 5: Paper 骨架（application 层）
                      │
                      ├── PaperSynchronizer 骨架
                      └── application/runtime/ 模块初始化
```

### 5.2 Step 1：定义抽象 `[S]`

**范围**：kernel 新增 2 个文件，零改动现有代码。

| 文件 | 内容 |
|------|------|
| `kernel/time_context.py` | `TimeContext` frozen dataclass |
| `kernel/synchronizer.py` | `TimeSlice` frozen dataclass + `Synchronizer` Protocol |

**验收**：
- kernel 新增 2 文件，零外部依赖
- `from ditto_kernel.time_context import TimeContext` 可用
- `from ditto_kernel.synchronizer import Synchronizer, TimeSlice` 可用
- `pixi run -e dev check` 通过
- kernel barrel `__all__` 保持 30 符号（新类型从叶模块导入）

### 5.3 Step 2：BacktestSynchronizer `[M]`

**范围**：backtest 新增 1 个文件。

| 文件 | 内容 |
|------|------|
| `backtest/synchronizer.py` | `BacktestSynchronizer` 类 |

**关键设计决策**：
- 不修改 `DataFeed` Protocol（向后兼容）
- 不修改 `Slice` 类（BacktestSynchronizer 内部转换 `Slice` → `TimeSlice`）
- 消费 `knowledge_lag_days` 参数（默认 1，对应 T+1 策略）

**测试**：
- 单元测试验证 `stream()` 产出 `TimeSlice` 序列
- 单元测试验证 `clock()` 返回 `SimulatedClock`
- 单元测试验证 `knowledge_date = decision_time.date() - lag`

**验收**：
- `BacktestSynchronizer` 满足 `Synchronizer` Protocol（结构化子类型）
- 测试通过

### 5.4 Step 3：EngineLoop 重构 `[L]`

**范围**：重构 backtest 核心文件。

| 文件 | 变更 |
|------|------|
| `backtest/engine.py` | 接受 `Synchronizer`，主循环改为 `for slice_ in sync.stream()` |
| `backtest/engine_steps.py` | `EngineOptions.clock` → `Synchronizer` |
| `backtest/steps/types.py` | `StepContext.date` → `StepContext.time_context` |
| `backtest/steps/data_fetch.py` | 简化（Slice 数据由 Synchronizer 提供） |
| `backtest/data_feed.py` | 不变（`DataFeed` Protocol 保留） |

**行为等价性验证**：
- Golden baseline 测试结果不变（相同输入 → 相同输出）
- 事件序列不变（相同步序 → 相同事件流）
- `trading_days` 过滤逻辑迁移到 `BacktestSynchronizer`

**StepContext 迁移**：

```python
# 所有通过 ctx.date 访问 trade_date 的代码改为：
ctx.time_context.trade_date

# 所有构造 StepContext 的代码改为：
StepContext(time_context=..., is_rebalance_day=...)
```

**风险评估**：高影响面（7 个 step 文件 + 测试），需要：
1. 先运行 golden baseline 捕获当前结果
2. 重构后验证结果一致
3. 逐文件迁移 `ctx.date` → `ctx.time_context.trade_date`

**验收**：
- `EngineLoop.__init__` 不再直接持有 `DataFeed`
- 主循环为 `for time_slice in self._synchronizer.stream()`
- Golden baseline 测试结果不变
- `pixi run -e dev check` 通过
- 36/36 arch contracts kept

### 5.5 Step 4：事件增强 `[M]`

**范围**：portfolio + kernel 事件相关文件。

| 文件 | 变更 |
|------|------|
| `portfolio/accounting/account.py` | `apply_fill()` 末尾发布 `PositionChanged` |
| `portfolio/accounting/account.py` | `__init__` 接受可选 `event_bus: EventBus` |
| `kernel/events.py` | `EventName` 新增 `ACCOUNT_UPDATED`、`STRATEGY_SIGNAL_GENERATED` |

**注意**：`Account` 的 `event_bus` 注入路径：
- 回测：`EngineOptions.event_bus` → `BacktestBrokerage` → `Account`
- 实盘：`MainLoop` 构造时注入

**测试**：
- 单元测试验证 `apply_fill()` 发布 `PositionChanged` 事件
- 单元测试验证 `event_bus=None` 时不发布（向后兼容）

**验收**：
- `apply_fill()` 在 `event_bus` 可用时发布 `PositionChanged`
- 现有测试不受影响（`event_bus=None` 为默认值）
- `pixi run -e dev check` 通过

### 5.6 Step 5：Paper 骨架 `[S]`

**范围**：application/runtime 新模块。

| 文件 | 内容 |
|------|------|
| `application/runtime/__init__.py` | 模块初始化（从占位符 docstring 升级） |
| `application/runtime/synchronizer.py` | `PaperSynchronizer` 骨架 |

**PaperSynchronizer 骨架**：
- 满足 `Synchronizer` Protocol
- `stream()` 方法标注 `# TODO: Paper Trading implementation`
- `clock()` 返回 `RealtimeClock()`

**验收**：
- `PaperSynchronizer` 满足 `Synchronizer` Protocol
- `application/runtime/` 模块可导入

---

## 6. Kernel 影响分析

### 6.1 新增文件

| 文件 | 行数估计 | 类型 |
|------|---------|------|
| `kernel/time_context.py` | ~30 行 | frozen dataclass |
| `kernel/synchronizer.py` | ~50 行 | frozen dataclass + Protocol |

### 6.2 Barrel 影响

kernel `__all__` 当前 30/30 符号。新增类型不加入 barrel，消费者从叶模块导入。

需在 kernel CLAUDE.md 模块结构中记录新文件。

### 6.3 importlinter 影响

无。kernel 新增文件零外部依赖，不违反任何现有契约。

---

## 7. importlinter 契约影响分析

| 契约 | 影响 | 说明 |
|------|------|------|
| kernel-isolation | ✅ 无变化 | 新文件仅依赖 stdlib |
| backtest-boundary | ✅ 无变化 | backtest 新增对 kernel 的引用（合法） |
| application → kernel | ✅ 合法 | PaperSynchronizer 引用 kernel Synchronizer |
| backtest → kernel | ✅ 合法 | BacktestSynchronizer 引用 kernel Synchronizer |
| application 内部 R8 | ✅ 无变化 | runtime/ 是新命名空间 |

需新增：
- `application/runtime` 到 importlinter 的 application 内部模块列表（如果尚未包含）

---

## 8. 测试策略

### 8.1 新增测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `kernel/tests/unit/test_time_context_unit.py` | TimeContext PIT 语义、pit_cutoff 属性 |
| `kernel/tests/unit/test_synchronizer_unit.py` | TimeSlice 构造、Synchronizer Protocol 满足性 |
| `backtest/tests/unit/test_backtest_synchronizer_unit.py` | stream() 输出、clock() 返回值、knowledge_date 计算 |
| `portfolio/tests/unit/test_account_events_unit.py` | apply_fill() 发布 PositionChanged |
| `application/tests/unit/test_paper_synchronizer_unit.py` | Protocol 满足性 |

### 8.2 回归测试

| 测试 | 目的 |
|------|------|
| `backtest/tests/integration/test_golden_baseline.py` | 行为等价性验证 |
| `backtest/tests/integration/test_reproducibility.py` | 可复现性验证 |
| `backtest/tests/integration/test_backtest_invariants.py` | 不变量保持 |
| `pixi run -e dev arch-check` | 36/36 契约保持 |

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|---------|
| EngineLoop 重构破坏回测结果 | 高 | Golden baseline 快照先行，重构后对比 |
| StepContext 迁移遗漏 `ctx.date` 引用 | 中 | `rg "ctx\.date"` 全库搜索验证 |
| kernel barrel 超出 30 限制 | 低 | 新类型不加入 barrel，从叶模块导入 |
| PositionChanged 发布影响回测性能 | 低 | event_bus=None 时零开销，发布仅 dict append |
| TimeContext 与现有 PIT 模式不兼容 | 中 | Step 1 只定义不消费，Step 3 才迁移消费端 |

---

## 10. 工作量估计

| Step | 复杂度 | 新增/修改文件 | 测试文件 | 估计 |
|------|--------|-------------|---------|------|
| Step 1: 定义抽象 | S | 2 新增 | 2 新增 | 0.5h |
| Step 2: BacktestSynchronizer | M | 1 新增 | 1 新增 | 1h |
| Step 3: EngineLoop 重构 | L | 5 修改 | 3 修改 | 3-4h |
| Step 4: 事件增强 | M | 2 修改 | 1 新增 | 1-2h |
| Step 5: Paper 骨架 | S | 2 新增 | 1 新增 | 0.5h |
| **合计** | — | **7 新增 + 7 修改** | **5 新增 + 3 修改** | **6-8h** |

---

## 11. 后续扩展

Phase 1 完成后的自然扩展路径：

| 扩展 | 依赖 Phase | 说明 |
|------|-----------|------|
| 分钟级 Synchronizer | Phase 1 | TDX 行情流 → TimeSlice（1m 粒度） |
| JournalingEventBus | Phase 2 | 包装 SimpleEventBus + append-only 持久化 |
| Order FSM | Phase 2 | ClientOrderId + 状态转换表 + Journal |
| DataProvider → 窄 Port | Phase 3 | DataProvider 拆分为消费端各自定义的 Protocol |
| Live Brokerage | Phase 2+ | BrokerGateway 实现 + LiveSynchronizer |
