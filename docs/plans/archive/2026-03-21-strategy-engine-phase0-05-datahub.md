# Phase 0 Part 4: DataHub 层新增

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** ✅ DONE (2026-03-21)

**Goal:** 在 DataHub 层实现 TradingRuleStore / FeeScheduleStore（PIT 版本化存储）和 InstrumentRuleProvider（三层规则组装）

**Architecture:** 复用现有 PIT 基础设施（SQLite + effective_from/effective_to）。Store 遵循 CQRS 模式（Reader/Writer 分离）。Provider 组装三层规则并缓存。

**Design Doc:** v3 §5.1.4 (InstrumentRuleProvider), §9.3 (DataHub 新增), §11.1 Phase 0

**前置依赖:** Part 1 (accounting/) + Part 2 (execution/rules.py)

---

## Task 1: TradingRuleStore (PIT 版本化) `[M]` ✅

**Files:**
- Create: `packages/data/src/ditto_data/stores/metadata/trading_rule_writer.py`
- Create: `packages/data/src/ditto_data/stores/metadata/trading_rule_reader.py`
- Test: `packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py`

> **关键约定**: 遵循 `.claude/rules/pit.md` 中的 PIT 查询规范。

**Step 1: Write the failing test**

```python
# packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py
"""Tests for TradingRuleReader / TradingRuleWriter (PIT versioned)."""

import pytest
from dataclasses import FrozenInstanceError


class TestTradingRuleRecord:
    def test_create_record(self) -> None:
        from ditto_data.stores.metadata.trading_rule_reader import TradingRuleRecord

        record = TradingRuleRecord(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
            effective_from="2026-01-01",
            effective_to=None,
        )
        assert record.settlement_cycle == 1
        assert record.effective_to is None

    def test_record_is_frozen(self) -> None:
        from ditto_data.stores.metadata.trading_rule_reader import TradingRuleRecord

        record = TradingRuleRecord(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
            effective_from="2026-01-01",
            effective_to=None,
        )
        with pytest.raises(FrozenInstanceError):
            record.settlement_cycle = 0  # type: ignore[misc]

    def test_to_core_model(self) -> None:
        from ditto_core.execution.rules import TradingRuleSet
        from ditto_data.stores.metadata.trading_rule_reader import TradingRuleRecord

        record = TradingRuleRecord(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            settlement_cycle=1,
            fund_settlement_cycle=1,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=("open", "close"),
            effective_from="2026-01-01",
            effective_to=None,
        )
        core_model = record.to_core()
        assert isinstance(core_model, TradingRuleSet)
        assert core_model.instrument_id == "159915.SZ"
```

**Step 2: Run test to verify it fails**

**Step 3: Write implementation**

```python
# packages/data/src/ditto_data/stores/metadata/trading_rule_reader.py
"""TradingRuleReader — PIT 版本化交易规则查询."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_core.execution.rules import TradingRuleSet

__all__ = ["TradingRuleReader", "TradingRuleRecord"]


@dataclass(frozen=True)
class TradingRuleRecord:
    """交易规则持久化记录（含 PIT 字段）。

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 规则适用日期
        settlement_cycle: T+N 交收
        fund_settlement_cycle: 资金 T+N 交收
        price_limit_pct: 涨跌停限制
        order_types_supported: 支持的订单类型
        call_auction_sessions: 集合竞价时段
        effective_from: PIT 生效日期
        effective_to: PIT 失效日期（None=当前版本）
    """

    instrument_id: str
    as_of_date: str
    settlement_cycle: int
    fund_settlement_cycle: int
    price_limit_pct: float | None
    order_types_supported: tuple[str, ...]
    call_auction_sessions: tuple[str, ...]
    effective_from: str
    effective_to: str | None = None

    def to_core(self) -> TradingRuleSet:
        """转换为 Core 层 TradingRuleSet。"""
        return TradingRuleSet(
            instrument_id=self.instrument_id,
            as_of_date=self.as_of_date,
            settlement_cycle=self.settlement_cycle,
            fund_settlement_cycle=self.fund_settlement_cycle,
            price_limit_pct=self.price_limit_pct,
            order_types_supported=self.order_types_supported,
            call_auction_sessions=self.call_auction_sessions,
        )


class TradingRuleReader:
    """交易规则 Reader — PIT 版本化查询。

    V1: 内存实现，供 Phase 2 接入真实 SQLite/Parquet 存储后替换。
    """

    def __init__(self) -> None:
        self._records: list[TradingRuleRecord] = []

    def load(self, records: list[TradingRuleRecord]) -> None:
        """加载记录（测试用，生产环境从存储读取）。"""
        self._records = records

    def get(self, instrument_id: str, as_of_date: str) -> TradingRuleRecord | None:
        """PIT 查询：获取 instrument_id 在 as_of_date 有效的规则。

        遵循 pit.md 规范：
        - effective_from <= as_of_date
        - effective_to IS NULL OR effective_to > as_of_date
        """
        candidates = [
            r for r in self._records
            if r.instrument_id == instrument_id
            and r.effective_from <= as_of_date
            and (r.effective_to is None or r.effective_to > as_of_date)
        ]
        if not candidates:
            return None
        # 取最新版本
        return max(candidates, key=lambda r: r.effective_from)
```

