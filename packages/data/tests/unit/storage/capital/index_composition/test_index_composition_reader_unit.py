"""IndexCompositionReader 单元测试 — 观察事实 as-of 语义（#452）."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
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
def reader(in_memory_db: SQLiteClient) -> IndexCompositionReader:
    return IndexCompositionReader(INDEX_COMPOSITION_SPEC, in_memory_db)


def _observe(
    db: SQLiteClient,
    index_id: str,
    trade_date: date,
    members: list[tuple[int, float]],
) -> None:
    for instrument_id, weight in members:
        db.execute(
            "INSERT INTO index_weight (index_id, instrument_id, trade_date, weight) "
            "VALUES (?, ?, ?, ?)",
            [index_id, instrument_id, trade_date, weight],
        )
    db.commit()


def test_get_returns_latest_snapshot_at_or_before_asof(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """as-of 返回 <= as_of 的最近一次观察快照."""
    _observe(in_memory_db, "000300.SH", date(2024, 6, 28), [(1, 60.0), (2, 40.0)])
    _observe(in_memory_db, "000300.SH", date(2024, 7, 31), [(2, 50.0), (3, 50.0)])

    july_mid = reader.get("000300.SH", date(2024, 7, 15))
    assert july_mid["instrument_id"].to_list() == [1, 2]
    after_july = reader.get("000300.SH", date(2024, 8, 1))
    assert after_july["instrument_id"].to_list() == [2, 3]


def test_get_empty_table(reader: IndexCompositionReader) -> None:
    result = reader.get("000300.SH", date(2024, 1, 5))
    assert result.height == 0
    assert isinstance(result, pl.DataFrame)


def test_get_unknown_index(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    _observe(in_memory_db, "000905.SH", date(2024, 1, 2), [(1, 100.0)])
    assert reader.get("000300.SH", date(2024, 1, 5)).height == 0


def test_get_observation_day_boundary_is_inclusive(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """观察日当天即视为已可查询（半开观察轴的左端闭合）."""
    _observe(in_memory_db, "000300.SH", date(2024, 6, 28), [(1, 100.0)])
    assert reader.get("000300.SH", date(2024, 6, 28)).height == 1
    assert reader.get("000300.SH", date(2024, 6, 27)).height == 0


@pytest.mark.pit
def test_get_excludes_future_observation_sentinel(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """未来哨兵：晚于 cutoff 的观察不得泄露；cutoff 内最近观察被采用."""
    _observe(in_memory_db, "000300.SH", date(2024, 6, 28), [(1, 60.0), (2, 40.0)])
    # 哨兵观察：cutoff 之后才存在，且成员池完全不同
    _observe(in_memory_db, "000300.SH", date(2024, 12, 31), [(9, 100.0)])

    visible = reader.get("000300.SH", date(2024, 7, 15))
    assert visible["instrument_id"].to_list() == [1, 2]
    # 允许瞬间（哨兵观察日当天）哨兵快照可见
    at_sentinel = reader.get("000300.SH", date(2024, 12, 31))
    assert at_sentinel["instrument_id"].to_list() == [9]


def test_get_handles_null_weight(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    _observe(in_memory_db, "000300.SH", date(2024, 6, 28), [(1, None)])
    result = reader.get("000300.SH", date(2024, 7, 1))
    assert result.height == 1
    assert result["weight"][0] is None
