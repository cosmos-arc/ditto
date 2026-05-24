"""Tests for reconciliation — diff types, reconciler logic, and ADR policy."""

from datetime import datetime

from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.reconciliation import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    reconcile,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting.fills import FillEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INST = InstrumentId(510300)
_DT = datetime(2026, 3, 1, 10, 0, 0)


def _ticket(
    order_id: str = "ord-1",
    quantity: int = 100,
    filled_quantity: int = 100,
    filled_price: float = 4.50,
    status: OrderStatus = OrderStatus.FILLED,
) -> OrderTicket:
    """Build a minimal OrderTicket for testing."""
    order = Order(
        client_id=ClientOrderId(order_id),
        instrument_id=_INST,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=quantity,
    )
    return OrderTicket(
        order=order,
        status=status,
        filled_quantity=filled_quantity,
        filled_price=filled_price,
        average_fill_price=filled_price,
    )


def _fill(
    fill_id: str = "fill-1",
    order_id: str = "ord-1",
    filled_quantity: int = 100,
    fill_price: float = 4.50,
) -> FillEvent:
    """Build a minimal FillEvent for testing."""
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=_INST,
        direction=OrderSide.BUY,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=0.0,
        slippage=0.0,
        event_time=_DT,
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


# ---------------------------------------------------------------------------
# E2B-1: ReconciliationReport backward compatibility + diff entries
# ---------------------------------------------------------------------------


class TestReconciliationReportBackwardCompat:
    """Existing construction must continue to work unchanged."""

    def test_summary_counts_without_diffs(self) -> None:
        report = ReconciliationReport(
            report_id="r-1",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected_count=3,
            actual_count=2,
            diff_count=1,
            status="mismatch",
        )
        assert report.expected_count == 3
        assert report.actual_count == 2
        assert report.diff_count == 1
        assert report.status == "mismatch"

    def test_default_diffs_is_empty_tuple(self) -> None:
        report = ReconciliationReport(
            report_id="r-2",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected_count=0,
            actual_count=0,
        )
        assert report.diffs == ()

    def test_report_accepts_typed_diffs(self) -> None:
        diff = ReconciliationDiff(
            mismatch_type=MismatchType.MISSING_FILL,
            order_id="ord-1",
        )
        report = ReconciliationReport(
            report_id="r-3",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected_count=1,
            actual_count=0,
            diff_count=1,
            diffs=(diff,),
        )
        assert len(report.diffs) == 1
        assert report.diffs[0].mismatch_type is MismatchType.MISSING_FILL


# ---------------------------------------------------------------------------
# E2B-1: ReconciliationDiff typed fields
# ---------------------------------------------------------------------------


class TestReconciliationDiff:
    def test_minimal_diff_with_required_fields(self) -> None:
        diff = ReconciliationDiff(
            mismatch_type=MismatchType.EXTRA_FILL,
            order_id="ord-x",
        )
        assert diff.mismatch_type is MismatchType.EXTRA_FILL
        assert diff.order_id == "ord-x"
        assert diff.expected_quantity is None
        assert diff.actual_quantity is None
        assert diff.expected_price is None
        assert diff.actual_price is None
        assert diff.expected_status is None
        assert diff.actual_status is None
        assert diff.fill_id is None

    def test_diff_with_all_fields(self) -> None:
        diff = ReconciliationDiff(
            mismatch_type=MismatchType.QTY_MISMATCH,
            order_id="ord-2",
            fill_id="fill-2",
            expected_quantity=100,
            actual_quantity=80,
            expected_price=4.50,
            actual_price=4.50,
            expected_status=OrderStatus.FILLED,
            actual_status=OrderStatus.PARTIALLY_FILLED,
        )
        assert diff.expected_quantity == 100
        assert diff.actual_quantity == 80
        assert diff.expected_price == 4.50
        assert diff.actual_price == 4.50
        assert diff.expected_status is OrderStatus.FILLED
        assert diff.actual_status is OrderStatus.PARTIALLY_FILLED
        assert diff.fill_id == "fill-2"


# ---------------------------------------------------------------------------
# E2B-3: MismatchType enum covers 5 types
# ---------------------------------------------------------------------------


class TestMismatchType:
    def test_all_five_mismatch_types_exist(self) -> None:
        expected = {
            "MISSING_FILL",
            "EXTRA_FILL",
            "QTY_MISMATCH",
            "PRICE_MISMATCH",
            "STATUS_MISMATCH",
        }
        actual = {m.name for m in MismatchType}
        assert actual == expected


# ---------------------------------------------------------------------------
# E2B-2: ExecutionReconciler — reconcile() function
# ---------------------------------------------------------------------------


class TestReconcilePerfectMatch:
    """When all fills match expected tickets, report should have no diffs."""

    def test_perfect_match_no_diffs(self) -> None:
        tickets = [
            _ticket("ord-1", 100, 100, 4.50),
            _ticket("ord-2", 200, 200, 3.20),
        ]
        fills = [
            _fill("fill-1", "ord-1", 100, 4.50),
            _fill("fill-2", "ord-2", 200, 3.20),
        ]
        report = reconcile(
            report_id="r-perfect",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
        )
        assert report.diffs == ()
        assert report.expected_count == 2
        assert report.actual_count == 2
        assert report.diff_count == 0
        assert report.status == "matched"


