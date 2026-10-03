"""
Dataset-level catalog freshness and provider-snapshot completion policies.

#394 之后精确来源覆盖不再住在 catalog 分区行里:一个 (dataset, source, date)
是否已被摄取完成,由「存在覆盖该日期的 completed provider snapshot」判定;
catalog 只保留数据集级描述行。本模块是这两类事实的应用层策略家。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Literal, Protocol

import orjson
from ditto_data.catalog import (
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)
from ditto_data.catalog.snapshot_completion import (
    canonical_write_identity,
    snapshot_completed,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.models.ingestion import IngestionLog, IngestionStatus

type CatalogFreshnessStatus = Literal[
    "fresh",
    "stale",
    "missing",
    "not_applicable",
]

__all__ = [
    "CatalogAsOfSnapshot",
    "CatalogFreshnessAssessment",
    "CatalogFreshnessStatus",
    "PersistedIngestionEvidenceVerifier",
    "SourceCoverageEvidence",
    "aggregate_source_snapshot_ids",
    "assess_catalog_freshness",
    "completed_covering_snapshot",
    "covering_snapshots",
    "dataset_namespace",
    "latest_catalog_entry_for_dataset",
    "observed_at",
    "observed_snapshot_ids",
    "select_ingestion_source",
    "snapshot_asof_evidence",
    "snapshot_repair_priority",
    "source_coverage_evidence",
    "visible_completed_snapshots",
]


class _IngestionLogReader(Protocol):
    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None: ...

    def list_ingested_dates(
        self,
        dataset: str,
        source: str,
        status: IngestionStatus | None = None,
    ) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class CatalogFreshnessAssessment:
    """Freshness assessment for one dataset-level catalog entry."""

    status: CatalogFreshnessStatus
    sla_hours: int | None
    entry: DataCatalogEntry | None = None


@dataclass(frozen=True, slots=True)
class CatalogAsOfSnapshot:
    """Cumulative provider-snapshot provenance selected under a signal-date cutoff."""

    effective_partition_date: str
    source_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    row_count: int
    freshness_sla_hours: int


@dataclass(frozen=True, slots=True)
class SourceCoverageEvidence:
    """Completion-fact evidence for one (dataset, source, trade_date)."""

    source: str
    status: CatalogFreshnessStatus
    sla_hours: int | None
    snapshot: ProviderSnapshot | None = None


def assess_catalog_freshness(
    *,
    dataset: str,
    catalog_entry: DataCatalogEntry | None,
    now: Callable[[], datetime] | None = None,
) -> CatalogFreshnessAssessment:
    """Assess a dataset-level catalog entry against the dataset freshness SLA."""
    metadata = default_dataset_metadata().get(dataset)
    freshness_sla_hours = metadata.freshness_sla_hours if metadata is not None else None
    if freshness_sla_hours is None:
        return CatalogFreshnessAssessment(
            status="not_applicable",
            sla_hours=None,
            entry=catalog_entry,
        )
    if catalog_entry is None:
        return CatalogFreshnessAssessment(
            status="missing",
            sla_hours=freshness_sla_hours,
        )

    freshness_age = _ensure_aware_utc((now or _utcnow)()) - _ensure_aware_utc(
        catalog_entry.freshness_at
    )
    status: CatalogFreshnessStatus = (
        "fresh" if freshness_age <= timedelta(hours=freshness_sla_hours) else "stale"
    )
    return CatalogFreshnessAssessment(
        status=status,
        sla_hours=freshness_sla_hours,
        entry=catalog_entry,
    )


def latest_catalog_entry_for_dataset(
    reader: DataCatalogReader,
    dataset: str,
) -> DataCatalogEntry | None:
    """Return the freshest dataset-level catalog row for a dataset."""
    entries = (
        entry
        for entry in reader.list_assets()
        if entry.asset.dataset_id == dataset and not entry.asset.partition_keys
    )
    return max(entries, key=_catalog_entry_freshness_sort_key, default=None)


def observed_at(snapshot: ProviderSnapshot) -> datetime:
    """Latest observation event time, falling back to content visibility."""
    if snapshot.observations:
        return snapshot.observations[-1]
    return snapshot.created_at


def covering_snapshots(
    snapshots: ProviderSnapshotReader,
    *,
    dataset: str,
    source: str,
    trade_date: str,
) -> tuple[ProviderSnapshot, ...]:
    """Snapshots whose provider request interval covers ``trade_date``."""
    target = _parse_iso_date(trade_date)
    if target is None:
        return ()
    covering: list[ProviderSnapshot] = []
    for snapshot in snapshots.list_snapshots(dataset_id=dataset, source=source):
        start = _parse_iso_date(snapshot.request_start)
        end = _parse_iso_date(snapshot.request_end)
        if start is None or end is None or not start <= target <= end:
            continue
        covering.append(snapshot)
    return tuple(covering)


def completed_covering_snapshot(
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    *,
    dataset: str,
    source: str,
    trade_date: str,
) -> ProviderSnapshot | None:
    """Latest observed completed snapshot covering one date, if any."""
    completed = tuple(
        snapshot
        for snapshot in covering_snapshots(
            snapshots,
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )
        if snapshot_completed(snapshot, lifecycle)
    )
    return max(
        completed,
        key=lambda item: (observed_at(item), item.snapshot_id),
        default=None,
    )


def source_coverage_evidence(
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    *,
    dataset: str,
    source: str,
    trade_date: str,
) -> SourceCoverageEvidence:
    """
    Completion-fact status for one source at one date.

    fresh — a completed snapshot covers the date (已覆盖,可跳过重复摄取);
    stale — snapshots were requested for the date but none completed (需重试);
    missing — no snapshot ever covered the date (可摄取);
    not_applicable — the dataset has no registered freshness/coverage contract.
    """
    metadata = default_dataset_metadata().get(dataset)
    sla_hours = metadata.freshness_sla_hours if metadata is not None else None
    if sla_hours is None:
        return SourceCoverageEvidence(
            source=source,
            status="not_applicable",
            sla_hours=None,
        )
    covering = covering_snapshots(
        snapshots,
        dataset=dataset,
        source=source,
        trade_date=trade_date,
    )
    if not covering:
        return SourceCoverageEvidence(
            source=source,
            status="missing",
            sla_hours=sla_hours,
        )
    snapshot = max(
        (item for item in covering if snapshot_completed(item, lifecycle)),
        key=lambda item: (observed_at(item), item.snapshot_id),
        default=None,
    )
    if snapshot is None:
        return SourceCoverageEvidence(
            source=source,
            status="stale",
            sla_hours=sla_hours,
        )
    return SourceCoverageEvidence(
        source=source,
        status="fresh",
        sla_hours=sla_hours,
        snapshot=snapshot,
    )


def visible_completed_snapshots(
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    *,
    dataset: str,
    source: str,
    cutoff: date,
) -> tuple[ProviderSnapshot, ...]:
    """
    Completed snapshots with request_end ≤ cutoff that carry observations.

    可见性锚定 #393 观察账本:快照必须已被本地观察(事件存在)才可参与
    聚合;行级内容可知性由 sparse PIT cutoff 校验保证,历史回补的快照
    不会因观察时间晚于信号日而被排除(与旧分区日期语义一致)。
    """
    visible: list[ProviderSnapshot] = []
    for snapshot in snapshots.list_snapshots(dataset_id=dataset, source=source):
        request_end = _parse_iso_date(snapshot.request_end)
        if request_end is None or request_end > cutoff:
            continue
        if not snapshot.observations:
            continue
        if not snapshot_completed(snapshot, lifecycle):
            continue
        visible.append(snapshot)
    active: dict[tuple[str, str, str], ProviderSnapshot] = {}
    for snapshot in visible:
        scope = (
            snapshot.request_start,
            snapshot.request_end,
            snapshot.request_parameters_hash,
        )
        previous = active.get(scope)
        if previous is None or observed_at(snapshot) > observed_at(previous):
            active[scope] = snapshot
        elif (
            observed_at(snapshot) == observed_at(previous)
            and snapshot.snapshot_id != previous.snapshot_id
        ):
            # Conflicting observations cannot establish an authoritative revision.
            return ()
    return tuple(active.values())


def snapshot_asof_evidence(
    *,
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    dataset: str,
    source: str,
    signal_date: str,
) -> CatalogAsOfSnapshot | None:
    """Aggregate all visible completed deltas at D under the dataset PIT SLA."""
    cutoff = _parse_iso_date(signal_date)
    if cutoff is None:
        return None
    metadata = default_dataset_metadata().get(dataset)
    sla_hours = metadata.freshness_sla_hours if metadata is not None else None
    if sla_hours is None:
        return None
    components = visible_completed_snapshots(
        snapshots,
        lifecycle,
        dataset=dataset,
        source=source,
        cutoff=cutoff,
    )
    if not components:
        return None
    effective_date = max(
        date.fromisoformat(snapshot.request_end) for snapshot in components
    )
    if (cutoff - effective_date).days * 24 > sla_hours:
        return None
    snapshot_ids = tuple(sorted({item.snapshot_id for item in components}))
    aggregate_id = aggregate_source_snapshot_ids(snapshot_ids)
    if aggregate_id is None:
        return None
    return CatalogAsOfSnapshot(
        effective_partition_date=effective_date.isoformat(),
        source_snapshot_id=aggregate_id,
        source_snapshot_ids=snapshot_ids,
        row_count=sum(item.row_count for item in components),
        freshness_sla_hours=sla_hours,
    )


def observed_snapshot_ids(
    snapshots: ProviderSnapshotReader,
    lifecycle: PartitionLifecycleReader,
    *,
    dataset_ids: tuple[str, ...],
    knowledge_cutoff: datetime,
) -> tuple[str, ...]:
    """Snapshot identities completed and already observed by the cutoff."""
    identities: set[str] = set()
    for dataset_id in dataset_ids:
        for snapshot in snapshots.list_snapshots(dataset_id=dataset_id):
            if (
                snapshot.created_at <= knowledge_cutoff
                and snapshot.payload_retained
                and snapshot_completed(snapshot, lifecycle)
            ):
                identities.add(snapshot.snapshot_id)
    return tuple(sorted(identities))


def aggregate_source_snapshot_ids(snapshot_ids: tuple[str, ...]) -> str | None:
    """Build the stable aggregate ID shared by PIT ingestion evidence."""
    normalized = tuple(sorted(set(snapshot_ids)))
    if not normalized:
        return None
    if len(normalized) == 1:
        return normalized[0]
    digest = sha256(orjson.dumps(normalized)).hexdigest()
    return f"snapshot-set:sha256:{digest}"


@dataclass(frozen=True, slots=True)
class PersistedIngestionEvidenceVerifier:
    """
    Bind serialized ingestion evidence to durable snapshot and log facts.

    三方交叉验证:success log × snapshot 的 canonical write binding ×
    snapshot_completed。原始 payload 与 canonical 输出分别保留自己的
    checksum/row_count；日志必须匹配同一次完成写入绑定的 canonical 身份。
    """

    snapshots: ProviderSnapshotReader
    lifecycle: PartitionLifecycleReader
    ingestion_logs: _IngestionLogReader

    def verify_exact_date(
        self,
        *,
        dataset: str,
        source: str,
        trade_date: str,
        checksum: str,
        row_count: int,
    ) -> bool:
        """Verify one non-sparse result against its completed snapshot facts."""
        if type(checksum) is not str or not checksum:
            return False
        if type(row_count) is not int:
            return False
        log = self.ingestion_logs.get_log(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )
        if (
            log is None
            or log.status is not IngestionStatus.SUCCESS
            or log.checksum != checksum
            or log.rows != row_count
        ):
            return False
        return any(
            canonical_write_identity(snapshot) == (checksum, row_count)
            and snapshot_completed(snapshot, self.lifecycle)
            for snapshot in covering_snapshots(
                self.snapshots,
                dataset=dataset,
                source=source,
                trade_date=trade_date,
            )
        )

    def verify_asof_snapshot(
        self,
        *,
        dataset: str,
        source: str,
        signal_date: str,
        expected_snapshot_ids: tuple[str, ...],
        expected_row_count: int,
    ) -> bool:
        """Verify every component of one cumulative sparse PIT snapshot."""
        if type(expected_row_count) is not int:
            return False
        cutoff = _parse_iso_date(signal_date)
        if cutoff is None:
            return False
        components = visible_completed_snapshots(
            self.snapshots,
            self.lifecycle,
            dataset=dataset,
            source=source,
            cutoff=cutoff,
        )
        if tuple(sorted({item.snapshot_id for item in components})) != tuple(
            sorted(set(expected_snapshot_ids))
        ):
            return False
        attested_payloads = self._success_payloads(dataset=dataset, source=source)
        return sum(item.row_count for item in components) == expected_row_count and all(
            canonical_write_identity(item) in attested_payloads for item in components
        )

    def _success_payloads(
        self,
        *,
        dataset: str,
        source: str,
    ) -> set[tuple[str, int]]:
        """Content identities proven by durable success logs."""
        payloads: set[tuple[str, int]] = set()
        for trade_date in self.ingestion_logs.list_ingested_dates(
            dataset,
            source,
            IngestionStatus.SUCCESS,
        ):
            log = self.ingestion_logs.get_log(dataset, source, trade_date)
            if (
                log is not None
                and log.status is IngestionStatus.SUCCESS
                and isinstance(log.checksum, str)
                and log.checksum
                and isinstance(log.rows, int)
                and not isinstance(log.rows, bool)
                and log.rows >= 0
            ):
                payloads.add((log.checksum, log.rows))
        return payloads


def snapshot_repair_priority(
    *,
    logs: _IngestionLogReader,
    dataset: str,
    source: str,
    trade_date: str,
) -> tuple[int, str, str]:
    """
    Sort failed dates for repair: never-attempted first, then fewest attempts.

    #394 之后精确日期条目不再存在,排序锚定 success log 的尝试簿记。
    """
    log = logs.get_log(dataset, source, trade_date)
    if log is None:
        return (0, "", trade_date)
    return (log.attempts, log.last_attempt_at or "", trade_date)


def select_ingestion_source(
    *,
    dataset: str,
    trade_date: str,
    available_sources: tuple[str, ...],
    snapshots: ProviderSnapshotReader | None = None,
    lifecycle: PartitionLifecycleReader | None = None,
) -> str:
    """Select the runtime source that should drive this ingestion request."""
    normalized_sources = tuple(
        dict.fromkeys(source.lower() for source in available_sources)
    )
    if not normalized_sources:
        msg = "available_sources must not be empty"
        raise ValueError(msg)

    metadata = default_dataset_metadata().get(dataset)
    supported_sources = (
        metadata.supported_sources if metadata is not None else normalized_sources
    )
    candidates = tuple(
        source for source in supported_sources if source in normalized_sources
    )
    if not candidates:
        return normalized_sources[0]

    default_source = (
        metadata.default_source
        if metadata is not None and metadata.default_source in candidates
        else candidates[0]
    )
    if snapshots is None or lifecycle is None:
        return default_source

    assessments = tuple(
        (
            source,
            source_coverage_evidence(
                snapshots,
                lifecycle,
                dataset=dataset,
                source=source,
                trade_date=trade_date,
            ),
        )
        for source in candidates
    )
    for status in ("fresh", "missing", "stale", "not_applicable"):
        for source, assessment in assessments:
            if assessment.status == status:
                return source
    return default_source


def dataset_namespace(dataset: str) -> str:
    """Return the catalog namespace for a known dataset."""
    metadata = default_dataset_metadata().get(dataset)
    if metadata is None:
        return "data"
    return metadata.domain


def _catalog_entry_freshness_sort_key(
    entry: DataCatalogEntry,
) -> tuple[datetime, str, str, tuple[str, ...]]:
    return (
        _ensure_aware_utc(entry.freshness_at),
        entry.storage_uri,
        entry.asset.namespace,
        entry.asset.partition_keys,
    )


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
