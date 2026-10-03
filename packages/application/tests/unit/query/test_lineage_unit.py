"""Tests for LineageQueryFacade — 运行血统查询."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock

from ditto_application.queries.lineage import LineageQueryFacade
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.lineage import (
    InMemoryDataLineage,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_kernel.strategy import RunStatus
from ditto_strategy.runs.models import StrategyRunRecord


def _make_record(
    run_id: str = "run-001",
    strategy_id: str = "strat-a",
    parent_run_id: str = "",
    **overrides: object,
) -> StrategyRunRecord:
    """构造测试用 StrategyRunRecord."""
    defaults: dict[str, object] = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": "1.0",
        "mode": "backtest",
        "status": RunStatus.COMPLETED,
        "started_at": "2024-01-15T08:00:00Z",
        "completed_at": "2024-01-15T09:30:00Z",
        "error_message": "",
        "parent_run_id": parent_run_id,
    }
    defaults.update(overrides)
    return StrategyRunRecord(**defaults)  # type: ignore[arg-type]


def _make_service() -> MagicMock:
    """构造 MagicMock 模拟 StrategyRunService."""
    return MagicMock(
        spec=["list_lineage", "list_replays", "get_run", "list_runs"],
    )


# ========== get_lineage ==========


class TestGetLineage:
    """LineageQueryFacade.get_lineage — 运行血统链查询."""

    def test_single_run_no_parent(self) -> None:
        """原始运行（无 parent_run_id）返回 depth=0."""
        service = _make_service()
        record = _make_record(run_id="run-001")
        service.list_lineage.return_value = [record]
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("run-001")

        assert result is not None
        assert result.depth == 0
        assert len(result.runs) == 1
        assert result.runs[0].run_id == "run-001"
        service.list_lineage.assert_called_once_with("run-001")

    def test_replay_chain_depth_1(self) -> None:
        """一级重放 — 原始 → 重放1."""
        service = _make_service()
        original = _make_record(run_id="run-001")
        replay = _make_record(run_id="run-002", parent_run_id="run-001")
        service.list_lineage.return_value = [original, replay]
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("run-002")

        assert result is not None
        assert result.depth == 1
        assert len(result.runs) == 2
        assert result.runs[0].run_id == "run-001"
        assert result.runs[1].run_id == "run-002"

    def test_replay_chain_depth_2(self) -> None:
        """二级重放 — 原始 → 重放1 → 重放2."""
        service = _make_service()
        original = _make_record(run_id="run-001")
        replay1 = _make_record(run_id="run-002", parent_run_id="run-001")
        replay2 = _make_record(run_id="run-003", parent_run_id="run-002")
        service.list_lineage.return_value = [original, replay1, replay2]
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("run-003")

        assert result is not None
        assert result.depth == 2
        assert len(result.runs) == 3

    def test_run_not_found_returns_none(self) -> None:
        """运行不存在时返回 None."""
        service = _make_service()
        service.list_lineage.return_value = []
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("nonexistent")

        assert result is None


# ========== list_replays ==========


class TestListReplays:
    """LineageQueryFacade.list_replays — 列出直接重放记录."""

    def test_list_replays(self) -> None:
        """列出原始运行的所有直接重放."""
        service = _make_service()
        replays = [
            _make_record(run_id="run-002", parent_run_id="run-001"),
            _make_record(run_id="run-003", parent_run_id="run-001"),
        ]
        service.list_replays.return_value = replays
        facade = LineageQueryFacade(run_service=service)

        result = facade.list_replays("run-001")

        assert len(result) == 2
        assert all(r.parent_run_id == "run-001" for r in result)
        service.list_replays.assert_called_once_with("run-001")

    def test_list_replays_empty(self) -> None:
        """无重放记录时返回空列表."""
        service = _make_service()
        service.list_replays.return_value = []
        facade = LineageQueryFacade(run_service=service)

        result = facade.list_replays("run-001")

        assert result == []


# ========== list_data_events_for_asset ==========


class TestListDataEventsForAsset:
    """LineageQueryFacade.list_data_events_for_asset — 查询数据资产血缘事件."""

    def test_maps_reader_events_to_application_dtos(self) -> None:
        """按 asset 查询时返回稳定的 application DTO，保留 inputs/outputs/roles。"""
        service = _make_service()
        lineage = InMemoryDataLineage()
        input_asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-01-05",),
        )
        output_asset = DataAssetRef(
            dataset_id="backtest_report",
            namespace="backtest",
            partition_keys=("run_id=run-001", "strategy_id=momentum-etf"),
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="backtest",
                inputs=(LineageInputRef(asset=input_asset, role="market_data"),),
                outputs=(LineageOutputRef(asset=output_asset, role="backtest_report"),),
                timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
        )

        result = facade.list_data_events_for_asset(
            namespace="backtest",
            dataset_id="backtest_report",
            partition_keys=("run_id=run-001", "strategy_id=momentum-etf"),
        )

        assert len(result) == 1
        event = result[0]
        assert event.run_id == "run-001"
        assert event.operation == "backtest"
        assert event.timestamp == datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        assert event.inputs[0].role == "market_data"
        assert event.inputs[0].asset.namespace == "market"
        assert event.outputs[0].role == "backtest_report"
        assert event.outputs[0].asset.partition_keys == (
            "run_id=run-001",
            "strategy_id=momentum-etf",
        )


# ========== get_data_lineage_for_run ==========


class TestGetDataLineageForRun:
    """LineageQueryFacade.get_data_lineage_for_run — 查询运行级数据血缘摘要."""

    def test_returns_run_summary_with_unique_input_and_output_assets(self) -> None:
        """按 run_id 查询时返回事件和去重后的输入/输出资产。"""
        service = _make_service()
        lineage = InMemoryDataLineage()
        raw_asset = DataAssetRef(dataset_id="raw_bars", namespace="market")
        clean_asset = DataAssetRef(dataset_id="clean_bars", namespace="market")
        feature_asset = DataAssetRef(dataset_id="alpha_inputs", namespace="features")
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="transform",
                inputs=(LineageInputRef(asset=raw_asset, role="source"),),
                outputs=(LineageOutputRef(asset=clean_asset, role="dataset"),),
                timestamp=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
            )
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-002",
                operation="unrelated",
                inputs=(LineageInputRef(asset=raw_asset, role="source"),),
                outputs=(LineageOutputRef(asset=feature_asset, role="dataset"),),
                timestamp=datetime(2026, 1, 5, 9, 1, tzinfo=UTC),
            )
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="materialize",
                inputs=(LineageInputRef(asset=clean_asset, role="market"),),
                outputs=(LineageOutputRef(asset=feature_asset, role="derived"),),
                timestamp=datetime(2026, 1, 5, 9, 2, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
        )

        result = facade.get_data_lineage_for_run("run-001")

        assert result.run_id == "run-001"
        assert [event.operation for event in result.events] == [
            "transform",
            "materialize",
        ]
        assert result.input_assets == (
            result.events[0].inputs[0].asset,
            result.events[1].inputs[0].asset,
        )
        assert result.output_assets == (
            result.events[0].outputs[0].asset,
            result.events[1].outputs[0].asset,
        )


# ========== get_data_lineage_catalog_report_for_run ==========


class TestGetDataLineageCatalogReportForRun:
    """LineageQueryFacade.get_data_lineage_catalog_report_for_run."""

    def test_enriches_run_assets_with_exact_catalog_metadata(self) -> None:
        """Run lineage catalog report should triage stale and missing assets."""
        service = _make_service()
        lineage = InMemoryDataLineage()
        catalog = InMemoryDataCatalog()
        input_asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-01-05",),
        )
        output_asset = DataAssetRef(
            dataset_id="backtest_report",
            namespace="backtest",
            partition_keys=("run_id=run-001",),
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="backtest",
                inputs=(LineageInputRef(asset=input_asset, role="market_data"),),
                outputs=(LineageOutputRef(asset=output_asset, role="report"),),
                timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
            )
        )
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=input_asset,
                storage_uri="stock_daily/2026-01-05.parquet",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=128,
                    created_at=datetime(2026, 1, 5, 9, 31, tzinfo=UTC),
                ),
                source="tushare",
                freshness_at=datetime(2026, 1, 5, 9, 32, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
            data_catalog_reader=catalog,
            now=lambda: datetime(2026, 1, 7, 10, 0, tzinfo=UTC),
        )

        result = facade.get_data_lineage_catalog_report_for_run("run-001")

        assert result.run_id == "run-001"
        assert result.events[0].operation == "backtest"
        assert result.input_assets[0].asset.dataset_id == "stock_daily"
        assert result.input_assets[0].catalog_status == "found"
        assert result.input_assets[0].storage_uri == "stock_daily/2026-01-05.parquet"
        assert result.input_assets[0].schema_hash == "schema:stock_daily:v1"
        assert result.input_assets[0].row_count == 128
        assert result.input_assets[0].source == "tushare"
        assert result.input_assets[0].freshness_status == "stale"
        assert result.input_assets[0].freshness_sla_hours == 36
        assert result.output_assets[0].asset.dataset_id == "backtest_report"
        assert result.output_assets[0].catalog_status == "missing"
        assert result.output_assets[0].storage_uri is None
        assert result.output_assets[0].freshness_status == "not_applicable"
        assert result.output_assets[0].freshness_sla_hours is None
        assert [(item.status, item.count) for item in result.catalog_status_counts] == [
            ("found", 1),
            ("missing", 1),
            ("not_configured", 0),
        ]
        assert [
            (item.status, item.count) for item in result.freshness_status_counts
        ] == [
            ("fresh", 0),
            ("stale", 1),
            ("missing", 0),
            ("not_applicable", 1),
        ]
        assert [
            (item.side, item.asset.asset.dataset_id, item.attention_reasons)
            for item in result.attention_required
        ] == [
            ("input", "stock_daily", ("catalog_stale",)),
            ("output", "backtest_report", ("catalog_missing",)),
        ]
        assert [item.attention_severity for item in result.attention_required] == [
            "warning",
            "critical",
        ]
        assert [
            (item.reason, item.count) for item in result.attention_reason_counts
        ] == [
            ("catalog_missing", 1),
            ("catalog_stale", 1),
        ]
        assert [
            (item.severity, item.count) for item in result.attention_severity_counts
        ] == [
            ("critical", 1),
            ("warning", 1),
            ("info", 0),
        ]

    def test_marks_assets_not_configured_when_catalog_reader_is_missing(self) -> None:
        """Missing catalog reader should be visible rather than silently empty."""
        service = _make_service()
        lineage = InMemoryDataLineage()
        asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-01-05",),
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="backtest",
                inputs=(LineageInputRef(asset=asset, role="market_data"),),
                outputs=(),
                timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
        )

        result = facade.get_data_lineage_catalog_report_for_run("run-001")

        assert result.input_assets[0].catalog_status == "not_configured"
        assert [(item.status, item.count) for item in result.catalog_status_counts] == [
            ("found", 0),
            ("missing", 0),
            ("not_configured", 1),
        ]
        assert result.attention_required[0].side == "input"
        assert result.attention_required[0].asset.catalog_status == "not_configured"
        assert result.attention_required[0].attention_reasons == (
            "catalog_not_configured",
        )
        assert result.attention_required[0].attention_severity == "critical"
        assert [
            (item.reason, item.count) for item in result.attention_reason_counts
        ] == [
            ("catalog_not_configured", 1),
        ]


# ========== get_data_lineage_graph_for_asset ==========


class TestGetDataLineageGraphForAsset:
    """LineageQueryFacade.get_data_lineage_graph_for_asset — 查询资产血缘图."""

    def test_traverses_downstream_assets_until_max_depth(self) -> None:
        """按下游方向遍历时返回去重资产、事件和 input→output 边。"""
        service = _make_service()
        lineage = InMemoryDataLineage()
        raw_asset = DataAssetRef(dataset_id="raw_bars", namespace="market")
        clean_asset = DataAssetRef(dataset_id="clean_bars", namespace="market")
        feature_asset = DataAssetRef(dataset_id="alpha_inputs", namespace="features")
        report_asset = DataAssetRef(dataset_id="backtest_report", namespace="backtest")
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="transform",
                inputs=(LineageInputRef(asset=raw_asset, role="source"),),
                outputs=(LineageOutputRef(asset=clean_asset, role="dataset"),),
                timestamp=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
            )
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-002",
                operation="materialize",
                inputs=(LineageInputRef(asset=clean_asset, role="market"),),
                outputs=(LineageOutputRef(asset=feature_asset, role="derived"),),
                timestamp=datetime(2026, 1, 5, 9, 1, tzinfo=UTC),
            )
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-003",
                operation="backtest",
                inputs=(LineageInputRef(asset=feature_asset, role="features"),),
                outputs=(LineageOutputRef(asset=report_asset, role="report"),),
                timestamp=datetime(2026, 1, 5, 9, 2, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
        )

        result = facade.get_data_lineage_graph_for_asset(
            namespace="market",
            dataset_id="raw_bars",
            direction="downstream",
            max_depth=2,
        )

        assert result.root.dataset_id == "raw_bars"
        assert result.direction == "downstream"
        assert result.max_depth == 2
        assert [asset.dataset_id for asset in result.assets] == [
            "raw_bars",
            "clean_bars",
            "alpha_inputs",
        ]
        assert [event.operation for event in result.events] == [
            "transform",
            "materialize",
        ]
        assert [
            (edge.source.dataset_id, edge.target.dataset_id, edge.event.operation)
            for edge in result.edges
        ] == [
            ("raw_bars", "clean_bars", "transform"),
            ("clean_bars", "alpha_inputs", "materialize"),
        ]

    def test_traverses_upstream_assets(self) -> None:
        """按上游方向遍历时沿 output→input 发现依赖资产。"""
        service = _make_service()
        lineage = InMemoryDataLineage()
        raw_asset = DataAssetRef(dataset_id="raw_bars", namespace="market")
        clean_asset = DataAssetRef(dataset_id="clean_bars", namespace="market")
        feature_asset = DataAssetRef(dataset_id="alpha_inputs", namespace="features")
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="transform",
                inputs=(LineageInputRef(asset=raw_asset, role="source"),),
                outputs=(LineageOutputRef(asset=clean_asset, role="dataset"),),
                timestamp=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
            )
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-002",
                operation="materialize",
                inputs=(LineageInputRef(asset=clean_asset, role="market"),),
                outputs=(LineageOutputRef(asset=feature_asset, role="derived"),),
                timestamp=datetime(2026, 1, 5, 9, 1, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
        )

        result = facade.get_data_lineage_graph_for_asset(
            namespace="features",
            dataset_id="alpha_inputs",
            direction="upstream",
            max_depth=3,
        )

        assert [asset.dataset_id for asset in result.assets] == [
            "alpha_inputs",
            "clean_bars",
            "raw_bars",
        ]
        assert [
            (edge.source.dataset_id, edge.target.dataset_id, edge.event.operation)
            for edge in result.edges
        ] == [
            ("clean_bars", "alpha_inputs", "materialize"),
            ("raw_bars", "clean_bars", "transform"),
        ]


# ========== ingest 事件合成（provider snapshots 单一事实） ==========


class _SnapshotReader:
    """Minimal ProviderSnapshotReader over in-memory snapshots."""

    def __init__(self, *snapshots) -> None:
        self._snapshots = tuple(snapshots)

    def get_snapshot(self, snapshot_id: str):
        return next(
            (item for item in self._snapshots if item.snapshot_id == snapshot_id),
            None,
        )

    def get_observed_at(self, snapshot_id: str):
        snapshot = self.get_snapshot(snapshot_id)
        return None if snapshot is None else snapshot.created_at

    def get_predecessor(self, snapshot_id: str):
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ):
        return tuple(
            item
            for item in self._snapshots
            if (dataset_id is None or item.dataset_id == dataset_id)
            and (source is None or item.source == source)
            and (canonical_asset is None or item.canonical_asset == canonical_asset)
        )


def _ingested_snapshot(
    *,
    created_at: datetime,
    observations: tuple[datetime, ...] = (),
    partition_keys: tuple[str, ...] = ("trade_date=2026-01-05",),
) -> ProviderSnapshot:
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-01-05",
            request_end="2026-01-05",
            schema_version="market.stock_daily.v1",
            checksum="sha256:payload",
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=partition_keys,
            ),
            request_parameters_hash="sha256:request",
            response_metadata=(),
            row_count=1,
            payload_uri="stock_daily/2026/01/05.parquet",
            payload_retained=True,
            created_at=created_at,
        )
    )
    return replace(snapshot, observations=observations)


class TestSyntheticIngestEvents:
    """摄取 ingest 事件从 provider snapshots 合成,store 只供非 ingest 血缘。"""

    def _facade(self, snapshots) -> LineageQueryFacade:
        lineage = InMemoryDataLineage()
        return LineageQueryFacade(
            run_service=_make_service(),
            data_lineage_reader=lineage,
            provider_snapshots=_SnapshotReader(*snapshots),
        )

    def test_synthesizes_ingest_event_for_canonical_asset(self) -> None:
        observed = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        reobserved = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)
        # 真实 store 中观察事件包含首次可见时间与其后重观察。
        snapshot = _ingested_snapshot(
            created_at=observed,
            observations=(observed, reobserved),
        )
        facade = self._facade((snapshot,))

        events = facade.list_data_events_for_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-01-05",),
        )

        assert len(events) == 1
        event = events[0]
        assert event.operation == "ingest"
        # 事件时间取观察事件(首次可见)。
        assert event.timestamp == observed
        assert event.inputs[0].asset.namespace == "source"
        assert event.inputs[0].asset.partition_keys == (
            "source=tushare",
            "start_date=2026-01-05",
            "end_date=2026-01-05",
        )
        assert event.outputs[0].asset.partition_keys == ("trade_date=2026-01-05",)

    def test_synthesizes_ingest_event_for_source_asset(self) -> None:
        snapshot = _ingested_snapshot(created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
        facade = self._facade((snapshot,))

        events = facade.list_data_events_for_asset(
            namespace="source",
            dataset_id="stock_daily",
            partition_keys=(
                "source=tushare",
                "start_date=2026-01-05",
                "end_date=2026-01-05",
            ),
        )

        assert [event.operation for event in events] == ["ingest"]

    def test_run_summary_resolves_synthetic_ingest_run_id(self) -> None:
        snapshot = _ingested_snapshot(created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
        facade = self._facade((snapshot,))

        events = facade.list_data_events_for_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-01-05",),
        )
        summary = facade.get_data_lineage_for_run(events[0].run_id)

        assert [event.run_id for event in summary.events] == [events[0].run_id]
        assert summary.input_assets[0].namespace == "source"
        assert summary.output_assets[0].namespace == "market"

    def test_store_ingest_rows_are_superseded_by_synthesis(self) -> None:
        """遗留 store ingest 行让位给合成事件,避免双源重复。"""
        service = _make_service()
        lineage = InMemoryDataLineage()
        asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-01-05",),
        )
        lineage.record_event(
            LineageEvent(
                run_id="ingest:legacy:tushare:stock_daily:2026-01-05:sha256:old",
                operation="ingest",
                inputs=(LineageInputRef(asset=asset, role="source"),),
                outputs=(LineageOutputRef(asset=asset, role="dataset"),),
                timestamp=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
            )
        )
        snapshot = _ingested_snapshot(created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
            provider_snapshots=_SnapshotReader(snapshot),
        )

        events = facade.list_data_events_for_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-01-05",),
        )

        assert len(events) == 1
        assert events[0].run_id == (
            f"ingest:tushare:stock_daily:2026-01-05:{snapshot.checksum}"
        )

    def test_graph_traverses_synthetic_ingest_edges(self) -> None:
        snapshot = _ingested_snapshot(created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
        facade = self._facade((snapshot,))

        graph = facade.get_data_lineage_graph_for_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-01-05",),
            direction="upstream",
            max_depth=1,
        )

        assert [event.operation for event in graph.events] == ["ingest"]
        assert [
            (edge.source.namespace, edge.target.namespace) for edge in graph.edges
        ] == [("source", "market")]
