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
from ditto_kernel.identity import InstrumentId

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
