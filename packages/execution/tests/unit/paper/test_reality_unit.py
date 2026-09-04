"""PAP-01..03: formal paper-order reality and lineage contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ditto_execution.errors import OrderStateError
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperOrder,
    PaperRealityContext,
    PaperRealityStatus,
)
from ditto_execution.paper.reality import ASharePaperReality
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import (
    FeeSchedule,
    InstrumentDefinition,
    MarketSnapshot,
    TradingRuleSet,
)

IID = InstrumentId(600519)
NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _order(
    *,
    side: OrderSide,
    quantity: int,
    price: float | None = None,
    trade_date: str = "2026-08-31",
) -> Order:
    return Order(
        client_id=ClientOrderId(value=f"paper-{side.value}-{quantity}"),
        instrument_id=IID,
        order_type=OrderType.MARKET if price is None else OrderType.LIMIT,
        direction=side,
        quantity=quantity,
        price=price,
        trade_date=trade_date,
    )


def _snapshot(
    *,
    close: float = 10.0,
    suspended: bool = False,
    limit_up: float | None = 11.0,
    limit_down: float | None = 9.0,
    trade_date: str = "2026-08-31",
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=trade_date,
        instrument_id=IID,
        open=9.8,
        high=max(close, 10.2),
        low=min(close, 9.7),
        close=close,
        prev_close=10.0,
        volume=1_000_000.0,
        amount=10_000_000.0,
        is_suspended=suspended,
        limit_up=limit_up,
        limit_down=limit_down,
    )


def _lineage(snapshot: MarketSnapshot | None = None) -> MarketSnapshotLineage:
    return MarketSnapshotLineage.create(
        snapshot=snapshot or _snapshot(),
        dataset_id="a-share-daily-bars",
        source="tushare",
        source_snapshot_id="tushare:20260831:600519",
        observed_at=NOW,
        publication_cutoff=NOW,
    )


def _rules(
    *,
    lot_size: int = 100,
    settlement_cycle: int = 1,
    as_of_date: str = "2026-08-31",
) -> tuple[
    InstrumentDefinition,
    TradingRuleSet,
    FeeSchedule,
]:
    return (
        InstrumentDefinition(
            instrument_id=IID,
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=0.01,
            lot_size=lot_size,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="listed",
        ),
        TradingRuleSet(
            instrument_id=IID,
            as_of_date=as_of_date,
            settlement_cycle=settlement_cycle,
            fund_settlement_cycle=0,
            price_limit_pct=0.10,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=IID,
            as_of_date=as_of_date,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        ),
    )


def _assumption(*, slippage_bps: float = 10.0) -> FillAssumption:
    return FillAssumption(
        assumption_id="paper-default-v1",
        version=1,
        reference_price_field="close",
        slippage_bps=slippage_bps,
    )


def _paper_order(order: Order) -> PaperOrder:
    return PaperOrder.create(
        session_id="session-1",
        account_id="paper-account-1",
        idempotency_key=f"idem-{order.order_id}",
        order=order,
        submitted_at=NOW,
    ).submit()


def _context(
    *,
    decision_at: datetime = NOW,
    execution_at: datetime | None = None,
    position_quantity: int = 0,
    available_quantity: int = 0,
    settlement_date: str = "2026-09-01",
) -> PaperRealityContext:
    return PaperRealityContext(
        decision_at=decision_at,
        execution_at=decision_at if execution_at is None else execution_at,
        settlement_date=settlement_date,
        position_quantity=position_quantity,
        available_quantity=available_quantity,
    )


class TestPaperOrderStateMachine:
    def test_terminal_fill_rejects_more_fills(self) -> None:
        reality = ASharePaperReality()
        paper_order = _paper_order(_order(side=OrderSide.BUY, quantity=100))
        result = reality.execute(
            paper_order=paper_order,
            lineage=_lineage(),
            rules=_rules(),
            assumption=_assumption(),
            context=_context(),
        )
        assert result.status is PaperRealityStatus.FILLED
        assert result.order.status.value == "filled"
        assert result.fill is not None

        with pytest.raises(OrderStateError):
            result.order.record_fill(result.fill)


class TestASharePaperReality:
    def test_buy_must_use_board_lots(self) -> None:
        result = ASharePaperReality().execute(
            paper_order=_paper_order(_order(side=OrderSide.BUY, quantity=101)),
            lineage=_lineage(),
            rules=_rules(),
            assumption=_assumption(),
            context=_context(),
        )
        assert result.status is PaperRealityStatus.REJECTED
        assert result.reason == "buy_quantity_not_board_lot"

    def test_t_plus_one_blocks_unsellable_quantity(self) -> None:
        result = ASharePaperReality().execute(
            paper_order=_paper_order(_order(side=OrderSide.SELL, quantity=100)),
            lineage=_lineage(),
            rules=_rules(settlement_cycle=1),
            assumption=_assumption(),
            context=_context(position_quantity=100),
        )
        assert result.status is PaperRealityStatus.DEFERRED
        assert result.reason == "t_plus1_not_sellable"

    @pytest.mark.parametrize(
        ("side", "snapshot", "reason"),
        [
            (OrderSide.BUY, _snapshot(suspended=True), "suspended"),
            (OrderSide.BUY, _snapshot(close=11.0), "limit_up_no_buy"),
            (OrderSide.SELL, _snapshot(close=9.0), "limit_down_no_sell"),
        ],
    )
    def test_market_boundaries_defer(
        self,
        side: OrderSide,
        snapshot: MarketSnapshot,
        reason: str,
    ) -> None:
        result = ASharePaperReality().execute(
            paper_order=_paper_order(_order(side=side, quantity=100)),
            lineage=_lineage(snapshot),
            rules=_rules(),
            assumption=_assumption(),
            context=_context(position_quantity=100, available_quantity=100),
        )
        assert result.status is PaperRealityStatus.DEFERRED
        assert result.reason == reason

    def test_sell_golden_cost_and_slippage(self) -> None:
        result = ASharePaperReality().execute(
            paper_order=_paper_order(_order(side=OrderSide.SELL, quantity=1000)),
            lineage=_lineage(),
            rules=_rules(),
            assumption=_assumption(slippage_bps=10.0),
            context=_context(position_quantity=1000, available_quantity=1000),
        )
        assert result.status is PaperRealityStatus.FILLED
        assert result.fill is not None
        assert result.fill.reference_price == 10.0
        assert result.fill.fill_price == pytest.approx(9.99)
        assert result.fill.slippage == pytest.approx(10.0)
        assert result.fill.commission == pytest.approx(5.0)
        assert result.fill.transfer_fee == pytest.approx(0.0999)
        assert result.fill.tax == pytest.approx(4.995)
        assert result.fill.total_cost == pytest.approx(10.0949)

    def test_odd_lot_sell_only_allowed_for_full_liquidation(self) -> None:
        reality = ASharePaperReality()
        rejected = reality.execute(
            paper_order=_paper_order(_order(side=OrderSide.SELL, quantity=1)),
            lineage=_lineage(),
            rules=_rules(),
            assumption=_assumption(),
            context=_context(position_quantity=101, available_quantity=101),
        )
        assert rejected.status is PaperRealityStatus.REJECTED
        assert rejected.reason == "sell_odd_lot_requires_full_liquidation"

        filled = reality.execute(
            paper_order=_paper_order(_order(side=OrderSide.SELL, quantity=101)),
            lineage=_lineage(),
            rules=_rules(),
            assumption=_assumption(),
            context=_context(position_quantity=101, available_quantity=101),
        )
        assert filled.status is PaperRealityStatus.FILLED


class TestFillAssumptionLineage:
    def test_hash_is_stable_for_exact_replay(self) -> None:
        first = _lineage()
        second = _lineage()
        assert first.snapshot_hash == second.snapshot_hash
        assert _assumption().assumption_hash == _assumption().assumption_hash

    def test_source_snapshot_identity_changes_lineage_hash(self) -> None:
        first = _lineage()
        second = MarketSnapshotLineage.create(
            snapshot=_snapshot(),
            dataset_id="a-share-daily-bars",
            source="tushare",
            source_snapshot_id="tushare:revision-2:20260831:600519",
            observed_at=NOW,
            publication_cutoff=NOW,
        )
        assert first.lineage_hash != second.lineage_hash

    def test_future_snapshot_after_execution_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="after execution_at"):
            ASharePaperReality().execute(
                paper_order=_paper_order(_order(side=OrderSide.BUY, quantity=100)),
                lineage=_lineage(),
                rules=_rules(),
                assumption=_assumption(),
                context=_context(decision_at=datetime(2026, 8, 31, 6, 59, tzinfo=UTC)),
            )

    @pytest.mark.pit
    def test_future_trade_date_fails_even_when_lineage_timestamps_are_visible(
        self,
    ) -> None:
        trade_date = "2026-09-01"
        with pytest.raises(ValueError, match="trade_date is after execution date"):
            ASharePaperReality().execute(
                paper_order=_paper_order(
                    _order(
                        side=OrderSide.BUY,
                        quantity=100,
                        trade_date=trade_date,
                    )
                ),
                lineage=_lineage(_snapshot(trade_date=trade_date)),
                rules=_rules(as_of_date=trade_date),
                assumption=_assumption(),
                context=_context(settlement_date="2026-09-02"),
            )

    @pytest.mark.pit
    def test_execution_snapshot_can_arrive_after_order_decision(self) -> None:
        decision_at = NOW - timedelta(minutes=2)
        execution_at = NOW + timedelta(minutes=1)

        result = ASharePaperReality().execute(
            paper_order=_paper_order(_order(side=OrderSide.BUY, quantity=100)),
            lineage=_lineage(),
            rules=_rules(),
            assumption=_assumption(),
            context=PaperRealityContext(
                decision_at=decision_at,
                execution_at=execution_at,
                settlement_date="2026-09-01",
                position_quantity=0,
                available_quantity=0,
            ),
        )

        assert result.status is PaperRealityStatus.FILLED
        assert result.fill is not None
        assert result.fill.event_time == execution_at

    def test_execution_cannot_precede_order_decision(self) -> None:
        with pytest.raises(ValueError, match="cannot precede"):
            _context(
                decision_at=NOW,
                execution_at=NOW - timedelta(microseconds=1),
            )
