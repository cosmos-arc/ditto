"""
Snapshot-backed dependency compatibility checks for materialization.

#394 之后精确来源覆盖来自 completed provider snapshots;catalog 只提供
数据集级 schema/版本描述行。覆盖校验与快照选择基于完成事实,schema
校验基于数据集级 catalog 行。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ditto_data.catalog import DataCatalogEntry, DataCatalogReader
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
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
    """Structured dependency compatibility failure details."""

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


@dataclass(frozen=True)
class DependencyCatalogCompatibilityReport:
    """Successful compatibility proof and selected source provenance."""

    source_snapshot_ids: tuple[str, ...] = ()


class DependencyCatalogCompatibilityError(AppProcessError):
    """Raised when dependency facts cannot prove compatibility."""

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
        message = (
            "dependency compatibility check failed: "
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
            + f"actual_source_snapshot_id={issue.actual_source_snapshot_id}"
        )
        super().__init__(message)


def validate_dependency_catalog_compatibility(
    *,
    contracts: Iterable[DependencyContract],
    catalog_reader: DataCatalogReader,
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    required_dates: Iterable[str] = (),
    expected_source_snapshot_id: str | None = None,
) -> DependencyCatalogCompatibilityReport:
    """Fail closed when dependency contracts cannot be proven satisfied."""
    dates = tuple(dict.fromkeys(required_dates))
    selected_snapshot_ids: list[str] = []
    for contract in contracts:
        entry = _dataset_catalog_entry(catalog_reader, contract)
        _validate_catalog_entry(contract, entry)
        snapshot_ids, missing_dates = _date_coverage(
            snapshots,
            lifecycle,
            contract=contract,
            dates=dates,
        )
        if missing_dates:
            raise DependencyCatalogCompatibilityError(
                DependencyCatalogCompatibilityIssue(
                    dataset_ref=contract.ref.ref,
                    reason="missing_catalog_coverage",
                    catalog_dataset_id=contract.catalog_dataset_id,
                    catalog_namespace=contract.catalog_namespace,
                    missing_dates=missing_dates,
                    expected_schema_version=contract.schema_version,
                    actual_schema_version=entry.schema.schema_version,
                )
            )
        if (
            dates
            and expected_source_snapshot_id is not None
            and expected_source_snapshot_id not in snapshot_ids
        ):
            raise DependencyCatalogCompatibilityError(
                DependencyCatalogCompatibilityIssue(
                    dataset_ref=contract.ref.ref,
                    reason="source_snapshot_mismatch",
                    catalog_dataset_id=contract.catalog_dataset_id,
                    catalog_namespace=contract.catalog_namespace,
                    expected_schema_version=contract.schema_version,
                    actual_schema_version=entry.schema.schema_version,
                    expected_source_snapshot_id=expected_source_snapshot_id,
                    actual_source_snapshot_id=snapshot_ids[0] if snapshot_ids else None,
                )
            )
        selected_snapshot_ids.extend(snapshot_ids)
    return DependencyCatalogCompatibilityReport(
        source_snapshot_ids=tuple(dict.fromkeys(selected_snapshot_ids)),
    )


def _dataset_catalog_entry(
    catalog_reader: DataCatalogReader,
    contract: DependencyContract,
) -> DataCatalogEntry:
    entries = tuple(
        entry
        for entry in catalog_reader.list_assets(namespace=contract.catalog_namespace)
        if entry.asset.dataset_id == contract.catalog_dataset_id
        and not entry.asset.partition_keys
    )
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
    return max(
        entries,
        key=lambda item: (item.freshness_at, item.storage_uri),
    )


def _validate_catalog_entry(
    contract: DependencyContract,
    entry: DataCatalogEntry,
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
    if entry.schema.schema_version != contract.schema_version:
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
    available_columns = entry.schema.columns
    missing_columns = tuple(
        column
        for column in contract.required_frame_columns
        if column not in available_columns
    )
    if missing_columns:
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
    metadata = default_dataset_metadata().get(contract.catalog_dataset_id)
    if metadata is not None and not metadata.supports_source(entry.source):
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


def _contract_snapshots(
    snapshots: ProviderSnapshotReader,
    contract: DependencyContract,
) -> tuple[ProviderSnapshot, ...]:
    return tuple(
        snapshot
        for snapshot in snapshots.list_snapshots(
            dataset_id=contract.catalog_dataset_id,
        )
        if snapshot.canonical_asset.namespace == contract.catalog_namespace
    )


def _date_coverage(
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    *,
    contract: DependencyContract,
    dates: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Selected snapshot IDs covering every date, plus dates left uncovered."""
    completed = tuple(
        snapshot
        for snapshot in _contract_snapshots(snapshots, contract)
        if snapshot_completed(snapshot, lifecycle)
    )
    selected: set[str] = set()
    missing: list[str] = []
    for date in dates:
        covering = [snapshot for snapshot in completed if _covers(snapshot, date)]
        if covering:
            selected.update(snapshot.snapshot_id for snapshot in covering)
        else:
            missing.append(date)
    return tuple(sorted(selected)), tuple(missing)


def _covers(snapshot: ProviderSnapshot, date: str) -> bool:
    # ISO 日期字符串按字典序即时间序。
    return snapshot.request_start <= date <= snapshot.request_end
