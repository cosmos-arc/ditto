"""Tests for RuntimeProvider derived catalog wiring."""

from unittest.mock import MagicMock

from dishka import Provider, Scope, make_container, provide
from ditto_datahub.models.strategy import (
    ArtifactKind,
    StrategyArtifactRecord,
    StrategySpecRecord,
)
from ditto_datahub.models.strategy_audit import RiskScanPayload
from ditto_datahub.services import DerivedCatalogService
from ditto_datahub.services.audit import ExecutionAuditService
from ditto_datahub.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_datahub.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_datahub.services.strategy.strategy_run_service import StrategyRunService
from ditto_datahub.sources.source import DataSources
from ditto_port.registry.datahub import RuntimeProvider
from ditto_port.registry.infra import ConfigProvider


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

    return SourcesProvider()


class TestRuntimeProviderDerivedCatalog:
    """Tests for RuntimeProvider derived catalog service wiring."""

    def test_runtime_provider_provides_derived_catalog_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider should build DerivedCatalogService."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(DerivedCatalogService)

        assert isinstance(service, DerivedCatalogService)
        container.close()

    def test_runtime_provider_reuses_derived_catalog_service_singleton(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """DerivedCatalogService should be an app-scoped singleton."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service_1 = container.get(DerivedCatalogService)
        service_2 = container.get(DerivedCatalogService)

        assert service_1 is service_2
        container.close()

    def test_runtime_provider_provides_shadow_slot_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider should build DerivedShadowSlotService."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(DerivedShadowSlotService)

        assert isinstance(service, DerivedShadowSlotService)
        container.close()

    def test_runtime_provider_provides_strategy_run_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider 应提供可持久化的 StrategyRunService。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(StrategyRunService)
        service.create_run(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="2026.03",
        )
        service.mark_completed("run-001")
        record = service.get_run("run-001")

        assert isinstance(service, StrategyRunService)
        assert record is not None
        assert record.strategy_version == "2026.03"
        assert record.status == "completed"
        assert record.started_at != ""
        assert record.completed_at != ""
        container.close()

    def test_runtime_provider_provides_strategy_catalog_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider 应提供可持久化的 StrategyCatalogService。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(StrategyCatalogService)
        service.save_spec(
            StrategySpecRecord(
                strategy_id="momentum-etf",
                name="Momentum ETF",
                spec_json={"lookback": 20, "top_k": 10},
                version=1,
                tags=("momentum", "etf"),
            )
        )
        service.publish_spec("momentum-etf", 1)
        record = service.get_spec("momentum-etf", 1)

        assert isinstance(service, StrategyCatalogService)
        assert record is not None
        assert record.name == "Momentum ETF"
        assert record.status == "published"
        assert record.tags == ("momentum", "etf")
        container.close()

    def test_runtime_provider_provides_strategy_artifact_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider 应提供可持久化的 StrategyArtifactService。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(StrategyArtifactService)
        service.save_artifact(
            StrategyArtifactRecord(
                artifact_id="artifact-001",
                strategy_id="momentum-etf",
                run_id="run-001",
                artifact_type=ArtifactKind.BACKTEST_REPORT,
                file_path="artifacts/momentum-etf/run-001/backtest_report.json",
                metadata={"total_return": 0.15},
            )
        )
        service.archive_artifact("artifact-001")
        record = service.get_artifact("artifact-001")

        assert isinstance(service, StrategyArtifactService)
        assert record is not None
        assert record.artifact_type is ArtifactKind.BACKTEST_REPORT
        assert record.status == "archived"
        assert record.metadata == {"total_return": 0.15}
        container.close()

    def test_runtime_provider_provides_execution_audit_service(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """RuntimeProvider 应提供已初始化 schema 的 ExecutionAuditService。"""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        container = make_container(
            ConfigProvider(),
            _sources_provider(),
            RuntimeProvider(),
        )

        service = container.get(ExecutionAuditService)
        count = service.save_risk_log(
            "run-001",
            (
                RiskScanPayload(
                    trade_date="2026-03-24",
                    rule_id="max_drawdown",
                    instrument_id="510300.SH",
                    severity="warning",
                    action_taken="log_only",
                    detail="drawdown near threshold",
                    current_value=0.09,
                    threshold=0.1,
                ),
            ),
        )
        records = service.query("run-001")

        assert isinstance(service, ExecutionAuditService)
        assert count == 1
        assert len(records) == 1
        assert records[0]["record_type"] == "risk_scan"
        container.close()
