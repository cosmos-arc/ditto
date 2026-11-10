"""Recent receipts must reach the ordinary consumer without future disclosures."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

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
from ditto_data.storage.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_data.storage.fundamental.specs import INCOME_STATEMENT_SPEC
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool

pytestmark = pytest.mark.pit
_RECEIPT = datetime(2026, 11, 9, tzinfo=UTC)
_IID = InstrumentId(2_000_001)


def _provider(
    *,
    future_close: float = 999.0,
    newer: str | None = None,
    stock: bool = False,
    halted: bool = False,
    start: str = "2014-10-13",
    prior_quote: bool = True,
    etf_reference: pl.DataFrame | None = None,
    etf_share_conversions: pl.DataFrame | None = None,
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
            pl.col("trade_date").is_in(days[1:3]).alias("is_suspended")
            if halted
            else pl.lit(False).alias("is_suspended"),
            pl.lit("").alias("suspend_timing"),
            pl.lit(False).alias("is_st"),
            pl.lit("L").alias("list_status"),
        )
        frames["stock_limit"] = execution.with_columns(
            pl.lit(11.0).alias("up_limit"), pl.lit(9.0).alias("down_limit")
        )
        if halted:
            for dataset in ("stock_daily", "stock_limit"):
                frames[dataset] = frames[dataset].filter(
                    ~pl.col("trade_date").is_in(days[1:3])
                )
        if not prior_quote:
            frames["stock_daily"] = frames["stock_daily"].filter(
                pl.col("trade_date") != days[0]
            )
        frames = {
            dataset: frame.with_columns(pl.lit("000001.SZ").alias("source_ticker"))
            if "source_ticker" in frame.columns
            else frame
            for dataset, frame in frames.items()
        }
    if etf_reference is not None:
        frames["etf_reference"] = etf_reference
    if etf_share_conversions is not None:
        frames["etf_share_conversions"] = etf_share_conversions
    snapshots = []
    contents = {}
    for index, (dataset, frame) in enumerate(frames.items()):
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset,
                source="config"
                if dataset in {"etf_reference", "etf_share_conversions"}
                else "tushare",
                request_start="2026-11-09"
                if dataset in {"etf_reference", "etf_share_conversions"}
                else "2014-10-13",
                request_end="2026-11-09"
                if dataset in {"etf_reference", "etf_share_conversions"}
                else "2014-10-17",
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
        start=start,
        end="2014-10-17",
        include_fundamentals=True,
    )
    return provider, snapshots, contents


@pytest.mark.parametrize("stock", [True, False])
@pytest.mark.parametrize("covered_start", ["2014-10-16", "2014-10-13", "2014-10-01"])
def test_dividend_coverage_includes_listing_to_run_announcements(covered_start, stock):
    provider, snapshots, contents = _provider(stock=stock)
    ticker = "000001.SZ" if stock else "510300.SH"
    dataset = "dividend" if stock else "etf_dividend"
    provider.roster.append({"source_ticker": ticker, "list_date": "2014-10-01"})
    frame = pl.DataFrame(
        {
            "source_ticker": [ticker],
            "knowledge_date": [date(2014, 10, 2)],
            "implementation_date": [date(2014, 10, 10)],
            "div_proc": ["实施"],
            "record_date": [date(2014, 10, 17)],
            "ex_dividend_date": [date(2014, 10, 20)],
            "pay_date": [date(2014, 10, 21)],
            "gross_dividend_per_share": [0.1],
            "stock_dividend_ratio": [0.0],
        }
    )
    if covered_start != "2014-10-01":
        frame = frame.head(0)
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset,
            source="tushare",
            request_start=covered_start,
            request_end="2014-10-17",
            schema_version="fundamental.dividend.v3",
            checksum="d" * 32,
            canonical_asset=DataAssetRef(dataset, "fundamental"),
            request_parameters_hash="e" * 32,
            response_metadata=(),
            row_count=frame.height,
            payload_uri="dividend.parquet",
            payload_retained=True,
            created_at=_RECEIPT,
        )
    )
    snapshots.append(snapshot)
    contents[snapshot.snapshot_id] = SnapshotContents(snapshot, None, _RECEIPT, frame)
    if covered_start != "2014-10-01":
        with pytest.raises(
            AppBuilderError, match=f"incomplete retained {dataset} coverage"
        ):
            provider.freeze_cash_dividends(start="2014-10-13", end="2014-10-17")
    else:
        provider.freeze_cash_dividends(start="2014-10-13", end="2014-10-17")
        assert len(provider.cash_dividends) == 1
        assert provider.cash_dividends[0].ex_date == date(2014, 10, 20)

        assert provider.cash_dividends[0].asset_class == ("stock" if stock else "etf")


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


def test_confirmed_halts_keep_past_valuation_without_fabricating_signal_history():
    provider, _, _ = _provider(stock=True, halted=True, future_close=999.0)
    query = BarQuery(
        instruments=("000001.SZ",),
        start="2014-10-13",
        end="2014-10-16",
        with_execution_state=True,
    )
    bars = provider.get_bars(query)
    assert bars["close"].to_list() == [10.0] * 4
    assert bars["is_valuation_only"].to_list() == [False, True, True, False]
    assert bars["is_suspended"].to_list() == [False, True, True, False]
    assert bars["volume"].to_list() == [1000.0, 0.0, 0.0, 1000.0]
    marks = bars.filter(pl.col("is_valuation_only"))
    assert marks["valuation_date"].to_list() == [date(2014, 10, 13)] * 2
    assert marks["status_source_snapshot_id"].null_count() == 0
    assert marks["source_snapshot_id"].null_count() == 0
    history = provider.get_bars(
        BarQuery(
            instruments=("000001.SZ",),
            start="2014-10-13",
            end="2014-10-15",
            adj="qfq",
            asof="2014-10-16",
        )
    )
    assert history["trade_date"].cast(pl.String).to_list() == ["2014-10-13"]


def test_halt_without_a_past_valuation_cannot_take_a_future_quote():
    provider, _, _ = _provider(stock=True, halted=True, prior_quote=False)
    with pytest.raises(
        AppBuilderError, match=r"missing prior suspension valuation.*2014"
    ):
        provider.get_bars(
            BarQuery(
                instruments=("000001.SZ",),
                start="2014-10-14",
                end="2014-10-16",
                with_execution_state=True,
            )
        )


def test_long_halt_retains_frozen_quote_before_warmup_without_adding_signal_history():
    provider, _, _ = _provider(stock=True, halted=True, start="2014-10-14")
    execution = provider.get_bars(
        BarQuery(
            instruments=("000001.SZ",),
            start="2014-10-14",
            end="2014-10-15",
            with_execution_state=True,
        )
    )
    assert execution["close"].to_list() == [10.0, 10.0]
    assert execution["valuation_date"].to_list() == [date(2014, 10, 13)] * 2
    assert execution["is_valuation_only"].to_list() == [True, True]
    history = provider.get_bars(
        BarQuery(instruments=("000001.SZ",), start="2014-10-14", end="2014-10-15")
    )
    assert history.is_empty()
    assert all(row["verified"] for row in provider.sources)


@pytest.mark.parametrize("incomplete", [False, True])
def test_long_halt_search_crosses_empty_snapshot_windows_but_not_invalid_evidence(
    incomplete,
):
    _, snapshots, contents = _provider(stock=True, halted=True, prior_quote=False)
    original = next(s for s in snapshots if s.dataset_id == "stock_daily")
    current = contents[original.snapshot_id].frame
    snapshots.remove(original)
    anchor = current.head(1).with_columns(
        pl.lit(date(2014, 8, 1)).alias("trade_date"),
        pl.lit(date(2014, 8, 2)).alias("knowledge_date"),
    )
    anchor_id = ""
    for first, last, frame, checksum in [
        ("2014-10-14", "2014-10-17", current, "c" * 32),
        ("2014-08-01", "2014-08-01", anchor, "a" * 32),
    ]:
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id="stock_daily",
                source="tushare",
                request_start=first,
                request_end=last,
                schema_version=original.schema_version,
                checksum=checksum,
                canonical_asset=original.canonical_asset,
                request_parameters_hash="f" * 32,
                response_metadata=(),
                row_count=frame.height,
                payload_uri="quotes.parquet",
                payload_retained=True,
                created_at=_RECEIPT,
            )
        )
        snapshots.append(snapshot)
        contents[snapshot.snapshot_id] = SnapshotContents(
            snapshot, None, _RECEIPT, frame
        )
        anchor_id = snapshot.snapshot_id
    reader = MagicMock(spec=SnapshotReadService)
    reader.list_snapshots.side_effect = lambda **kw: tuple(
        s for s in snapshots if s.dataset_id == kw["dataset_id"]
    )

    def read(identity, **_):
        if incomplete and identity == anchor_id:
            raise ValueError("provider snapshot has no COMPLETE checkpoint")
        return contents[identity]

    reader.read.side_effect = read
    provider = FrozenHistoryProvider(reader, frozen_at=_RECEIPT)
    if incomplete:
        with pytest.raises(AppBuilderError, match="no COMPLETE checkpoint"):
            provider.freeze(
                ticker_ids={"000001.SZ": _IID},
                asset_class="stock",
                start="2014-10-14",
                end="2014-10-17",
            )
        return
    provider.freeze(
        ticker_ids={"000001.SZ": _IID},
        asset_class="stock",
        start="2014-10-14",
        end="2014-10-17",
    )
    execution = provider.get_bars(
        BarQuery(
            instruments=("000001.SZ",),
            start="2014-10-14",
            end="2014-10-15",
            with_execution_state=True,
        )
    )
    assert execution["valuation_date"].to_list() == [date(2014, 8, 1)] * 2
    assert execution["source_snapshot_id"].to_list() == [anchor_id] * 2


def test_frozen_exit_fact_rejects_quotes_on_or_after_delisting():
    """A frozen delist_date must shadow any retained post-exit quote rows."""
    provider, _, _ = _provider(stock=True)
    provider.roster.append(
        {
            "instrument_id": int(_IID),
            "list_date": "2014-01-01",
            "delist_date": "2014-10-16",
            "ticker": "000001",
            "exchange": "SZSE",
            "asset_class": "stock",
            "source_ticker": "000001.SZ",
            "effective_from": "2014-10-13",
            "effective_to": None,
        }
    )
    with pytest.raises(
        AppBuilderError,
        match=r"delisted instrument quoted after exit.*000001.SZ.*2014-10-16",
    ):
        provider.get_bars(
            BarQuery(
                instruments=("000001.SZ",),
                start="2014-10-13",
                end="2014-10-17",
                with_execution_state=True,
            )
        )


def test_frozen_etf_exit_fact_rejects_quotes_on_or_after_termination():
    """The ETF channel enforces the same conflict the stock channel does."""
    provider, _, _ = _provider()
    provider.roster.append(
        {
            "instrument_id": int(_IID),
            "list_date": "2014-01-01",
            "delist_date": "2014-10-16",
            "ticker": "510300",
            "exchange": "SSE",
            "asset_class": "etf",
            "source_ticker": "510300.SH",
            "effective_from": "2014-10-13",
            "effective_to": None,
        }
    )
    with pytest.raises(
        AppBuilderError,
        match=r"delisted instrument quoted after exit.*510300.SH.*2014-10-16",
    ):
        provider.get_bars(
            BarQuery(
                instruments=("510300.SH",),
                start="2014-10-13",
                end="2014-10-17",
            )
        )


def test_quotes_before_the_frozen_exit_fact_still_reach_both_channels():
    provider, _, _ = _provider(stock=True)
    provider.roster.append(
        {
            "instrument_id": int(_IID),
            "list_date": "2014-01-01",
            "delist_date": "2014-10-18",
            "ticker": "000001",
            "exchange": "SZSE",
            "asset_class": "stock",
            "source_ticker": "000001.SZ",
            "effective_from": "2014-10-13",
            "effective_to": None,
        }
    )
    execution = provider.get_bars(
        BarQuery(
            instruments=("000001.SZ",),
            start="2014-10-13",
            end="2014-10-17",
            with_execution_state=True,
        )
    )
    assert execution.height == 5


def test_etf_quotes_before_the_frozen_exit_fact_still_reach_both_channels():
    provider, _, _ = _provider()
    provider.roster.append(
        {
            "instrument_id": int(_IID),
            "list_date": "2014-01-01",
            "delist_date": "2014-10-18",
            "ticker": "510300",
            "exchange": "SSE",
            "asset_class": "etf",
            "source_ticker": "510300.SH",
            "effective_from": "2014-10-13",
            "effective_to": None,
        }
    )
    execution = provider.get_bars(
        BarQuery(
            instruments=("510300.SH",),
            start="2014-10-13",
            end="2014-10-17",
            with_execution_state=True,
        )
    )
    assert execution.height == 5


def test_exit_conflict_in_the_pre_window_valuation_slice_is_rejected():
    """A post-exit quote before the query start must not become an anchor."""
    provider, _, _ = _provider(stock=True)
    provider.roster.append(
        {
            "instrument_id": int(_IID),
            "list_date": "2014-01-01",
            "delist_date": "2014-10-14",
            "ticker": "000001",
            "exchange": "SZSE",
            "asset_class": "stock",
            "source_ticker": "000001.SZ",
            "effective_from": "2014-10-13",
            "effective_to": None,
        }
    )
    # Retained quotes stop on the frozen exit day; the queried window lies
    # entirely after it, so only the pre-start valuation slice can leak the
    # conflicting row into suspension anchoring.
    provider._frames["stock_daily"] = provider._frames["stock_daily"].filter(
        pl.col("trade_date") <= date(2014, 10, 14)
    )
    with pytest.raises(
        AppBuilderError,
        match=r"delisted instrument quoted after exit.*000001.SZ.*2014-10-14",
    ):
        provider.get_bars(
            BarQuery(
                instruments=("000001.SZ",),
                start="2014-10-15",
                end="2014-10-17",
                with_execution_state=True,
            )
        )


def test_etf_rule_versions_freeze_from_current_receipt_without_backdating():
    facts = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"] * 2,
            "field": ["settlement_cycle"] * 2,
            "value": ["1", "0"],
            "unit": ["days"] * 2,
            "effective_from": ["2014-01-01", "2027-01-01"],
            "effective_to": ["2027-01-01", None],
            "basis": ["synthetic old rule", "future sentinel"],
        }
    )
    provider, snapshots, contents = _provider(etf_reference=facts)
    frozen = provider.freeze_etf_reference()
    assert frozen["value"].to_list() == ["1", "0"]
    assert frozen["instrument_id"].to_list() == [int(_IID)] * 2
    reference = next(s for s in snapshots if s.dataset_id == "etf_reference")
    assert frozen["source_snapshot_id"].to_list() == [reference.snapshot_id] * 2
    assert provider.sources[-1]["received_at"] == _RECEIPT.isoformat()
    assert provider.sources[-1]["request_start"] == "2026-11-09"
    contents.clear()
    assert provider.freeze_etf_reference().equals(frozen)


def test_etf_missing_latest_reference_must_not_use_legacy_ticker_whitelist():
    provider, _, _ = _provider()
    with pytest.raises(AppBuilderError, match=r"etf_reference.*510300.SH"):
        provider.freeze_etf_reference()


@pytest.mark.parametrize("revision", ["empty", "incomplete", "future"])
def test_etf_latest_receipt_must_be_complete_without_future_or_old_fallback(revision):
    facts = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"],
            "field": ["settlement_cycle"],
            "value": ["1"],
            "unit": ["days"],
            "effective_from": ["2014-01-01"],
            "effective_to": [None],
            "basis": ["synthetic historical declaration"],
        }
    )
    provider, snapshots, contents = _provider(etf_reference=facts)
    original = snapshots[-1]
    provider.frozen_at = _RECEIPT + timedelta(seconds=1)
    timestamp = _RECEIPT + timedelta(seconds=2 if revision == "future" else 1)
    newer = replace(
        original,
        snapshot_id="f" * 64,
        checksum="e" * 32,
        created_at=timestamp,
        row_count=0,
    )
    newer = replace(newer, snapshot_id=newer.expected_snapshot_id())
    snapshots.append(newer)
    contents[newer.snapshot_id] = SnapshotContents(
        newer, original.snapshot_id, timestamp, facts.head(0)
    )
    if revision == "incomplete":
        with (
            patch.object(
                provider._reader,
                "read",
                side_effect=ValueError("no COMPLETE checkpoint"),
            ),
            pytest.raises(AppBuilderError, match="COMPLETE"),
        ):
            provider.freeze_etf_reference()
        return
    if revision == "future":
        assert provider.freeze_etf_reference()["value"].to_list() == ["1"]
    else:
        with pytest.raises(AppBuilderError, match="lacks declarations"):
            provider.freeze_etf_reference()


def _conversion_frame(**overrides: object) -> pl.DataFrame:
    row: dict[str, object] = {
        "source_ticker": "510300.SH",
        "ratio": 4.0,
        "announcement_date": "2024-06-28",
        "effective_date": "2024-07-01",
        "basis": "synthetic issuer split announcement",
        "rounding_note": "1:4 整倍拆分、无碎份",
    }
    row.update(overrides)
    return pl.DataFrame([row])


def test_share_conversions_freeze_from_retained_config_declaration():
    provider, snapshots, _ = _provider(etf_share_conversions=_conversion_frame())
    provider.freeze_share_conversions(start="2014-10-13", end="2014-10-17")
    assert provider.share_conversions == ()
    provider.freeze_share_conversions(start="2024-07-01", end="2024-07-05")
    declaration = next(s for s in snapshots if s.dataset_id == "etf_share_conversions")
    (conversion,) = provider.share_conversions
    assert conversion.instrument_id == _IID
    assert conversion.effective_date == date(2024, 7, 1)
    assert conversion.announcement_date == date(2024, 6, 28)
    assert conversion.ratio == 4.0
    assert conversion.source_snapshot_id == declaration.snapshot_id
    assert declaration.source == "config"


def test_share_conversions_out_of_window_are_not_declared_for_the_run():
    provider, _, _ = _provider(
        etf_share_conversions=pl.concat(
            [
                _conversion_frame(),
                _conversion_frame(
                    source_ticker="510300.SH",
                    announcement_date="2014-10-01",
                    effective_date="2014-10-15",
                    ratio=2.0,
                ),
            ]
        )
    )
    provider.freeze_share_conversions(start="2014-10-13", end="2014-10-17")
    assert len(provider.share_conversions) == 1
    assert provider.share_conversions[0].effective_date == date(2014, 10, 15)


def test_missing_declaration_snapshots_do_not_block_the_run():
    provider, _, _ = _provider()
    provider.freeze_share_conversions(start="2014-10-13", end="2014-10-17")
    assert provider.share_conversions == ()


def test_conflicting_share_conversion_declarations_fail_closed():
    provider, _, _ = _provider(
        etf_share_conversions=pl.concat(
            [
                _conversion_frame(),
                _conversion_frame(ratio=2.0, basis="conflicting revision"),
            ]
        )
    )
    with pytest.raises(AppBuilderError, match="conflicting conversion revision"):
        provider.freeze_share_conversions(start="2024-06-30", end="2024-07-02")


def test_future_share_conversion_declaration_receipt_is_invisible():
    provider, _, _ = _provider(etf_share_conversions=_conversion_frame())
    provider.frozen_at = _RECEIPT - timedelta(days=1)
    provider.freeze_share_conversions(start="2024-07-01", end="2024-07-05")
    assert provider.share_conversions == ()


# ---------------------------------------------------------------------------
# #765 历史财务因子按公开时间参与选股：同一冻结（代表运行）内的
# 公告门控、报告期对照、晚修订切换与未来哨兵矩阵。
# ---------------------------------------------------------------------------

_FIN_IID = InstrumentId(3_000_001)
_FIN_TICKER = "600001.SH"
# 代表运行窗口：2026-10-08..2026-11-13（交易日），knowledge_lag=1。
_RUN_START, _RUN_END = "2026-10-08", "2026-11-13"


def _financial_matrix_provider(
    income_rows: list[dict[str, object]],
    *,
    balance_rows: list[dict[str, object]] | None = None,
    end: str = _RUN_END,
    omit_financial_snapshots: bool = False,
    financial_snapshots: list[tuple[str, str, pl.DataFrame, pl.DataFrame]]
    | None = None,
) -> FrozenHistoryProvider:
    """Build one frozen stock provider around a disclosure-row matrix.

    ``financial_snapshots`` overrides the default single wide financial window
    with explicit ``(request_start, request_end, income, balance)`` snapshot
    payloads — used to reproduce the production window shapes (quarter
    backfill wide windows vs single-day pull windows).
    """
    days = [
        day
        for day in pl.date_range(
            date(2026, 9, 1), date.fromisoformat(end), eager=True
        ).to_list()
        if day.weekday() < 5
    ]
    bars = pl.DataFrame(
        {
            "source_ticker": [_FIN_TICKER] * len(days),
            "trade_date": days,
            "knowledge_date": [day + timedelta(days=1) for day in days],
            "open": [10.0] * len(days),
            "high": [10.0] * len(days),
            "low": [10.0] * len(days),
            "close": [10.0] * len(days),
            "pre_close": [10.0] * len(days),
            "volume": [1000000.0] * len(days),
            "amount": [100000.0] * len(days),
        }
    )
    if balance_rows is None:
        balance_rows = [
            {
                "source_ticker": _FIN_TICKER,
                "report_date": date(2026, 6, 30),
                "knowledge_date": date(2026, 9, 1),
                "net_assets": 100.0,
            }
        ]
    frames = {
        "stock_daily": bars,
        "adj_factor": bars.select(
            "source_ticker", "trade_date", "knowledge_date"
        ).with_columns(pl.lit(1.0).alias("adj_factor")),
        "stock_status": bars.select("source_ticker", "trade_date").with_columns(
            pl.lit(False).alias("is_suspended"),
            pl.lit("").alias("suspend_timing"),
            pl.lit(False).alias("is_st"),
            pl.lit("L").alias("list_status"),
        ),
        "stock_limit": bars.select("source_ticker", "trade_date").with_columns(
            pl.lit(11.0).alias("up_limit"), pl.lit(9.0).alias("down_limit")
        ),
        "calendar": pl.DataFrame(
            {
                "trade_date": pl.date_range(
                    date(2026, 9, 1), date(2026, 12, 31), eager=True
                )
            }
        ).with_columns(pl.col("trade_date").dt.weekday().le(5).alias("is_open")),
        "income_statement": pl.DataFrame(
            income_rows,
            schema={
                "source_ticker": pl.String,
                "report_date": pl.Date,
                "knowledge_date": pl.Date,
                "net_profit": pl.Float64,
                "revenue": pl.Float64,
                "eps": pl.Float64,
            },
        ),
        "balance_sheet": pl.DataFrame(
            balance_rows,
            schema={
                "source_ticker": pl.String,
                "report_date": pl.Date,
                "knowledge_date": pl.Date,
                "net_assets": pl.Float64,
            },
        ),
    }
    snapshots: list[ProviderSnapshot] = []
    contents: dict[str, SnapshotContents] = {}
    if omit_financial_snapshots:
        frames.pop("income_statement")
        frames.pop("balance_sheet")
    if financial_snapshots is not None:
        frames.pop("income_statement")
        frames.pop("balance_sheet")
    for index, (dataset, frame) in enumerate(frames.items()):
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset,
                source="tushare",
                request_start="2026-09-01",
                request_end=end,
                schema_version=f"{dataset}.v1",
                checksum=f"{index + 16:032x}",
                canonical_asset=DataAssetRef(dataset, "market"),
                request_parameters_hash=f"{index + 16:032x}",
                response_metadata=(),
                row_count=frame.height,
                payload_uri=f"{dataset}-financial.parquet",
                payload_retained=True,
                created_at=_RECEIPT,
            )
        )
        snapshots.append(snapshot)
        contents[snapshot.snapshot_id] = SnapshotContents(
            snapshot, None, _RECEIPT, frame
        )
    for offset, (request_start, request_end, income, balance) in enumerate(
        financial_snapshots or []
    ):
        for dataset, frame in (
            ("income_statement", income),
            ("balance_sheet", balance),
        ):
            snapshot = ProviderSnapshot.create(
                ProviderSnapshotDraft(
                    dataset_id=dataset,
                    source="tushare",
                    request_start=request_start,
                    request_end=request_end,
                    schema_version=f"{dataset}.v1",
                    checksum=f"{len(snapshots) + offset + 64:032x}",
                    canonical_asset=DataAssetRef(dataset, "market"),
                    request_parameters_hash=f"{len(snapshots) + offset + 64:032x}",
                    response_metadata=(),
                    row_count=frame.height,
                    payload_uri=f"{dataset}-{offset}-window.parquet",
                    payload_retained=True,
                    # 观察时刻随 offset 递增但都落在冻结时点之前：
                    # 晚观察快照在同披露键上胜出（frozen_at=_RECEIPT）。
                    created_at=_RECEIPT
                    - timedelta(minutes=len(financial_snapshots or []) - offset),
                )
            )
            snapshots.append(snapshot)
            contents[snapshot.snapshot_id] = SnapshotContents(
                snapshot, None, snapshot.created_at, frame
            )
    reader = MagicMock(spec=SnapshotReadService)
    reader.list_snapshots.side_effect = lambda **kw: tuple(
        s for s in snapshots if s.dataset_id == kw.get("dataset_id", s.dataset_id)
    )
    reader.read.side_effect = lambda identity, **_: contents[identity]
    provider = FrozenHistoryProvider(reader, frozen_at=_RECEIPT)
    provider.freeze(
        ticker_ids={_FIN_TICKER: _FIN_IID},
        asset_class="stock",
        start=_RUN_START,
        end=end,
        include_fundamentals=True,
    )
    return provider


def test_report_period_is_not_a_knowledge_date_within_one_run():
    """公告前不可用、公告后可用；报告期早于运行起点不能替代披露锚。"""
    provider = _financial_matrix_provider(
        [
            {
                "source_ticker": _FIN_TICKER,
                "report_date": date(2026, 6, 30),
                "knowledge_date": date(2026, 10, 13),
                "net_profit": 20.0,
                "revenue": 100.0,
                "eps": 1.0,
            }
        ]
    )
    # 报告期 2026-06-30 早已过去，但公告（披露锚）2026-10-13 尚未到达：
    # 运行内 10-13 之前的会话不可消费该报告（报告期不是可知日期）。
    before = provider.get_income_statement(int(_FIN_IID), date(2026, 10, 12))
    assert before is not None
    assert before.is_empty()
    # 公告日当天即成为当时可见版本。
    on_announcement = provider.get_income_statement(int(_FIN_IID), date(2026, 10, 13))
    assert on_announcement is not None
    assert on_announcement.height == 1
    assert on_announcement["net_profit"].to_list() == [20.0]


def test_late_revision_switches_visible_version_inside_one_run():
    """同一报告期多次披露：修订公告前后，同一运行取到不同披露版本。"""
    provider = _financial_matrix_provider(
        [
            {
                "source_ticker": _FIN_TICKER,
                "report_date": date(2026, 6, 30),
                "knowledge_date": date(2026, 10, 13),
                "net_profit": 20.0,
                "revenue": 100.0,
                "eps": 1.0,
            },
            {
                "source_ticker": _FIN_TICKER,
                "report_date": date(2026, 6, 30),
                "knowledge_date": date(2026, 10, 20),
                "net_profit": 5.0,
                "revenue": 100.0,
                "eps": 1.0,
            },
        ]
    )
    # 修订公告（10-20）前的最后一个会话仍取首披版本。
    pre_revision = provider.get_income_statement(int(_FIN_IID), date(2026, 10, 19))
    assert pre_revision is not None
    assert pre_revision["net_profit"].to_list() == [20.0]
    # 修订公告当天的会话起收敛到新披露版本。
    post_revision = provider.get_income_statement(int(_FIN_IID), date(2026, 10, 20))
    assert post_revision is not None
    assert post_revision["net_profit"].to_list() == [5.0]


def test_future_disclosure_sentinel_never_enters_any_run_session():
    """披露锚晚于运行终点的哨兵行在任何会话都不可见；内侧阳性对照可见。"""
    provider = _financial_matrix_provider(
        [
            {
                "source_ticker": _FIN_TICKER,
                "report_date": date(2026, 6, 30),
                "knowledge_date": date(2026, 10, 13),
                "net_profit": 20.0,
                "revenue": 100.0,
                "eps": 1.0,
            },
            # 未来哨兵：同一报告期的更晚披露，披露锚在运行终点之后。
            {
                "source_ticker": _FIN_TICKER,
                "report_date": date(2026, 6, 30),
                "knowledge_date": date(2026, 12, 31),
                "net_profit": 999.0,
                "revenue": 100.0,
                "eps": 1.0,
            },
        ]
    )
    for asof in (date(2026, 10, 13), date(2026, 11, 12), date(2026, 11, 13)):
        visible = provider.get_income_statement(int(_FIN_IID), asof)
        assert visible is not None
        assert visible.height == 1
        assert visible["net_profit"].to_list() == [20.0]
    # 哨兵行从未进入冻结帧：冻结网格止于运行终点。
    frozen = provider._frames["income_statement"]
    assert frozen.filter(pl.col("knowledge_date") == date(2026, 12, 31)).is_empty()


def test_cross_weekend_disclosure_in_pull_only_snapshots_enters_freeze():
    """F1 回归：单日拉取窗内的跨周末公告不得被窗 lineage 静默剔除。

    生产形态：季度回补快照是宽公告日窗，日线增量快照窗=拉取日。公告日为
    非交易日（如周六 2026-10-31 的三季报）只出现在之后的单日拉取 payload
    里——窗不覆盖该公告日格。冻结必须按披露键直接归并全部候选 payload，
    不得依赖「拉取日窗包含公告日」，否则该披露静默缺失、缺证门不触发。
    """
    h1 = {
        "source_ticker": _FIN_TICKER,
        "report_date": date(2026, 6, 30),
        "knowledge_date": date(2026, 8, 28),
        "net_profit": 100.0,
        "revenue": 1000.0,
        "eps": 1.0,
    }
    # 周六公告的 Q3 报告：只存在于周一 11-02 拉取快照 payload。
    q3 = {
        "source_ticker": _FIN_TICKER,
        "report_date": date(2026, 9, 30),
        "knowledge_date": date(2026, 10, 31),
        "net_profit": 199.0,
        "revenue": 1000.0,
        "eps": 2.0,
    }
    income_schema = {
        "source_ticker": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "net_profit": pl.Float64,
        "revenue": pl.Float64,
        "eps": pl.Float64,
    }
    balance_schema = {
        "source_ticker": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "net_assets": pl.Float64,
    }

    def _balance(rows: list[dict[str, object]]) -> pl.DataFrame:
        return pl.DataFrame(
            [
                {
                    "source_ticker": row["source_ticker"],
                    "report_date": row["report_date"],
                    "knowledge_date": row["knowledge_date"],
                    "net_assets": 1000.0,
                }
                for row in rows
            ],
            schema=balance_schema,
        )

    # 晚到拉取快照同键重发 H1（修正值 101.0）——最新观察快照胜出。
    h1_reissued = {**h1, "net_profit": 101.0}
    provider = _financial_matrix_provider(
        [],
        financial_snapshots=[
            # 8 月宽窗回补：覆盖 H1 公告日。
            (
                "2026-08-01",
                "2026-08-31",
                pl.DataFrame([h1], schema=income_schema),
                _balance([h1]),
            ),
            # 11-02 单日拉取窗：payload 含周六 10-31 公告的 Q3 与重发的 H1。
            (
                "2026-11-02",
                "2026-11-02",
                pl.DataFrame([q3, h1_reissued], schema=income_schema),
                _balance([q3, h1]),
            ),
        ],
    )
    frozen = provider._frames["income_statement"]
    # Q3 行必须进入冻结帧（当前窗 lineage 剔除 → 红）。
    q3_rows = frozen.filter(pl.col("report_date") == date(2026, 9, 30))
    assert q3_rows.height == 1
    assert q3_rows["knowledge_date"].to_list() == [date(2026, 10, 31)]
    # 同披露键跨快照去重：晚观察快照的修正值胜出。
    h1_rows = frozen.filter(pl.col("report_date") == date(2026, 6, 30))
    assert h1_rows.height == 1
    assert h1_rows["net_profit"].to_list() == [101.0]
    # 公告前 as-of 仍只看见 H1（修正后版本）。
    before = provider.get_income_statement(int(_FIN_IID), date(2026, 10, 30))
    assert before is not None
    assert before["report_date"].to_list() == [date(2026, 6, 30)]
    assert before["net_profit"].to_list() == [101.0]
    # 公告日 as-of 起消费 Q3（报告期更新即最新可见版本）。
    after = provider.get_income_statement(int(_FIN_IID), date(2026, 10, 31))
    assert after is not None
    assert after["report_date"].to_list() == [date(2026, 9, 30)]
    assert after["net_profit"].to_list() == [199.0]


def test_dirty_future_report_period_pins_lane_gates(tmp_path):
    """F2 对照：报告期晚于披露锚的脏行在两车道的既定门控（#765 留证）。

    活车道 SQLite 读取器（#628 收敛）闸门是 (knowledge_date, effective_from,
    effective_to) 版本轴，不含 report_date<=as_of；脏行（report_date 晚于
    knowledge_date）在其版本区间内可见并按 report_date 倒序居首。冻结车道
    ``_financial`` 另有 report_date<=asof 门，同一脏行被剔除——保守侧，未来
    报告期不参与历史因子。上游 ``_dedupe_fina_disclosure_key`` 去重后当前
    无可观察差异；两侧语义由此钉住，如需统一收敛另立票裁决。
    """
    dirty = {
        "source_ticker": _FIN_TICKER,
        "report_date": date(2026, 12, 31),
        "knowledge_date": date(2026, 10, 31),
        "net_profit": 777.0,
        "revenue": 1000.0,
        "eps": 7.0,
    }
    clean = {
        "source_ticker": _FIN_TICKER,
        "report_date": date(2026, 6, 30),
        "knowledge_date": date(2026, 8, 28),
        "net_profit": 100.0,
        "revenue": 1000.0,
        "eps": 1.0,
    }
    provider = _financial_matrix_provider([dirty, clean])
    frozen_visible = provider.get_income_statement(int(_FIN_IID), date(2026, 11, 6))
    assert frozen_visible is not None
    assert frozen_visible["report_date"].to_list() == [date(2026, 6, 30)]
    assert frozen_visible["net_profit"].to_list() == [100.0]

    # 活车道：同一行集写入真实 SQLite 读模型，#628 读取器无 report_date 门。
    pool = SQLitePool(str(tmp_path / "live.sqlite"))
    try:
        client = SQLiteClient(pool)
        pool.get_connection().execute(
            """CREATE TABLE IF NOT EXISTS income_statement (
            instrument_id INTEGER NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            revenue REAL,
            operating_revenue REAL,
            operating_profit REAL,
            net_profit REAL,
            eps REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )"""
        )
        insert = (
            "INSERT INTO income_statement VALUES "
            "(?, ?, ?, ?, NULL, ?, NULL, NULL, ?, ?)"
        )
        pool.get_connection().executemany(
            insert,
            [
                (
                    int(_FIN_IID),
                    row["report_date"].isoformat(),
                    row["knowledge_date"].isoformat(),
                    row["knowledge_date"].isoformat(),
                    row["revenue"],
                    row["net_profit"],
                    row["eps"],
                )
                for row in (dirty, clean)
            ],
        )
        live = IncomeStatementReader(INCOME_STATEMENT_SPEC, client).get(
            int(_FIN_IID), date(2026, 11, 6)
        )
        assert live.height == 2
        # 定序（report_date 倒序）使脏行居首——快照闭包取首行即得脏值；
        # 这是活车道既定语义，与冻结车道的剔除构成钉住的对照。
        # （SQLite DATE 列读回为 ISO 字符串。）
        assert live["report_date"].to_list() == ["2026-12-31", "2026-06-30"]
    finally:
        pool.close_all()


def _freeze_without_financial_evidence(evidence: str) -> None:
    if evidence == "empty-payload":
        # 目录有快照，但运行范围内一份披露都冻不到。
        _financial_matrix_provider([])
    else:
        # 目录里根本没有财务快照。
        _financial_matrix_provider(
            [
                {
                    "source_ticker": _FIN_TICKER,
                    "report_date": date(2026, 6, 30),
                    "knowledge_date": date(2026, 10, 13),
                    "net_profit": 20.0,
                    "revenue": 100.0,
                    "eps": 1.0,
                }
            ],
            omit_financial_snapshots=True,
        )


@pytest.mark.parametrize("evidence", ["no-snapshot", "empty-payload"])
def test_stock_history_without_financial_evidence_fails_closed(evidence):
    """股票历史冻结缺财务证据必须显式阻断，不得静默全现金运行（#765）。"""
    with pytest.raises(
        AppBuilderError, match=r"missing retained (income_statement|balance_sheet)"
    ):
        _freeze_without_financial_evidence(evidence)