```python
# packages/data/src/ditto_data/stores/metadata/trading_rule_writer.py
"""TradingRuleWriter — PIT 版本化交易规则写入."""

from __future__ import annotations

from ditto_data.stores.metadata.trading_rule_reader import TradingRuleRecord

__all__ = ["TradingRuleWriter"]


class TradingRuleWriter:
    """交易规则 Writer。

    V1: 内存实现，供 Phase 2 接入真实存储后替换。
    """

    def __init__(self) -> None:
        self._records: list[TradingRuleRecord] = []

    def write(self, record: TradingRuleRecord) -> None:
        """写入一条规则记录。"""
        self._records.append(record)

    def get_records(self) -> list[TradingRuleRecord]:
        """获取所有记录（测试用）。"""
        return list(self._records)
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py -v
```

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/stores/metadata/trading_rule_reader.py \
        packages/data/src/ditto_data/stores/metadata/trading_rule_writer.py \
        packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py
git commit -m "feat(datahub): add TradingRuleReader/Writer with PIT versioning"
```

---

## Task 2: FeeScheduleStore (PIT 版本化) `[M]` ✅

**Files:**
- Create: `packages/data/src/ditto_data/stores/metadata/fee_schedule_writer.py`
- Create: `packages/data/src/ditto_data/stores/metadata/fee_schedule_reader.py`
- Test: `packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py`

**Step 1: Write the failing test**

```python
# packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py
"""Tests for FeeScheduleReader / FeeScheduleWriter (PIT versioned)."""

import pytest
from dataclasses import FrozenInstanceError


class TestFeeScheduleRecord:
    def test_create_record(self) -> None:
        from ditto_data.stores.metadata.fee_schedule_reader import FeeScheduleRecord

        record = FeeScheduleRecord(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            effective_from="2026-01-01",
            effective_to=None,
        )
        assert record.stamp_duty_rate == 0.0

    def test_record_is_frozen(self) -> None:
        from ditto_data.stores.metadata.fee_schedule_reader import FeeScheduleRecord

        record = FeeScheduleRecord(
            instrument_id="159915.SZ",
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            effective_from="2026-01-01",
            effective_to=None,
        )
        with pytest.raises(FrozenInstanceError):
            record.commission_rate = 0.0  # type: ignore[misc]

    def test_to_core_model(self) -> None:
        from ditto_core.execution.rules import FeeSchedule
        from ditto_data.stores.metadata.fee_schedule_reader import FeeScheduleRecord

        record = FeeScheduleRecord(
            instrument_id="600000.SH",
            as_of_date="2026-01-01",
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            effective_from="2026-01-01",
            effective_to=None,
        )
        core_model = record.to_core()
        assert isinstance(core_model, FeeSchedule)
        assert core_model.stamp_duty_rate == 0.0005