class TestReconcileMissingFill:
    """Expected ticket with no matching fill → MISSING_FILL."""

    def test_missing_fill(self) -> None:
        tickets = [_ticket("ord-1", 100, 100, 4.50)]
        fills: list[FillEvent] = []
        report = reconcile(
            report_id="r-missing",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
        )
        assert len(report.diffs) == 1
        assert report.diffs[0].mismatch_type is MismatchType.MISSING_FILL
        assert report.diffs[0].order_id == "ord-1"
        assert report.diff_count == 1
        assert report.status == "mismatch"


class TestReconcileExtraFill:
    """Fill with no matching expected ticket → EXTRA_FILL."""

    def test_extra_fill(self) -> None:
        tickets: list[OrderTicket] = []
        fills = [_fill("fill-x", "ord-x", 100, 4.50)]
        report = reconcile(
            report_id="r-extra",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
        )
        assert len(report.diffs) == 1
        assert report.diffs[0].mismatch_type is MismatchType.EXTRA_FILL
        assert report.diffs[0].order_id == "ord-x"
        assert report.diffs[0].fill_id == "fill-x"


class TestReconcileQtyMismatch:
    """Fill quantity differs from expected → QTY_MISMATCH."""

    def test_qty_mismatch(self) -> None:
        tickets = [_ticket("ord-1", 100, 100, 4.50)]
        fills = [_fill("fill-1", "ord-1", 80, 4.50)]
        report = reconcile(
            report_id="r-qty",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
        )
        assert len(report.diffs) == 1
        diff = report.diffs[0]
        assert diff.mismatch_type is MismatchType.QTY_MISMATCH
        assert diff.order_id == "ord-1"
        assert diff.expected_quantity == 100
        assert diff.actual_quantity == 80


class TestReconcilePriceMismatch:
    """Fill price differs beyond tolerance → PRICE_MISMATCH."""

    def test_price_mismatch_beyond_tolerance(self) -> None:
        tickets = [_ticket("ord-1", 100, 100, 4.50)]
        fills = [_fill("fill-1", "ord-1", 100, 4.80)]
        report = reconcile(
            report_id="r-price",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
            price_tolerance=0.01,
        )
        assert len(report.diffs) == 1
        diff = report.diffs[0]
        assert diff.mismatch_type is MismatchType.PRICE_MISMATCH
        assert diff.expected_price == 4.50
        assert diff.actual_price == 4.80

    def test_price_within_tolerance_no_diff(self) -> None:
        tickets = [_ticket("ord-1", 100, 100, 4.50)]
        # 0.005 difference — within 0.01 tolerance
        fills = [_fill("fill-1", "ord-1", 100, 4.505)]
        report = reconcile(
            report_id="r-price-ok",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
            price_tolerance=0.01,
        )
        assert report.diffs == ()


class TestReconcileStatusMismatch:
    """Expected FILLED but actual ticket is not FILLED → STATUS_MISMATCH."""

    def test_status_mismatch(self) -> None:
        ticket = _ticket("ord-1", 100, 50, 4.50, status=OrderStatus.PARTIALLY_FILLED)
        # Fill exists with partial quantity — qty already covered above,
        # but here we test that status itself is a mismatch.
        fills = [_fill("fill-1", "ord-1", 50, 4.50)]
        report = reconcile(
            report_id="r-status",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=[ticket],
            actual=fills,
        )
        status_diffs = [
            d for d in report.diffs if d.mismatch_type is MismatchType.STATUS_MISMATCH
        ]
        assert len(status_diffs) == 1
        diff = status_diffs[0]
        assert diff.expected_status is OrderStatus.FILLED
        assert diff.actual_status is OrderStatus.PARTIALLY_FILLED


class TestReconcileMultipleMismatches:
    """Mix of missing, extra, and mismatched items in one report."""

    def test_mixed_mismatches(self) -> None:
        tickets = [
            _ticket("ord-1", 100, 100, 4.50),  # matched
            _ticket("ord-2", 200, 200, 3.20),  # missing fill
        ]
        fills = [
            _fill("fill-1", "ord-1", 100, 4.50),  # matches ord-1
            _fill("fill-x", "ord-x", 50, 2.00),  # extra
        ]
        report = reconcile(
            report_id="r-mixed",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
        )
        types = {d.mismatch_type for d in report.diffs}
        assert MismatchType.MISSING_FILL in types
        assert MismatchType.EXTRA_FILL in types
        assert report.expected_count == 2
        assert report.actual_count == 2


class TestReconcileEmptyInputs:
    """Both empty → perfect match with zero counts."""

    def test_empty_both(self) -> None:
        report = reconcile(
            report_id="r-empty",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=[],
            actual=[],
        )
        assert report.diffs == ()
        assert report.expected_count == 0
        assert report.actual_count == 0
        assert report.status == "matched"


class TestReconcileDefaultPriceTolerance:
    """Default tolerance should allow reasonable slippage."""

    def test_default_tolerance_accepts_small_slippage(self) -> None:
        tickets = [_ticket("ord-1", 100, 100, 4.5000)]
        fills = [_fill("fill-1", "ord-1", 100, 4.5001)]
        report = reconcile(
            report_id="r-tol",
            account_id="acct-1",
            trade_date="2026-03-01",
            expected=tickets,
            actual=fills,
        )
        assert report.diffs == ()
