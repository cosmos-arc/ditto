"""运行血统查询 — 提供 lineage chain 查询能力."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.contracts import DataCatalogEntry, DataCatalogReader
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.lineage import (
    DataLineageReader,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_application.catalog_freshness import (
    CatalogFreshnessStatus,
    assess_catalog_freshness,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.backtest import RunSummary, to_run_summary

__all__ = [
    "DataLineageAsset",
    "DataLineageCatalogAsset",
    "DataLineageCatalogAttentionAsset",
    "DataLineageCatalogAttentionReason",
    "DataLineageCatalogAttentionReasonCount",
    "DataLineageCatalogAttentionSeverity",
    "DataLineageCatalogAttentionSeverityCount",
    "DataLineageCatalogFreshnessStatusCount",
    "DataLineageCatalogRunReport",
    "DataLineageCatalogStatus",
    "DataLineageCatalogStatusCount",
    "DataLineageEvent",
    "DataLineageGraph",
    "DataLineageGraphEdge",
    "DataLineageRef",
    "DataLineageRunSummary",
    "LineageChain",
    "LineageQueryFacade",
]

_ALLOWED_GRAPH_DIRECTIONS = frozenset({"upstream", "downstream", "both"})

type DataLineageCatalogStatus = Literal["found", "missing", "not_configured"]
type DataLineageCatalogSide = Literal["input", "output"]
type DataLineageCatalogAttentionReason = Literal[
    "catalog_missing",
    "catalog_not_configured",
    "catalog_stale",
]
type DataLineageCatalogAttentionSeverity = Literal["critical", "warning", "info"]


@dataclass(frozen=True)
class LineageChain:
    """
    运行血统链.

    Attributes:
        runs: 血统链（原始运行 → ... → 当前运行，按时间正序）
        depth: 当前运行的重放深度（0 = 原始运行）

    """

    runs: tuple[RunSummary, ...]
    depth: int


@dataclass(frozen=True)
class DataLineageAsset:
    """Application-facing data asset identity."""

    dataset_id: str
    namespace: str
    partition_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataLineageRef:
    """Application-facing lineage edge reference."""

    asset: DataLineageAsset
    role: str


@dataclass(frozen=True)
class DataLineageEvent:
    """Application-facing lineage event summary."""

    run_id: str
    operation: str
    inputs: tuple[DataLineageRef, ...]
    outputs: tuple[DataLineageRef, ...]
    timestamp: datetime


@dataclass(frozen=True)
class DataLineageRunSummary:
    """Application-facing data lineage summary for one run."""

    run_id: str
    events: tuple[DataLineageEvent, ...]
    input_assets: tuple[DataLineageAsset, ...]
    output_assets: tuple[DataLineageAsset, ...]


@dataclass(frozen=True)
class DataLineageCatalogAsset:
    """Run lineage asset enriched with exact DataCatalog metadata when available."""

    asset: DataLineageAsset
    catalog_status: DataLineageCatalogStatus
    storage_uri: str | None = None
    source: str | None = None
    schema_hash: str | None = None
    row_count: int | None = None
    schema_created_at: datetime | None = None
    freshness_at: datetime | None = None
    freshness_status: CatalogFreshnessStatus | None = None
    freshness_sla_hours: int | None = None


@dataclass(frozen=True)
class DataLineageCatalogStatusCount:
    """Catalog status count across run-level lineage assets."""

    status: DataLineageCatalogStatus
    count: int


@dataclass(frozen=True)
class DataLineageCatalogFreshnessStatusCount:
    """Catalog freshness status count across run-level lineage assets."""

    status: CatalogFreshnessStatus
    count: int


@dataclass(frozen=True)
class DataLineageCatalogAttentionReasonCount:
    """Lineage catalog attention reason count across run assets."""

    reason: DataLineageCatalogAttentionReason
    count: int


@dataclass(frozen=True)
class DataLineageCatalogAttentionSeverityCount:
    """Lineage catalog attention severity count across run assets."""

    severity: DataLineageCatalogAttentionSeverity
    count: int


@dataclass(frozen=True)
class DataLineageCatalogAttentionAsset:
    """Run lineage catalog asset requiring operator attention."""

    side: DataLineageCatalogSide
    asset: DataLineageCatalogAsset
    attention_reasons: tuple[DataLineageCatalogAttentionReason, ...]
    attention_severity: DataLineageCatalogAttentionSeverity


@dataclass(frozen=True)
class DataLineageCatalogRunReport:
    """Run lineage report enriched with exact catalog metadata for assets."""

    run_id: str
    events: tuple[DataLineageEvent, ...]
    input_assets: tuple[DataLineageCatalogAsset, ...]
    output_assets: tuple[DataLineageCatalogAsset, ...]
    catalog_status_counts: tuple[DataLineageCatalogStatusCount, ...] = ()
    freshness_status_counts: tuple[DataLineageCatalogFreshnessStatusCount, ...] = ()
    attention_reason_counts: tuple[DataLineageCatalogAttentionReasonCount, ...] = ()
    attention_severity_counts: tuple[DataLineageCatalogAttentionSeverityCount, ...] = ()
    attention_required: tuple[DataLineageCatalogAttentionAsset, ...] = ()


@dataclass(frozen=True)
class DataLineageGraphEdge:
    """Application-facing directed lineage edge from input asset to output asset."""

    source: DataLineageAsset
    target: DataLineageAsset
    event: DataLineageEvent


@dataclass(frozen=True)
class DataLineageGraph:
    """Application-facing asset-centric data lineage graph."""

    root: DataLineageAsset
    direction: str
    max_depth: int
    assets: tuple[DataLineageAsset, ...]
    events: tuple[DataLineageEvent, ...]
    edges: tuple[DataLineageGraphEdge, ...]


class LineageQueryFacade:
    """
    运行血统查询 facade — 提供血统链查询.

    摄取 ingest 事件不再写入 lineage store:读取侧从 provider snapshots
    (按 asset 关联)合成,事件时间取观察事件;物化血缘仍读 lineage store。
    """

    def __init__(
        self,
        run_service: StrategyRunLifecycleStore,
        data_lineage_reader: DataLineageReader | None = None,
        data_catalog_reader: DataCatalogReader | None = None,
        provider_snapshots: ProviderSnapshotReader | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = run_service
        self._data_lineage_reader = data_lineage_reader
        self._data_catalog_reader = data_catalog_reader
        self._provider_snapshots = provider_snapshots
        self._now = now

    def get_lineage(self, run_id: str) -> LineageChain | None:
        """获取运行血统链."""
        chain = self._service.list_lineage(run_id)
        if not chain:
            return None
        return LineageChain(
            runs=tuple(to_run_summary(r) for r in chain),
            depth=len(chain) - 1,
        )

    def list_replays(self, run_id: str) -> list[RunSummary]:
        """列出指定运行的所有直接重放记录."""
        return [to_run_summary(r) for r in self._service.list_replays(run_id)]

    def list_data_events_for_asset(
        self,
        *,
        namespace: str,
        dataset_id: str,
        partition_keys: tuple[str, ...] = (),
    ) -> tuple[DataLineageEvent, ...]:
        """Return recorded data lineage events mentioning one asset."""
        asset = DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=partition_keys,
        )
        return tuple(_to_data_lineage_event(e) for e in self._events_for_asset(asset))

    def get_data_lineage_for_run(self, run_id: str) -> DataLineageRunSummary:
        """Return recorded data lineage summary for one run."""
        events = tuple(_to_data_lineage_event(e) for e in self._events_for_run(run_id))
        return DataLineageRunSummary(
            run_id=run_id,
            events=events,
            input_assets=_unique_assets(ref.asset for e in events for ref in e.inputs),
            output_assets=_unique_assets(
                ref.asset for e in events for ref in e.outputs
            ),
        )

    def get_data_lineage_catalog_report_for_run(
        self,
        run_id: str,
    ) -> DataLineageCatalogRunReport:
        """Return run-level data lineage enriched with exact catalog metadata."""
        summary = self.get_data_lineage_for_run(run_id)
        input_assets = tuple(
            self._to_catalog_asset_report(asset) for asset in summary.input_assets
        )
        output_assets = tuple(
            self._to_catalog_asset_report(asset) for asset in summary.output_assets
        )
        attention_required = _catalog_attention_required(
            input_assets=input_assets,
            output_assets=output_assets,
        )
        return DataLineageCatalogRunReport(
            run_id=summary.run_id,
            events=summary.events,
            input_assets=input_assets,
            output_assets=output_assets,
            catalog_status_counts=_catalog_status_counts(
                (*input_assets, *output_assets)
            ),
            freshness_status_counts=_catalog_freshness_status_counts(
                (*input_assets, *output_assets)
            ),
            attention_reason_counts=_catalog_attention_reason_counts(
                attention_required
            ),
            attention_severity_counts=_catalog_attention_severity_counts(
                attention_required
            ),
            attention_required=attention_required,
        )

    def get_data_lineage_graph_for_asset(
        self,
        *,
        namespace: str,
        dataset_id: str,
        partition_keys: tuple[str, ...] = (),
        direction: str = "both",
        max_depth: int = 3,
    ) -> DataLineageGraph:
        """Return an asset-centric lineage graph discovered through asset queries."""
        normalized_direction = _normalize_graph_direction(direction)
        if max_depth < 0:
            raise AppQueryError("max_depth must be greater than or equal to 0")

        root = DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=partition_keys,
        )
        assets: tuple[DataAssetRef, ...] = (root,)
        events: tuple[LineageEvent, ...] = ()
        edges: tuple[tuple[DataAssetRef, DataAssetRef, LineageEvent], ...] = ()
        if max_depth > 0:
            assets, events, edges = _traverse_data_lineage_graph(
                events_for_asset=self._events_for_asset,
                root=root,
                direction=normalized_direction,
                max_depth=max_depth,
            )

        return _to_data_lineage_graph(
            root=root,
            direction=normalized_direction,
            max_depth=max_depth,
            assets=tuple(assets),
            events=tuple(events),
            edges=tuple(edges),
        )

    def _events_for_asset(self, asset: DataAssetRef) -> tuple[LineageEvent, ...]:
        """Combine synthesized ingest events with stored non-ingest lineage."""
        recorded: tuple[LineageEvent, ...] = ()
        reader = self._data_lineage_reader
        if reader is not None:
            # 摄取写侧已删除;遗留 ingest 行让位给合成事件,避免双源重复。
            recorded = tuple(
                event
                for event in reader.list_events_for_asset(asset)
                if event.operation != _INGEST_OPERATION
            )
        return _sorted_lineage_events(
            (*recorded, *_synthetic_ingest_events(asset, self._provider_snapshots))
        )

    def _events_for_run(self, run_id: str) -> tuple[LineageEvent, ...]:
        """Combine synthesized ingest events with stored non-ingest lineage."""
        recorded: tuple[LineageEvent, ...] = ()
        reader = self._data_lineage_reader
        if reader is not None:
            recorded = tuple(
                event
                for event in reader.list_events_for_run(run_id)
                if event.operation != _INGEST_OPERATION
            )
        synthesized = (
            event
            for event in _all_synthetic_ingest_events(self._provider_snapshots)
            if event.run_id == run_id
        )
        return _sorted_lineage_events((*recorded, *synthesized))

    def _to_catalog_asset_report(
        self,
        asset: DataLineageAsset,
    ) -> DataLineageCatalogAsset:
        reader = self._data_catalog_reader
        if reader is None:
            return DataLineageCatalogAsset(
                asset=asset,
                catalog_status="not_configured",
            )

        entry = reader.get_asset(_to_data_asset_ref(asset))
        if entry is None:
            freshness = assess_catalog_freshness(
                dataset=asset.dataset_id,
                catalog_entry=None,
                now=self._now,
            )
            return DataLineageCatalogAsset(
                asset=asset,
                catalog_status="missing",
                freshness_status=freshness.status,
                freshness_sla_hours=freshness.sla_hours,
            )
        return _to_data_lineage_catalog_asset(
            asset=asset,
            entry=entry,
            now=self._now,
        )


def _to_data_lineage_asset(asset: DataAssetRef) -> DataLineageAsset:
    return DataLineageAsset(
        dataset_id=asset.dataset_id,
        namespace=asset.namespace,
        partition_keys=asset.partition_keys,
    )


_INGEST_OPERATION = "ingest"


def _canonical_partition_values(snapshot: ProviderSnapshot) -> dict[str, str]:
    values: dict[str, str] = {}
    for partition in snapshot.canonical_asset.partition_keys:
        key, separator, value = partition.partition("=")
        if separator and key and value:
            values[key] = value
    return values


def _ingest_source_asset(snapshot: ProviderSnapshot) -> DataAssetRef:
    """Rebuild the provider-side input asset recorded by the old ingest writes."""
    values = _canonical_partition_values(snapshot)
    ticker = values.get("source_ticker")
    keys: list[str] = [f"source={snapshot.source}"]
    if ticker is not None:
        keys.append(f"source_ticker={ticker}")
    keys.append(f"start_date={snapshot.request_start}")
    keys.append(f"end_date={snapshot.request_end}")
    return DataAssetRef(
        dataset_id=snapshot.dataset_id,
        namespace="source",
        partition_keys=tuple(keys),
    )


def _ingest_run_id(snapshot: ProviderSnapshot) -> str:
    values = _canonical_partition_values(snapshot)
    ticker = values.get("source_ticker")
    if ticker is None and snapshot.request_start == snapshot.request_end:
        return (
            f"ingest:{snapshot.source}:{snapshot.dataset_id}:"
            f"{snapshot.request_start}:{snapshot.checksum}"
        )
    return (
        f"ingest:{snapshot.source}:{snapshot.dataset_id}:{ticker or 'all'}:"
        f"{snapshot.request_start}:{snapshot.request_end}:{snapshot.checksum}"
    )


def _synthetic_ingest_event(snapshot: ProviderSnapshot) -> LineageEvent:
    """One ingest lineage event rebuilt from immutable snapshot evidence."""
    observed = min(snapshot.observations, default=snapshot.created_at)
    return LineageEvent(
        run_id=_ingest_run_id(snapshot),
        operation=_INGEST_OPERATION,
        inputs=(LineageInputRef(asset=_ingest_source_asset(snapshot), role="source"),),
        outputs=(LineageOutputRef(asset=snapshot.canonical_asset, role="dataset"),),
        timestamp=observed,
    )


def _synthetic_ingest_events(
    asset: DataAssetRef,
    snapshots: ProviderSnapshotReader | None,
) -> tuple[LineageEvent, ...]:
    """Synthesize ingest events for snapshots bound to one asset either side."""
    if snapshots is None:
        return ()
    if asset.namespace == "source":
        return tuple(
            _synthetic_ingest_event(snapshot)
            for snapshot in snapshots.list_snapshots(dataset_id=asset.dataset_id)
            if _ingest_source_asset(snapshot) == asset
        )
    return tuple(
        _synthetic_ingest_event(snapshot)
        for snapshot in snapshots.list_snapshots(canonical_asset=asset)
    )


def _all_synthetic_ingest_events(
    snapshots: ProviderSnapshotReader | None,
) -> tuple[LineageEvent, ...]:
    if snapshots is None:
        return ()
    return tuple(
        _synthetic_ingest_event(snapshot) for snapshot in snapshots.list_snapshots()
    )


def _sorted_lineage_events(
    events: tuple[LineageEvent, ...],
) -> tuple[LineageEvent, ...]:
    return tuple(sorted(events, key=lambda event: (event.timestamp, event.run_id)))


def _to_data_asset_ref(asset: DataLineageAsset) -> DataAssetRef:
    return DataAssetRef(
        dataset_id=asset.dataset_id,
        namespace=asset.namespace,
        partition_keys=asset.partition_keys,
    )


def _to_data_lineage_catalog_asset(
    *,
    asset: DataLineageAsset,
    entry: DataCatalogEntry,
    now: Callable[[], datetime] | None,
) -> DataLineageCatalogAsset:
    freshness = assess_catalog_freshness(
        dataset=asset.dataset_id,
        catalog_entry=entry,
        now=now,
    )
    return DataLineageCatalogAsset(
        asset=asset,
        catalog_status="found",
        storage_uri=entry.storage_uri,
        source=entry.source,
        schema_hash=entry.schema.schema_hash,
        row_count=entry.schema.row_count,
        schema_created_at=entry.schema.created_at,
        freshness_at=entry.freshness_at,
        freshness_status=freshness.status,
        freshness_sla_hours=freshness.sla_hours,
    )


def _catalog_status_counts(
    assets: tuple[DataLineageCatalogAsset, ...],
) -> tuple[DataLineageCatalogStatusCount, ...]:
    counts: dict[DataLineageCatalogStatus, int] = {
        "found": 0,
        "missing": 0,
        "not_configured": 0,
    }
    for asset in assets:
        counts[asset.catalog_status] += 1
    return tuple(
        DataLineageCatalogStatusCount(status=status, count=counts[status])
        for status in counts
    )


def _catalog_freshness_status_counts(
    assets: tuple[DataLineageCatalogAsset, ...],
) -> tuple[DataLineageCatalogFreshnessStatusCount, ...]:
    counts: dict[CatalogFreshnessStatus, int] = {
        "fresh": 0,
        "stale": 0,
        "missing": 0,
        "not_applicable": 0,
    }
    for asset in assets:
        if asset.freshness_status is not None:
            counts[asset.freshness_status] += 1
    return tuple(
        DataLineageCatalogFreshnessStatusCount(status=status, count=counts[status])
        for status in counts
    )


def _catalog_attention_required(
    *,
    input_assets: tuple[DataLineageCatalogAsset, ...],
    output_assets: tuple[DataLineageCatalogAsset, ...],
) -> tuple[DataLineageCatalogAttentionAsset, ...]:
    attention: list[DataLineageCatalogAttentionAsset] = []
    side_assets: tuple[
        tuple[DataLineageCatalogSide, tuple[DataLineageCatalogAsset, ...]],
        ...,
    ] = (("input", input_assets), ("output", output_assets))
    for side, assets in side_assets:
        for asset in assets:
            reasons = _catalog_attention_reasons(asset)
            if not reasons:
                continue
            attention.append(
                DataLineageCatalogAttentionAsset(
                    side=side,
                    asset=asset,
                    attention_reasons=reasons,
                    attention_severity=_catalog_attention_severity(reasons),
                )
            )
    return tuple(attention)


def _catalog_attention_reasons(
    asset: DataLineageCatalogAsset,
) -> tuple[DataLineageCatalogAttentionReason, ...]:
    if asset.catalog_status == "missing":
        return ("catalog_missing",)
    if asset.catalog_status == "not_configured":
        return ("catalog_not_configured",)
    if asset.freshness_status == "stale":
        return ("catalog_stale",)
    return ()


def _catalog_attention_reason_counts(
    attention_required: tuple[DataLineageCatalogAttentionAsset, ...],
) -> tuple[DataLineageCatalogAttentionReasonCount, ...]:
    counts: dict[DataLineageCatalogAttentionReason, int] = {}
    for item in attention_required:
        for reason in item.attention_reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return tuple(
        DataLineageCatalogAttentionReasonCount(
            reason=reason,
            count=counts[reason],
        )
        for reason in sorted(counts)
    )


def _catalog_attention_severity_counts(
    attention_required: tuple[DataLineageCatalogAttentionAsset, ...],
) -> tuple[DataLineageCatalogAttentionSeverityCount, ...]:
    severity_order: tuple[DataLineageCatalogAttentionSeverity, ...] = (
        "critical",
        "warning",
        "info",
    )
    counts: dict[DataLineageCatalogAttentionSeverity, int] = dict.fromkeys(
        severity_order,
        0,
    )
    for item in attention_required:
        counts[item.attention_severity] += 1
    return tuple(
        DataLineageCatalogAttentionSeverityCount(
            severity=severity,
            count=counts[severity],
        )
        for severity in severity_order
    )


def _catalog_attention_severity(
    reasons: tuple[DataLineageCatalogAttentionReason, ...],
) -> DataLineageCatalogAttentionSeverity:
    critical_reasons: frozenset[DataLineageCatalogAttentionReason] = frozenset(
        {"catalog_missing", "catalog_not_configured"}
    )
    if any(reason in critical_reasons for reason in reasons):
        return "critical"
    if "catalog_stale" in reasons:
        return "warning"
    return "info"


def _to_data_lineage_event(event: LineageEvent) -> DataLineageEvent:
    return DataLineageEvent(
        run_id=event.run_id,
        operation=event.operation,
        inputs=tuple(
            DataLineageRef(asset=_to_data_lineage_asset(ref.asset), role=ref.role)
            for ref in event.inputs
        ),
        outputs=tuple(
            DataLineageRef(asset=_to_data_lineage_asset(ref.asset), role=ref.role)
            for ref in event.outputs
        ),
        timestamp=event.timestamp,
    )


def _unique_assets(
    assets: Iterable[DataLineageAsset],
) -> tuple[DataLineageAsset, ...]:
    unique: list[DataLineageAsset] = []
    for asset in assets:
        if asset not in unique:
            unique.append(asset)
    return tuple(unique)


def _normalize_graph_direction(direction: str) -> str:
    normalized = direction.lower()
    if normalized not in _ALLOWED_GRAPH_DIRECTIONS:
        allowed = ", ".join(sorted(_ALLOWED_GRAPH_DIRECTIONS))
        raise AppQueryError(f"direction must be one of: {allowed}")
    return normalized


def _lineage_adjacent_assets(
    *,
    asset: DataAssetRef,
    event: LineageEvent,
    direction: str,
) -> tuple[tuple[DataAssetRef, DataAssetRef, DataAssetRef], ...]:
    adjacent: list[tuple[DataAssetRef, DataAssetRef, DataAssetRef]] = []
    if direction in {"downstream", "both"} and any(
        ref.asset == asset for ref in event.inputs
    ):
        adjacent.extend((asset, ref.asset, ref.asset) for ref in event.outputs)
    if direction in {"upstream", "both"} and any(
        ref.asset == asset for ref in event.outputs
    ):
        adjacent.extend((ref.asset, asset, ref.asset) for ref in event.inputs)
    return tuple(adjacent)


def _traverse_data_lineage_graph(
    *,
    events_for_asset: Callable[[DataAssetRef], tuple[LineageEvent, ...]],
    root: DataAssetRef,
    direction: str,
    max_depth: int,
) -> tuple[
    tuple[DataAssetRef, ...],
    tuple[LineageEvent, ...],
    tuple[tuple[DataAssetRef, DataAssetRef, LineageEvent], ...],
]:
    assets: list[DataAssetRef] = [root]
    events: list[LineageEvent] = []
    edges: list[tuple[DataAssetRef, DataAssetRef, LineageEvent]] = []
    queue: deque[tuple[DataAssetRef, int]] = deque([(root, 0)])
    visited_assets: set[DataAssetRef] = set()

    while queue:
        asset, depth = queue.popleft()
        if asset in visited_assets:
            continue
        visited_assets.add(asset)
        if depth >= max_depth:
            continue

        for event in events_for_asset(asset):
            next_assets = _lineage_adjacent_assets(
                asset=asset,
                event=event,
                direction=direction,
            )
            if not next_assets:
                continue
            _append_unique_event(events, event)
            _append_lineage_graph_edges(
                edges=edges,
                assets=assets,
                queue=queue,
                visited_assets=visited_assets,
                depth=depth,
                event=event,
                next_assets=next_assets,
            )

    return tuple(assets), tuple(events), tuple(edges)


def _append_unique_event(events: list[LineageEvent], event: LineageEvent) -> None:
    if event not in events:
        events.append(event)


def _append_lineage_graph_edges(
    *,
    edges: list[tuple[DataAssetRef, DataAssetRef, LineageEvent]],
    assets: list[DataAssetRef],
    queue: deque[tuple[DataAssetRef, int]],
    visited_assets: set[DataAssetRef],
    depth: int,
    event: LineageEvent,
    next_assets: tuple[tuple[DataAssetRef, DataAssetRef, DataAssetRef], ...],
) -> None:
    for source, target, next_asset in next_assets:
        edge = (source, target, event)
        if edge not in edges:
            edges.append(edge)
        if next_asset not in assets:
            assets.append(next_asset)
        if next_asset not in visited_assets:
            queue.append((next_asset, depth + 1))


def _to_data_lineage_graph(
    *,
    root: DataAssetRef,
    direction: str,
    max_depth: int,
    assets: tuple[DataAssetRef, ...],
    events: tuple[LineageEvent, ...],
    edges: tuple[tuple[DataAssetRef, DataAssetRef, LineageEvent], ...],
) -> DataLineageGraph:
    return DataLineageGraph(
        root=_to_data_lineage_asset(root),
        direction=direction,
        max_depth=max_depth,
        assets=tuple(_to_data_lineage_asset(asset) for asset in assets),
        events=tuple(_to_data_lineage_event(event) for event in events),
        edges=tuple(
            DataLineageGraphEdge(
                source=_to_data_lineage_asset(source),
                target=_to_data_lineage_asset(target),
                event=_to_data_lineage_event(event),
            )
            for source, target, event in edges
        ),
    )
