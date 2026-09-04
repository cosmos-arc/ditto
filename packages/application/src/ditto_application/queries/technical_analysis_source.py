"""Technical bars loaded from exact immutable provider payloads."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import cast
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

__all__ = ["ProviderPayloadTechnicalAnalysisSource"]

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_COMPACT_DATE_LENGTH = 8


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
    instrument_code: str,
) -> pl.DataFrame:
    filters: list[pl.Expr] = []
    if "instrument_id" in frame.columns:
        filters.append(
            pl.col("instrument_id").cast(pl.Int64, strict=False) == int(instrument_id)
        )
    for column in ("source_ticker", "instrument_code", "ts_code", "ticker"):
        if column in frame.columns:
            filters.append(pl.col(column).cast(pl.String) == instrument_code)
    if not filters:
        raise _source_error(
            "TECHNICAL_SOURCE_IDENTITY_REQUIRED",
            "instrument_identity_column_missing",
        )
    expression = filters[0]
    for item in filters[1:]:
        expression |= item
    return frame.filter(expression)


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
        instrument_code: str,
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
