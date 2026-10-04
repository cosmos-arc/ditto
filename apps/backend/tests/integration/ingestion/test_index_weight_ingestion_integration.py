"""Application-to-storage integration proof for index weight observations."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_data.observability import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter
from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.specs import INDEX_COMPOSITION_SPEC
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.mark.integration
def test_index_weight_ingestion_persists_observation_facts(mocker) -> None:
    """Write two monthly observations; as-of resolves the latest observed pool."""
    register_metrics()
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    client.execute(
        """CREATE TABLE index_weight (
            index_id TEXT NOT NULL,
            instrument_id INTEGER NOT NULL,
            trade_date DATE NOT NULL,
            weight REAL,
            PRIMARY KEY (index_id, instrument_id, trade_date)
        )"""
    )
    client.commit()
    reader = IndexCompositionReader(INDEX_COMPOSITION_SPEC, client)
    writer = SqliteTableWriter(INDEX_COMPOSITION_SPEC, client)
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
                "trade_date": [date(2024, 1, 3), date(2024, 1, 3)],
                "weight": [60.0, 40.0],
            }
        )
        second = pl.DataFrame(
            {
                "index_code": ["000300.SH", "000300.SH"],
                "source_ticker": ["600036.SH", "600519.SH"],
                "trade_date": [date(2024, 1, 10), date(2024, 1, 10)],
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
        # 两次观察都原样保留：不伪造 effective_to，观察日是唯一时间轴
        persisted = client.fetchall(
            """SELECT trade_date, instrument_id, weight FROM index_weight
            ORDER BY trade_date, instrument_id"""
        )
        assert [(row["trade_date"], row["instrument_id"]) for row in persisted] == [
            ("2024-01-03", 1_000_001),
            ("2024-01-03", 1_000_002),
            ("2024-01-10", 1_000_002),
            ("2024-01-10", 1_000_003),
        ]
    finally:
        pool.close()
