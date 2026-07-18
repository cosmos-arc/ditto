"""Application-to-storage integration proof for effective-dated index weights."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_data.observability import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_data.storage.capital.specs import INDEX_COMPOSITION_SPEC
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.mark.integration
def test_index_weight_ingestion_persists_non_overlapping_pit_snapshots(
    mocker,
) -> None:
    """Write two provider snapshots and query only the effective constituents."""
    register_metrics()
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    client.execute(
        """CREATE TABLE index_weight (
            index_id TEXT NOT NULL,
            instrument_id INTEGER NOT NULL,
            weight REAL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            PRIMARY KEY (index_id, instrument_id, effective_from)
        )"""
    )
    client.commit()
    reader = IndexCompositionReader(INDEX_COMPOSITION_SPEC, client)
    writer = IndexCompositionWriter(INDEX_COMPOSITION_SPEC, client)
    capital_store = CapitalStore(
        read_ports=CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=reader,
        ),
        write_ports=CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=writer,
        ),
    )
    metadata = mocker.MagicMock()
    instrument_ids = {
        "600000.SH": 1_000_001,
        "600036.SH": 1_000_002,
        "600519.SH": 1_000_003,
    }
    metadata.instrument.resolve_instrument_ids_batch.side_effect = (
        lambda *, identifiers, **_: {
            ticker: instrument_ids[ticker] for ticker in identifiers
        }
    )
    ingestion_writer = IngestionDataWriter(
        metadata_service=metadata,
        market_write_service=mocker.MagicMock(),
        fundamental_store=mocker.MagicMock(),
        capital_store=capital_store,
        macro_service=mocker.MagicMock(),
        source_name="tushare",
    )

    try:
        first = pl.DataFrame(
            {
                "index_code": ["000300.SH", "000300.SH"],
                "source_ticker": ["600000.SH", "600036.SH"],
                "effective_from": [date(2024, 1, 3), date(2024, 1, 3)],
                "weight": [60.0, 40.0],
            }
        )
        second = pl.DataFrame(
            {
                "index_code": ["000300.SH", "000300.SH"],
                "source_ticker": ["600036.SH", "600519.SH"],
                "effective_from": [date(2024, 1, 10), date(2024, 1, 10)],
                "weight": [45.0, 55.0],
            }
        )

        assert (
            ingestion_writer.write_data(
                "index_weight", first, "2024-01-03"
            ).rows_written
            == 2
        )
        assert (
            ingestion_writer.write_data(
                "index_weight", second, "2024-01-10"
            ).rows_written
            == 2
        )

        before_rebalance = capital_store.get_index_composition(
            "000300.SH", date(2024, 1, 9)
        )
        after_rebalance = capital_store.get_index_composition(
            "000300.SH", date(2024, 1, 10)
        )
        assert dict(
            zip(
                before_rebalance["instrument_id"].to_list(),
                before_rebalance["weight"].to_list(),
                strict=True,
            )
        ) == {1_000_001: 60.0, 1_000_002: 40.0}
        assert dict(
            zip(
                after_rebalance["instrument_id"].to_list(),
                after_rebalance["weight"].to_list(),
                strict=True,
            )
        ) == {1_000_002: 45.0, 1_000_003: 55.0}
        persisted_intervals = client.fetchall(
            """SELECT effective_from, effective_to FROM index_weight
            ORDER BY effective_from, instrument_id"""
        )
        assert [row["effective_to"] for row in persisted_intervals[:2]] == [
            "2024-01-10",
            "2024-01-10",
        ]
        assert [row["effective_to"] for row in persisted_intervals[2:]] == [
            None,
            None,
        ]
    finally:
        pool.close()
