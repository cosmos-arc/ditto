"""index_weight 观察事实写入测试（#452）.

写入 = 追加观察行：不回填改写历史、不维护 effective 区间。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter
from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.specs import INDEX_COMPOSITION_SPEC
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """按 #452 观察事实契约建表."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    client.execute(
        """CREATE TABLE IF NOT EXISTS index_weight (
        index_id TEXT NOT NULL,
        instrument_id INTEGER NOT NULL,
        trade_date DATE NOT NULL,
        weight REAL,
        PRIMARY KEY (index_id, instrument_id, trade_date)
    )"""
    )
    client.commit()
    return client


@pytest.fixture
def writer(in_memory_db: SQLiteClient) -> SqliteTableWriter:
    return SqliteTableWriter(INDEX_COMPOSITION_SPEC, in_memory_db)


@pytest.fixture
def reader(in_memory_db: SQLiteClient) -> IndexCompositionReader:
    return IndexCompositionReader(INDEX_COMPOSITION_SPEC, in_memory_db)


def test_write_appends_observation_rows(writer: SqliteTableWriter) -> None:
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH", "000300.SH"],
            "instrument_id": [1, 2],
            "trade_date": [date(2024, 6, 28), date(2024, 6, 28)],
            "weight": [60.0, 40.0],
        }
    )
    assert writer.write(df) == 2


def test_write_empty_dataframe(writer: SqliteTableWriter) -> None:
    df = pl.DataFrame(
        schema={
            "index_id": pl.String,
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "weight": pl.Float64,
        }
    )
    assert writer.write(df) == 0


def test_write_conflict_does_nothing(
    writer: SqliteTableWriter, in_memory_db: SQLiteClient
) -> None:
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": [1],
            "trade_date": [date(2024, 6, 28)],
            "weight": [100.0],
        }
    )
    writer.write(df)
    writer.write(df)
    rows = in_memory_db.fetchall("SELECT * FROM index_weight")
    assert len(rows) == 1


def test_write_failure_rollback() -> None:
    mock_client = Mock(spec=SQLiteClient)
    mock_client.executemany.side_effect = RuntimeError("Database error")
    mock_client.commit = Mock()
    mock_client.rollback = Mock()
    writer = SqliteTableWriter(INDEX_COMPOSITION_SPEC, mock_client)

    df = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": [1],
            "trade_date": [date(2024, 6, 28)],
            "weight": [100.0],
        }
    )
    with pytest.raises(RuntimeError, match="Database error"):
        writer.write(df)
    mock_client.rollback.assert_called_once()


def test_rebalance_does_not_rewrite_prior_observation(
    writer: SqliteTableWriter,
    reader: IndexCompositionReader,
    in_memory_db: SQLiteClient,
) -> None:
    """#452 验收：换仓后，历史观察不被新池改写，观察日保留原字段."""
    june = pl.DataFrame(
        {
            "index_id": ["000300.SH", "000300.SH"],
            "instrument_id": [1, 2],
            "trade_date": [date(2024, 6, 28), date(2024, 6, 28)],
            "weight": [60.0, 40.0],
        }
    )
    # 7 月换仓：成分 1 剔除，成分 3 纳入
    july = pl.DataFrame(
        {
            "index_id": ["000300.SH", "000300.SH"],
            "instrument_id": [2, 3],
            "trade_date": [date(2024, 7, 31), date(2024, 7, 31)],
            "weight": [50.0, 50.0],
        }
    )
    writer.write(june)
    writer.write(july)

    june_rows = in_memory_db.fetchall(
        "SELECT instrument_id, trade_date, weight FROM index_weight "
        "WHERE index_id = ? AND trade_date = ? ORDER BY instrument_id",
        ["000300.SH", date(2024, 6, 28)],
    )
    assert [(row["instrument_id"], row["weight"]) for row in june_rows] == [
        (1, 60.0),
        (2, 40.0),
    ]

    # 7 月中旬 as-of：仍是 6 月观察池（无未来泄露）
    assert reader.get("000300.SH", date(2024, 7, 15))["instrument_id"].to_list() == [
        1,
        2,
    ]
    # 8 月 as-of：7 月池
    assert reader.get("000300.SH", date(2024, 8, 1))["instrument_id"].to_list() == [
        2,
        3,
    ]

    # 当前池回填（重写 7 月观察）不得触碰 6 月行
    writer.write(july)
    june_after = in_memory_db.fetchall(
        "SELECT instrument_id, trade_date, weight FROM index_weight "
        "WHERE index_id = ? AND trade_date = ? ORDER BY instrument_id",
        ["000300.SH", date(2024, 6, 28)],
    )
    assert june_after == june_rows


def test_out_of_order_backfill_keeps_both_observations(
    writer: SqliteTableWriter,
    reader: IndexCompositionReader,
) -> None:
    """晚写早观察不互相覆盖：两个观察日并存，as-of 各取所属快照."""
    later = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": [3],
            "trade_date": [date(2024, 7, 31)],
            "weight": [100.0],
        }
    )
    earlier = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": [1],
            "trade_date": [date(2024, 6, 28)],
            "weight": [100.0],
        }
    )
    writer.write(later)
    writer.write(earlier)

    assert reader.get("000300.SH", date(2024, 7, 15))["instrument_id"].to_list() == [1]
    assert reader.get("000300.SH", date(2024, 8, 1))["instrument_id"].to_list() == [3]
