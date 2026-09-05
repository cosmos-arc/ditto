"""Fail-closed validation contracts for deterministic paper execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import inf, nan

import pytest
from ditto_execution.errors import OrderStateError
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperFill,
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

_INSTRUMENT = InstrumentId(600519)
_OTHER_INSTRUMENT = InstrumentId(1)
_NOW = datetime(2026, 9, 4, 7, 0, tzinfo=UTC)
_TRADE_DATE = "2026-09-04"


def _order(
    *,
    instrument_id: InstrumentId = _INSTRUMENT,
    side: OrderSide = OrderSide.BUY,
    quantity: int = 100,
    price: float | None = None,
    trade_date: str | None = _TRADE_DATE,
) -> Order:
    return Order(
        client_id=ClientOrderId(value=f"paper-{side.value}-{quantity}"),
        instrument_id=instrument_id,
        order_type=OrderType.MARKET if price is None else OrderType.LIMIT,
        direction=side,
        quantity=quantity,
        price=price,
        trade_date=trade_date,
    )


def _snapshot(
    *,
    instrument_id: InstrumentId = _INSTRUMENT,
    trade_date: str = _TRADE_DATE,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=trade_date,
        instrument_id=instrument_id,
        open=9.8,
        high=10.2,
        low=9.7,
        close=10.0,
        prev_close=10.0,
        volume=1_000_000.0,
        amount=10_000_000.0,
        limit_up=11.0,
        limit_down=9.0,
    )


def _lineage(
    *,
    snapshot: MarketSnapshot | None = None,
    observed_at: datetime = _NOW,
    publication_cutoff: datetime = _NOW,
) -> MarketSnapshotLineage:
    return MarketSnapshotLineage.create(
        snapshot=snapshot or _snapshot(),
        dataset_id="a-share-daily-bars",
        source="tushare",
        source_snapshot_id="tushare:20260904:600519",
        observed_at=observed_at,
        publication_cutoff=publication_cutoff,
    )


def _rules(
    *,
    instrument_id: InstrumentId = _INSTRUMENT,
    as_of_date: str = _TRADE_DATE,
    settlement_cycle: int = 1,
    lot_size: int = 100,
    tick_size: float = 0.01,
) -> tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]:
    return (
        InstrumentDefinition(
            instrument_id=instrument_id,
            asset_class="stock",
            exchange="XSHG",
            currency="CNY",
            tick_size=tick_size,
            lot_size=lot_size,
            multiplier=1.0,
            board_segment="main",
            lifecycle_state="listed",
        ),
        TradingRuleSet(
            instrument_id=instrument_id,
            as_of_date=as_of_date,
            settlement_cycle=settlement_cycle,
            fund_settlement_cycle=0,
            price_limit_pct=0.1,
            order_types_supported=("market", "limit"),
            call_auction_sessions=(),
        ),
        FeeSchedule(
            instrument_id=instrument_id,
            as_of_date=as_of_date,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        ),
    )


def _paper_order(
    order: Order | None = None,
    *,
    submit: bool = True,
) -> PaperOrder:
    paper_order = PaperOrder.create(
        session_id="session-1",
        account_id="account-1",
        idempotency_key="request-1",
        order=order or _order(),
        submitted_at=_NOW,
    )
    return paper_order.submit() if submit else paper_order


def _context(
    *,
    execution_at: datetime = _NOW,
    settlement_date: str = "2026-09-05",
    position_quantity: int = 100,
    available_quantity: int = 100,
) -> PaperRealityContext:
    return PaperRealityContext(
        decision_at=_NOW,
        execution_at=execution_at,
        settlement_date=settlement_date,
        position_quantity=position_quantity,
        available_quantity=available_quantity,
    )


def _execute(
    *,
    paper_order: PaperOrder | None = None,
    lineage: MarketSnapshotLineage | None = None,
    rules: tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule] | None = None,
    context: PaperRealityContext | None = None,
    assumption: FillAssumption | None = None,
):
    return ASharePaperReality().execute(
        paper_order=paper_order or _paper_order(),
        lineage=lineage or _lineage(),
        rules=rules or _rules(),
        assumption=assumption
        or FillAssumption(
            assumption_id="paper-v1",
            version=1,
            reference_price_field="close",
            slippage_bps=0.0,
        ),
        context=context or _context(),
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"assumption_id": " "}, "assumption_id"),
        ({"version": 0}, "version"),
        ({"reference_price_field": "high"}, "reference_price_field"),
        ({"slippage_bps": -0.1}, "slippage_bps"),
        ({"slippage_bps": inf}, "slippage_bps"),
    ],
)
def test_fill_assumption_rejects_ambiguous_or_invalid_policy(
    changes: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "assumption_id": "paper-v1",
        "version": 1,
        "reference_price_field": "close",
        "slippage_bps": 0.0,
    }
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        FillAssumption(**values)


@pytest.mark.parametrize("field", ["dataset_id", "source", "source_snapshot_id"])
def test_lineage_requires_explicit_source_identity(field: str) -> None:
    values = {
        "snapshot": _snapshot(),
        "dataset_id": "a-share-daily-bars",
        "source": "tushare",
        "source_snapshot_id": "tushare:20260904:600519",
        "observed_at": _NOW,
        "publication_cutoff": _NOW,
    }
    values[field] = " "
    with pytest.raises(ValueError, match=field):
        MarketSnapshotLineage.create(**values)


def test_lineage_and_fill_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="observed_at"):
        _lineage(observed_at=_NOW.replace(tzinfo=None))

    fill = _execute().fill
    assert fill is not None
    with pytest.raises(ValueError, match="event_time"):
        replace(fill, event_time=_NOW.replace(tzinfo=None))


@pytest.mark.pit
def test_publication_visibility_has_exact_future_sentinel() -> None:
    # Exactly T is visible; the smallest representable timestamp after T is not.
    _lineage(publication_cutoff=_NOW).assert_visible_at(_NOW)
    with pytest.raises(ValueError, match="publication_cutoff"):
        _lineage(publication_cutoff=_NOW + timedelta(microseconds=1)).assert_visible_at(
            _NOW
        )


@pytest.mark.parametrize(
    ("quantity", "fill_price", "message"),
    [
        (0, 10.0, "quantity"),
        (100, 0.0, "price"),
        (100, nan, "price"),
    ],
)
def test_paper_fill_requires_positive_finite_economics(
    quantity: int,
    fill_price: float,
    message: str,
) -> None:
    fill = _execute().fill
    assert fill is not None
    with pytest.raises(ValueError, match=message):
        replace(fill, quantity=quantity, fill_price=fill_price)


@pytest.mark.parametrize("field", ["session_id", "account_id", "idempotency_key"])
def test_paper_order_requires_explicit_request_identity(field: str) -> None:
    values = {
        "session_id": "session-1",
        "account_id": "account-1",
        "idempotency_key": "request-1",
        "order": _order(),
        "submitted_at": _NOW,
    }
    values[field] = " "
    with pytest.raises(ValueError, match=field):
        PaperOrder.create(**values)


def test_paper_order_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValueError, match="quantity"):
        _paper_order(_order(quantity=0))


def test_paper_fill_must_match_order_identity() -> None:
    result = _execute()
    assert result.fill is not None
    conflicting_fill: PaperFill = replace(result.fill, account_id="other-account")
    submitted_order = _paper_order()
    with pytest.raises(OrderStateError, match="identity"):
        submitted_order.record_fill(conflicting_fill)


def test_unsubmitted_order_is_not_executable() -> None:
    with pytest.raises(ValueError, match="submitted"):
        _execute(paper_order=_paper_order(submit=False))


def test_order_requires_trade_date() -> None:
    with pytest.raises(ValueError, match="trade_date"):
        _execute(paper_order=_paper_order(_order(trade_date=None)))


@pytest.mark.parametrize(
    ("lineage", "message"),
    [
        (_lineage(snapshot=_snapshot(trade_date="2026-09-03")), "trade_date"),
        (
            _lineage(snapshot=_snapshot(instrument_id=_OTHER_INSTRUMENT)),
            "instrument",
        ),
    ],
)
def test_order_requires_exact_market_snapshot(
    lineage: MarketSnapshotLineage,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _execute(lineage=lineage)


def test_order_requires_exact_instrument_rules() -> None:
    with pytest.raises(ValueError, match="rules do not match"):
        _execute(rules=_rules(instrument_id=_OTHER_INSTRUMENT))
    with pytest.raises(ValueError, match="trade-date rules"):
        _execute(rules=_rules(as_of_date="2026-09-03"))


@pytest.mark.parametrize(
    ("context", "message"),
    [
        (_context(settlement_date="not-a-date"), "valid"),
        (_context(settlement_date="2026-09-03"), "precede"),
        (_context(settlement_date=_TRADE_DATE), "later"),
        (_context(position_quantity=-1, available_quantity=0), "non-negative"),
        (_context(position_quantity=100, available_quantity=-1), "non-negative"),
        (_context(position_quantity=100, available_quantity=101), "exceed"),
    ],
)
def test_execution_rejects_invalid_dates_or_position_state(
    context: PaperRealityContext,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _execute(context=context)


def test_sell_cannot_exceed_position() -> None:
    result = _execute(
        paper_order=_paper_order(_order(side=OrderSide.SELL)),
        context=_context(position_quantity=99, available_quantity=99),
    )
    assert result.status is PaperRealityStatus.REJECTED
    assert result.reason == "insufficient_position"


def test_invalid_lot_and_tick_rules_fail_closed() -> None:
    with pytest.raises(ValueError, match="lot_size"):
        _execute(rules=_rules(lot_size=0))
    with pytest.raises(ValueError, match="tick_size"):
        _execute(rules=_rules(tick_size=0.0))


@pytest.mark.parametrize(
    ("side", "limit_price"),
    [(OrderSide.BUY, 9.99), (OrderSide.SELL, 10.01)],
)
def test_limit_order_waits_when_simulated_price_is_not_marketable(
    side: OrderSide,
    limit_price: float,
) -> None:
    result = _execute(paper_order=_paper_order(_order(side=side, price=limit_price)))
    assert result.status is PaperRealityStatus.DEFERRED
    assert result.reason == "limit_price_not_marketable"
