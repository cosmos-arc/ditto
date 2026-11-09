"""Recent receipts must reach the ordinary consumer without future disclosures."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.builders.frozen_history import FrozenHistoryProvider
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.fundamental_snapshot import (
    build_fundamental_snapshot_fn,
)
from ditto_backtest.data_feed import (
    FeedInputRequirements,
    ProviderBackedDataFeed,
    SnapshotProviders,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.snapshot_reader import SnapshotContents, SnapshotReadService
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.provider import BarQuery
from ditto_kernel.identity import InstrumentId

pytestmark = pytest.mark.pit
_RECEIPT = datetime(2026, 11, 9, tzinfo=UTC)
_IID = InstrumentId(2_000_001)


def _provider(
    *, future_close: float = 999.0, newer: str | None = None, stock: bool = False
):
    days = [date(2014, 10, 13) + timedelta(days=i) for i in range(5)]
    bars = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"] * 5,
            "trade_date": days,
            "knowledge_date": [day + timedelta(days=1) for day in days],
            "open": [10.0] * 5,
            "high": [11.0] * 5,
            "low": [9.0] * 5,
            "close": [10.0] * 4 + [future_close],
            "pre_close": [10.0] * 5,
            "volume": [1000.0] * 5,
            "amount": [100.0] * 5,
        }
    )
    frames = {
        "etf_daily": bars,
        "fund_adj": bars.select(
            "source_ticker", "trade_date", "knowledge_date"
        ).with_columns(pl.lit(1.0).alias("adj_factor")),
        "calendar": pl.DataFrame({"trade_date": days, "is_open": [True] * 5}),
        "income_statement": pl.DataFrame(
            {
                "source_ticker": ["510300.SH"] * 2,
                "report_date": [date(2014, 6, 30)] * 2,
                "knowledge_date": [days[0], days[-1]],
                "net_profit": [10.0, future_close],
                "revenue": [100.0, 100.0],
                "eps": [1.0, future_close],
            }
        ),
        "balance_sheet": pl.DataFrame(
            {
                "source_ticker": ["510300.SH"],
                "report_date": [date(2014, 6, 30)],
                "knowledge_date": [days[0]],
                "net_assets": [100.0],
            }
        ),
    }
    if stock:
        frames["stock_daily"] = frames.pop("etf_daily")
        frames["adj_factor"] = frames.pop("fund_adj")
        execution = bars.select("source_ticker", "trade_date")
        frames["stock_status"] = execution.with_columns(
            pl.lit(False).alias("is_suspended"),
            pl.lit(False).alias("is_st"),
            pl.lit("L").alias("list_status"),
        )
        frames["stock_limit"] = execution.with_columns(
            pl.lit(11.0).alias("up_limit"), pl.lit(9.0).alias("down_limit")
        )
        frames = {
            dataset: frame.with_columns(pl.lit("000001.SZ").alias("source_ticker"))
            if "source_ticker" in frame.columns
            else frame
            for dataset, frame in frames.items()
        }
    snapshots = []
    contents = {}
    for index, (dataset, frame) in enumerate(frames.items()):
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset,
                source="tushare",
                request_start="2014-10-13",
                request_end="2014-10-17",
                schema_version=f"{dataset}.v1",
                checksum=f"{index:032x}",
                canonical_asset=DataAssetRef(dataset, "market"),
                request_parameters_hash="f" * 32,
                response_metadata=(),
                row_count=frame.height,
                payload_uri=f"{dataset}.parquet",
                payload_retained=True,
                created_at=_RECEIPT,
            )
        )
        snapshots.append(snapshot)
        contents[snapshot.snapshot_id] = SnapshotContents(
            snapshot, None, _RECEIPT, frame
        )
    if newer:
        original = snapshots[0]
        # A newer request with different bytes must shadow, not fill from old data.
        draft = ProviderSnapshotDraft(
            dataset_id=original.dataset_id,
            source=original.source,
            request_start=original.request_start,
            request_end=original.request_end,
            schema_version=original.schema_version,
            checksum="e" * 32,
            canonical_asset=original.canonical_asset,
            request_parameters_hash=original.request_parameters_hash,
            response_metadata=(),
            row_count=0,
            payload_uri="empty.parquet",
            payload_retained=True,
            created_at=_RECEIPT + timedelta(seconds=1),
        )
        revision = ProviderSnapshot.create(draft)
        snapshots.append(revision)
        contents[revision.snapshot_id] = SnapshotContents(
            revision, original.snapshot_id, revision.created_at, bars.head(0)
        )
    reader = MagicMock(spec=SnapshotReadService)
    reader.list_snapshots.side_effect = lambda **kw: tuple(
        s for s in snapshots if s.dataset_id == kw.get("dataset_id", s.dataset_id)
    )

    def read(identity, **_):
        if newer == "incomplete" and identity == snapshots[-1].snapshot_id:
            raise ValueError("provider snapshot has no COMPLETE checkpoint")
        return contents[identity]

    reader.read.side_effect = read
    provider = FrozenHistoryProvider(
        reader, frozen_at=_RECEIPT + timedelta(seconds=1) if newer else _RECEIPT
    )
    provider.freeze(
        ticker_ids={"000001.SZ" if stock else "510300.SH": _IID},
        asset_class="stock" if stock else "etf",
        start="2014-10-13",
        end="2014-10-17",
        include_fundamentals=True,
    )
    return provider, snapshots, contents


def test_ordinary_history_reads_2014_with_2026_receipt_and_excludes_future():
    provider, snapshots, _ = _provider()
    feed = ProviderBackedDataFeed(
        provider,
        tickers=("510300.SH",),
        start_date="2014-10-13",
        end_date="2014-10-17",
        id_map={"510300.SH": _IID},
        snapshot_providers=SnapshotProviders(
            fundamental=build_fundamental_snapshot_fn(
                provider, allow_experimental_data=False
            ),
            require_source_snapshot_lineage=True,
            requirements=FeedInputRequirements(start_date="2014-10-16", warmup_days=1),
        ),
    )
    feed.validate_inputs()
    history = feed.get_history([_IID], "2014-10-16", 2)
    assert history["close"].to_list() == [10.0, 10.0]
    fundamentals = feed.get_fundamental_snapshot([_IID], date(2014, 10, 16))
    assert fundamentals["eps"].to_list() == [1.0]
    assert feed.get_fundamental_snapshot([_IID], date(2014, 10, 17))[
        "eps"
    ].to_list() == [999.0]
    assert all(s.created_at == _RECEIPT for s in snapshots)
    assert provider.sources
    assert all(s["received_at"] == _RECEIPT.isoformat() for s in provider.sources)


def test_frozen_history_does_not_reread_after_source_revision():
    provider, _, contents = _provider()
    before = provider.get_income_statement(int(_IID), date(2014, 10, 16))
    contents.clear()
    after = provider.get_income_statement(int(_IID), date(2014, 10, 16))
    assert before is not None
    assert after is not None
    assert before.equals(after)


@pytest.mark.parametrize("newer", ["empty", "incomplete"])
def test_newer_missing_evidence_never_falls_back_to_older_prices(newer):
    if newer == "incomplete":
        with pytest.raises(AppBuilderError, match="COMPLETE"):
            _provider(newer=newer)
    else:
        provider, _, _ = _provider(newer=newer)
        assert provider.get_bars(
            BarQuery(
                instruments=("510300.SH",),
                start="2014-10-13",
                end="2014-10-17",
                frequency="daily",
                adj="none",
            )
        ).is_empty()


def test_warmup_expands_calendar_until_actual_sessions_exist():
    days = pl.date_range(date(2014, 8, 1), date(2014, 10, 17), eager=True)
    calendar = pl.DataFrame({"trade_date": days}).with_columns(
        pl.col("trade_date")
        .is_in(
            [date(2014, 8, 1), date(2014, 9, 1), date(2014, 10, 1), date(2014, 10, 16)]
        )
        .alias("is_open")
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="calendar",
            source="tushare",
            request_start="2014-08-01",
            request_end="2014-10-17",
            schema_version="calendar.v1",
            checksum="1" * 32,
            canonical_asset=DataAssetRef("calendar", "market"),
            request_parameters_hash="2" * 32,
            response_metadata=(),
            row_count=calendar.height,
            payload_uri="calendar.parquet",
            payload_retained=True,
            created_at=_RECEIPT,
        )
    )
    reader = MagicMock(spec=SnapshotReadService)
    reader.list_snapshots.return_value = (snapshot,)
    reader.read.return_value = SnapshotContents(snapshot, None, _RECEIPT, calendar)
    provider = FrozenHistoryProvider(reader, frozen_at=_RECEIPT)
    assert (
        provider.prepare_calendar(start="2014-10-16", end="2014-10-17", warmup=3, lag=0)
        == "2014-08-01"
    )
    assert len(provider.sources) == 1
    assert provider.sources[0]["received_at"] == _RECEIPT.isoformat()


def test_actual_stock_execution_schema_does_not_require_invented_knowledge_dates():
    provider, _, _ = _provider(stock=True)
    bars = provider.get_bars(
        BarQuery(
            instruments=("000001.SZ",),
            start="2014-10-13",
            end="2014-10-16",
            with_execution_state=True,
        )
    )
    assert bars.height == 4
    assert bars["limit_up"].to_list() == [11.0] * 4
    assert bars["is_st"].to_list() == [False] * 4
    assert bars["status_source_snapshot_id"].null_count() == 0
    assert bars["limit_source_snapshot_id"].null_count() == 0