class TestFeeScheduleReaderPIT:
    def test_get_current_version(self) -> None:
        from ditto_data.stores.metadata.fee_schedule_reader import (
            FeeScheduleReader,
            FeeScheduleRecord,
        )

        reader = FeeScheduleReader()
        reader.load([
            FeeScheduleRecord(
                instrument_id="159915.SZ",
                as_of_date="2026-01-01",
                commission_rate=0.0003,
                min_commission=5.0,
                stamp_duty_rate=0.0005,  # 印花税减半前
                transfer_fee_rate=0.00001,
                effective_from="2023-01-01",
                effective_to="2023-08-27",
            ),
            FeeScheduleRecord(
                instrument_id="159915.SZ",
                as_of_date="2026-01-01",
                commission_rate=0.0003,
                min_commission=5.0,
                stamp_duty_rate=0.00025,  # 印花税减半后
                transfer_fee_rate=0.00001,
                effective_from="2023-08-28",
                effective_to=None,
            ),
        ])
        result = reader.get("159915.SZ", "2026-01-01")
        assert result is not None
        assert result.stamp_duty_rate == pytest.approx(0.00025)

    def test_get_historical_version(self) -> None:
        from ditto_data.stores.metadata.fee_schedule_reader import (
            FeeScheduleReader,
            FeeScheduleRecord,
        )

        reader = FeeScheduleReader()
        reader.load([
            FeeScheduleRecord(
                instrument_id="159915.SZ",
                as_of_date="2023-01-01",
                commission_rate=0.0003,
                min_commission=5.0,
                stamp_duty_rate=0.0005,
                transfer_fee_rate=0.00001,
                effective_from="2023-01-01",
                effective_to="2023-08-27",
            ),
            FeeScheduleRecord(
                instrument_id="159915.SZ",
                as_of_date="2023-08-28",
                commission_rate=0.0003,
                min_commission=5.0,
                stamp_duty_rate=0.00025,
                transfer_fee_rate=0.00001,
                effective_from="2023-08-28",
                effective_to=None,
            ),
        ])
        # 2023-01-15 应获取旧版规则
        result = reader.get("159915.SZ", "2023-01-15")
        assert result is not None
        assert result.stamp_duty_rate == pytest.approx(0.0005)
