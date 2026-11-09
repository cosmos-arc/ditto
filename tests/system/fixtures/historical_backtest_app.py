"""Ordinary historical request over synthetic 2014 facts retained now.

Production app, API, snapshot verifier, catalog builder and engine are unchanged.
Only this isolated fixture can install the missing adjustment payload.
"""

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.sources.reference_config import EtfReferenceConfigSource
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter
from ditto_platform.foundation import DataCache, SQLiteClient, SQLitePool

from tests.system.fixtures.backtest_nav_app import app

_state = Path(os.environ["DITTO_STATE_ROOT"])
if os.environ.get(
    "DITTO_ENVIRONMENT"
) != "testing" or not _state.resolve().is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("historical fixture requires isolated testing state")


def retain_history_payload(
    dataset: str,
    frame: pl.DataFrame,
    *,
    period: tuple[str, str] = ("2014-01-01", "2014-12-31"),
    source: str = "tushare",
) -> None:
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    try:
        now = datetime.now(UTC)
        payload = FilesystemProviderPayloadStore(_state).retain_payload(
            dataset_id=dataset, source=source, payload=frame
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset,
                source=source,
                request_start=period[0],
                request_end=period[1],
                schema_version=f"synthetic.{dataset}.v1",
                checksum=payload.checksum,
                canonical_asset=DataAssetRef(dataset, "market"),
                request_parameters_hash=f"synthetic:{dataset}",
                response_metadata=(("fixture", "synthetic-2014-received-now"),),
                row_count=frame.height,
                payload_uri=payload.uri,
                payload_retained=True,
                created_at=now,
                schema_fingerprint=payload.schema_fingerprint,
            )
        )
        snapshots = SQLiteProviderSnapshotStore(client)
        if snapshots.get_snapshot(snapshot.snapshot_id) is not None:
            return
        snapshots.append_snapshot(snapshot)
        lifecycle = SQLitePartitionLifecycleStore(client)
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=snapshot.snapshot_id,
                dataset_id=dataset,
                source=source,
                request_start=period[0],
                request_end=period[1],
                status=PartitionLifecycleStatus.PLANNED,
                payload_id=None,
                complete_evidence_id=None,
                error_code=None,
                updated_at=now,
            )
        )
        lifecycle.advance_partition(
            snapshot.snapshot_id,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            occurred_at=now,
            evidence_id=f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}",
        )
        lifecycle.advance_partition(
            snapshot.snapshot_id,
            PartitionLifecycleStatus.COMPLETE,
            occurred_at=now,
            evidence_id=snapshot.snapshot_id,
        )
    finally:
        pool.close_all()


def retain_empty_dividends(period: tuple[str, str]) -> None:
    """Declare a completed empty announcement response for a synthetic window."""
    retain_history_payload(
        "dividend",
        pl.DataFrame(
            schema={
                "source_ticker": pl.String,
                "knowledge_date": pl.Date,
                "div_proc": pl.String,
                "record_date": pl.Date,
                "ex_dividend_date": pl.Date,
                "pay_date": pl.Date,
                "implementation_date": pl.Date,
                "gross_dividend_per_share": pl.Float64,
                "stock_dividend_ratio": pl.Float64,
            }
        ),
        period=("1990-01-01", period[1]),
    )


def _daily(tickers: tuple[str, ...]) -> pl.DataFrame:
    days = pl.date_range(date(2014, 1, 1), date(2014, 12, 31), eager=True)
    dates = [day for day in days if day.weekday() < 5]
    return pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "trade_date": day,
                "knowledge_date": day + timedelta(days=1),
                "open": 4.0 + i * 0.001,
                "high": 4.05 + i * 0.001,
                "low": 3.95 + i * 0.001,
                "close": 4.01 + i * 0.001,
                "pre_close": 4.009 + i * 0.001,
                "volume": 10000000.0,
                "amount": 4000000.0,
            }
            for ticker in tickers
            for i, day in enumerate(dates)
            if ticker != "510050.SH" or day >= date(2014, 10, 14)
        ]
    )


def _seed_history() -> None:
    today = datetime.now(UTC).date().isoformat()
    retain_history_payload(
        "etf_reference",
        EtfReferenceConfigSource(
            Path(__file__).resolve().parents[3] / "config/default/etf_reference.json"
        ).fetch_etf_reference(),
        period=(today, today),
        source="config",
    )
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    try:
        InstrumentWriter(client=client, cache=None).register(
            3_000_001,
            InstrumentRegistration(
                source_ticker="000300.SH",
                ticker="000300",
                name="沪深300-历史验收",
                exchange="SSE",
                asset_class="index",
                list_date="2005-04-08",
            ),
        )
        InstrumentWriter(client=client, cache=None).register(
            2_001_004,
            InstrumentRegistration(
                source_ticker="510050.SH",
                ticker="510050",
                name="晚上市-固定样例",
                exchange="SSE",
                asset_class="etf",
                list_date="2014-10-14",
            ),
        )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe(
            "csi_etf_broad",
            "历史请求验收池",
            description="Synthetic fixed pool; no historical membership certification",
        )
        universe.add_constituents(
            "csi_etf_broad",
            [
                {
                    "instrument_id": 2_001_001,
                    "effective_from": "2014-01-01",
                    "source": "synthetic",
                },
                {
                    "instrument_id": 2_001_002,
                    "effective_from": "2014-01-01",
                    "effective_to": "2014-10-20",
                    "source": "synthetic",
                },
                {
                    "instrument_id": 2_001_002,
                    "effective_from": "2014-11-03",
                    "source": "synthetic",
                },
                {
                    "instrument_id": 2_001_004,
                    "effective_from": "2014-01-01",
                    "source": "synthetic",
                },
            ],
        )
    finally:
        pool.close_all()
    retain_history_payload("etf_daily", _daily(("510300.SH", "510500.SH", "510050.SH")))
    retain_history_payload("index_daily", _daily(("000300.SH",)))
    dates = pl.date_range(date(2014, 1, 1), date(2014, 12, 31), eager=True)
    retain_history_payload(
        "calendar",
        pl.DataFrame({"trade_date": dates, "is_open": dates.dt.weekday() <= 5}),
    )


_seed_history()


@app.post("/system-fixture/history/repair")
def repair() -> dict[str, bool]:
    """Install the missing synthetic input only in this isolated fixture."""
    frame = _daily(("510300.SH", "510500.SH", "510050.SH")).select(
        "source_ticker", "trade_date", "knowledge_date"
    )
    retain_history_payload(
        "fund_adj", frame.with_columns(pl.lit(1.0).alias("adj_factor"))
    )
    return {"repaired": True}
