"""DataCatalog-backed dependency compatibility checks for materialization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ditto_data.catalog import DataCatalogEntry, DataCatalogReader
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_features.materialization.dependency_registry import DependencyContract

from ditto_application.exceptions import AppProcessError

__all__ = [
    "DependencyCatalogCompatibilityError",
    "DependencyCatalogCompatibilityIssue",
    "DependencyCatalogCompatibilityReport",
    "validate_dependency_catalog_compatibility",
]


@dataclass(frozen=True)
class DependencyCatalogCompatibilityIssue:
    """Structured DataCatalog compatibility failure details."""

    dataset_ref: str
    reason: str
    catalog_dataset_id: str
    catalog_namespace: str
    missing_columns: tuple[str, ...] = ()
    missing_dates: tuple[str, ...] = ()
    available_columns: tuple[str, ...] = ()
    expected_schema_version: str | None = None
    actual_schema_version: str | None = None
    source: str | None = None
    expected_source_snapshot_id: str | None = None
    actual_source_snapshot_id: str | None = None
    missing_source_ticker_dates: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependencyCatalogCompatibilityReport:
    """Successful catalog compatibility proof and selected source provenance."""

    source_snapshot_ids: tuple[str, ...] = ()


class DependencyCatalogCompatibilityError(AppProcessError):
    """Raised when DataCatalog metadata cannot prove dependency compatibility."""

    def __init__(self, issue: DependencyCatalogCompatibilityIssue) -> None:
        self.issue = issue
        self.dataset_ref = issue.dataset_ref
        self.reason = issue.reason
        self.catalog_dataset_id = issue.catalog_dataset_id
        self.catalog_namespace = issue.catalog_namespace
        self.missing_columns = issue.missing_columns
        self.missing_dates = issue.missing_dates
        self.available_columns = issue.available_columns
        self.expected_schema_version = issue.expected_schema_version
        self.actual_schema_version = issue.actual_schema_version
        self.source = issue.source
        self.expected_source_snapshot_id = issue.expected_source_snapshot_id
        self.actual_source_snapshot_id = issue.actual_source_snapshot_id
        self.missing_source_ticker_dates = issue.missing_source_ticker_dates
        message = (
            "DataCatalog dependency compatibility check failed: "
            + f"dataset_ref={issue.dataset_ref}, reason={issue.reason}, "
            + "catalog_asset="
            + f"{issue.catalog_namespace}.{issue.catalog_dataset_id}, "
            + f"missing_columns={list(issue.missing_columns)}, "
            + f"missing_dates={list(issue.missing_dates)}, "
            + f"available_columns={list(issue.available_columns)}, "
            + f"expected_schema_version={issue.expected_schema_version}, "
            + f"actual_schema_version={issue.actual_schema_version}, "
            + f"source={issue.source}, "
            + "expected_source_snapshot_id="
            + f"{issue.expected_source_snapshot_id}, "
            + "actual_source_snapshot_id="
            + f"{issue.actual_source_snapshot_id}, "
            + "missing_source_ticker_dates="
            + f"{list(issue.missing_source_ticker_dates)}"
        )
        super().__init__(message)


def validate_dependency_catalog_compatibility(
    *,
    contracts: Iterable[DependencyContract],
    catalog_reader: DataCatalogReader,
    required_dates: Iterable[str] = (),
    expected_source_snapshot_id: str | None = None,
    required_source_tickers: Iterable[str] = (),
    required_source_tickers_by_date: Mapping[str, Iterable[str]] | None = None,
    required_source_tickers_by_date_by_ref: (
        Mapping[str, Mapping[str, Iterable[str]]] | None
    ) = None,
) -> DependencyCatalogCompatibilityReport:
    """Fail closed when catalog metadata cannot satisfy dependency contracts."""
    dates = tuple(dict.fromkeys(required_dates))
    source_tickers = tuple(dict.fromkeys(required_source_tickers))
    source_tickers_by_date = _normalize_source_tickers_by_date(
        required_source_tickers_by_date or {},
    )
    source_tickers_by_date_by_ref = {
        dependency_ref: _normalize_source_tickers_by_date(tickers_by_date)
        for dependency_ref, tickers_by_date in (
            required_source_tickers_by_date_by_ref or {}
        ).items()
    }
    selected_entries: list[DataCatalogEntry] = []
    for contract in contracts:
        entries = _catalog_entries(catalog_reader, contract)
        if not entries:
            raise DependencyCatalogCompatibilityError(
                DependencyCatalogCompatibilityIssue(
                    dataset_ref=contract.ref.ref,
                    reason="missing_catalog_asset",
                    catalog_dataset_id=contract.catalog_dataset_id,
                    catalog_namespace=contract.catalog_namespace,
                    expected_schema_version=contract.schema_version,
                )
            )
        contract_source_tickers_by_date = (
            source_tickers_by_date_by_ref.get(contract.ref.ref)
            or source_tickers_by_date
        )
        if contract_source_tickers_by_date:
            selected_entries.extend(
                _validate_source_ticker_coverage_by_date(
                    contract=contract,
                    entries=entries,
                    source_tickers_by_date=contract_source_tickers_by_date,
                    expected_source_snapshot_id=expected_source_snapshot_id,
                )
            )
            continue
        if dates and source_tickers:
            selected_entries.extend(
                _validate_source_ticker_coverage(
                    contract=contract,
                    entries=entries,
                    dates=dates,
                    source_tickers=source_tickers,
                    expected_source_snapshot_id=expected_source_snapshot_id,
                )
            )
            continue
        if source_tickers:
            selected_entries.extend(
                _validate_source_ticker_latest(
                    contract=contract,
                    entries=entries,
                    source_tickers=source_tickers,
                    expected_source_snapshot_id=expected_source_snapshot_id,
                )
            )
            continue
        if dates:
            selected_entries.extend(
                _validate_catalog_coverage(
                    contract=contract,
                    entries=entries,
                    dates=dates,
                    expected_source_snapshot_id=expected_source_snapshot_id,
                )
            )
            continue
        selected_entry = _latest_catalog_entry(entries)
        _validate_catalog_entry(
            contract,
            selected_entry,
            expected_source_snapshot_id=expected_source_snapshot_id,
        )
        selected_entries.append(selected_entry)
    return DependencyCatalogCompatibilityReport(
        source_snapshot_ids=_source_snapshot_ids(selected_entries)
    )


def _normalize_source_tickers_by_date(
    source_tickers_by_date: Mapping[str, Iterable[str]],
) -> dict[str, tuple[str, ...]]:
    return {
        date: tuple(dict.fromkeys(source_tickers))
        for date, source_tickers in source_tickers_by_date.items()
    }


def _catalog_entries(
    catalog_reader: DataCatalogReader,
    contract: DependencyContract,
) -> tuple[DataCatalogEntry, ...]:
    return tuple(
        entry
        for entry in catalog_reader.list_assets(namespace=contract.catalog_namespace)
        if entry.asset.dataset_id == contract.catalog_dataset_id
    )


def _latest_catalog_entry(entries: tuple[DataCatalogEntry, ...]) -> DataCatalogEntry:
    return max(
        entries,
        key=_catalog_entry_sort_key,
    )


def _validate_catalog_coverage(
    *,
    contract: DependencyContract,
    entries: tuple[DataCatalogEntry, ...],
    dates: tuple[str, ...],
    expected_source_snapshot_id: str | None,
) -> tuple[DataCatalogEntry, ...]:
    selected_entries: list[DataCatalogEntry] = []
    missing_dates: list[str] = []
    for date in dates:
        covering_entries = tuple(
            entry for entry in entries if _entry_covers_date(entry, date)
        )
        if not covering_entries:
            missing_dates.append(date)
            continue
        selected_entries.append(_latest_catalog_entry(covering_entries))

    if missing_dates:
        raise DependencyCatalogCompatibilityError(
            DependencyCatalogCompatibilityIssue(
                dataset_ref=contract.ref.ref,
                reason="missing_catalog_coverage",
                catalog_dataset_id=contract.catalog_dataset_id,
                catalog_namespace=contract.catalog_namespace,
                missing_dates=tuple(missing_dates),
                expected_schema_version=contract.schema_version,
            )
        )
    for entry in _dedupe_entries(selected_entries):
        _validate_catalog_entry(
            contract,
            entry,
            expected_source_snapshot_id=expected_source_snapshot_id,
        )
    return _dedupe_entries(selected_entries)


def _validate_source_ticker_coverage(
    *,
    contract: DependencyContract,
    entries: tuple[DataCatalogEntry, ...],
    dates: tuple[str, ...],
    source_tickers: tuple[str, ...],
    expected_source_snapshot_id: str | None,
) -> tuple[DataCatalogEntry, ...]:
    selected_entries: list[DataCatalogEntry] = []
    missing_source_ticker_dates: list[str] = []
    for source_ticker in source_tickers:
        for date in dates:
            covering_entries = tuple(
                entry
                for entry in entries
                if _entry_covers_date(
                    entry,
                    date,
                    required_source_ticker=source_ticker,
                )
            )
            if not covering_entries:
                missing_source_ticker_dates.append(f"{source_ticker}@{date}")
                continue
            selected_entries.append(_latest_catalog_entry(covering_entries))

    if missing_source_ticker_dates:
        raise DependencyCatalogCompatibilityError(
            DependencyCatalogCompatibilityIssue(
                dataset_ref=contract.ref.ref,
                reason="missing_source_ticker_coverage",
                catalog_dataset_id=contract.catalog_dataset_id,
                catalog_namespace=contract.catalog_namespace,
                expected_schema_version=contract.schema_version,
                missing_source_ticker_dates=tuple(missing_source_ticker_dates),
            )
        )
    for entry in _dedupe_entries(selected_entries):
        _validate_catalog_entry(
            contract,
            entry,
            expected_source_snapshot_id=expected_source_snapshot_id,
        )
    return _dedupe_entries(selected_entries)


def _validate_source_ticker_coverage_by_date(
    *,
    contract: DependencyContract,
    entries: tuple[DataCatalogEntry, ...],
    source_tickers_by_date: Mapping[str, tuple[str, ...]],
    expected_source_snapshot_id: str | None,
) -> tuple[DataCatalogEntry, ...]:
    selected_entries: list[DataCatalogEntry] = []
    missing_source_ticker_dates: list[str] = []
    for date, source_tickers in source_tickers_by_date.items():
        for source_ticker in source_tickers:
            covering_entries = tuple(
                entry
                for entry in entries
                if _entry_covers_date(
                    entry,
                    date,
                    required_source_ticker=source_ticker,
                )
            )
            if not covering_entries:
                missing_source_ticker_dates.append(f"{source_ticker}@{date}")
                continue
            selected_entries.append(_latest_catalog_entry(covering_entries))

    if missing_source_ticker_dates:
        raise DependencyCatalogCompatibilityError(
            DependencyCatalogCompatibilityIssue(
                dataset_ref=contract.ref.ref,
                reason="missing_source_ticker_coverage",
                catalog_dataset_id=contract.catalog_dataset_id,
                catalog_namespace=contract.catalog_namespace,
                expected_schema_version=contract.schema_version,
                missing_source_ticker_dates=tuple(missing_source_ticker_dates),
            )
        )
    for entry in _dedupe_entries(selected_entries):
        _validate_catalog_entry(
            contract,
            entry,
            expected_source_snapshot_id=expected_source_snapshot_id,
        )
    return _dedupe_entries(selected_entries)


def _validate_source_ticker_latest(
    *,
    contract: DependencyContract,
    entries: tuple[DataCatalogEntry, ...],
    source_tickers: tuple[str, ...],
    expected_source_snapshot_id: str | None,
) -> tuple[DataCatalogEntry, ...]:
    selected_entries: list[DataCatalogEntry] = []
    missing_source_tickers: list[str] = []
    for source_ticker in source_tickers:
        matching_entries = tuple(
            entry for entry in entries if _entry_source_ticker(entry) == source_ticker
        )
        if not matching_entries:
            missing_source_tickers.append(f"{source_ticker}@latest")
            continue
        selected_entries.append(_latest_catalog_entry(matching_entries))

    if missing_source_tickers:
        raise DependencyCatalogCompatibilityError(
            DependencyCatalogCompatibilityIssue(
                dataset_ref=contract.ref.ref,
                reason="missing_source_ticker_coverage",
                catalog_dataset_id=contract.catalog_dataset_id,
                catalog_namespace=contract.catalog_namespace,
                expected_schema_version=contract.schema_version,
                missing_source_ticker_dates=tuple(missing_source_tickers),
            )
        )
    for entry in _dedupe_entries(selected_entries):
        _validate_catalog_entry(
            contract,
            entry,
            expected_source_snapshot_id=expected_source_snapshot_id,
        )
    return _dedupe_entries(selected_entries)


def _validate_catalog_entry(
    contract: DependencyContract,
    entry: DataCatalogEntry,
    *,
    expected_source_snapshot_id: str | None,
) -> None:
    if not entry.schema.schema_version:
        raise DependencyCatalogCompatibilityError(
            DependencyCatalogCompatibilityIssue(
                dataset_ref=contract.ref.ref,
                reason="missing_schema_version",
                catalog_dataset_id=contract.catalog_dataset_id,
                catalog_namespace=contract.catalog_namespace,
                expected_schema_version=contract.schema_version,
                actual_schema_version=entry.schema.schema_version,
                source=entry.source,
            )
        )
    _validate_schema_version(contract, entry)
    _validate_schema_columns(contract, entry)
    _validate_source(contract, entry)
    _validate_source_snapshot(contract, entry, expected_source_snapshot_id)


def _validate_source_snapshot(
    contract: DependencyContract,
    entry: DataCatalogEntry,
    expected_source_snapshot_id: str | None,
) -> None:
    if expected_source_snapshot_id is None:
        return
    if entry.source_snapshot_id == expected_source_snapshot_id:
        return
    reason = (
        "missing_source_snapshot_id"
        if entry.source_snapshot_id is None
        else "source_snapshot_mismatch"
    )
    raise DependencyCatalogCompatibilityError(
        DependencyCatalogCompatibilityIssue(
            dataset_ref=contract.ref.ref,
            reason=reason,
            catalog_dataset_id=contract.catalog_dataset_id,
            catalog_namespace=contract.catalog_namespace,
            expected_schema_version=contract.schema_version,
            actual_schema_version=entry.schema.schema_version,
            source=entry.source,
            expected_source_snapshot_id=expected_source_snapshot_id,
            actual_source_snapshot_id=entry.source_snapshot_id,
        )
    )


def _validate_schema_version(
    contract: DependencyContract,
    entry: DataCatalogEntry,
) -> None:
    if entry.schema.schema_version == contract.schema_version:
        return
    raise DependencyCatalogCompatibilityError(
        DependencyCatalogCompatibilityIssue(
            dataset_ref=contract.ref.ref,
            reason="schema_version_mismatch",
            catalog_dataset_id=contract.catalog_dataset_id,
            catalog_namespace=contract.catalog_namespace,
            expected_schema_version=contract.schema_version,
            actual_schema_version=entry.schema.schema_version,
            source=entry.source,
        )
    )


def _validate_schema_columns(
    contract: DependencyContract,
    entry: DataCatalogEntry,
) -> None:
    available_columns = entry.schema.columns
    missing_columns = tuple(
        column
        for column in contract.required_frame_columns
        if column not in available_columns
    )
    if not missing_columns:
        return
    raise DependencyCatalogCompatibilityError(
        DependencyCatalogCompatibilityIssue(
            dataset_ref=contract.ref.ref,
            reason="schema_columns_mismatch",
            catalog_dataset_id=contract.catalog_dataset_id,
            catalog_namespace=contract.catalog_namespace,
            missing_columns=missing_columns,
            available_columns=available_columns,
            expected_schema_version=contract.schema_version,
            actual_schema_version=entry.schema.schema_version,
            source=entry.source,
        )
    )


def _validate_source(
    contract: DependencyContract,
    entry: DataCatalogEntry,
) -> None:
    metadata = default_dataset_metadata().get(contract.catalog_dataset_id)
    if metadata is None or metadata.supports_source(entry.source):
        return
    raise DependencyCatalogCompatibilityError(
        DependencyCatalogCompatibilityIssue(
            dataset_ref=contract.ref.ref,
            reason="unsupported_source",
            catalog_dataset_id=contract.catalog_dataset_id,
            catalog_namespace=contract.catalog_namespace,
            expected_schema_version=contract.schema_version,
            actual_schema_version=entry.schema.schema_version,
            source=entry.source,
        )
    )


def _entry_covers_date(
    entry: DataCatalogEntry,
    date: str,
    *,
    required_source_ticker: str | None = None,
) -> bool:
    partition = _partition_dict(entry.asset.partition_keys)
    source_ticker = partition.get("source_ticker")
    if required_source_ticker is not None:
        if source_ticker != required_source_ticker:
            return False
    elif source_ticker is not None:
        return False
    trade_date = partition.get("trade_date")
    if trade_date is not None:
        return trade_date == date
    start_date = partition.get("start_date")
    end_date = partition.get("end_date")
    if start_date is None or end_date is None:
        return False
    return start_date <= date <= end_date


def _entry_source_ticker(entry: DataCatalogEntry) -> str | None:
    return _partition_dict(entry.asset.partition_keys).get("source_ticker")


def _partition_dict(partition_keys: tuple[str, ...]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key in partition_keys:
        if "=" not in key:
            continue
        name, value = key.split("=", maxsplit=1)
        parsed[name] = value
    return parsed


def _catalog_entry_sort_key(
    entry: DataCatalogEntry,
) -> tuple[object, str, tuple[str, ...]]:
    return (entry.freshness_at, entry.storage_uri, entry.asset.partition_keys)


def _dedupe_entries(
    entries: Iterable[DataCatalogEntry],
) -> tuple[DataCatalogEntry, ...]:
    return tuple(dict.fromkeys(entries))


def _source_snapshot_ids(entries: Iterable[DataCatalogEntry]) -> tuple[str, ...]:
    snapshot_ids = {
        entry.source_snapshot_id
        for entry in entries
        if entry.source_snapshot_id is not None and entry.source_snapshot_id != ""
    }
    return tuple(sorted(snapshot_ids))