```

**Step 2: Run test to verify it fails**

**Step 3: Write implementation**

```python
# packages/data/src/ditto_data/stores/metadata/fee_schedule_reader.py
"""FeeScheduleReader — PIT 版本化费率查询."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_core.execution.rules import FeeSchedule

__all__ = ["FeeScheduleReader", "FeeScheduleRecord"]


@dataclass(frozen=True)
class FeeScheduleRecord:
    """费率持久化记录（含 PIT 字段）。"""

    instrument_id: str
    as_of_date: str
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    effective_from: str
    effective_to: str | None = None

    def to_core(self) -> FeeSchedule:
        return FeeSchedule(
            instrument_id=self.instrument_id,
            as_of_date=self.as_of_date,
            commission_rate=self.commission_rate,
            min_commission=self.min_commission,
            stamp_duty_rate=self.stamp_duty_rate,
            transfer_fee_rate=self.transfer_fee_rate,
        )


class FeeScheduleReader:
    """费率 Reader — PIT 版本化查询。V1 内存实现。"""

    def __init__(self) -> None:
        self._records: list[FeeScheduleRecord] = []

    def load(self, records: list[FeeScheduleRecord]) -> None:
        self._records = records

    def get(self, instrument_id: str, as_of_date: str) -> FeeScheduleRecord | None:
        candidates = [
            r for r in self._records
            if r.instrument_id == instrument_id
            and r.effective_from <= as_of_date
            and (r.effective_to is None or r.effective_to > as_of_date)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.effective_from)
```

```python
# packages/data/src/ditto_data/stores/metadata/fee_schedule_writer.py
"""FeeScheduleWriter — PIT 版本化费率写入."""

from __future__ import annotations

from ditto_data.stores.metadata.fee_schedule_reader import FeeScheduleRecord

__all__ = ["FeeScheduleWriter"]


class FeeScheduleWriter:
    """费率 Writer。V1 内存实现。"""

    def __init__(self) -> None:
        self._records: list[FeeScheduleRecord] = []

    def write(self, record: FeeScheduleRecord) -> None:
        self._records.append(record)

    def get_records(self) -> list[FeeScheduleRecord]:
        return list(self._records)
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py -v
```

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/stores/metadata/fee_schedule_reader.py \
        packages/data/src/ditto_data/stores/metadata/fee_schedule_writer.py \
        packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py
git commit -m "feat(datahub): add FeeScheduleReader/Writer with PIT versioning"
```

---

## Task 3: InstrumentRuleProvider `[L]` ✅

**Files:**
- Create: `packages/data/src/ditto_data/services/strategy/__init__.py`
- Create: `packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py`
- Test: `packages/data/tests/unit/services/strategy/test_instrument_rule_provider_unit.py`

**Step 1: Write the failing test**

```python
# packages/data/tests/unit/services/strategy/test_instrument_rule_provider_unit.py
"""Tests for InstrumentRuleProvider — 三层规则组装."""

import pytest


class TestInstrumentRuleProvider:
    def test_get_definition(self) -> None:
        from ditto_core.execution.rules import InstrumentDefinition
        from ditto_data.services.strategy.instrument_rule_provider import (
            InstrumentRuleProvider,
        )

        provider = InstrumentRuleProvider()
        provider.load_definition(InstrumentDefinition(
            instrument_id="159915.SZ",
            asset_class="etf",
            exchange="XSHE",
            currency="CNY",
            tick_size=0.001,
            lot_size=100,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="normal",
        ))
        defn = provider.get_definition("159915.SZ")
        assert defn is not None
        assert defn.lot_size == 100

    def test_get_definition_not_found(self) -> None:
        from ditto_data.services.strategy.instrument_rule_provider import (
            InstrumentRuleProvider,
        )

        provider = InstrumentRuleProvider()
        assert provider.get_definition("NONEXISTENT") is None

    def test_get_trading_rule(self) -> None:
        from ditto_data.services.strategy.instrument_rule_provider import (
            InstrumentRuleProvider,
        )
        from ditto_data.stores.metadata.trading_rule_reader import TradingRuleRecord

        provider = InstrumentRuleProvider()
        provider.load_trading_rules([
            TradingRuleRecord(
                instrument_id="159915.SZ",
                as_of_date="2026-01-01",
                settlement_cycle=1,
                fund_settlement_cycle=1,
                price_limit_pct=0.10,
                order_types_supported=("market", "limit"),
                call_auction_sessions=("open", "close"),
                effective_from="2026-01-01",
                effective_to=None,
            ),
        ])
        rule = provider.get_trading_rule("159915.SZ", "2026-01-15")
        assert rule is not None
        assert rule.settlement_cycle == 1

    def test_get_fee_schedule(self) -> None:
        from ditto_data.services.strategy.instrument_rule_provider import (
            InstrumentRuleProvider,
        )
        from ditto_data.stores.metadata.fee_schedule_reader import FeeScheduleRecord

        provider = InstrumentRuleProvider()
        provider.load_fee_schedules([
            FeeScheduleRecord(
                instrument_id="159915.SZ",
                as_of_date="2026-01-01",
                commission_rate=0.0003,
                min_commission=5.0,
                stamp_duty_rate=0.0,
                transfer_fee_rate=0.0,
                effective_from="2026-01-01",
                effective_to=None,
            ),
        ])
        fee = provider.get_fee_schedule("159915.SZ", "2026-01-15")
        assert fee is not None
        assert fee.commission_rate == pytest.approx(0.0003)

    def test_get_rules_batch(self) -> None:
        from ditto_core.execution.rules import InstrumentDefinition
        from ditto_data.services.strategy.instrument_rule_provider import (
            InstrumentRuleProvider,
        )
        from ditto_data.stores.metadata.fee_schedule_reader import FeeScheduleRecord
        from ditto_data.stores.metadata.trading_rule_reader import TradingRuleRecord

        provider = InstrumentRuleProvider()
        provider.load_definition(InstrumentDefinition(
            instrument_id="159915.SZ", asset_class="etf", exchange="XSHE",
            currency="CNY", tick_size=0.001, lot_size=100, multiplier=1.0,
            board_segment="main", lifecycle_state="normal",
        ))
        provider.load_definition(InstrumentDefinition(
            instrument_id="510300.SH", asset_class="etf", exchange="XSHG",
            currency="CNY", tick_size=0.001, lot_size=100, multiplier=1.0,
            board_segment="main", lifecycle_state="normal",
        ))
        provider.load_trading_rules([
            TradingRuleRecord(
                instrument_id="159915.SZ", as_of_date="2026-01-01",
                settlement_cycle=1, fund_settlement_cycle=1,
                price_limit_pct=0.10, order_types_supported=("market", "limit"),
                call_auction_sessions=("open", "close"),
                effective_from="2026-01-01", effective_to=None,
            ),
            TradingRuleRecord(
                instrument_id="510300.SH", as_of_date="2026-01-01",
                settlement_cycle=1, fund_settlement_cycle=1,
                price_limit_pct=0.10, order_types_supported=("market", "limit"),
                call_auction_sessions=("open", "close"),
                effective_from="2026-01-01", effective_to=None,
            ),
        ])
        provider.load_fee_schedules([
            FeeScheduleRecord(
                instrument_id="159915.SZ", as_of_date="2026-01-01",
                commission_rate=0.0003, min_commission=5.0,
                stamp_duty_rate=0.0, transfer_fee_rate=0.0,
                effective_from="2026-01-01", effective_to=None,
            ),
            FeeScheduleRecord(
                instrument_id="510300.SH", as_of_date="2026-01-01",
                commission_rate=0.0003, min_commission=5.0,
                stamp_duty_rate=0.0, transfer_fee_rate=0.0,
                effective_from="2026-01-01", effective_to=None,
            ),
        ])

        rules = provider.get_rules("2026-01-15", ["159915.SZ", "510300.SH"])
        assert len(rules) == 2
        assert "159915.SZ" in rules
        assert "510300.SH" in rules

        # 每个 value 是 (InstrumentDefinition, TradingRuleSet, FeeSchedule) 元组
        defn, trading_rule, fee = rules["159915.SZ"]
        assert defn.lot_size == 100
        assert trading_rule.settlement_cycle == 1
        assert fee.commission_rate == pytest.approx(0.0003)
```

**Step 2: Run test to verify it fails**

**Step 3: Write implementation**

```python
# packages/data/src/ditto_data/services/strategy/__init__.py
"""Strategy DataHub services."""

from ditto_data.services.strategy.instrument_rule_provider import (
    InstrumentRuleProvider,
)

__all__ = ["InstrumentRuleProvider"]
```

```python
# packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py
"""InstrumentRuleProvider — 三层规则组装层 (R6).

