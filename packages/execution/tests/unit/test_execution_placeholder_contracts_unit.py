"""Tests for minimal execution capability contracts."""

import inspect
from typing import Protocol, get_args, get_origin

from ditto_execution.fills.store import FillStore
from ditto_execution.models import FillRecord
from ditto_execution.orders.store import OrderRecord, OrderStore
from ditto_execution.reconciliation import ReconciliationReport


def test_order_store_contract_is_actionable() -> None:
    assert issubclass(OrderStore, Protocol)
    assert hasattr(OrderStore, "save_order")
    assert hasattr(OrderStore, "get_order")
    assert hasattr(OrderStore, "list_orders")


def test_order_record_captures_order_identity_and_trade_date() -> None:
    record = OrderRecord(
        order_id="ord-1",
        strategy_id="trend",
        trade_date="2026-05-05",
        instrument_id=510300,
        side="buy",
        quantity=100,
    )

    assert record.order_id == "ord-1"
    assert record.trade_date == "2026-05-05"
    assert record.status == "pending"


def test_order_store_uses_order_record_annotations() -> None:
    save_annotations = inspect.get_annotations(OrderStore.save_order, eval_str=True)
    get_annotations = inspect.get_annotations(OrderStore.get_order, eval_str=True)
    list_annotations = inspect.get_annotations(OrderStore.list_orders, eval_str=True)

    assert save_annotations["record"] == OrderRecord
    assert get_annotations["order_id"] is str
    assert get_annotations["return"] == OrderRecord | None
    assert list_annotations["strategy_id"] is str
    assert list_annotations["trade_date"] == str | None
    assert get_origin(list_annotations["return"]) is list
    assert get_args(list_annotations["return"]) == (OrderRecord,)


def test_fill_store_contract_is_actionable() -> None:
    assert issubclass(FillStore, Protocol)
    assert hasattr(FillStore, "save_fill")
    assert hasattr(FillStore, "get_fill")
    assert hasattr(FillStore, "list_fills")


def test_fill_store_uses_existing_fill_record() -> None:
    annotations = inspect.get_annotations(FillStore.save_fill, eval_str=True)

    assert annotations["record"] == FillRecord


def test_reconciliation_report_captures_summary_counts() -> None:
    report = ReconciliationReport(
        report_id="recon-1",
        account_id="acct-1",
        trade_date="2026-05-05",
        expected_count=3,
        actual_count=2,
        diff_count=1,
    )

    assert report.diff_count == 1
    assert report.status == "pending"
