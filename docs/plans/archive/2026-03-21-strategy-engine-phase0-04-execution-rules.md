# Phase 0 Part 2: execution/ 执行层类型定义

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** ✅ DONE (2026-03-21)

**Goal:** 实现 execution/rules.py (三层规则数据对象) 和 execution/fills.py (FillOutcome 联合类型)

**Architecture:** 纯数据结构层。InstrumentDefinition / TradingRuleSet / FeeSchedule 是 frozen dataclass，通过 PIT 基础设施版本化。FillOutcome 是显式联合类型（F4），替代 FillEvent | None 模式。

**Design Doc:** v3 §4.3 (FillOutcome), §5.1 (三层规则)

**前置依赖:** Part 1 (accounting/) — OrderType/OrderDirection/OrderStatus 已在 order_book.py 内联定义

---

## Task 1: execution/ 模块脚手架 `[S]` ✅

**Files:**
- Create: `packages/core/src/ditto_core/execution/__init__.py`
- Create: `packages/core/tests/unit/execution/__init__.py`

**Step 1: 创建 __init__.py**

```python
# packages/core/src/ditto_core/execution/__init__.py
"""Execution — 执行层类型定义.

Phase 0: rules (三层规则), fills (FillOutcome).
Phase 2+: planner, brokerage, trade_builder, reality/.
"""

__all__: list[str] = []
```

```bash
mkdir -p packages/core/tests/unit/execution
touch packages/core/tests/unit/execution/__init__.py
```

**Step 2: Commit**

```bash
git add packages/core/src/ditto_core/execution/ packages/core/tests/unit/execution/
git commit -m "chore(core): add execution module scaffold"
```

---

## Task 2: InstrumentDefinition / TradingRuleSet / FeeSchedule (三层规则) `[M]` ✅

