"""Market-context facts loaded from exact immutable provider payloads."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from hashlib import sha256
from zoneinfo import ZoneInfo

import orjson
import polars as pl
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_data.query.service import PITDatasetReader, PITQueryService
from ditto_features.market_context.contracts import MarketRegimeInput

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market_context import (
    MarketContextFacts,
    MarketContextMetric,
)

__all__ = ["ProviderPayloadMarketContextSource"]

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_BENCHMARK_PREFERENCE = ("000300.SH", "000001.SH", "000985.CSI")
_SMALL_CAP_PREFERENCE = ("000852.SH", "000905.SH", "399006.SZ")
_LARGE_CAP_PREFERENCE = ("000300.SH", "000016.SH")
_COMPACT_DATE_LENGTH = 8
_PERCENT_SCALE_THRESHOLD = 2.0
_RETURN_WINDOW_OBSERVATIONS = 21
_PAIR_SIZE = 2


def _parse_datetime(value: object, *, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time(16), tzinfo=_SHANGHAI)
    elif isinstance(value, str):
        normalized = value.strip()
        if len(normalized) == _COMPACT_DATE_LENGTH and normalized.isdigit():
            parsed = datetime.strptime(normalized, "%Y%m%d")
        else:
            parsed = datetime.fromisoformat(normalized)
    else:
        raise AppQueryError(f"unsupported PIT datetime value: {value!r}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=_SHANGHAI)
    return parsed.astimezone(UTC)


def _datetime_values(
    frame: pl.DataFrame,
    *,
    candidates: tuple[str, ...],
    fallback: datetime | None,
) -> list[datetime]:
    column = next((name for name in candidates if name in frame.columns), None)
    if column is None:
        if fallback is None:
            raise AppQueryError(
                f"provider payload lacks PIT time column {candidates!r}"
            )
        return [fallback] * len(frame)
    default = fallback or datetime.min.replace(tzinfo=_SHANGHAI)
    return [_parse_datetime(value, fallback=default) for value in frame[column]]


def _validate_bound_column(
    frame: pl.DataFrame,
    *,
    column: str,
    expected: str,
) -> None:
    if column not in frame.columns:
        return
    actual = set(frame.get_column(column).cast(pl.String).unique().to_list())
    if actual != {expected}:
        raise AppQueryError(f"provider payload {column} drifted from snapshot identity")


def _normalize_payload(
    snapshot: ProviderSnapshot,
    payload: pl.DataFrame,
) -> pl.DataFrame:
    _validate_bound_column(
        payload,
        column="source_snapshot_id",
        expected=snapshot.snapshot_id,
    )
    _validate_bound_column(
        payload,
        column="dataset_version",
        expected=snapshot.schema_version,
    )
    event_times = _datetime_values(
        payload,
        candidates=(
            "event_time",
            "trade_date",
            "observation_date",
            "report_date",
            "effective_from",
            "date",
        ),
        fallback=None,
    )
    published_at = _datetime_values(
        payload,
        candidates=(
            "published_at",
            "publication_date",
            "knowledge_date",
            "ann_date",
        ),
        fallback=snapshot.created_at,
    )
    available_at = _datetime_values(
        payload,
        candidates=("available_at", "knowledge_date"),
        fallback=snapshot.created_at,
    )
    return payload.with_columns(
        pl.Series("event_time", event_times),
        pl.Series("published_at", published_at),
        pl.Series("available_at", available_at),
        pl.lit(snapshot.snapshot_id).alias("source_snapshot_id"),
        pl.lit(snapshot.schema_version).alias("dataset_version"),
    )


class _ProviderSnapshotDatasetReader(PITDatasetReader):
    def __init__(
        self,
        *,
        snapshot_reader: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
    ) -> None:
        self._snapshot_reader = snapshot_reader
        self._payload_reader = payload_reader

    def read_dataset(self, snapshot: DatasetSnapshot) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for snapshot_id in snapshot.source_snapshot_ids:
            provider_snapshot = self._snapshot_reader.get_snapshot(snapshot_id)
            if (
                provider_snapshot is None
                or provider_snapshot.snapshot_id != snapshot_id
                or provider_snapshot.dataset_id != snapshot.dataset_id
                or provider_snapshot.schema_version != snapshot.dataset_version
                or not provider_snapshot.payload_retained
                or provider_snapshot.payload_uri is None
            ):
                raise AppQueryError(
                    f"provider snapshot {snapshot_id!r} lacks exact retained payload"
                )
            artifact = ProviderPayloadArtifact(
                dataset_id=provider_snapshot.dataset_id,
                source=provider_snapshot.source,
                checksum=provider_snapshot.checksum,
                row_count=provider_snapshot.row_count,
                uri=provider_snapshot.payload_uri,
            )
            frames.append(
                _normalize_payload(
                    provider_snapshot,
                    self._payload_reader.read_payload(artifact),
                )
            )
        if not frames:
            raise AppQueryError(
                f"dataset {snapshot.dataset_id!r} has no retained payload"
            )
        return pl.concat(frames, how="diagonal_relaxed")


def _evidence_ref(snapshot: DatasetSnapshot) -> str:
    if len(snapshot.source_snapshot_ids) == 1:
        return snapshot.source_snapshot_ids[0]
    digest = sha256(orjson.dumps(sorted(snapshot.source_snapshot_ids))).hexdigest()
    return f"snapshot-set:sha256:{digest}"


def _ticker_column(frame: pl.DataFrame) -> str | None:
    return next(
        (
            name
            for name in (
                "source_ticker",
                "index_code",
                "instrument_code",
                "instrument_id",
            )
            if name in frame.columns
        ),
        None,
    )


def _normalized_return_expr(frame: pl.DataFrame) -> pl.Expr | None:
    if "pct_chg" in frame.columns:
        return (
            pl.when(pl.col("pct_chg").cast(pl.Float64).abs() > _PERCENT_SCALE_THRESHOLD)
            .then(pl.col("pct_chg").cast(pl.Float64) / 100.0)
            .otherwise(pl.col("pct_chg").cast(pl.Float64))
        )
    if {"close", "pre_close"}.issubset(frame.columns):
        return (
            pl.col("close").cast(pl.Float64) / pl.col("pre_close").cast(pl.Float64)
            - 1.0
        )
    return None


def _breadth(frame: pl.DataFrame) -> tuple[int, int, int] | None:
    expression = _normalized_return_expr(frame)
    if expression is None or frame.is_empty():
        return None
    latest = frame.get_column("event_time").max()
    cross_section = frame.filter(pl.col("event_time") == latest).with_columns(
        expression.alias("_return")
    )
    ticker = _ticker_column(cross_section)
    if ticker is not None:
        cross_section = cross_section.unique(subset=[ticker], keep="last")
    returns = cross_section.get_column("_return").drop_nulls()
    return (
        int((returns > 0).sum()),
        int((returns < 0).sum()),
        len(returns),
    )


def _ticker_values(frame: pl.DataFrame) -> tuple[str, ...]:
    column = _ticker_column(frame)
    if column is None:
        return ("all",)
    return tuple(sorted(str(value) for value in frame[column].drop_nulls().unique()))


def _select_ticker(
    frame: pl.DataFrame,
    preference: tuple[str, ...],
) -> str | None:
    available = _ticker_values(frame)
    for ticker in preference:
        if ticker in available:
            return ticker
    return available[0] if available else None


def _close_series(frame: pl.DataFrame, ticker: str) -> pl.Series:
    selected = frame
    column = _ticker_column(frame)
    if column is not None:
        selected = frame.filter(pl.col(column).cast(pl.String) == ticker)
    return (
        selected.sort("event_time")
        .unique(subset=["event_time"], keep="last")
        .get_column("close")
        .cast(pl.Float64)
        .drop_nulls()
    )


def _return_and_volatility(
    frame: pl.DataFrame,
    preference: tuple[str, ...],
) -> tuple[float | None, float | None]:
    if "close" not in frame.columns:
        return None, None
    ticker = _select_ticker(frame, preference)
    if ticker is None:
        return None, None
    closes = _close_series(frame, ticker)
    if len(closes) < _RETURN_WINDOW_OBSERVATIONS:
        return None, None
    window = closes.tail(_RETURN_WINDOW_OBSERVATIONS)
    start = float(window[0])
    end = float(window[-1])
    if start == 0:
        return None, None
    returns = window.pct_change().drop_nulls()
    volatility = returns.std(ddof=1)
    volatility_value = (
        float(volatility) * math.sqrt(252.0)
        if isinstance(volatility, (int, float))
        else None
    )
    return (
        end / start - 1.0,
        volatility_value,
    )


def _one_day_return(frame: pl.DataFrame) -> float | None:
    expression = _normalized_return_expr(frame)
    if expression is not None:
        values = frame.sort("event_time").select(expression.alias("value"))["value"]
        latest = values.drop_nulls().tail(1)
        return None if latest.is_empty() else float(latest[0])
    if "close" not in frame.columns:
        return None
    ticker = _select_ticker(frame, ())
    if ticker is None:
        return None
    closes = _close_series(frame, ticker).tail(_PAIR_SIZE)
    if len(closes) != _PAIR_SIZE or float(closes[0]) == 0:
        return None
    return float(closes[1]) / float(closes[0]) - 1.0


def _global_index_return(frame: pl.DataFrame) -> float | None:
    """Return an equal-weighted visible close return across global indices."""
    ticker = _ticker_column(frame)
    groups = (frame,) if ticker is None else frame.partition_by(ticker)
    values = tuple(
        value for group in groups if (value := _one_day_return(group)) is not None
    )
    return sum(values) / len(values) if values else None


def _macro_scores(frame: pl.DataFrame) -> tuple[float | None, float | None]:
    value_column = next(
        (name for name in ("value", "actual", "close") if name in frame.columns),
        None,
    )
    if value_column is None or frame.is_empty():
        return None, None
    indicator = next(
        (
            name
            for name in ("indicator", "series_id", "source_ticker")
            if name in frame.columns
        ),
        None,
    )
    trend_values: list[float] = []
    groups = (frame,) if indicator is None else frame.partition_by(indicator)
    for group in groups:
        values = (
            group.sort("event_time")
            .get_column(value_column)
            .cast(pl.Float64, strict=False)
            .drop_nulls()
            .tail(_PAIR_SIZE)
        )
        if len(values) == _PAIR_SIZE:
            scale = max(abs(float(values[0])), 1.0)
            trend_values.append(max(-1.0, min(1.0, (values[1] - values[0]) / scale)))
    trend = sum(trend_values) / len(trend_values) if trend_values else None
    surprise = None
    forecast_column = next(
        (
            name
            for name in ("forecast", "consensus", "expected")
            if name in frame.columns
        ),
        None,
    )
    if forecast_column is not None:
        latest = frame.sort("event_time").tail(1)
        actual = latest.get_column(value_column).cast(pl.Float64, strict=False)[0]
        forecast = latest.get_column(forecast_column).cast(pl.Float64, strict=False)[0]
        if actual is not None and forecast is not None:
            scale = max(abs(float(forecast)), 1.0)
            surprise = max(-1.0, min(1.0, (float(actual) - float(forecast)) / scale))
    return surprise, trend


@dataclass(frozen=True, slots=True)
class _CoreFacts:
    advancing: int | None
    declining: int | None
    universe: int | None
    benchmark_return: float | None
    small_cap_return: float | None
    large_cap_return: float | None
    volatility: float | None
    metrics: tuple[MarketContextMetric, ...]
    missing: frozenset[str]


def _breadth_facts(
    context: PITQueryContext,
    frame: pl.DataFrame | None,
) -> tuple[int | None, int | None, int | None, tuple[MarketContextMetric, ...]]:
    breadth = None if frame is None else _breadth(frame)
    if breadth is None or breadth[2] == 0:
        return None, None, None, ()
    advancing, declining, universe = breadth
    metric = MarketContextMetric(
        name="a_share_breadth",
        category="a_share",
        value=(advancing - declining) / universe,
        unit="ratio",
        trend=(
            "rising"
            if advancing > declining
            else "falling"
            if declining > advancing
            else "flat"
        ),
        freshness="fresh",
        evidence_ref=_evidence_ref(context.snapshot_for("stock_daily")),
    )
    return advancing, declining, universe, (metric,)


def _index_facts(
    context: PITQueryContext,
    frame: pl.DataFrame | None,
) -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
    tuple[MarketContextMetric, ...],
]:
    if frame is None:
        return None, None, None, None, ()
    benchmark, volatility = _return_and_volatility(frame, _BENCHMARK_PREFERENCE)
    small_cap, _ = _return_and_volatility(frame, _SMALL_CAP_PREFERENCE)
    large_cap, _ = _return_and_volatility(frame, _LARGE_CAP_PREFERENCE)
    reference = _evidence_ref(context.snapshot_for("index_daily"))
    metrics: list[MarketContextMetric] = []
    if benchmark is not None:
        metrics.append(
            MarketContextMetric(
                name="benchmark_return_20d",
                category="a_share",
                value=benchmark,
                unit="decimal_return",
                trend="rising" if benchmark > 0 else "falling",
                freshness="fresh",
                evidence_ref=reference,
            )
        )
    if volatility is not None:
        metrics.append(
            MarketContextMetric(
                name="realized_volatility_20d",
                category="a_share",
                value=volatility,
                unit="annualized_decimal",
                trend="unknown",
                freshness="fresh",
                evidence_ref=reference,
            )
        )
    return benchmark, small_cap, large_cap, volatility, tuple(metrics)


def _derive_core_facts(
    context: PITQueryContext,
    frames: dict[str, pl.DataFrame],
) -> _CoreFacts:
    advancing, declining, universe, breadth_metrics = _breadth_facts(
        context,
        frames.get("stock_daily"),
    )
    benchmark, small_cap, large_cap, volatility, index_metrics = _index_facts(
        context,
        frames.get("index_daily"),
    )
    values = {
        "advancing_count": advancing,
        "declining_count": declining,
        "universe_count": universe,
        "benchmark_return_20d": benchmark,
        "small_cap_return_20d": small_cap,
        "large_cap_return_20d": large_cap,
        "realized_volatility_20d": volatility,
    }
    return _CoreFacts(
        advancing=advancing,
        declining=declining,
        universe=universe,
        benchmark_return=benchmark,
        small_cap_return=small_cap,
        large_cap_return=large_cap,
        volatility=volatility,
        metrics=(*breadth_metrics, *index_metrics),
        missing=frozenset(name for name, value in values.items() if value is None),
    )


def _derive_optional_facts(
    context: PITQueryContext,
    frames: dict[str, pl.DataFrame],
) -> tuple[
    float | None,
    float | None,
    float | None,
    frozenset[str],
    tuple[MarketContextMetric, ...],
]:
    global_frame = frames.get("global_index_daily")
    global_return = None if global_frame is None else _global_index_return(global_frame)
    macro = frames.get("macro_indicators")
    macro_surprise, macro_trend = (
        (None, None) if macro is None else _macro_scores(macro)
    )
    values = {
        "global_return_1d": global_return,
        "macro_surprise_score": macro_surprise,
        "macro_trend_score": macro_trend,
    }
    metrics = (
        ()
        if global_return is None
        else (
            MarketContextMetric(
                name="global_index_return_1d",
                category="global",
                value=global_return,
                unit="decimal_return",
                trend="rising" if global_return > 0 else "falling",
                freshness="fresh",
                evidence_ref=_evidence_ref(context.snapshot_for("global_index_daily")),
            ),
        )
    )
    return (
        global_return,
        macro_surprise,
        macro_trend,
        frozenset(name for name, value in values.items() if value is None),
        metrics,
    )


class ProviderPayloadMarketContextSource:
    """Compute real market facts from only the requested immutable snapshots."""

    def __init__(
        self,
        *,
        snapshot_reader: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
    ) -> None:
        self._query = PITQueryService(
            _ProviderSnapshotDatasetReader(
                snapshot_reader=snapshot_reader,
                payload_reader=payload_reader,
            )
        )

    def load(self, context: PITQueryContext) -> MarketContextFacts:
        """Load exact snapshots, apply PIT filters, and derive documented facts."""
        frames = self._load_frames(context)
        core = _derive_core_facts(context, frames)
        (
            global_return,
            macro_surprise,
            macro_trend,
            optional_missing,
            optional_metrics,
        ) = _derive_optional_facts(context, frames)
        missing = core.missing | optional_missing
        uncertainties = tuple(
            f"{name}_not_derivable_from_requested_snapshots" for name in sorted(missing)
        )
        return MarketContextFacts(
            regime_input=MarketRegimeInput(
                as_of=context.as_of,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_ids=context.source_snapshot_ids,
                advancing_count=core.advancing,
                declining_count=core.declining,
                universe_count=core.universe,
                benchmark_return_20d=core.benchmark_return,
                small_cap_return_20d=core.small_cap_return,
                large_cap_return_20d=core.large_cap_return,
                realized_volatility_20d=core.volatility,
                global_return_1d=global_return,
                macro_surprise_score=macro_surprise,
                macro_trend_score=macro_trend,
                declared_missing_inputs=tuple(sorted(missing)),
            ),
            metrics=(*core.metrics, *optional_metrics),
            data_conflicts=(),
            uncertainties=uncertainties,
        )

    def _load_frames(self, context: PITQueryContext) -> dict[str, pl.DataFrame]:
        """Load every requested dataset through the common PIT filter."""
        frames: dict[str, pl.DataFrame] = {}
        for snapshot in context.source_snapshots:
            try:
                frames[snapshot.dataset_id] = self._query.query(
                    dataset_id=snapshot.dataset_id,
                    context=context,
                )
            except (OSError, ValueError, pl.exceptions.PolarsError) as error:
                message = "market context payload failed closed for "
                message += f"{snapshot.dataset_id!r}: {error}"
                raise AppQueryError(message) from error
        return frames
