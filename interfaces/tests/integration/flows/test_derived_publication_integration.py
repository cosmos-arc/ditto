"""Integration tests for derived publication orchestration."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_analytics.materialization import DerivedMaterializationRequest
from ditto_analytics.materialization.models import (
    DerivedRunMode,
    DerivedRunTrigger,
    DerivedVersionStatus,
)
from ditto_analytics.publication_safety import (
    CertificationStage,
    CompatibilityManifest,
)
from ditto_app.process.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_app.process.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_app.query.research import ResearchDatasetFacade
from ditto_data.di import (
    DerivedProvider,
    MetadataProvider,
    RuntimeProvider,
)
from ditto_data.ingestion.publication_safety_record_service import (
    PublicationSafetyRecordService,
)
from ditto_data.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_data.models.publication_safety import CompatibilityManifestRecord
from ditto_data.services import (
    DerivedCatalogService,
    DerivedQueryService,
)
from ditto_data.services.derived import DerivedLatestQuery
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_interfaces.jobs.flows.materialization import (
    certify_publication_flow,
    promote_publication_flow,
    shadow_compare_flow,
)
from ditto_interfaces.registry import ConfigProvider
from ditto_interfaces.registry.contexts.bundle import MaterializationBundle
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile

pytestmark = pytest.mark.serial


def _sources_provider() -> Provider:
    class SourcesProvider(Provider):
        scope = Scope.APP

        @provide
        def data_sources(self) -> DataSources:
            return DataSources(tushare=MagicMock(), fred=None)

        @provide
        def exchange_transformers(self) -> ExchangeTransformers:
            return ExchangeTransformers(
                tushare=MagicMock(),
                tdx=MagicMock(),
            )

    return SourcesProvider()


def _make_test_container():
    return make_container(
        ConfigProvider(),
        _sources_provider(),
        RuntimeProvider(),
        MetadataProvider(),
        DerivedProvider(),
    )


@contextmanager
def _materialization_bundle_context():
    from ditto_app.process.materialization.orchestrator import (
        DerivedMaterializationOrchestrator,
    )

    container = _make_test_container()
    try:
        yield MaterializationBundle(
            materialization_service=container.get(DerivedMaterializationOrchestrator),
            invalidation_service=container.get(InvalidationCascadeOrchestrator),
            publication_facade=container.get(DerivedPublicationFacade),
            research_dataset_facade=container.get(ResearchDatasetFacade),
        )
    finally:
        container.close()


def _invoke_flow(flow_entrypoint: Any, **kwargs: Any) -> dict[str, Any]:
    runner: Any = getattr(flow_entrypoint, "fn", flow_entrypoint)
    return runner(**kwargs)


def _write_market_truth_layers(data_root: Path, *, close_values: list[float]) -> None:
    market_root = data_root / "market" / "stock"
    (market_root / "bars").mkdir(parents=True, exist_ok=True)
    (market_root / "adj").mkdir(parents=True, exist_ok=True)
    (market_root / "status").mkdir(parents=True, exist_ok=True)
    trade_dates = [date(2026, 3, 10), date(2026, 3, 11)]
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": trade_dates,
            "open": close_values,
            "high": close_values,
            "low": close_values,
            "close": close_values,
            "pre_close": close_values,
            "volume": [100.0, 110.0],
            "amount": [1_000.0, 1_100.0],
        }
    ).write_parquet(market_root / "bars" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": trade_dates,
            "adj_factor": [1.0, 1.0],
        }
    ).write_parquet(market_root / "adj" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": trade_dates,
            "is_suspended": [False, False],
            "suspend_timing": [None, None],
            "is_st": [False, False],
            "st_type": [None, None],
            "list_status": ["L", "L"],
            "source": ["test", "test"],
            "source_ticker": ["000001.SZ", "000001.SZ"],
        }
    ).write_parquet(market_root / "status" / "2026.parquet")


def _seed_series_spec(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
    expression: str,
    status: str,
    is_online: bool,
    is_primary: bool,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expression,
    )
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=derived_id,
            version=version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{derived_id}:v{version}",
            spec_json=asdict(spec),
            created_at="2026-03-14T12:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=derived_id,
            version=version,
            status=status,
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-14T12:00:00+08:00",
            updated_at=None,
        )
    )


def _write_series_artifact(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    values: list[float],
) -> None:
    artifact_root = (
        data_root / "derived" / "artifacts" / "series" / derived_id / f"v{version}"
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "close": values,
            "availability_time": [date(2026, 3, 10), date(2026, 3, 11)],
            "value": values,
        }
    ).write_parquet(artifact_root / "2026.parquet")


def _save_manifest(
    publication_record_service: PublicationSafetyRecordService,
    *,
    derived_id: str,
    version: int,
    manifest_hash: str,
) -> None:
    manifest = CompatibilityManifest(
        engine_codegen_version="codegen-v1",
        analysis_version="analysis-v1",
        polars_version="1.30.0",
        expr_serialization_format="expr-json-v1",
        operator_fingerprint=f"operator-{version}",
        global_compile_flags={"grain": "1d"},
        calendar_id="cn_stock",
        timezone="Asia/Shanghai",
        time_semantics_version="time-v1",
        python_version="3.13.0",
        platform="linux",
        builder_version="unified-derived-v1",
        manifest_hash=manifest_hash,
    )
    publication_record_service.save_manifest(
        CompatibilityManifestRecord(
            derived_id=derived_id,
            version=version,
            manifest_hash=manifest_hash,
            payload=asdict(manifest),
            created_at="2026-03-14T12:00:00+08:00",
        )
    )


@pytest.mark.integration
class TestDerivedPublicationIntegration:
    """Integration tests for the publication chain."""

    def test_publication_chain_promotes_candidate_after_clean_shadow_audit(
        self,
        monkeypatch,
        mocker,
        tmp_path: Path,
    ) -> None:
        """Materialize -> compare -> certify -> promote should flip serving primary."""
        sqlite_path = tmp_path / "metadata" / "metadata.sqlite"
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())
        monkeypatch.setenv("SQLITE_PATH", sqlite_path.as_posix())
        _write_market_truth_layers(tmp_path, close_values=[10.0, 11.0])

        seed_container = _make_test_container()
        try:
            from ditto_app.process.materialization.orchestrator import (
                DerivedMaterializationOrchestrator,
            )

            catalog_service = seed_container.get(DerivedCatalogService)
            materialization_service = seed_container.get(
                DerivedMaterializationOrchestrator
            )
            publication_record_service = seed_container.get(
                PublicationSafetyRecordService
            )
            _seed_series_spec(
                catalog_service,
                derived_id="factor.alpha_publish",
                version=2,
                expression="market.close",
                status=DerivedVersionStatus.PUBLISHED,
                is_online=True,
                is_primary=True,
            )
            _seed_series_spec(
                catalog_service,
                derived_id="factor.alpha_publish",
                version=3,
                expression="market.close",
                status=DerivedVersionStatus.MATERIALIZED,
                is_online=False,
                is_primary=False,
            )
            _write_series_artifact(
                tmp_path,
                derived_id="factor.alpha_publish",
                version=2,
                values=[10.0, 11.0],
            )
            _save_manifest(
                publication_record_service,
                derived_id="factor.alpha_publish",
                version=2,
                manifest_hash="manifest-v2",
            )
            materialized = materialization_service.materialize(
                DerivedMaterializationRequest(
                    derived_id="factor.alpha_publish",
                    version=3,
                    mode=DerivedRunMode.FULL,
                    request_start="2026-03-10",
                    request_end="2026-03-11",
                    trigger=DerivedRunTrigger.MANUAL,
                    source_snapshot_id="market:20260311-001",
                )
            )
        finally:
            seed_container.close()

        mocker.patch(
            "ditto_interfaces.jobs.flows.materialization.create_materialization_bundle",
            side_effect=_materialization_bundle_context,
        )

        shadow_result = _invoke_flow(
            shadow_compare_flow,
            derived_id="factor.alpha_publish",
            start="2026-03-10",
            end="2026-03-11",
        )
        certify_result = _invoke_flow(
            certify_publication_flow,
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY.value,
        )
        promote_result = _invoke_flow(
            promote_publication_flow,
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )

        verify_container = _make_test_container()
        try:
            catalog_service = verify_container.get(DerivedCatalogService)
            publication_record_service = verify_container.get(
                PublicationSafetyRecordService
            )
            query_service = verify_container.get(DerivedQueryService)
            current_primary = catalog_service.get_version("factor.alpha_publish", 3)
            previous_primary = catalog_service.get_version("factor.alpha_publish", 2)
            latest_frame = query_service.find_latest(
                DerivedLatestQuery(
                    derived_ids=("factor.alpha_publish",),
                    instrument_ids=(1,),
                )
            )
            certification_record = (
                publication_record_service.get_latest_certification_report(
                    "factor.alpha_publish",
                    3,
                    CertificationStage.PUBLISH_READY.value,
                )
            )
        finally:
            verify_container.close()

        assert materialized.rows_written == 2
        assert shadow_result["results"][0]["error_count"] == 0
        assert certify_result["summary"]["version"] == 3
        assert promote_result["results"][0]["version"] == 3
        assert current_primary is not None
        assert previous_primary is not None
        assert current_primary.is_primary is True
        assert current_primary.is_online is True
        assert previous_primary.is_primary is False
        assert latest_frame["version"].to_list() == [3]
        assert latest_frame["value"].to_list() == [11.0]
        assert certification_record is not None
        assert certification_record.payload["passed"] is True
