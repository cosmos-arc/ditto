"""Schedule-aware catalog coverage facts for R2 data products."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from ditto_data.catalog.contracts import DataCatalogReader
from ditto_data.catalog.metadata import DatasetSchedule, default_dataset_metadata
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

__all__ = [
    "CoverageCollector",
    "CoverageException",
    "DatasetCoverage",
]


@dataclass(frozen=True, slots=True)
class CoverageException:
    """A reviewed gap exception with accountable evidence."""

    code: str
    owner: str
    evidence_uri: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        """Validate exception accountability and interval ordering."""
        for field in ("code", "owner", "evidence_uri"):
            _validate_text(field, str(getattr(self, field)))
        if self.end_date < self.start_date:
            raise ValueError("coverage exception end_date precedes start_date")

    def covers(self, partition_date: date) -> bool:
        """Return whether this approval covers one missing partition."""
        return self.start_date <= partition_date <= self.end_date


@dataclass(frozen=True, slots=True)
class DatasetCoverage:
    """Frozen machine assessment of one dataset interval."""

    dataset_id: str
    schedule: DatasetSchedule
    target_from: date
    target_to: date
    native_from: date | None
    native_to: date | None
    actual_from: date | None
    actual_to: date | None
    raw_from: date | None
    complete_from: date | None
    expected_partitions: int
    actual_partitions: int
    gaps: tuple[date, ...]
    exceptions: tuple[CoverageException, ...]
    collected_at: datetime

    def __post_init__(self) -> None:
        """Validate the frozen coverage fact set."""
        _validate_text("dataset_id", self.dataset_id)
        if self.target_to < self.target_from:
            raise ValueError("coverage target_to precedes target_from")
        if self.expected_partitions < 0 or self.actual_partitions < 0:
            raise ValueError("coverage partition counts cannot be negative")
        if self.actual_partitions > self.expected_partitions:
            raise ValueError("actual partitions exceed expected partitions")
        if len(set(self.gaps)) != len(self.gaps):
            raise ValueError("coverage gaps must be unique")
        if self.collected_at.tzinfo is None:
            raise ValueError("coverage collected_at must be timezone-aware")

    @property
    def unapproved_gaps(self) -> tuple[date, ...]:
        """Return gaps not covered by an accountable reviewed exception."""
        return tuple(
            gap
            for gap in self.gaps
            if not any(exception.covers(gap) for exception in self.exceptions)
        )

    @property
    def is_complete(self) -> bool:
        """Return whether every expected partition exists or is excepted."""
        return self.expected_partitions > 0 and not self.unapproved_gaps


class CoverageCollector:
    """Collect canonical partition coverage against an explicit schedule."""

    def __init__(
        self,
        catalog_reader: DataCatalogReader,
        snapshot_reader: ProviderSnapshotReader | None = None,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._snapshot_reader = snapshot_reader

    def collect(
        self,
        dataset_id: str,
        *,
        target_to: date,
        expected_dates: tuple[date, ...],
        exceptions: tuple[CoverageException, ...] = (),
    ) -> DatasetCoverage:
        """Assess expected versus canonical partitions for one target interval."""
        try:
            metadata = default_dataset_metadata()[dataset_id]
        except KeyError as error:
            raise ValueError(f"unknown dataset: {dataset_id}") from error
        contract = metadata.product_contract
        if contract is None:
            raise ValueError(f"dataset has no product contract: {dataset_id}")
        raw_target = contract.raw_target_from
        if raw_target is None:
            raise ValueError(f"dataset has no R2 raw target: {dataset_id}")
        try:
            target_from = date.fromisoformat(raw_target)
        except ValueError:
            if not expected_dates:
                raise ValueError(
                    f"symbolic coverage target requires expected dates: {dataset_id}"
                ) from None
            target_from = min(expected_dates)
        if target_to < target_from:
            raise ValueError("coverage target_to precedes product target_from")

        expected = tuple(
            sorted(
                {
                    partition_date
                    for partition_date in expected_dates
                    if target_from <= partition_date <= target_to
                }
            )
        )
        actual_dates = self._actual_partition_dates(dataset_id)
        actual = tuple(
            partition_date
            for partition_date in expected
            if partition_date in actual_dates
        )
        gaps = tuple(
            partition_date
            for partition_date in expected
            if partition_date not in actual_dates
        )
        unapproved = tuple(
            gap
            for gap in gaps
            if not any(exception.covers(gap) for exception in exceptions)
        )
        complete_from = _complete_from(expected, unapproved)
        native_from, native_to = self._native_interval(dataset_id)
        return DatasetCoverage(
            dataset_id=dataset_id,
            schedule=metadata.schedule,
            target_from=target_from,
            target_to=target_to,
            native_from=native_from,
            native_to=native_to,
            actual_from=min(actual, default=None),
            actual_to=max(actual, default=None),
            raw_from=min(actual, default=None),
            complete_from=complete_from,
            expected_partitions=len(expected),
            actual_partitions=len(actual),
            gaps=gaps,
            exceptions=exceptions,
            collected_at=datetime.now(UTC),
        )

    def _actual_partition_dates(self, dataset_id: str) -> frozenset[date]:
        contract = default_dataset_metadata()[dataset_id].product_contract
        if contract is None:
            raise ValueError(f"dataset has no product contract: {dataset_id}")
        keys = set(contract.partition_keys)
        dates: set[date] = set()
        for entry in self._catalog_reader.list_assets():
            if entry.asset.dataset_id != dataset_id:
                continue
            for partition in entry.asset.partition_keys:
                key, separator, raw_value = partition.partition("=")
                if separator and key in keys:
                    try:
                        dates.add(date.fromisoformat(raw_value))
                    except ValueError:
                        continue
        return frozenset(dates)

    def _native_interval(self, dataset_id: str) -> tuple[date | None, date | None]:
        if self._snapshot_reader is None:
            return None, None
        snapshots = self._snapshot_reader.list_snapshots(dataset_id=dataset_id)
        starts: list[date] = []
        ends: list[date] = []
        for snapshot in snapshots:
            try:
                starts.append(date.fromisoformat(snapshot.request_start))
                ends.append(date.fromisoformat(snapshot.request_end))
            except ValueError:
                continue
        return min(starts, default=None), max(ends, default=None)


def _complete_from(
    expected: tuple[date, ...],
    unapproved_gaps: tuple[date, ...],
) -> date | None:
    if not expected:
        return None
    if not unapproved_gaps:
        return expected[0]
    final_gap = max(unapproved_gaps)
    return next(
        (partition_date for partition_date in expected if partition_date > final_gap),
        None,
    )


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"invalid coverage {field}: {value!r}")
