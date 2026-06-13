"""Tests for LineageQueryFacade — 运行血统查询."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from ditto_application.queries.catalog import CatalogSourceFallbackPolicyEffect
from ditto_application.queries.lineage import LineageQueryFacade
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
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
                operation="ingest",
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
            "ingest",
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

    def test_summarizes_source_fallback_policy_effect_counts(self) -> None:
        """Source context should expose policy-effect counts."""
        service = _make_service()
        lineage = InMemoryDataLineage()
        source_health = MagicMock()
        source_health.get_source_health_summary.return_value = SimpleNamespace(
            reports=(
                SimpleNamespace(
                    source_fallback_policy_effect=CatalogSourceFallbackPolicyEffect(
                        policy_id="fallback-policy-001",
                        policy_status="active",
                        catalog_selected_source="tushare",
                        effective_selected_source="fred",
                        reason_codes=("selected_source_missing",),
                        recommended_actions=("repair_catalog_source_coverage",),
                    )
                ),
                SimpleNamespace(
                    source_fallback_policy_effect=CatalogSourceFallbackPolicyEffect(
                        policy_id="fallback-policy-001",
                        policy_status="active",
                        catalog_selected_source="tushare",
                        effective_selected_source="fred",
                        reason_codes=("selected_source_missing",),
                        recommended_actions=("repair_catalog_source_coverage",),
                    )
                ),
                SimpleNamespace(source_fallback_policy_effect=None),
            )
        )
        input_asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-06-01",),
        )
        lineage.record_event(
            LineageEvent(
                run_id="run-001",
                operation="backtest",
                inputs=(LineageInputRef(asset=input_asset, role="market_data"),),
                outputs=(),
                timestamp=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            )
        )
        facade = LineageQueryFacade(
            run_service=service,
            data_lineage_reader=lineage,
            source_health_summary_query=source_health,
        )

        result = facade.get_data_lineage_catalog_report_for_run(
            "run-001",
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

        assert [
            (
                item.policy_id,
                item.policy_status,
                item.catalog_selected_source,
                item.effective_selected_source,
                item.count,
            )
            for item in result.source_fallback_policy_effect_counts
        ] == [
            ("fallback-policy-001", "active", "tushare", "fred", 2),
        ]
        source_health.get_source_health_summary.assert_called_once_with(
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )


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
                operation="ingest",
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
            "ingest",
            "materialize",
        ]
        assert [
            (edge.source.dataset_id, edge.target.dataset_id, edge.event.operation)
            for edge in result.edges
        ] == [
            ("raw_bars", "clean_bars", "ingest"),
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
                operation="ingest",
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
            ("raw_bars", "clean_bars", "ingest"),
        ]
