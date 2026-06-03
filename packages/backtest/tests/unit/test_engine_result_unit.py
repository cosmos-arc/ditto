"""EngineResult 不可变性与 EngineResultBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from ditto_backtest import result as result_module
from ditto_backtest.manifest_types import RunManifest, RunMode
from ditto_backtest.result import EngineResult, EngineResultBuilder
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import AccountView, CashBook, FillEvent

IID_1 = InstrumentId(1)


def _checkpoint_cls() -> type:
    """Return BacktestCheckpoint once the checkpoint API exists."""
    return result_module.BacktestCheckpoint


def _sample_order() -> Order:
    """创建最小 Order 用于测试。"""
    return Order(
        client_id=ClientOrderId(value="ord-1"),
        instrument_id=IID_1,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=100,
    )


def _sample_fill() -> FillEvent:
    """创建最小 FillEvent 用于测试。"""
    return FillEvent(
        fill_id="fill-1",
        order_id="ord-1",
        instrument_id=IID_1,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        event_time=datetime(2026, 1, 5, tzinfo=UTC),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _sample_account_view() -> AccountView:
    """创建最小 AccountView 用于测试。"""
    return AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
        total_value=1_000_000.0,
        nav=1_000_000.0,
        exposure=0.0,
    )


# ---------------------------------------------------------------------------
# EngineResult 不可变性测试
# ---------------------------------------------------------------------------


class TestEngineResultFrozen:
    """EngineResult 必须是不可变的（frozen dataclass）。"""

    def test_frozen_assign_raises(self) -> None:
        """对 frozen field 赋值应抛出 FrozenInstanceError。"""
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        with pytest.raises(FrozenInstanceError):
            result.final_nav = 999.0  # type: ignore[misc]

    def test_frozen_assign_run_id_raises(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        with pytest.raises(FrozenInstanceError):
            result.run_id = "other"  # type: ignore[misc]

    def test_frozen_assign_cancelled_raises(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        with pytest.raises(FrozenInstanceError):
            result.cancelled = True  # type: ignore[misc]

    def test_orders_is_tuple(self) -> None:
        """orders 字段必须是 tuple，不可变容器。"""
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            orders=(_sample_order(),),
        )
        assert isinstance(result.orders, tuple)
        assert len(result.orders) == 1

    def test_fills_is_tuple(self) -> None:
        """fills 字段必须是 tuple，不可变容器。"""
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            fills=(_sample_fill(),),
        )
        assert isinstance(result.fills, tuple)
        assert len(result.fills) == 1

    def test_default_orders_is_empty_tuple(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        assert result.orders == ()

    def test_default_fills_is_empty_tuple(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        assert result.fills == ()

    def test_docstring_says_immutable(self) -> None:
        """文档字符串应标记为不可变。"""
        assert EngineResult.__doc__ is not None
        assert "不可变" in EngineResult.__doc__


class TestBacktestCheckpoint:
    """BacktestCheckpoint freezes the recovery boundary."""

    def test_resume_from_next_trade_date(self) -> None:
        checkpoint = _checkpoint_cls()(
            run_id="run-001",
            strategy_id="strategy-a",
            completed_trade_date="2026-03-01",
            resume_from="2026-03-02",
            completed_days=1,
            total_days=3,
            nav=1_000_000.0,
            fill_count=2,
            order_count=2,
        )

        assert checkpoint.resume_from == "2026-03-02"
        assert checkpoint.can_resume is True

    def test_final_checkpoint_has_no_resume_date(self) -> None:
        checkpoint = _checkpoint_cls()(
            run_id="run-001",
            strategy_id="strategy-a",
            completed_trade_date="2026-03-03",
            resume_from=None,
            completed_days=3,
            total_days=3,
            nav=1_001_000.0,
            fill_count=4,
            order_count=4,
        )

        assert checkpoint.can_resume is False

    def test_account_state_hash_survives_integer_zero_exposure_roundtrip(self) -> None:
        """全现金账户的 int 0 exposure 不应导致 JSON/hash round-trip 漂移."""
        snapshot = result_module.BacktestAccountStateSnapshot(
            cash_available=1_000_000.0,
            cash_settled=1_000_000.0,
            cash_frozen=0.0,
            total_value=1_000_000.0,
            nav=1_000_000.0,
            exposure=0,
        )

        restored = result_module.BacktestAccountStateSnapshot.from_json(
            snapshot.to_json(),
        )

        assert restored.state_hash == snapshot.state_hash


# ---------------------------------------------------------------------------
# EngineResultBuilder 测试
# ---------------------------------------------------------------------------


class TestEngineResultBuilder:
    """EngineResultBuilder 可变累积 + build() 产出不可变结果。"""

    def test_initial_state_empty(self) -> None:
        builder = EngineResultBuilder()
        assert builder.orders == []
        assert builder.fills == []
        assert builder.skipped == []

    def test_add_order(self) -> None:
        builder = EngineResultBuilder()
        order = _sample_order()
        builder.add_order(order)
        assert len(builder.orders) == 1
        assert builder.orders[0] is order

    def test_add_fill(self) -> None:
        builder = EngineResultBuilder()
        fill = _sample_fill()
        builder.add_fill(fill)
        assert len(builder.fills) == 1
        assert builder.fills[0] is fill

    def test_add_skipped(self) -> None:
        builder = EngineResultBuilder()
        builder.add_skipped("2026-01-05")
        assert builder.skipped == ["2026-01-05"]

    def test_extend_orders(self) -> None:
        builder = EngineResultBuilder()
        orders = [_sample_order(), _sample_order()]
        builder.extend_orders(orders)
        assert len(builder.orders) == 2

    def test_extend_fills(self) -> None:
        builder = EngineResultBuilder()
        fills = [_sample_fill(), _sample_fill()]
        builder.extend_fills(fills)
        assert len(builder.fills) == 2

    def test_build_produces_frozen_result(self) -> None:
        builder = EngineResultBuilder()
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert isinstance(result, EngineResult)
        with pytest.raises(FrozenInstanceError):
            result.final_nav = 0.0  # type: ignore[misc]

    def test_build_orders_as_tuple(self) -> None:
        builder = EngineResultBuilder()
        order = _sample_order()
        builder.add_order(order)
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.orders == (order,)

    def test_build_fills_as_tuple(self) -> None:
        builder = EngineResultBuilder()
        fill = _sample_fill()
        builder.add_fill(fill)
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.fills == (fill,)

    def test_build_skipped_as_tuple(self) -> None:
        builder = EngineResultBuilder()
        builder.add_skipped("2026-01-05")
        builder.add_skipped("2026-01-06")
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.skipped_dates == ("2026-01-05", "2026-01-06")

    def test_build_total_trades_from_fills(self) -> None:
        builder = EngineResultBuilder()
        builder.add_fill(_sample_fill())
        builder.add_fill(_sample_fill())
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.total_trades == 2

    def test_build_copies_mutable_state(self) -> None:
        """build() 应将 list 转为 tuple，后续 builder 修改不影响已产出的 result。"""
        builder = EngineResultBuilder()
        builder.add_order(_sample_order())
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        # 继续往 builder 添加
        builder.add_order(_sample_order())
        # result 不受影响
        assert len(result.orders) == 1

    def test_build_with_all_fields(self) -> None:
        """完整参数 build 测试。"""

        manifest = RunManifest(
            run_id="run-001",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
        )
        order = _sample_order()
        fill = _sample_fill()
        checkpoint = _checkpoint_cls()(
            run_id="run-001",
            strategy_id="test-strategy",
            completed_trade_date="2026-01-05",
            resume_from="2026-01-06",
            completed_days=1,
            total_days=2,
            nav=1_050_000.0,
            fill_count=1,
            order_count=1,
        )
        builder = EngineResultBuilder()
        builder.add_order(order)
        builder.add_fill(fill)
        builder.add_skipped("2026-01-05")
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_050_000.0,
            account_view=None,
            manifest=manifest,
            last_checkpoint=checkpoint,
            cancelled=True,
        )
        assert result.run_id == "run-001"
        assert result.final_nav == 1_050_000.0
        assert result.total_trades == 1
        assert result.orders == (order,)
        assert result.fills == (fill,)
        assert result.skipped_dates == ("2026-01-05",)
        assert result.manifest is manifest
        assert result.last_checkpoint is checkpoint
        assert result.cancelled is True


# ---------------------------------------------------------------------------
# assemble_engine_result 集成测试
# ---------------------------------------------------------------------------


class TestAssembleEngineResult:
    """assemble_engine_result 应返回 frozen EngineResult。"""

    def test_returns_frozen_result(self) -> None:
        from ditto_backtest.engine_steps import assemble_engine_result

        account_view = _sample_account_view()
        manifest = RunManifest(
            run_id="run-001",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
        )
        result = assemble_engine_result(
            run_id="run-001",
            start="2026-01-01",
            end="2026-01-31",
            account_view=account_view,
            manifest=manifest,
            fills=[],
            orders=[],
            skipped=[],
            cancelled=False,
        )
        with pytest.raises(FrozenInstanceError):
            result.final_nav = 0.0  # type: ignore[misc]

    def test_orders_and_fills_are_tuples(self) -> None:
        from ditto_backtest.engine_steps import assemble_engine_result

        order = _sample_order()
        fill = _sample_fill()
        account_view = _sample_account_view()
        manifest = RunManifest(
            run_id="run-001",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
        )
        result = assemble_engine_result(
            run_id="run-001",
            start="2026-01-01",
            end="2026-01-31",
            account_view=account_view,
            manifest=manifest,
            fills=[fill],
            orders=[order],
            skipped=["2026-01-05"],
            cancelled=False,
        )
        assert isinstance(result.orders, tuple)
        assert isinstance(result.fills, tuple)
        assert result.orders == (order,)
        assert result.fills == (fill,)
        assert result.skipped_dates == ("2026-01-05",)
