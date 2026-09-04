"""Inclusive date and immutable adjustment filters for fill storage."""

from __future__ import annotations

from ditto_execution.models import FillAdjustmentRecord, FillRecord
from ditto_execution.storage.sqlite.trade import (
    FILL_ADJUSTMENTS_DDL,
    FILLS_DDL,
    FillAdjustmentReader,
    FillAdjustmentWriter,
    FillReader,
    FillWriter,
)
from ditto_execution.storage.sqlite.trade._sql import build_where_clause
from ditto_platform.foundation import SQLiteClient


def _fill(fill_id: str, trade_date: str, *, intent_id: str) -> FillRecord:
    return FillRecord(
        fill_id=fill_id,
        intent_id=intent_id,
        strategy_id="strategy-1",
        trade_date=trade_date,
        instrument_id=600519,
        direction="buy",
        quantity=100,
        fill_price=10.0,
        fee=5.0,
        created_at=f"{trade_date}T15:00:00+08:00",
    )


def _seed(client: SQLiteClient) -> None:
    client.executescript(FILLS_DDL + FILL_ADJUSTMENTS_DDL)
    writer = FillWriter(client)
    writer.save_strict_uncommitted(_fill("fill-1", "2026-09-01", intent_id="intent-1"))
    writer.save_strict_uncommitted(_fill("fill-2", "2026-09-02", intent_id="intent-2"))
    writer.save_strict_uncommitted(_fill("fill-3", "2026-09-03", intent_id="intent-3"))
    client.commit()


def test_fill_reader_supports_closed_and_open_ended_date_ranges(
    sqlite_client: SQLiteClient,
) -> None:
    _seed(sqlite_client)
    reader = FillReader(sqlite_client)

    assert [
        item.fill_id
        for item in reader.list(
            "strategy-1",
            trade_date="2026-09-02",
            end_date="2026-09-03",
        )
    ] == ["fill-2", "fill-3"]
    assert [
        item.fill_id for item in reader.list("strategy-1", trade_date="2026-09-02")
    ] == ["fill-2"]
    assert [
        item.fill_id for item in reader.list("strategy-1", end_date="2026-09-02")
    ] == ["fill-1", "fill-2"]

    assert [
        item.fill_id
        for item in reader.list_effective(
            "strategy-1",
            trade_date="2026-09-02",
            end_date="2026-09-03",
        )
    ] == ["fill-2", "fill-3"]
    assert [
        item.fill_id
        for item in reader.list_effective(
            "strategy-1",
            trade_date="2026-09-02",
        )
    ] == ["fill-2"]
    assert [
        item.fill_id
        for item in reader.list_effective("strategy-1", end_date="2026-09-02")
    ] == ["fill-1", "fill-2"]
    assert [
        item.fill_id
        for item in reader.list_effective("strategy-1", intent_id="intent-2")
    ] == ["fill-2"]


def test_where_builder_preserves_a_start_only_inclusive_range() -> None:
    sql, params = build_where_clause(
        "SELECT * FROM execution_fills WHERE strategy_id = ?",
        "strategy-1",
        {"trade_date": ("2026-09-02", "")},
        "trade_date ASC",
    )

    assert "trade_date >= ?" in sql
    assert "trade_date <= ?" not in sql
    assert params == ["strategy-1", "2026-09-02"]


def test_adjustment_reader_can_bind_fill_and_intent_identity_together(
    sqlite_client: SQLiteClient,
) -> None:
    _seed(sqlite_client)
    adjustment = FillAdjustmentRecord(
        adjustment_id="adjustment-1",
        fill_id="fill-1",
        adjustment_type="void",
        replacement_fill_id=None,
        reason="duplicate broker event",
        created_at="2026-09-04T09:00:00+08:00",
    )
    FillAdjustmentWriter(sqlite_client).save_uncommitted(adjustment)
    sqlite_client.commit()

    result = FillAdjustmentReader(sqlite_client).list(
        "strategy-1",
        fill_id="fill-1",
        intent_id="intent-1",
    )

    assert result == [adjustment]
