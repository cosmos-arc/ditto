"""Technical bars loaded from exact immutable provider payloads."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from math import isfinite
from typing import NamedTuple, cast
from zoneinfo import ZoneInfo

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
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId

from ditto_application.exceptions import AppQueryError
from ditto_application.paper_contracts import PaperMarketSnapshotInput
from ditto_application.queries.retained_calendar import snapshot_observed_by

__all__ = ["ProviderPayloadTechnicalAnalysisSource"]

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_COMPACT_DATE_LENGTH = 8


class AdjustmentFactor(NamedTuple):
    value: float
    snapshot_id: str
    available_at: datetime
    published_at: datetime


def _source_error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"technical analysis source failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _column(
    frame: pl.DataFrame,
    candidates: tuple[str, ...],
    *,
    field: str,
    required: bool = True,
) -> str | None:
    value = next((item for item in candidates if item in frame.columns), None)
    if value is None and required:
        raise _source_error(
            "TECHNICAL_SOURCE_SCHEMA_INVALID",
            "required_column_missing",
            field=field,
        )
    return value


def _parse_datetime(value: object, *, fallback: datetime | None) -> datetime:
    if value is None:
        if fallback is None:
            raise _source_error(
                "TECHNICAL_SOURCE_TIME_INVALID",
                "event_time_missing",
            )
        return fallback
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time(15), tzinfo=_SHANGHAI)
    elif isinstance(value, str):
        normalized = value.strip()
        try:
            if len(normalized) == _COMPACT_DATE_LENGTH and normalized.isdigit():
                parsed = datetime.strptime(normalized, "%Y%m%d")
            else:
                parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise _source_error(
                "TECHNICAL_SOURCE_TIME_INVALID",
                "event_time_unparseable",
                value=normalized,
            ) from exc
    else:
        raise _source_error(
            "TECHNICAL_SOURCE_TIME_INVALID",
            "event_time_type_invalid",
            value_type=type(value).__name__,
        )
    aware = parsed.replace(tzinfo=_SHANGHAI) if parsed.tzinfo is None else parsed
    return aware.astimezone(UTC)


def _times(
    frame: pl.DataFrame,
    candidates: tuple[str, ...],
    *,
    fallback: datetime | None,
) -> list[datetime]:
    column = _column(frame, candidates, field="PIT time", required=False)
    if column is None:
        if fallback is None:
            raise _source_error(
                "TECHNICAL_SOURCE_TIME_INVALID",
                "event_time_missing",
            )
        return [fallback] * len(frame)
    return [_parse_datetime(item, fallback=fallback) for item in frame[column]]


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
        raise _source_error(
            "TECHNICAL_SOURCE_LINEAGE_MISMATCH",
            "payload_identity_drift",
            column=column,
            expected=expected,
            actual=tuple(sorted(str(item) for item in actual)),
        )


def _normalize(snapshot: ProviderSnapshot, frame: pl.DataFrame) -> pl.DataFrame:
    _validate_bound_column(
        frame,
        column="source_snapshot_id",
        expected=snapshot.snapshot_id,
    )
    _validate_bound_column(
        frame,
        column="dataset_version",
        expected=snapshot.schema_version,
    )
    return frame.with_columns(
        pl.Series(
            "event_time",
            _times(
                frame,
                ("event_time", "trade_date", "date", "occurred_at"),
                fallback=None,
            ),
        ),
        pl.Series(
            "published_at",
            _times(
                frame,
                ("published_at", "publication_at", "ann_date"),
                fallback=snapshot.created_at,
            ),
        ),
        pl.Series(
            "available_at",
            _times(
                frame,
                ("available_at", "knowledge_at", "knowledge_date"),
                fallback=snapshot.created_at,
            ),
        ),
        pl.lit(snapshot.snapshot_id).alias("source_snapshot_id"),
        pl.lit(snapshot.schema_version).alias("dataset_version"),
    )


class _PayloadDatasetReader(PITDatasetReader):
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
                provider_snapshot is not None
                and provider_snapshot.snapshot_id == snapshot_id
                and provider_snapshot.dataset_id == snapshot.dataset_id
                and provider_snapshot.schema_version == snapshot.dataset_version
                and provider_snapshot.row_count == 0
                and dict(provider_snapshot.response_metadata).get("snapshot_layer")
                == "verified_empty_provider_observation"
            ):
                continue
            if (
                provider_snapshot is None
                or provider_snapshot.snapshot_id != snapshot_id
                or provider_snapshot.dataset_id != snapshot.dataset_id
                or provider_snapshot.schema_version != snapshot.dataset_version
                or not provider_snapshot.payload_retained
                or provider_snapshot.payload_uri is None
            ):
                raise _source_error(
                    "TECHNICAL_SOURCE_PAYLOAD_UNAVAILABLE",
                    "exact_retained_payload_missing",
                    snapshot_id=snapshot_id,
                )
            artifact = ProviderPayloadArtifact(
                dataset_id=provider_snapshot.dataset_id,
                source=provider_snapshot.source,
                checksum=provider_snapshot.checksum,
                row_count=provider_snapshot.row_count,
                uri=provider_snapshot.payload_uri,
            )
            frames.append(
                _normalize(
                    provider_snapshot,
                    self._payload_reader.read_payload(artifact),
                )
            )
        if not frames:
            raise _source_error(
                "TECHNICAL_SOURCE_PAYLOAD_UNAVAILABLE",
                "retained_payload_set_empty",
            )
        return pl.concat(frames, how="diagonal_relaxed")


def _instrument_rows(
    frame: pl.DataFrame,
    *,
    instrument_id: InstrumentId,
    instrument_code: str | Callable[[date], str | None],
) -> pl.DataFrame:
    """
    Select rows for exactly one instrument.

    Retained artifacts predate FK enrichment, so the provider ticker is the
    primary identity; the internal ID is a cross-check when the optional
    enriched column exists. Requiring agreement keeps a corrected mapping
    from mixing rows of two different instruments into one price series.
    """
    selected = frame
    expected = (
        pl.Series(
            "expected_ticker",
            [
                instrument_code(cast(datetime, value).astimezone(_SHANGHAI).date())
                for value in frame["event_time"]
            ],
            dtype=pl.String,
        )
        if callable(instrument_code)
        else instrument_code
    )
    ticker_filters = [
        pl.col(column).cast(pl.String) == expected
        for column in ("source_ticker", "instrument_code", "ts_code", "ticker")
        if column in frame.columns
    ]
    id_filter = (
        pl.col("instrument_id").cast(pl.Int64, strict=False) == int(instrument_id)
        if "instrument_id" in frame.columns
        else None
    )
    if not ticker_filters and id_filter is None:
        raise _source_error(
            "TECHNICAL_SOURCE_IDENTITY_REQUIRED",
            "instrument_identity_column_missing",
        )
    if ticker_filters:
        selected = selected.filter(pl.all_horizontal(ticker_filters))
    if id_filter is not None:
        selected = selected.filter(id_filter)
    return selected


def _values(
    frame: pl.DataFrame,
    candidates: tuple[str, ...],
    *,
    field: str,
    default: float | None = None,
    required: bool = True,
) -> list[float | None]:
    column = _column(frame, candidates, field=field, required=required)
    if column is None:
        return [default] * len(frame)
    values: list[float | None] = []
    for item in frame[column]:
        if item is None:
            if required:
                raise _source_error(
                    "TECHNICAL_SOURCE_VALUE_INVALID",
                    "required_value_null",
                    field=field,
                )
            values.append(default)
        else:
            try:
                values.append(float(item))
            except (TypeError, ValueError) as exc:
                raise _source_error(
                    "TECHNICAL_SOURCE_VALUE_INVALID",
                    "numeric_value_invalid",
                    field=field,
                    value_type=type(item).__name__,
                ) from exc
    return values


def _booleans(frame: pl.DataFrame) -> list[bool]:
    column = _column(
        frame,
        ("is_suspended", "suspended", "trade_status"),
        field="suspension",
        required=False,
    )
    if column is None:
        return [False] * len(frame)
    return [
        item is True
        or (isinstance(item, str) and item.casefold() in {"suspended", "停牌"})
        for item in frame[column]
    ]


def _bars(frame: pl.DataFrame) -> tuple[TechnicalBar, ...]:
    if frame.is_empty():
        return ()
    columns = {
        name: _column(frame, (name,), field="OHLC")
        for name in ("open", "high", "low", "close")
    }
    opens = _values(frame, (cast(str, columns["open"]),), field="open")
    highs = _values(frame, (cast(str, columns["high"]),), field="high")
    lows = _values(frame, (cast(str, columns["low"]),), field="low")
    closes = _values(frame, (cast(str, columns["close"]),), field="close")
    volumes = _values(
        frame,
        ("volume", "vol"),
        field="volume",
        default=0.0,
        required=False,
    )
    turnovers = _values(
        frame,
        ("turnover", "amount"),
        field="turnover",
        default=0.0,
        required=False,
    )
    adjustments = _values(
        frame,
        ("adjustment_factor", "adj_factor"),
        field="adjustment factor",
        default=1.0,
        required=False,
    )
    benchmarks = _values(
        frame,
        ("benchmark_close",),
        field="benchmark close",
        default=None,
        required=False,
    )
    industries = _values(
        frame,
        ("industry_close",),
        field="industry close",
        default=None,
        required=False,
    )
    suspended = _booleans(frame)
    return tuple(
        TechnicalBar(
            occurred_at=cast(datetime, frame["event_time"][index]),
            knowledge_at=cast(datetime, frame["available_at"][index]),
            publication_at=cast(datetime, frame["published_at"][index]),
            source_snapshot_id=str(frame["source_snapshot_id"][index]),
            open=cast(float, opens[index]),
            high=cast(float, highs[index]),
            low=cast(float, lows[index]),
            close=cast(float, closes[index]),
            volume=cast(float, volumes[index]),
            turnover=cast(float, turnovers[index]),
            adjustment_factor=cast(float, adjustments[index]),
            suspended=suspended[index],
            benchmark_close=benchmarks[index],
            industry_close=industries[index],
        )
        for index in range(len(frame))
    )


class ProviderPayloadTechnicalAnalysisSource:
    """Load technical bars through common PIT filters and exact artifacts."""

    def __init__(
        self,
        *,
        snapshot_reader: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
    ) -> None:
        self._snapshot_reader = snapshot_reader
        self._query = PITQueryService(
            _PayloadDatasetReader(
                snapshot_reader=snapshot_reader,
                payload_reader=payload_reader,
            )
        )

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str | Callable[[date], str | None],
    ) -> tuple[TechnicalBar, ...]:
        """Return ordered bars for exactly one requested instrument."""
        frames = tuple(
            self._query.query(dataset_id=item.dataset_id, context=context)
            for item in context.source_snapshots
        )
        combined = pl.concat(frames, how="diagonal_relaxed")
        selected = _instrument_rows(
            combined,
            instrument_id=instrument_id,
            instrument_code=instrument_code,
        ).sort("event_time")
        return _bars(selected)

    def load_adjustment_factors(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str | Callable[[date], str | None],
    ) -> dict[str, AdjustmentFactor]:
        """Read exact visible adjustment factors without a latest-store fallback."""
        frame = self._query.query(dataset_id="adj_factor", context=context)
        selected = _instrument_rows(
            frame, instrument_id=instrument_id, instrument_code=instrument_code
        ).sort("event_time")
        factor_column = _column(
            selected, ("adj_factor", "adjustment_factor"), field="adjustment factor"
        )
        factors: dict[str, AdjustmentFactor] = {}
        for row in selected.to_dicts():
            try:
                factor = float(row[cast(str, factor_column)])
            except (TypeError, ValueError) as error:
                raise _source_error(
                    "TECHNICAL_SOURCE_VALUE_INVALID", "adjustment factor invalid"
                ) from error
            if not isfinite(factor) or factor <= 0:
                raise _source_error(
                    "TECHNICAL_SOURCE_VALUE_INVALID", "adjustment factor invalid"
                )
            day = (
                cast(datetime, row["event_time"])
                .astimezone(_SHANGHAI)
                .date()
                .isoformat()
            )
            snapshot_id = str(row["source_snapshot_id"])
            snapshot = self._snapshot_reader.get_snapshot(snapshot_id)
            if snapshot is None:
                raise _source_error(
                    "TECHNICAL_SOURCE_LINEAGE_MISMATCH", "adjustment snapshot missing"
                )
            prior = factors.get(day)
            prior_snapshot = (
                self._snapshot_reader.get_snapshot(prior.snapshot_id) if prior else None
            )
            if prior_snapshot is None or snapshot_observed_by(
                snapshot, context.as_of
            ) > snapshot_observed_by(prior_snapshot, context.as_of):
                factors[day] = AdjustmentFactor(
                    factor,
                    snapshot_id,
                    cast(datetime, row["available_at"]),
                    cast(datetime, row["published_at"]),
                )
        return factors

    def load_suspensions(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: Callable[[date], str | None],
    ) -> dict[str, str]:
        """Return exact visible full-day suspension evidence; unknown stays a gap."""
        frame = self._query.query(dataset_id="stock_status", context=context)
        selected = _instrument_rows(
            frame, instrument_id=instrument_id, instrument_code=instrument_code
        )
        if "is_suspended" not in selected.columns:
            return {}
        rows: dict[str, dict[str, object]] = {}
        for row in selected.to_dicts():
            day = (
                cast(datetime, row["event_time"])
                .astimezone(_SHANGHAI)
                .date()
                .isoformat()
            )
            snapshot = self._snapshot_reader.get_snapshot(
                str(row["source_snapshot_id"])
            )
            previous = rows.get(day)
            prior = (
                self._snapshot_reader.get_snapshot(str(previous["source_snapshot_id"]))
                if previous
                else None
            )
            if snapshot is not None and (
                prior is None
                or snapshot_observed_by(snapshot, context.as_of)
                > snapshot_observed_by(prior, context.as_of)
            ):
                rows[day] = row
        return {
            day: str(row["source_snapshot_id"])
            for day, row in rows.items()
            if row["is_suspended"] is True
            and row.get("suspend_timing") in (None, "", "09:30-15:00")
        }

    def load_paper_market(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
        trade_date: str,
    ) -> PaperMarketSnapshotInput:
        """Load one complete ETF bar whose exact payload is visible after close."""
        dataset = context.snapshot_for("etf_daily")
        if len(dataset.source_snapshot_ids) != 1:
            raise _source_error(
                "ETF_PAPER_SNAPSHOT_AMBIGUOUS", "one exact bar snapshot required"
            )
        snapshot = self._snapshot_reader.get_snapshot(dataset.source_snapshot_ids[0])
        if (
            snapshot is None
            or snapshot.dataset_id != "etf_daily"
            or snapshot.created_at > context.knowledge_cutoff
        ):
            raise _source_error(
                "ETF_PAPER_SNAPSHOT_UNAVAILABLE", "bar snapshot is absent or future"
            )
        frame = self._query.query(dataset_id="etf_daily", context=context)
        # Retained artifacts predate FK enrichment, so the provider ticker is
        # the primary identity; the internal ID is only a cross-check when the
        # optional enriched column exists.
        ticker_columns = [
            name for name in ("source_ticker", "ts_code") if name in frame.columns
        ]
        if not ticker_columns and "instrument_id" not in frame.columns:
            raise _source_error(
                "ETF_PAPER_IDENTITY_MISSING", "bar instrument identity is absent"
            )
        selected = frame
        for name in ticker_columns:
            selected = selected.filter(pl.col(name).cast(pl.String) == instrument_code)
        if "instrument_id" in selected.columns:
            selected = selected.filter(
                pl.col("instrument_id").cast(pl.Int64, strict=False)
                == int(instrument_id)
            )
        selected = selected.filter(
            pl.col("event_time").dt.convert_time_zone("Asia/Shanghai").dt.date()
            == date.fromisoformat(trade_date)
        )
        if len(selected) != 1:
            raise _source_error(
                "ETF_PAPER_BAR_AMBIGUOUS", "one exact execution-day bar required"
            )
        return _paper_market_from_row(selected.row(0, named=True), snapshot)


def _paper_market_from_row(
    row: dict[str, object], snapshot: ProviderSnapshot
) -> PaperMarketSnapshotInput:

    def number(name: str, *, positive: bool = True) -> float:
        raw = row.get(name)
        if raw is None:
            raise _source_error("ETF_PAPER_BAR_INVALID", f"{name} is missing")
        try:
            value = float(str(raw))
        except (TypeError, ValueError) as exc:
            raise _source_error("ETF_PAPER_BAR_INVALID", f"{name} is missing") from exc
        if not isfinite(value) or (value <= 0 if positive else value < 0):
            raise _source_error("ETF_PAPER_BAR_INVALID", f"{name} is invalid")
        return value

    def optional_number(name: str) -> float | None:
        if row.get(name) is None:
            return None
        return number(name)

    open_price = number("open")
    high = number("high")
    low = number("low")
    close = number("close")
    prev_close = number("pre_close")
    volume = number("volume", positive=False)
    amount = number("amount", positive=False)
    # The canonical ETF daily producer has no limit columns; callers derive
    # the limits from pre_close and the instrument's price_limit_pct instead.
    limit_up = optional_number("up_limit")
    limit_down = optional_number("down_limit")
    if not low <= min(open_price, close) <= max(open_price, close) <= high:
        raise _source_error("ETF_PAPER_BAR_INVALID", "bar OHLC is inconsistent")
    if limit_up is not None and limit_down is not None and limit_down >= limit_up:
        raise _source_error(
            "ETF_PAPER_BAR_INVALID", "bar price limits are inconsistent"
        )
    raw_suspended = row.get("is_suspended")
    if volume <= 0 or amount <= 0:
        raise _source_error("ETF_PAPER_TRADABILITY_UNKNOWN", "suspension is unverified")
    suspended = raw_suspended is True
    observed_at = cast(datetime, row["event_time"])
    published_at = cast(datetime, row["published_at"])
    available_at = cast(datetime, row["available_at"])
    return PaperMarketSnapshotInput(
        dataset_id="etf_daily",
        source=snapshot.source,
        source_snapshot_id=snapshot.snapshot_id,
        observed_at=observed_at,
        publication_cutoff=max(published_at, available_at, snapshot.created_at),
        open=open_price,
        high=high,
        low=low,
        close=close,
        prev_close=prev_close,
        volume=volume,
        amount=amount,
        is_suspended=suspended,
        limit_up=limit_up,
        limit_down=limit_down,
    )
