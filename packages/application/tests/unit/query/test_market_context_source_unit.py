"""Immutable-payload market-context source tests."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market_context import MarketContextFacts
from ditto_application.queries.market_context_source import (
    ProviderPayloadMarketContextSource,
)
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    ProviderPayloadArtifact,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext


class _SnapshotReader:
    def __init__(self, values: tuple[ProviderSnapshot, ...]) -> None:
        self._values = {value.snapshot_id: value for value in values}

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._values.get(snapshot_id)

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(
            value
            for value in self._values.values()
            if (dataset_id is None or value.dataset_id == dataset_id)
            and (source is None or value.source == source)
            and (canonical_asset is None or value.canonical_asset == canonical_asset)
        )


def _snapshot(
    *,
    dataset_id: str,
    frame: pl.DataFrame,
    store: FilesystemProviderPayloadStore,
    created_at: datetime,
) -> ProviderSnapshot:
    artifact = store.retain_payload(
        dataset_id=dataset_id,
        source="tushare",
        payload=frame,
    )
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source="tushare",
            request_start="2026-08-01",
            request_end="2026-08-31",
            schema_version=f"market.{dataset_id}.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(
                dataset_id=dataset_id,
                namespace="market",
                partition_keys=("month=2026-08",),
            ),
            request_parameters_hash="sha256:test-request",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id=f"license:tushare:{dataset_id}:test",
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=created_at,
        )
    )


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_excludes_future_rows_and_computes_core_facts(
    tmp_path: Path,
) -> None:
    timezone = UTC
    cutoff = datetime(2026, 8, 31, 8, 0, tzinfo=timezone)
    stock = pl.DataFrame(
        {
            "source_ticker": ["000001.SZ", "000002.SZ", "000003.SZ", "000001.SZ"],
            "event_time": [
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff + timedelta(days=1),
            ],
            "published_at": [
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff + timedelta(days=1),
            ],
            "available_at": [
                cutoff - timedelta(minutes=30),
                cutoff - timedelta(minutes=30),
                cutoff - timedelta(minutes=30),
                cutoff + timedelta(days=1),
            ],
            "pct_chg": [1.0, -0.5, 0.0, -99.0],
            "close": [10.0, 20.0, 30.0, 0.1],
        }
    )
    index_times = [cutoff - timedelta(days=20 - index) for index in range(21)]
    index = pl.DataFrame(
        {
            "source_ticker": ["000300.SH"] * 21,
            "event_time": index_times,
            "published_at": index_times,
            "available_at": index_times,
            "close": [100.0 + index for index in range(21)],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshots = (
        _snapshot(
            dataset_id="stock_daily",
            frame=stock,
            store=store,
            created_at=cutoff - timedelta(minutes=15),
        ),
        _snapshot(
            dataset_id="index_daily",
            frame=index,
            store=store,
            created_at=cutoff - timedelta(minutes=15),
        ),
    )
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=tuple(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            )
            for snapshot in snapshots
        ),
    )
    source = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader(snapshots),
        payload_reader=store,
    )

    facts = source.load(context)

    assert facts.regime_input.advancing_count == 1
    assert facts.regime_input.declining_count == 1
    assert facts.regime_input.universe_count == 3
    assert facts.regime_input.benchmark_return_20d == pytest.approx(0.20)
    assert facts.regime_input.realized_volatility_20d is not None
    assert facts.regime_input.realized_volatility_20d >= 0
    assert "market_context_source_unavailable" not in facts.uncertainties


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_normalizes_provider_dates_before_utc_cutoff(
    tmp_path: Path,
) -> None:
    """Provider-local date strings must compare by instant against UTC cutoffs."""
    cutoff = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    stock = pl.DataFrame(
        {
            "source_ticker": ["000001.SZ", "000002.SZ"],
            "trade_date": ["2026-08-31", "2026-08-31"],
            "knowledge_date": ["2026-08-31", "2026-08-31"],
            "pct_chg": [1.0, -0.5],
            "close": [10.0, 20.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(
        dataset_id="stock_daily",
        frame=stock,
        store=store,
        created_at=cutoff - timedelta(minutes=15),
    )
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )

    facts = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader((snapshot,)),
        payload_reader=store,
    ).load(context)

    assert facts.regime_input.advancing_count == 1
    assert facts.regime_input.declining_count == 1
    assert facts.regime_input.universe_count == 2


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_global_return_uses_visible_global_index_previous_close(
    tmp_path: Path,
) -> None:
    """A-share context must not substitute FX/commodity for global indices."""
    cutoff = datetime(2026, 8, 31, 1, 0, tzinfo=UTC)
    global_index = pl.DataFrame(
        {
            "source_ticker": ["SPX", "SPX"],
            "event_time": [
                cutoff - timedelta(hours=8),
                cutoff + timedelta(hours=16),
            ],
            "published_at": [
                cutoff - timedelta(hours=7, minutes=45),
                cutoff + timedelta(hours=16, minutes=15),
            ],
            "available_at": [
                cutoff - timedelta(hours=7, minutes=30),
                cutoff + timedelta(hours=16, minutes=30),
            ],
            "close": [101.5, 1.0],
            "pre_close": [100.0, 100.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(
        dataset_id="global_index_daily",
        frame=global_index,
        store=store,
        created_at=cutoff - timedelta(minutes=15),
    )
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )
    source = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader((snapshot,)),
        payload_reader=store,
    )

    facts = source.load(context)

    assert facts.regime_input.global_return_1d == pytest.approx(0.015)
    assert "global_return_1d" not in facts.regime_input.declared_missing_inputs


def _context(
    cutoff: datetime,
    *snapshot_groups: tuple[ProviderSnapshot, ...],
) -> PITQueryContext:
    bindings: list[DatasetSnapshot] = []
    for snapshots in snapshot_groups:
        assert snapshots
        first = snapshots[0]
        assert all(item.dataset_id == first.dataset_id for item in snapshots)
        assert all(item.schema_version == first.schema_version for item in snapshots)
        bindings.append(
            DatasetSnapshot(
                dataset_id=first.dataset_id,
                dataset_version=first.schema_version,
                source_snapshot_ids=tuple(item.snapshot_id for item in snapshots),
                created_at=max(item.created_at for item in snapshots),
            )
        )
    return PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=tuple(bindings),
    )


def _source_case(
    tmp_path: Path,
    *,
    dataset_id: str,
    frame: pl.DataFrame,
    cutoff: datetime,
) -> tuple[
    ProviderPayloadMarketContextSource,
    PITQueryContext,
    ProviderSnapshot,
    FilesystemProviderPayloadStore,
]:
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(
        dataset_id=dataset_id,
        frame=frame,
        store=store,
        created_at=cutoff - timedelta(minutes=1),
    )
    context = _context(cutoff, (snapshot,))
    return (
        ProviderPayloadMarketContextSource(
            snapshot_reader=_SnapshotReader((snapshot,)),
            payload_reader=store,
        ),
        context,
        snapshot,
        store,
    )


def _load_single(
    tmp_path: Path,
    *,
    dataset_id: str,
    frame: pl.DataFrame,
    cutoff: datetime,
) -> MarketContextFacts:
    source, context, _snapshot_value, _store = _source_case(
        tmp_path,
        dataset_id=dataset_id,
        frame=frame,
        cutoff=cutoff,
    )
    return source.load(context)


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param("trade_date", date(2026, 8, 31), id="provider-date"),
        pytest.param("trade_date", "20260831", id="compact-provider-date"),
    ],
)
def test_market_context_source_normalizes_supported_provider_time_values(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame({column: [value], "pct_chg": [1.0]}),
        cutoff=cutoff,
    )

    assert facts.regime_input.advancing_count == 1


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param(None, "PIT time columns must be comparable", id="null"),
        pytest.param(123, "unsupported PIT datetime value", id="integer"),
    ],
)
def test_market_context_source_rejects_unusable_provider_time_value(
    tmp_path: Path,
    value: object,
    message: str,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    source, context, *_ = _source_case(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame({"event_time": [value], "pct_chg": [1.0]}),
        cutoff=cutoff,
    )

    with pytest.raises(AppQueryError, match=message):
        source.load(context)


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_requires_an_event_time_column(tmp_path: Path) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    source, context, *_ = _source_case(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame({"pct_chg": [1.0]}),
        cutoff=cutoff,
    )

    with pytest.raises(AppQueryError, match="lacks PIT time column"):
        source.load(context)


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize("column", ["source_snapshot_id", "dataset_version"])
def test_market_context_source_rejects_payload_bound_to_another_identity(
    tmp_path: Path,
    column: str,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    source, context, *_ = _source_case(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(hours=1)],
                "pct_chg": [1.0],
                column: ["foreign-identity"],
            }
        ),
        cutoff=cutoff,
    )

    with pytest.raises(AppQueryError, match=f"{column} drifted"):
        source.load(context)


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_accepts_exact_declared_dataset_version(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(hours=1)],
                "pct_chg": [1.0],
                "dataset_version": ["market.stock_daily.v1"],
            }
        ),
        cutoff=cutoff,
    )

    assert facts.regime_input.advancing_count == 1


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_rejects_snapshot_without_retained_payload(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    source, context, snapshot, _store = _source_case(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame(
            {"event_time": [cutoff - timedelta(hours=1)], "pct_chg": [1.0]}
        ),
        cutoff=cutoff,
    )
    object.__setattr__(snapshot, "payload_retained", False)

    with pytest.raises(AppQueryError, match="lacks exact retained payload"):
        source.load(context)


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_rejects_empty_source_snapshot_set(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    source, context, _snapshot_value, _store = _source_case(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame(
            {"event_time": [cutoff - timedelta(hours=1)], "pct_chg": [1.0]}
        ),
        cutoff=cutoff,
    )
    object.__setattr__(context.source_snapshots[0], "source_snapshot_ids", ())

    with pytest.raises(AppQueryError, match="has no retained payload"):
        source.load(context)


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_hashes_multi_snapshot_evidence(tmp_path: Path) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshots = tuple(
        _snapshot(
            dataset_id="stock_daily",
            frame=pl.DataFrame(
                {
                    "source_ticker": [ticker],
                    "event_time": [cutoff - timedelta(hours=1)],
                    "pct_chg": [change],
                }
            ),
            store=store,
            created_at=cutoff - timedelta(minutes=1),
        )
        for ticker, change in (("000001.SZ", 1.0), ("000002.SZ", -1.0))
    )
    context = _context(cutoff, snapshots)
    source = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader(snapshots),
        payload_reader=store,
    )

    facts = source.load(context)
    breadth = next(item for item in facts.metrics if item.name == "a_share_breadth")

    assert breadth.evidence_ref.startswith("snapshot-set:sha256:")
    assert facts.regime_input.universe_count == 2


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_reports_breadth_unavailable_without_returns(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame({"event_time": [cutoff - timedelta(hours=1)]}),
        cutoff=cutoff,
    )

    assert facts.regime_input.advancing_count is None
    assert "advancing_count" in facts.regime_input.declared_missing_inputs


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_computes_tickerless_breadth(tmp_path: Path) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(hours=1)] * 2,
                "pct_chg": [1.0, -1.0],
            }
        ),
        cutoff=cutoff,
    )

    assert facts.regime_input.advancing_count == 1
    assert facts.regime_input.declining_count == 1
    assert facts.regime_input.universe_count == 2


def _index_edge_frame(variant: str, cutoff: datetime) -> pl.DataFrame:
    observations = 21
    values: dict[str, object] = {
        "event_time": [
            cutoff - timedelta(days=observations - index)
            for index in range(observations)
        ],
        "source_ticker": ["000300.SH"] * observations,
    }
    if variant == "missing_close":
        values["pct_chg"] = [1.0] * observations
    elif variant == "no_ticker":
        values["source_ticker"] = [None] * observations
        values["close"] = [100.0 + index for index in range(observations)]
    elif variant == "short":
        values["event_time"] = values["event_time"][:2]
        values["source_ticker"] = values["source_ticker"][:2]
        values["close"] = [100.0, 101.0]
    elif variant == "zero_start":
        values["close"] = [0.0, *(100.0 + index for index in range(20))]
    else:
        raise AssertionError(f"unsupported test variant: {variant}")
    return pl.DataFrame(values)


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize(
    "variant",
    ["missing_close", "no_ticker", "short", "zero_start"],
)
def test_market_context_source_declares_incomplete_index_windows(
    tmp_path: Path,
    variant: str,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="index_daily",
        frame=_index_edge_frame(variant, cutoff),
        cutoff=cutoff,
    )

    assert facts.regime_input.benchmark_return_20d is None
    assert "benchmark_return_20d" in facts.regime_input.declared_missing_inputs
    assert all(item.name != "benchmark_return_20d" for item in facts.metrics)


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_computes_tickerless_index_window(tmp_path: Path) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    observations = 21
    facts = _load_single(
        tmp_path,
        dataset_id="index_daily",
        frame=pl.DataFrame(
            {
                "event_time": [
                    cutoff - timedelta(days=observations - index)
                    for index in range(observations)
                ],
                "close": [100.0 + index for index in range(observations)],
            }
        ),
        cutoff=cutoff,
    )

    assert facts.regime_input.benchmark_return_20d == pytest.approx(0.20)


def _global_edge_frame(variant: str, cutoff: datetime) -> pl.DataFrame:
    if variant == "missing_close":
        return pl.DataFrame(
            {"event_time": [cutoff - timedelta(hours=1)], "value": [1.0]}
        )
    if variant == "no_ticker":
        return pl.DataFrame(
            {
                "source_ticker": [None, None],
                "event_time": [cutoff - timedelta(days=1), cutoff],
                "close": [100.0, 110.0],
            }
        )
    if variant == "short":
        return pl.DataFrame({"event_time": [cutoff], "close": [100.0]})
    if variant == "zero_start":
        return pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(days=1), cutoff],
                "close": [0.0, 100.0],
            }
        )
    if variant == "valid":
        return pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(days=1), cutoff],
                "close": [100.0, 110.0],
            }
        )
    raise AssertionError(f"unsupported test variant: {variant}")


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        pytest.param("missing_close", None),
        pytest.param("no_ticker", None),
        pytest.param("short", None),
        pytest.param("zero_start", None),
        pytest.param("valid", 0.10),
    ],
)
def test_market_context_source_handles_global_close_return_edges(
    tmp_path: Path,
    variant: str,
    expected: float | None,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="global_index_daily",
        frame=_global_edge_frame(variant, cutoff),
        cutoff=cutoff,
    )

    if expected is None:
        assert facts.regime_input.global_return_1d is None
        assert "global_return_1d" in facts.regime_input.declared_missing_inputs
    else:
        assert facts.regime_input.global_return_1d == pytest.approx(expected)


def _macro_edge_frame(variant: str, cutoff: datetime) -> pl.DataFrame:
    if variant == "missing_value":
        return pl.DataFrame({"event_time": [cutoff]})
    if variant == "ungrouped_trend":
        return pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(days=1), cutoff],
                "value": [10.0, 12.0],
            }
        )
    if variant == "short_group":
        return pl.DataFrame(
            {"event_time": [cutoff], "indicator": ["pmi"], "value": [50.0]}
        )
    if variant == "null_surprise":
        return pl.DataFrame(
            {
                "event_time": [cutoff],
                "indicator": ["pmi"],
                "value": [None],
                "forecast": [49.0],
            }
        )
    if variant == "valid":
        return pl.DataFrame(
            {
                "event_time": [cutoff - timedelta(days=1), cutoff],
                "indicator": ["pmi", "pmi"],
                "value": [50.0, 55.0],
                "forecast": [49.0, 54.0],
            }
        )
    raise AssertionError(f"unsupported test variant: {variant}")


@pytest.mark.unit
@pytest.mark.pit
@pytest.mark.parametrize(
    ("variant", "expected_surprise", "expected_trend"),
    [
        pytest.param("missing_value", None, None),
        pytest.param("ungrouped_trend", None, 0.20),
        pytest.param("short_group", None, None),
        pytest.param("null_surprise", None, None),
        pytest.param("valid", 1.0 / 54.0, 0.10),
    ],
)
def test_market_context_source_derives_macro_edges(
    tmp_path: Path,
    variant: str,
    expected_surprise: float | None,
    expected_trend: float | None,
) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    facts = _load_single(
        tmp_path,
        dataset_id="macro_indicators",
        frame=_macro_edge_frame(variant, cutoff),
        cutoff=cutoff,
    )

    if expected_surprise is None:
        assert facts.regime_input.macro_surprise_score is None
    else:
        assert facts.regime_input.macro_surprise_score == pytest.approx(
            expected_surprise
        )
    if expected_trend is None:
        assert facts.regime_input.macro_trend_score is None
    else:
        assert facts.regime_input.macro_trend_score == pytest.approx(expected_trend)


class _FailingPayloadReader:
    def read_payload(self, artifact: ProviderPayloadArtifact) -> pl.DataFrame:
        raise OSError(f"cannot read {artifact.uri}")


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_wraps_payload_io_failure(tmp_path: Path) -> None:
    cutoff = datetime(2026, 8, 31, 12, tzinfo=UTC)
    _source, context, snapshot, _store = _source_case(
        tmp_path,
        dataset_id="stock_daily",
        frame=pl.DataFrame(
            {"event_time": [cutoff - timedelta(hours=1)], "pct_chg": [1.0]}
        ),
        cutoff=cutoff,
    )
    source = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader((snapshot,)),
        payload_reader=_FailingPayloadReader(),
    )

    with pytest.raises(AppQueryError, match="payload failed closed for 'stock_daily'"):
        source.load(context)