从 InstrumentRegistration + Extension 组装 InstrumentDefinition，
从 PIT Store 查询 TradingRuleSet / FeeSchedule。
V1: 内存实现，Phase 2+ 接入真实 DataHub 存储后替换。
"""

from __future__ import annotations

from ditto_core.execution.rules import (
    FeeSchedule,
    InstrumentDefinition,
    TradingRuleSet,
)
from ditto_data.stores.metadata.fee_schedule_reader import (
    FeeScheduleReader,
    FeeScheduleRecord,
)
from ditto_data.stores.metadata.trading_rule_reader import (
    TradingRuleReader,
    TradingRuleRecord,
)

__all__ = ["InstrumentRuleProvider"]


class InstrumentRuleProvider:
    """三层规则组装 + PIT 版本化查询。

    V1: 内存实现。Phase 2+ 从 DataHub metadata service 读取。
    """

    def __init__(
        self,
        trading_rule_reader: TradingRuleReader | None = None,
        fee_schedule_reader: FeeScheduleReader | None = None,
    ) -> None:
        self._definitions: dict[str, InstrumentDefinition] = {}
        self._trading_rule_reader = trading_rule_reader or TradingRuleReader()
        self._fee_schedule_reader = fee_schedule_reader or FeeScheduleReader()

    # ── 加载方法（V1 测试用，生产环境从存储读取）──

    def load_definition(self, definition: InstrumentDefinition) -> None:
        self._definitions[definition.instrument_id] = definition

    def load_trading_rules(self, records: list[TradingRuleRecord]) -> None:
        self._trading_rule_reader.load(records)

    def load_fee_schedules(self, records: list[FeeScheduleRecord]) -> None:
        self._fee_schedule_reader.load(records)

    # ── 查询方法 ──

    def get_definition(self, instrument_id: str) -> InstrumentDefinition | None:
        return self._definitions.get(instrument_id)

    def get_trading_rule(
        self, instrument_id: str, as_of_date: str,
    ) -> TradingRuleSet | None:
        record = self._trading_rule_reader.get(instrument_id, as_of_date)
        return record.to_core() if record else None

    def get_fee_schedule(
        self, instrument_id: str, as_of_date: str,
    ) -> FeeSchedule | None:
        record = self._fee_schedule_reader.get(instrument_id, as_of_date)
        return record.to_core() if record else None

    def get_rules(
        self, as_of_date: str, instrument_ids: list[str],
    ) -> dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]:
        """批量获取三层规则。

        Returns:
            {instrument_id: (InstrumentDefinition, TradingRuleSet, FeeSchedule)}

        Raises:
            ValueError: 某个标的缺少规则数据
        """
        result: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]] = {}
        for iid in instrument_ids:
            defn = self.get_definition(iid)
            trading_rule = self.get_trading_rule(iid, as_of_date)
            fee = self.get_fee_schedule(iid, as_of_date)
            if defn is None:
                raise ValueError(f"InstrumentDefinition not found: {iid}")
            if trading_rule is None:
                raise ValueError(f"TradingRuleSet not found for {iid} @ {as_of_date}")
            if fee is None:
                raise ValueError(f"FeeSchedule not found for {iid} @ {as_of_date}")
            result[iid] = (defn, trading_rule, fee)
        return result
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest packages/data/tests/unit/services/strategy/test_instrument_rule_provider_unit.py -v
```

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/services/strategy/ \
        packages/data/tests/unit/services/strategy/
git commit -m "feat(datahub): add InstrumentRuleProvider with three-layer rule assembly"
```

---

## Task 4: DataHub 层完整验证 `[S]` ✅

```bash
pixi run -e dev pytest packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py \
                        packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py \
                        packages/data/tests/unit/services/strategy/ -v
pixi run -e dev check
```

---

## 完成记录

**完成时间:** 2026-03-21

**设计偏差（经用户确认）:**
1. **转换移到调用方**: 计划中 `TradingRuleRecord.to_core()` / `FeeScheduleRecord.to_core()` 转换为 Core 模型被移除。DataHub 层不依赖 Core，只返回 Records，由调用方负责转换。
2. **DefinitionRecord 替代 InstrumentDefinition**: `InstrumentRuleProvider` 使用 DataHub 本地的 `DefinitionRecord` frozen dataclass 替代 Core 层的 `InstrumentDefinition`，避免 DataHub → Core 依赖。
3. **泛型基类提取**: 代码简化器将 PIT 查询逻辑提取到 `_pit_base.py` 中的 `PITRecordReader[RecordT]` / `PITRecordWriter[RecordT]` / `PITRecord` Protocol，TradingRuleReader/Writer 和 FeeScheduleReader/Writer 继承自泛型基类。

**新增文件:**
- `packages/data/src/ditto_data/stores/metadata/_pit_base.py` — 泛型 PIT 基类
- `packages/data/src/ditto_data/stores/metadata/trading_rule_reader.py`
- `packages/data/src/ditto_data/stores/metadata/trading_rule_writer.py`
- `packages/data/src/ditto_data/stores/metadata/fee_schedule_reader.py`
- `packages/data/src/ditto_data/stores/metadata/fee_schedule_writer.py`
- `packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py`
- `packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py`
- `packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py`
- `packages/data/tests/unit/services/strategy/test_instrument_rule_provider_unit.py`