**Files:**
- Create: `packages/core/src/ditto_core/execution/rules.py`
- Test: `packages/core/tests/unit/execution/test_rules_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/execution/test_rules_unit.py
"""Tests for InstrumentDefinition / TradingRuleSet / FeeSchedule (R6 三层分离)."""

import pytest
from dataclasses import FrozenInstanceError


class TestInstrumentDefinition:
    def test_create_etf_definition(self) -> None:
        from ditto_core.execution.rules import InstrumentDefinition

        defn = InstrumentDefinition(
            instrument_id="159915.SZ",
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        )
        assert defn.asset_class == "etf"
        assert defn.lot_size == 100
        assert defn.tick_size == 0.001

    def test_create_stock_definition(self) -> None:
        from ditto_core.execution.rules import InstrumentDefinition

        defn = InstrumentDefinition(
            instrument_id="600000.SH",
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.01,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        )
        assert defn.asset_class == "stock"
        assert defn.tick_size == 0.01

    def test_is_frozen(self) -> None:
        from ditto_core.execution.rules import InstrumentDefinition

        defn = InstrumentDefinition(
            instrument_id="159915.SZ",
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        )
        with pytest.raises(FrozenInstanceError):
            defn.lot_size = 1  # type: ignore[misc]

    def test_st_lifecycle(self) -> None:
        from ditto_core.execution.rules import InstrumentDefinition

        defn = InstrumentDefinition(
            instrument_id="600123.SH",
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.01,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="st",
        )
        assert defn.lifecycle_state == "st"


class TestTradingRuleSet:
    def test_create_with_pit_fields(self) -> None:
        from ditto_core.execution.rules import TradingRuleSet

        rule = TradingRuleSet(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
        )
        assert rule.settlement_cycle == 1
        assert rule.price_limit_pct == 0.10

    def test_no_price_limit(self) -> None:
        from ditto_core.execution.rules import TradingRuleSet

        rule = TradingRuleSet(
            instrument_id="600999.SH",
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=None,  # 新股前5日无限制
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
        )
        assert rule.price_limit_pct is None

    def test_is_frozen(self) -> None:
        from ditto_core.execution.rules import TradingRuleSet

        rule = TradingRuleSet(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
        )
        with pytest.raises(FrozenInstanceError):
            rule.settlement_cycle = 0  # type: ignore[misc]


class TestFeeSchedule:
    def test_create_etf_fee(self) -> None:
        from ditto_core.execution.rules import FeeSchedule

        fee = FeeSchedule(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,  # ETF 无印花税
            transfer_fee_rate=0.0,  # ETF 无过户费
        )
        assert fee.stamp_duty_rate == 0.0

    def test_create_stock_fee(self) -> None:
        from ditto_core.execution.rules import FeeSchedule

        fee = FeeSchedule(
            instrument_id="600000.SH",
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,  # 卖出 0.05%
            transfer_fee_rate=0.00001,  # 过户费
        )
        assert fee.stamp_duty_rate == 0.0005
        assert fee.transfer_fee_rate == 0.00001

    def test_is_frozen(self) -> None:
        from ditto_core.execution.rules import FeeSchedule

        fee = FeeSchedule(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
        )
        with pytest.raises(FrozenInstanceError):
            fee.commission_rate = 0.0  # type: ignore[misc]
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/test_rules_unit.py -v
```

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/execution/rules.py
"""InstrumentDefinition / TradingRuleSet / FeeSchedule — 三层规则数据对象 (R6).

- InstrumentDefinition: 静态资产属性（很少变化）
- TradingRuleSet: 可变交易规则（PIT 版本化，effective_from / effective_to）
- FeeSchedule: 可变费用结构（PIT 版本化）
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FeeSchedule",
    "InstrumentDefinition",
    "TradingRuleSet",
]


@dataclass(frozen=True)
class InstrumentDefinition:
    """资产的静态定义 — 很少变化，不按日期生效。

    Attributes:
        instrument_id: 标的 ID
        asset_class: 资产类别 (stock / etf / index / future / ...)
        exchange: 交易所 (XSHE / XSHG / XBSE)
        currency: 货币 (CNY)
        tick_size: 最小价格变动
        lot_size: 最小手数 (A股=100)
        multiplier: 合约乘数 (股票/ETF=1)
        board_segment: 板块 (main / gem / star / bse)
        lifecycle_state: 生命周期 (normal / st / st_star / delisting / ipo)
    """

    instrument_id: str
    asset_class: str
    exchange: str
    currency: str
    tick_size: float
    lot_size: int
    multiplier: float
    board_segment: str
    lifecycle_state: str


@dataclass(frozen=True)
class TradingRuleSet:
    """某个标的在某个时间点的交易规则 — 按日期生效，可回放。

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 规则生效日期 (YYYY-MM-DD)
        settlement_cycle: T+N 的 N（1=次日可卖, 0=当日可卖）
        fund_settlement_cycle: 资金交收 T+N
        price_limit_pct: 涨跌停限制 (None=无限制，如新股前5日)
        order_types_supported: 支持的订单类型
        call_auction_sessions: 集合竞价时段
    """

    instrument_id: str
    as_of_date: str
    settlement_cycle: int
    fund_settlement_cycle: int
    price_limit_pct: float | None
    order_types_supported: tuple[str, ...]
    call_auction_sessions: tuple[str, ...]


@dataclass(frozen=True)
class FeeSchedule:
    """某个标的在某个时间点的费用结构 — 按日期生效。

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 生效日期 (YYYY-MM-DD)
        commission_rate: 佣金费率
        min_commission: 最低佣金 (A股=5元)
        stamp_duty_rate: 印花税率 (ETF=0, 股票=0.0005 卖出)
        transfer_fee_rate: 过户费率 (ETF=0, 股票=0.00001)
    """

    instrument_id: str
    as_of_date: str
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/test_rules_unit.py -v
```

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/execution/ packages/core/tests/unit/execution/
git commit -m "feat(core): add InstrumentDefinition/TradingRuleSet/FeeSchedule (R6 三层分离)"
```

---

## Task 3: FillOutcome / Filled / NoFill (F4 显式联合类型) `[M]` ✅

**Files:**
- Create: `packages/core/src/ditto_core/execution/fills.py`
- Test: `packages/core/tests/unit/execution/test_fills_unit.py`

**Step 1: Write the failing test**

```python
# packages/core/tests/unit/execution/test_fills_unit.py
"""Tests for FillOutcome (F4: 显式联合类型)."""

from __future__ import annotations

from datetime import datetime

from ditto_core.accounting.order_book import OrderDirection


class TestFillEvent:
    def test_create_fill_event(self) -> None:
        from ditto_core.execution.fills import FillEvent

        fill = FillEvent(
            fill_id="FILL-001",
            order_id="ORD-001",
            instrument_id="159915.SZ",
            direction=OrderDirection.BUY,
            filled_quantity=100,
            fill_price=0.452,
            fee=2.26,
            slippage=0.001,
            event_time=datetime(2026, 1, 15, 10, 30, 5),
            cumulative_quantity=100,
            leaves_quantity=0,
        )
        assert fill.filled_quantity == 100
        assert fill.cumulative_quantity == 100
        assert fill.leaves_quantity == 0

    def test_fill_event_is_frozen(self) -> None:
        from ditto_core.execution.fills import FillEvent
        from dataclasses import FrozenInstanceError

        fill = FillEvent(
            fill_id="FILL-001",
            order_id="ORD-001",
            instrument_id="159915.SZ",
            direction=OrderDirection.BUY,
            filled_quantity=100,
            fill_price=0.452,
            fee=2.26,
            slippage=0.001,
            event_time=datetime(2026, 1, 15, 10, 30, 5),
            cumulative_quantity=100,
            leaves_quantity=0,
        )
        with pytest.raises(FrozenInstanceError):
            fill.filled_quantity = 200  # type: ignore[misc]


class TestFilled:
    def test_create_filled(self) -> None:
        from ditto_core.execution.fills import Filled, FillEvent

        event = FillEvent(
            fill_id="FILL-001",
            order_id="ORD-001",
            instrument_id="159915.SZ",
            direction=OrderDirection.BUY,
            filled_quantity=100,
            fill_price=0.452,
            fee=2.26,
            slippage=0.001,
            event_time=datetime(2026, 1, 15, 10, 30, 5),
            cumulative_quantity=100,
            leaves_quantity=0,
        )
        filled = Filled(fill_event=event)
        assert filled.fill_event.filled_quantity == 100

    def test_filled_is_fill_outcome(self) -> None:
        from ditto_core.execution.fills import Filled, FillEvent, FillOutcome

        event = FillEvent(
            fill_id="FILL-001",
            order_id="ORD-001",
            instrument_id="159915.SZ",
            direction=OrderDirection.BUY,
            filled_quantity=100,
            fill_price=0.452,
            fee=2.26,
            slippage=0.001,
            event_time=datetime(2026, 1, 15, 10, 30, 5),
            cumulative_quantity=100,
            leaves_quantity=0,
        )
        filled = Filled(fill_event=event)
        assert isinstance(filled, FillOutcome)


class TestNoFill:
    def test_no_fill_retryable(self) -> None:
        from ditto_core.execution.fills import NoFill, FillOutcome

        nofill = NoFill(reason="suspended", can_retry=True)
        assert nofill.reason == "suspended"
        assert nofill.can_retry is True
        assert isinstance(nofill, FillOutcome)

    def test_no_fill_not_retryable(self) -> None:
        from ditto_core.execution.fills import NoFill

        nofill = NoFill(reason="insufficient_auction", can_retry=False)
        assert nofill.can_retry is False

    def test_limit_up_deferred(self) -> None:
        from ditto_core.execution.fills import NoFill

        nofill = NoFill(reason="limit_up_deferred", can_retry=True)
        assert nofill.reason == "limit_up_deferred"

    def test_limit_down_deferred(self) -> None:
        from ditto_core.execution.fills import NoFill

        nofill = NoFill(reason="limit_down_deferred", can_retry=True)
        assert nofill.reason == "limit_down_deferred"

    def test_price_out_of_range(self) -> None:
        from ditto_core.execution.fills import NoFill

        nofill = NoFill(reason="price_out_of_range", can_retry=False)
        assert nofill.can_retry is False


# 需要在文件顶部添加: import pytest
import pytest
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/test_fills_unit.py -v
```

**Step 3: Write implementation**

```python
# packages/core/src/ditto_core/execution/fills.py
"""FillOutcome — 显式联合类型 (F4).

