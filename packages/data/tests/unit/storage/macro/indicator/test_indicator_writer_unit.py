"""PIT revision tests for the macro indicator writer."""

from datetime import date

import polars as pl
from ditto_data.storage.macro.indicator.indicator_writer import IndicatorWriter
from ditto_platform.foundation import SQLiteClient


def _register_indicator(client: SQLiteClient) -> None:
    client.execute(
        """INSERT INTO macro_indicators
        (indicator_id, code, name, category, frequency, need_pit, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [1, "CN_CPI_YOY", "CPI同比", "prices", "monthly", True, "tushare"],
    )
    client.commit()


def _frame(*rows: tuple[date, float, date]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "indicator_id": [1 for _ in rows],
            "date": [row[0] for row in rows],
            "value": [row[1] for row in rows],
            "knowledge_date": [row[2] for row in rows],
        }
    )


def test_retrieval_snapshot_with_same_value_does_not_create_false_revision(
    sqlite_client: SQLiteClient,
) -> None:
    """A later retrieval date alone is not evidence of a provider revision."""
    _register_indicator(sqlite_client)
    writer = IndicatorWriter(sqlite_client)
    observation = date(2024, 1, 1)

    assert writer.write(_frame((observation, 2.5, date(2026, 9, 1)))) == 1
    assert writer.write(_frame((observation, 2.5, date(2026, 9, 2)))) == 0

    rows = sqlite_client.fetchall(
        """SELECT value, knowledge_date, effective_from, effective_to
        FROM macro_indicator_data ORDER BY effective_from"""
    )
    assert rows == [
        {
            "value": 2.5,
            "knowledge_date": "2026-09-01",
            "effective_from": "2026-09-01",
            "effective_to": None,
        }
    ]


def test_changed_value_creates_revision_and_closes_previous_interval(
    sqlite_client: SQLiteClient,
) -> None:
    """A changed provider value becomes a new left-closed PIT interval."""
    _register_indicator(sqlite_client)
    writer = IndicatorWriter(sqlite_client)
    observation = date(2024, 1, 1)

    writer.write(_frame((observation, 2.5, date(2026, 9, 1))))
    assert writer.write(_frame((observation, 2.6, date(2026, 9, 2)))) == 1

    rows = sqlite_client.fetchall(
        """SELECT value, effective_from, effective_to
        FROM macro_indicator_data ORDER BY effective_from"""
    )
    assert rows == [
        {
            "value": 2.5,
            "effective_from": "2026-09-01",
            "effective_to": "2026-09-02",
        },
        {
            "value": 2.6,
            "effective_from": "2026-09-02",
            "effective_to": None,
        },
    ]


def test_unsorted_vintage_batch_is_persisted_in_temporal_order(
    sqlite_client: SQLiteClient,
) -> None:
    """Provider order cannot corrupt the effective interval chain."""
    _register_indicator(sqlite_client)
    writer = IndicatorWriter(sqlite_client)
    observation = date(2024, 1, 1)

    written = writer.write(
        _frame(
            (observation, 2.6, date(2026, 9, 2)),
            (observation, 2.5, date(2026, 9, 1)),
        )
    )

    assert written == 2
    rows = sqlite_client.fetchall(
        """SELECT value, effective_from, effective_to
        FROM macro_indicator_data ORDER BY effective_from"""
    )
    assert rows == [
        {
            "value": 2.5,
            "effective_from": "2026-09-01",
            "effective_to": "2026-09-02",
        },
        {
            "value": 2.6,
            "effective_from": "2026-09-02",
            "effective_to": None,
        },
    ]


def test_exact_replay_reports_zero_written(sqlite_client: SQLiteClient) -> None:
    """The ingestion writer reports physical mutations, not attempted rows."""
    _register_indicator(sqlite_client)
    writer = IndicatorWriter(sqlite_client)
    frame = _frame((date(2024, 1, 1), 2.5, date(2026, 9, 1)))

    assert writer.write(frame) == 1
    assert writer.write(frame) == 0
