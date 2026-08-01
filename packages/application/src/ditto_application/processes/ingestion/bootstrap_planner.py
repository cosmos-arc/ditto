"""Schedule-aware durable bootstrap planning for R2 data products."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Protocol

from ditto_data.catalog import default_dataset_metadata
from ditto_data.ingestion.partition_state import (
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "BootstrapChunk",
    "BootstrapPlan",
    "BootstrapPlanner",
    "SourceScheduleResolver",
]

type BootstrapExecutionMode = Literal["date_range", "instrument_range"]
type SourceScheduleResolver = Callable[[str, str, str, str], tuple[str, ...]]

_EFFECTIVE_DATED_SNAPSHOT_DATASETS = frozenset(
    {"stock_basic", "etf_basic", "index_basic"}
)
_QUERY_CONTRACT_VERSIONS = {
    "corporate_actions": "ann-date-v2",
    "dividend": "ann-date-v2",
}


class _TradingCalendar(Protocol):
    def list_trading_days(self, start: str, end: str) -> list[str]:
        """Return trading dates in an inclusive interval."""
        ...


@dataclass(frozen=True, slots=True)
class BootstrapChunk:
    """One deterministic provider request/checkpoint unit."""

    chunk_id: str
    chunk_key: str
    dataset_id: str
    source: str
    request_start: str
    request_end: str
    partition_dates: tuple[str, ...]
    execution_mode: BootstrapExecutionMode
    instrument_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class BootstrapPlan:
    """Pending chunks and already-complete checkpoints for one target interval."""

    dataset_id: str
    source: str
    target_start: str
    target_end: str
    chunks: tuple[BootstrapChunk, ...]
    skipped_complete_chunk_ids: tuple[str, ...] = ()

    @property
    def expected_partition_count(self) -> int:
        """Return the partition count still requiring work."""
        return sum(len(chunk.partition_dates) for chunk in self.chunks)


class BootstrapPlanner:
    """Build schedule/chunk/capability-aware bootstrap checkpoints."""

    def __init__(
        self,
        *,
        metadata_service: _TradingCalendar,
        source_schedule_resolver: SourceScheduleResolver | None = None,
        partition_lifecycle_reader: PartitionLifecycleReader | None = None,
    ) -> None:
        self._metadata_service = metadata_service
        self._source_schedule_resolver = source_schedule_resolver
        self._partition_lifecycle_reader = partition_lifecycle_reader

    def plan(
        self,
        *,
        dataset_id: str,
        source: str,
        start_date: str,
        end_date: str,
        instrument_ids: tuple[int, ...] = (),
    ) -> BootstrapPlan:
        """Build deterministic pending chunks for one data product interval."""
        start, end = _validated_interval(start_date, end_date)
        try:
            metadata = default_dataset_metadata()[dataset_id]
        except KeyError:
            raise AppProcessError(f"unknown bootstrap dataset: {dataset_id}") from None
        if source not in metadata.supported_sources:
            raise AppProcessError(
                f"unsupported bootstrap source {source!r} for {dataset_id!r}"
            )
        normalized_instruments = tuple(sorted(set(instrument_ids)))
        if normalized_instruments and not metadata.supports_instrument_ingestion:
            raise AppProcessError(
                f"dataset does not support instrument bootstrap: {dataset_id}"
            )

        execution_mode: BootstrapExecutionMode = (
            "instrument_range" if normalized_instruments else "date_range"
        )
        product_contract = metadata.product_contract
        if product_contract is None:
            raise AppProcessError(f"dataset has no bootstrap contract: {dataset_id}")
        all_chunks = self._base_chunks(
            dataset_id=dataset_id,
            source=source,
            interval=(start.isoformat(), end.isoformat()),
            schedule=metadata.schedule,
            chunk_policy=(
                "year" if normalized_instruments else product_contract.bootstrap_chunk
            ),
            execution_mode=execution_mode,
            instrument_ids=normalized_instruments,
        )

        all_chunks = tuple(
            _bind_query_contract(chunk, dataset_id) for chunk in all_chunks
        )
        if normalized_instruments:
            all_chunks = tuple(
                _instrument_chunk(chunk, instrument_id)
                for chunk in all_chunks
                for instrument_id in normalized_instruments
            )

        pending: list[BootstrapChunk] = []
        skipped: list[str] = []
        for chunk in all_chunks:
            checkpoint = (
                self._partition_lifecycle_reader.get_checkpoint(chunk.chunk_id)
                if self._partition_lifecycle_reader is not None
                else None
            )
            if (
                checkpoint is not None
                and checkpoint.status is PartitionLifecycleStatus.COMPLETE
            ):
                skipped.append(chunk.chunk_id)
            else:
                pending.append(chunk)
        return BootstrapPlan(
            dataset_id=dataset_id,
            source=source,
            target_start=start.isoformat(),
            target_end=end.isoformat(),
            chunks=tuple(pending),
            skipped_complete_chunk_ids=tuple(skipped),
        )

    def _base_chunks(
        self,
        *,
        dataset_id: str,
        source: str,
        interval: tuple[str, str],
        schedule: str,
        chunk_policy: str,
        execution_mode: BootstrapExecutionMode,
        instrument_ids: tuple[int, ...],
    ) -> tuple[BootstrapChunk, ...]:
        """Build unversioned chunks before resume and instrument expansion."""
        start_date, end_date = interval
        intervals = _annual_intervals(start_date, end_date)
        if dataset_id == "calendar":
            return tuple(
                _calendar_range_chunk(
                    source=source,
                    start_date=range_start,
                    end_date=range_end,
                )
                for range_start, range_end in intervals
            )
        if dataset_id in _EFFECTIVE_DATED_SNAPSHOT_DATASETS:
            return (
                _effective_dated_snapshot_chunk(
                    dataset_id=dataset_id,
                    source=source,
                    start_date=start_date,
                    end_date=end_date,
                    execution_mode=execution_mode,
                    instrument_ids=instrument_ids,
                ),
            )
        if schedule == "source_defined" and self._source_schedule_resolver is None:
            return tuple(
                _source_defined_range_chunk(
                    dataset_id=dataset_id,
                    source=source,
                    start_date=range_start,
                    end_date=range_end,
                    execution_mode=execution_mode,
                    instrument_ids=instrument_ids,
                )
                for range_start, range_end in intervals
            )
        partitions = self._expected_partitions(
            dataset_id=dataset_id,
            source=source,
            start_date=start_date,
            end_date=end_date,
            schedule=schedule,
        )
        return tuple(
            _build_chunk(
                dataset_id=dataset_id,
                source=source,
                chunk_key=chunk_key,
                partition_dates=partition_dates,
                execution_mode=execution_mode,
                instrument_ids=instrument_ids,
            )
            for chunk_key, partition_dates in _group_partitions(
                partitions,
                chunk_policy,
            )
        )

    def _expected_partitions(
        self,
        *,
        dataset_id: str,
        source: str,
        start_date: str,
        end_date: str,
        schedule: str,
    ) -> tuple[str, ...]:
        if dataset_id == "calendar":
            raw = _annual_request_anchors(start_date, end_date)
        elif dataset_id in _EFFECTIVE_DATED_SNAPSHOT_DATASETS:
            raw = (end_date,)
        elif schedule == "trading_days":
            raw = tuple(self._metadata_service.list_trading_days(start_date, end_date))
        elif schedule == "natural_days":
            raw = _natural_days(start_date, end_date)
        elif self._source_schedule_resolver is not None:
            raw = self._source_schedule_resolver(
                dataset_id,
                source,
                start_date,
                end_date,
            )
        else:
            raw = ()
        return _validated_partitions(raw, start_date=start_date, end_date=end_date)


def _annual_request_anchors(start_date: str, end_date: str) -> tuple[str, ...]:
    """Return one calendar-provider request anchor for every intersected year."""
    start, end = _validated_interval(start_date, end_date)
    return tuple(
        min(date(year, 12, 31), end).isoformat()
        for year in range(start.year, end.year + 1)
    )


def _annual_intervals(
    start_date: str,
    end_date: str,
) -> tuple[tuple[str, str], ...]:
    """Split a provider range into bounded calendar-year requests."""
    start, end = _validated_interval(start_date, end_date)
    return tuple(
        (
            max(start, date(year, 1, 1)).isoformat(),
            min(end, date(year, 12, 31)).isoformat(),
        )
        for year in range(start.year, end.year + 1)
    )


def _calendar_range_chunk(
    *,
    source: str,
    start_date: str,
    end_date: str,
) -> BootstrapChunk:
    """Bind a year-anchor provider call to the full returned calendar interval."""
    year = start_date[:4]
    return BootstrapChunk(
        chunk_id=f"chunk:{source}:calendar:{year}:{start_date}:{end_date}",
        chunk_key=year,
        dataset_id="calendar",
        source=source,
        request_start=start_date,
        request_end=end_date,
        partition_dates=(end_date,),
        execution_mode="date_range",
        instrument_ids=(),
    )


def _validated_interval(start_date: str, end_date: str) -> tuple[date, date]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise AppProcessError("bootstrap end_date precedes start_date")
    return start, end


def _natural_days(start_date: str, end_date: str) -> tuple[str, ...]:
    start, end = _validated_interval(start_date, end_date)
    result: list[str] = []
    current = start
    while current <= end:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(result)


def _validated_partitions(
    partitions: tuple[str, ...],
    *,
    start_date: str,
    end_date: str,
) -> tuple[str, ...]:
    start, end = _validated_interval(start_date, end_date)
    normalized: set[str] = set()
    for value in partitions:
        partition_date = date.fromisoformat(value)
        if partition_date < start or partition_date > end:
            raise AppProcessError(f"source partition outside target interval: {value}")
        normalized.add(partition_date.isoformat())
    return tuple(sorted(normalized))


def _chunk_key(partition_date: str, chunk_policy: str) -> str:
    value = date.fromisoformat(partition_date)
    if chunk_policy == "month":
        return f"{value.year:04d}-{value.month:02d}"
    if chunk_policy == "quarter":
        return f"{value.year:04d}-Q{((value.month - 1) // 3) + 1}"
    if chunk_policy == "year":
        return f"{value.year:04d}"
    return f"source:{partition_date}"


def _group_partitions(
    partitions: tuple[str, ...],
    chunk_policy: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for partition_date in partitions:
        grouped[_chunk_key(partition_date, chunk_policy)].append(partition_date)
    return tuple((key, tuple(values)) for key, values in sorted(grouped.items()))


def _build_chunk(
    *,
    dataset_id: str,
    source: str,
    chunk_key: str,
    partition_dates: tuple[str, ...],
    execution_mode: BootstrapExecutionMode,
    instrument_ids: tuple[int, ...],
) -> BootstrapChunk:
    request_start = partition_dates[0]
    request_end = partition_dates[-1]
    chunk_id = f"chunk:{source}:{dataset_id}:{chunk_key}:{request_start}:{request_end}"
    return BootstrapChunk(
        chunk_id=chunk_id,
        chunk_key=chunk_key,
        dataset_id=dataset_id,
        source=source,
        request_start=request_start,
        request_end=request_end,
        partition_dates=partition_dates,
        execution_mode=execution_mode,
        instrument_ids=instrument_ids,
    )


def _instrument_chunk(
    chunk: BootstrapChunk,
    instrument_id: int,
) -> BootstrapChunk:
    """Expand a range chunk into one independently resumable instrument request."""
    return BootstrapChunk(
        chunk_id=f"{chunk.chunk_id}:instrument:{instrument_id}",
        chunk_key=f"{chunk.chunk_key}:instrument:{instrument_id}",
        dataset_id=chunk.dataset_id,
        source=chunk.source,
        request_start=chunk.request_start,
        request_end=chunk.request_end,
        partition_dates=chunk.partition_dates,
        execution_mode="instrument_range",
        instrument_ids=(instrument_id,),
    )


def _bind_query_contract(
    chunk: BootstrapChunk,
    dataset_id: str,
) -> BootstrapChunk:
    """Bind provider query semantics into resumable chunk identity."""
    version = _QUERY_CONTRACT_VERSIONS.get(dataset_id)
    if version is None:
        return chunk
    suffix = f":query:{version}"
    return BootstrapChunk(
        chunk_id=f"{chunk.chunk_id}{suffix}",
        chunk_key=f"{chunk.chunk_key}{suffix}",
        dataset_id=chunk.dataset_id,
        source=chunk.source,
        request_start=chunk.request_start,
        request_end=chunk.request_end,
        partition_dates=chunk.partition_dates,
        execution_mode=chunk.execution_mode,
        instrument_ids=chunk.instrument_ids,
    )


def _source_defined_range_chunk(
    *,
    dataset_id: str,
    source: str,
    start_date: str,
    end_date: str,
    execution_mode: BootstrapExecutionMode,
    instrument_ids: tuple[int, ...],
) -> BootstrapChunk:
    chunk_key = f"source:{start_date}:{end_date}"
    return BootstrapChunk(
        chunk_id=f"chunk:{source}:{dataset_id}:{chunk_key}",
        chunk_key=chunk_key,
        dataset_id=dataset_id,
        source=source,
        request_start=start_date,
        request_end=end_date,
        partition_dates=(end_date,),
        execution_mode=execution_mode,
        instrument_ids=instrument_ids,
    )


def _effective_dated_snapshot_chunk(
    *,
    dataset_id: str,
    source: str,
    start_date: str,
    end_date: str,
    execution_mode: BootstrapExecutionMode,
    instrument_ids: tuple[int, ...],
) -> BootstrapChunk:
    """Use one current snapshot whose effective dates reconstruct the target range."""
    chunk_key = f"effective:{start_date}:{end_date}"
    return BootstrapChunk(
        chunk_id=f"chunk:{source}:{dataset_id}:{chunk_key}",
        chunk_key=chunk_key,
        dataset_id=dataset_id,
        source=source,
        request_start=start_date,
        request_end=end_date,
        partition_dates=(end_date,),
        execution_mode=execution_mode,
        instrument_ids=instrument_ids,
    )
