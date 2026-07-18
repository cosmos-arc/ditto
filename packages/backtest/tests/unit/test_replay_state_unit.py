"""Tests for ReplayProof — fill and account state comparison."""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType

from ditto_backtest.manifest import RunManifest, RunMode
from ditto_backtest.replay import (
    AccountStateComparison,
    FillComparison,
    ReplayProof,
    ReplayStateProof,
    ReplayValidator,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import CashBook
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.accounting.position import Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fill(
    instrument_id: InstrumentId = InstrumentId(600_000),
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 100,
    fill_price: float = 10.0,
    fee: float = 5.0,
    fill_id: str = "f1",
    order_id: str = "o1",
) -> FillEvent:
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=0.0,
        event_time=datetime(2024, 1, 15, 15, 0),
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


def _account_view(
    nav: float = 100_000.0,
    cash: CashBook | None = None,
    positions: dict[InstrumentId, Position] | None = None,
) -> AccountView:
    return AccountView(
        positions=MappingProxyType(positions or {}),
        cash=cash or CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav,
        nav=nav,
        exposure=0.0,
    )


def _make_manifest(run_id: str = "run-001") -> RunManifest:
    return RunManifest(
        run_id=run_id,
        strategy_id="state-proof",
        strategy_version="1.0",
        mode=RunMode.BACKTEST,
        created_at="2026-04-11T00:00:00Z",
        config_hash="config",
        engine_version="engine",
        spec_hash="a" * 64,
    )


# ---------------------------------------------------------------------------
# TestFillComparison
# ---------------------------------------------------------------------------


class TestFillComparison:
    """FillComparison frozen dataclass + ReplayProof.compare_fills."""

    def test_identical_fills(self) -> None:
        fills = [_make_fill(fill_id="f1"), _make_fill(fill_id="f2", fill_price=11.0)]
        result: FillComparison = ReplayProof.compare_fills(fills, fills)
        assert result.identical is True
        assert result.mismatch_count == 0
        assert result.length_mismatch is False

    def test_different_lengths(self) -> None:
        original = [
            _make_fill(fill_id="f1"),
            _make_fill(fill_id="f2"),
            _make_fill(fill_id="f3"),
        ]
        replay = [_make_fill(fill_id="f1"), _make_fill(fill_id="f2")]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False
        assert result.length_mismatch is True
        assert result.point_count == 3

    def test_different_prices(self) -> None:
        original = [_make_fill(fill_id="f1", fill_price=10.0)]
        replay = [_make_fill(fill_id="f1", fill_price=10.5)]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False
        assert result.mismatch_count > 0

    def test_empty_fills(self) -> None:
        result = ReplayProof.compare_fills([], [])
        assert result.identical is True
        assert result.mismatch_count == 0
        assert result.point_count == 0

    def test_different_fee_detected(self) -> None:
        """fee 不同但 fill_id/price/quantity 相同时，应判定为不一致。"""
        original = [_make_fill(fill_id="f1", fee=5.0)]
        replay = [_make_fill(fill_id="f1", fee=50.0)]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False
        assert result.mismatch_count > 0

    def test_different_instrument_detected(self) -> None:
        """instrument_id 不同但 fill_id/price/quantity 相同时，应判定为不一致。"""
        original = [_make_fill(instrument_id=InstrumentId(600_000))]
        replay = [_make_fill(instrument_id=InstrumentId(600_001))]
        result = ReplayProof.compare_fills(original, replay)
        assert result.identical is False


# ---------------------------------------------------------------------------
# TestAccountStateComparison
# ---------------------------------------------------------------------------


class TestAccountStateComparison:
    """AccountStateComparison frozen dataclass + ReplayProof.compare_account_state."""

    def test_identical_accounts(self) -> None:
        view = _account_view(nav=100_000.0)
        result: AccountStateComparison = ReplayProof.compare_account_state(view, view)
        assert result.identical is True
        assert result.nav_diff == 0.0
        assert result.available_cash_diff == 0.0
        assert result.position_count_diff == 0

    def test_different_nav(self) -> None:
        original = _account_view(nav=100_000.0)
        replay = _account_view(nav=99_500.0)
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
        assert result.nav_diff == 500.0

    def test_different_cash(self) -> None:
        original = _account_view(
            nav=100_000.0,
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        replay = _account_view(
            nav=100_000.0,
            cash=CashBook(available=90_000.0, settled=90_000.0, frozen=0.0),
        )
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
        assert result.available_cash_diff == 10_000.0

    def test_different_settled_cash_detected(self) -> None:
        """settled 不同但 available 相同时，应判定为不一致。"""
        original = _account_view(
            nav=100_000.0,
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        replay = _account_view(
            nav=100_000.0,
            cash=CashBook(available=100_000.0, settled=80_000.0, frozen=0.0),
        )
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False

    def test_different_frozen_cash_detected(self) -> None:
        """frozen 不同但 available 相同时，应判定为不一致。"""
        original = _account_view(
            nav=100_000.0,
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        replay = _account_view(
            nav=100_000.0,
            cash=CashBook(available=100_000.0, settled=100_000.0, frozen=20_000.0),
        )
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False

    def test_different_positions(self) -> None:
        pos = Position(
            instrument_id=InstrumentId(600_000),
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        original = _account_view(positions={InstrumentId(600_000): pos})
        replay = _account_view(positions={})
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False
        assert result.position_count_diff == 1

    def test_same_keys_different_quantity(self) -> None:
        """相同持仓 key 但 quantity 不同时，应判定为不一致。"""
        iid = InstrumentId(600_000)
        pos_a = Position(
            instrument_id=iid,
            quantity=100,
            available_quantity=100,
            average_cost=10.0,
            market_value=1000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        pos_b = Position(
            instrument_id=iid,
            quantity=200,
            available_quantity=200,
            average_cost=10.0,
            market_value=2000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        original = _account_view(
            nav=1000.0,
            positions={iid: pos_a},
        )
        replay = _account_view(
            nav=2000.0,
            positions={iid: pos_b},
        )
        result = ReplayProof.compare_account_state(original, replay)
        assert result.identical is False


class TestReplayValidatorStateProof:
    """ReplayValidator.validate includes fill and account state proof."""

    def test_fill_mismatch_makes_replay_not_reproducible(self) -> None:
        """相同 manifest/NAV 下，fill drift 也应让 replay 失败。"""
        manifest = _make_manifest()
        nav = [100_000.0, 100_100.0]
        original_fill = _make_fill(fill_id="f1", fee=5.0)
        replay_fill = _make_fill(fill_id="f1", fee=50.0)

        result = ReplayValidator.validate(
            manifest,
            manifest,
            nav,
            nav,
            state_proof=ReplayStateProof(
                original_fills=(original_fill,),
                replay_fills=(replay_fill,),
            ),
        )

        assert result.is_reproducible is False
        assert result.fill_match is False
        assert result.fill_comparison is not None
        assert result.fill_comparison.mismatch_count == 1

    def test_account_state_mismatch_makes_replay_not_reproducible(self) -> None:
        """相同 manifest/NAV/fills 下，最终账户状态 drift 也应让 replay 失败。"""
        manifest = _make_manifest()
        nav = [100_000.0, 100_100.0]
        fill = _make_fill()
        original_account = _account_view(
            nav=100_100.0,
            cash=CashBook(available=99_000.0, settled=99_000.0, frozen=0.0),
        )
        replay_account = _account_view(
            nav=100_100.0,
            cash=CashBook(available=98_000.0, settled=99_000.0, frozen=0.0),
        )

        result = ReplayValidator.validate(
            manifest,
            manifest,
            nav,
            nav,
            state_proof=ReplayStateProof(
                original_fills=(fill,),
                replay_fills=(fill,),
                original_account=original_account,
                replay_account=replay_account,
            ),
        )

        assert result.is_reproducible is False
        assert result.account_state_match is False
        assert result.account_state_comparison is not None
        assert result.account_state_comparison.available_cash_diff == 1000.0

    def test_matching_state_sets_state_match_evidence(self) -> None:
        """fill/account 都一致时，结果显式暴露 state proof 通过。"""
        manifest = _make_manifest()
        nav = [100_000.0, 100_100.0]
        fill = _make_fill()
        account = _account_view(nav=100_100.0)

        result = ReplayValidator.validate(
            manifest,
            manifest,
            nav,
            nav,
            state_proof=ReplayStateProof(
                original_fills=(fill,),
                replay_fills=(fill,),
                original_account=account,
                replay_account=account,
            ),
        )

        assert result.is_reproducible is True
        assert result.fill_match is True
        assert result.account_state_match is True
