"""Round-trip tests for provider-native global index bars."""

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest
from ditto_data.storage.market.index.global_bars import (
    GlobalIndexBarsReader,
    GlobalIndexBarsWriter,
)
from ditto_platform.foundation import ParquetStore


def _global_store(root: Path) -> ParquetStore:
    return ParquetStore(
        root,
        key_columns=("source_ticker", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="source_ticker",
    )


@pytest.mark.unit
def test_global_index_round_trip_preserves_market_and_knowledge_time(
    tmp_path: Path,
) -> None:
    """Provider identity and both revisions survive a storage round trip."""
    store = _global_store(tmp_path)
    writer = GlobalIndexBarsWriter(store)
    reader = GlobalIndexBarsReader(store)
    frame = pl.DataFrame(
        {
            "source_ticker": ["SPX", "SPX"],
            "trade_date": [date(2024, 3, 28), date(2024, 3, 28)],
            "event_time": [
                datetime(2024, 3, 28, 20, tzinfo=UTC),
                datetime(2024, 3, 28, 20, tzinfo=UTC),
            ],
            "published_at": [
                datetime(2026, 9, 1, 2, tzinfo=UTC),
                datetime(2026, 9, 2, 2, tzinfo=UTC),
            ],
            "available_at": [
                datetime(2026, 9, 1, 2, tzinfo=UTC),
                datetime(2026, 9, 2, 2, tzinfo=UTC),
            ],
            "knowledge_date": [date(2026, 9, 1), date(2026, 9, 2)],
            "timezone": ["America/New_York", "America/New_York"],
            "currency": ["USD", "USD"],
            "close": [5_254.35, 5_254.36],
        }
    )

    result = writer.write(frame, year=2024)
    restored = reader.read(start_date="2024-03-28", end_date="2024-03-28")

    assert result.added == 2
    assert restored.height == 2
    assert restored.get_column("source_ticker").unique().to_list() == ["SPX"]
    assert restored.get_column("knowledge_date").sort().to_list() == [
        date(2026, 9, 1),
        date(2026, 9, 2),
    ]
    assert restored.get_column("event_time").unique().to_list() == [
        datetime(2024, 3, 28, 20, tzinfo=UTC)
    ]
