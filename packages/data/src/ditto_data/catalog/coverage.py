"""Schedule-aware catalog coverage facts for R2 data products."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from ditto_data.catalog.contracts import DataAssetRef, DataCatalogReader
from ditto_data.catalog.metadata import DatasetSchedule, default_dataset_metadata
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader

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
        snapshot_ids: frozenset[str] | None = None,
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
        actual_dates = self._actual_partition_dates(
            dataset_id,
            expected_dates=frozenset(expected),
            snapshot_ids=snapshot_ids,
        )
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
        complete_from = _complete_from(
            target_from=target_from,
            expected=expected,
            unapproved_gaps=unapproved,
        )
        native_from, native_to = self._native_interval(
            dataset_id,
            snapshot_ids=snapshot_ids,
        )
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

    def _actual_partition_dates(
        self,
        dataset_id: str,
        *,
        expected_dates: frozenset[date],
        snapshot_ids: frozenset[str] | None,
    ) -> frozenset[date]:
        contract = default_dataset_metadata()[dataset_id].product_contract
        if contract is None:
            raise ValueError(f"dataset has no product contract: {dataset_id}")
        keys = frozenset(contract.partition_keys)
        dates: set[date] = set()
        selected_snapshots = self._selected_snapshots(
            dataset_id,
            snapshot_ids=snapshot_ids,
        )
        allowed_assets = (
            None
            if snapshot_ids is None
            else {snapshot.canonical_asset for snapshot in selected_snapshots}
        )
        canonical_assets: set[DataAssetRef] = set()
        for entry in self._catalog_reader.list_assets():
            if entry.asset.dataset_id != dataset_id:
                continue
            if allowed_assets is not None and entry.asset not in allowed_assets:
                continue
            canonical_assets.add(entry.asset)
            dates.update(
                _asset_partition_dates(
                    entry.asset.partition_keys,
                    contract_keys=keys,
                    expected_dates=expected_dates,
                )
            )
        for snapshot in selected_snapshots:
            if snapshot.canonical_asset in canonical_assets:
                dates.update(
                    _expected_dates_in_interval(
                        snapshot.request_start,
                        snapshot.request_end,
                        expected_dates=expected_dates,
                    )
                )
        return frozenset(dates)

    def _selected_snapshots(
        self,
        dataset_id: str,
        *,
        snapshot_ids: frozenset[str] | None,
    ) -> tuple[ProviderSnapshot, ...]:
        if self._snapshot_reader is None:
            return ()
        return tuple(
            snapshot
            for snapshot in self._snapshot_reader.list_snapshots(dataset_id=dataset_id)
            if snapshot_ids is None or snapshot.snapshot_id in snapshot_ids
        )

    def _native_interval(
        self,
        dataset_id: str,
        *,
        snapshot_ids: frozenset[str] | None,
    ) -> tuple[date | None, date | None]:
        if self._snapshot_reader is None:
            return None, None
        snapshots = tuple(
            snapshot
            for snapshot in self._snapshot_reader.list_snapshots(dataset_id=dataset_id)
            if snapshot_ids is None or snapshot.snapshot_id in snapshot_ids
        )
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
    *,
    target_from: date,
    expected: tuple[date, ...],
    unapproved_gaps: tuple[date, ...],
) -> date | None:
    if not expected:
        return None
    if not unapproved_gaps:
        return target_from
    final_gap = max(unapproved_gaps)
    return next(
        (partition_date for partition_date in expected if partition_date > final_gap),
        None,
    )


def _asset_partition_dates(
    partition_keys: tuple[str, ...],
    *,
    contract_keys: frozenset[str],
    expected_dates: frozenset[date],
) -> frozenset[date]:
    values: dict[str, str] = {}
    for partition in partition_keys:
        key, separator, raw_value = partition.partition("=")
        if separator:
            values[key] = raw_value
    dates = {
        parsed
        for key, raw_value in values.items()
        if key in contract_keys
        if (parsed := _optional_iso_date(raw_value)) is not None
    }
    raw_start = values.get("start_date")
    raw_end = values.get("end_date")
    if raw_start is not None and raw_end is not None:
        dates.update(
            _expected_dates_in_interval(
                raw_start,
                raw_end,
                expected_dates=expected_dates,
            )
        )
    return frozenset(dates)


def _expected_dates_in_interval(
    raw_start: str,
    raw_end: str,
    *,
    expected_dates: frozenset[date],
) -> frozenset[date]:
    start = _optional_iso_date(raw_start)
    end = _optional_iso_date(raw_end)
    if start is None or end is None or end < start:
        return frozenset()
    return frozenset(
        expected_date
        for expected_date in expected_dates
        if start <= expected_date <= end
    )


def _optional_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"invalid coverage {field}: {value!r}")
