"""运行血统查询 — 提供 lineage chain 查询能力."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.contracts import DataCatalogEntry, DataCatalogReader
from ditto_data.lineage import DataLineageReader, LineageEvent
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.backtest import RunSummary, to_run_summary

__all__ = [
    "DataLineageAsset",
    "DataLineageCatalogAsset",
    "DataLineageCatalogRunReport",
    "DataLineageCatalogStatus",
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


@dataclass(frozen=True)
class DataLineageCatalogRunReport:
    """Run lineage report enriched with exact catalog metadata for assets."""

    run_id: str
    events: tuple[DataLineageEvent, ...]
    input_assets: tuple[DataLineageCatalogAsset, ...]
    output_assets: tuple[DataLineageCatalogAsset, ...]


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
    """运行血统查询 facade — 提供血统链查询."""

    def __init__(
        self,
        run_service: StrategyRunLifecycleStore,
        data_lineage_reader: DataLineageReader | None = None,
        data_catalog_reader: DataCatalogReader | None = None,
    ) -> None:
        self._service = run_service
        self._data_lineage_reader = data_lineage_reader
        self._data_catalog_reader = data_catalog_reader

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
        reader = self._data_lineage_reader
        if reader is None:
            return ()
        asset = DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=partition_keys,
        )
        events = reader.list_events_for_asset(asset)
        return tuple(_to_data_lineage_event(e) for e in events)

    def get_data_lineage_for_run(self, run_id: str) -> DataLineageRunSummary:
        """Return recorded data lineage summary for one run."""
        reader = self._data_lineage_reader
        if reader is None:
            return DataLineageRunSummary(
                run_id=run_id,
                events=(),
                input_assets=(),
                output_assets=(),
            )
        events = tuple(
            _to_data_lineage_event(e) for e in reader.list_events_for_run(run_id)
        )
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
        return DataLineageCatalogRunReport(
            run_id=summary.run_id,
            events=summary.events,
            input_assets=tuple(
                self._to_catalog_asset_report(asset) for asset in summary.input_assets
            ),
            output_assets=tuple(
                self._to_catalog_asset_report(asset) for asset in summary.output_assets
            ),
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
        reader = self._data_lineage_reader
        assets: tuple[DataAssetRef, ...] = (root,)
        events: tuple[LineageEvent, ...] = ()
        edges: tuple[tuple[DataAssetRef, DataAssetRef, LineageEvent], ...] = ()
        if reader is not None and max_depth > 0:
            assets, events, edges = _traverse_data_lineage_graph(
                reader=reader,
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
            return DataLineageCatalogAsset(
                asset=asset,
                catalog_status="missing",
            )
        return _to_data_lineage_catalog_asset(asset=asset, entry=entry)


def _to_data_lineage_asset(asset: DataAssetRef) -> DataLineageAsset:
    return DataLineageAsset(
        dataset_id=asset.dataset_id,
        namespace=asset.namespace,
        partition_keys=asset.partition_keys,
    )


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
) -> DataLineageCatalogAsset:
    return DataLineageCatalogAsset(
        asset=asset,
        catalog_status="found",
        storage_uri=entry.storage_uri,
        source=entry.source,
        schema_hash=entry.schema.schema_hash,
        row_count=entry.schema.row_count,
        schema_created_at=entry.schema.created_at,
        freshness_at=entry.freshness_at,
    )


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
    reader: DataLineageReader,
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

        for event in reader.list_events_for_asset(asset):
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