替代 v2 的 FillEvent | None + side-channel 模式。
FillModel 恢复纯函数语义，无隐式状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_core.accounting.order_book import OrderDirection

__all__ = [
    "FillEvent",
    "FillOutcome",
    "Filled",
    "NoFill",
]


class FillOutcome:
    """FillModel 的显式返回值基类。"""


@dataclass(frozen=True)
class Filled(FillOutcome):
    """成交。"""

    fill_event: FillEvent


@dataclass(frozen=True)
class NoFill(FillOutcome):
    """不成交 — 明确原因，无隐式状态。

    Attributes:
        reason: 不成交原因 (suspended / limit_up_deferred / limit_down_deferred / insufficient_auction / price_out_of_range)
        can_retry: True = 下一 step 可能成交，False = 该订单逻辑上无效
    """

    reason: str
    can_retry: bool


@dataclass(frozen=True)
class FillEvent:
    """单次成交事件 — Brokerage 产出（仅在确实成交时产生）。

    Attributes:
        fill_id: 成交 ID
        order_id: 关联订单 ID
        instrument_id: 标的 ID
        direction: 买/卖
        filled_quantity: 本次成交量
        fill_price: 成交价格
        fee: 交易费用
        slippage: 滑点
        event_time: 成交时间
        cumulative_quantity: 该订单累计已成交量
        leaves_quantity: 该订单剩余未成交量
    """

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

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/test_fills_unit.py -v
```

**Step 5: Update execution/__init__.py and commit**

```python
# packages/core/src/ditto_core/execution/__init__.py — 更新:
from ditto_core.execution.fills import (
    FillEvent,
    FillOutcome,
    Filled,
    NoFill,
)
from ditto_core.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    TradingRuleSet,
)

__all__ = [
    "FeeSchedule",
    "FillEvent",
    "FillOutcome",
    "Filled",
    "InstrumentDefinition",
    "NoFill",
    "TradingRuleSet",
]
```

```bash
git add packages/core/src/ditto_core/execution/ packages/core/tests/unit/execution/
git commit -m "feat(core): add FillOutcome (F4) and FillEvent"
```

---

## Task 4: execution/ 模块完整验证 `[S]` ✅

```bash
pixi run -e dev pytest packages/core/tests/unit/execution/ -v
pixi run -e dev check
```
