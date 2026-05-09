"""Integration tests for research dataset build flow."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import orjson
import polars as pl
import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.queries.research import ResearchDatasetFacade
from ditto_apps.jobs.flows.research import research_dataset_build_flow
from ditto_apps.registry import ConfigProvider
from ditto_apps.registry.contexts.bundle import MaterializationBundle
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_features.materialization.models import DerivedVersionStatus
from ditto_features.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_features.services import DerivedCatalogService
from ditto_kernel.research import (
    ResearchDatasetSpecRecord,
    ResearchSpineSpecRecord,
)
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_platform.foundation import SQLiteClient

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
    from ditto_apps.registry.container import _get_base_providers

    return make_container(
        ConfigProvider(),
        _sources_provider(),
        *_get_base_providers(),
    )


def _invoke_research_build_flow(**kwargs: Any) -> dict[str, Any]:
    flow_entrypoint: Any = getattr(
        research_dataset_build_flow,
        "fn",
        research_dataset_build_flow,
    )
    return flow_entrypoint(**kwargs)


def _seed_calendar(sqlite_client: SQLiteClient, dates: list[date]) -> None:
    rows = []
    for idx, trade_date in enumerate(dates):
        prev_trade_date = dates[idx - 1].isoformat() if idx > 0 else None
        next_trade_date = dates[idx + 1].isoformat() if idx + 1 < len(dates) else None
        rows.append(
            (
                trade_date.isoformat(),
                1,
                prev_trade_date,
                next_trade_date,
                11,
                trade_date.month,
                1,
                trade_date.year,
                0,
                0,
                0,
            )
        )
    sqlite_client.executemany(
        """
        INSERT INTO trading_calendar (
            trade_date, is_open, prev_trade_date, next_trade_date,
            week_of_year, month, quarter, year,
            is_week_end, is_month_end, is_quarter_end
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    sqlite_client.commit()


def _seed_universe(sqlite_client: SQLiteClient) -> None:
    sqlite_client.execute(
        """
        INSERT INTO instrument (
            instrument_id, ticker, name, display_name, exchange,
            board, asset_class, list_date, delist_date,
            is_st, is_active, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "000001",
            "Ping An Bank",
            "Ping An Bank",
            "SZSE",
            "main",
            "stock",
            "2020-01-01",
            None,
            0,
            1,
            None,
        ),
    )
    sqlite_client.execute(
        """
        INSERT INTO universe (
            universe_id, name, description, universe_type, source_ref
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("universe.cn.all", "CN All", None, "custom", None),
    )
    sqlite_client.executemany(
        """
        INSERT INTO universe_constituent (
            universe_id, instrument_id, effective_from, effective_to,
            weight, source, source_ticker
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("universe.cn.all", 1, "2026-01-01", None, 1.0, "test", "000001.SZ"),
        ],
    )
    sqlite_client.commit()


def _seed_derived_spec(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression="market.close",
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
            status=DerivedVersionStatus.PUBLISHED,
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-14T12:00:00+08:00",
            updated_at=None,
        )
    )


def _write_artifact(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    rows: list[dict[str, object]],
) -> None:
    version_root = (
        data_root / "derived" / "artifacts" / "series" / derived_id / f"v{version}"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(version_root / "2026.parquet")
    metadata_dir = version_root / "_runs" / f"run-{derived_id.replace('.', '-')}"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.joinpath("artifact_metadata.json").write_bytes(
        orjson.dumps(
            {
                "input_snapshots": ["market:20260311-001"],
            },
            option=orjson.OPT_INDENT_2,
        )
    )


@contextmanager
def _materialization_bundle_context():
    from ditto_application.processes.materialization.orchestrator import (
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


@pytest.mark.integration
class TestResearchDatasetBuildFlowIntegration:
    """Integration tests for research dataset build flow."""

    def test_flow_builds_snapshot_and_writes_build_report(
        self,
        monkeypatch,
        mocker,
        tmp_path: Path,
    ) -> None:
        """Flow should build a dataset snapshot and persist a build report."""
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", tmp_path.as_posix())

        seed_container = _make_test_container()
        try:
            sqlite_client = seed_container.get(SQLiteClient)
            _seed_calendar(sqlite_client, [date(2026, 3, 10), date(2026, 3, 11)])
            _seed_universe(sqlite_client)

            derived_catalog = seed_container.get(DerivedCatalogService)
            research_catalog = seed_container.get(ResearchCatalogService)
            _seed_derived_spec(
                derived_catalog,
                derived_id="factor.alpha",
                version=2,
            )
            _write_artifact(
                tmp_path,
                derived_id="factor.alpha",
                version=2,
                rows=[
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 10),
                        "value": 10.0,
                        "availability_time": date(2026, 3, 11),
                    },
                    {
                        "instrument_id": 1,
                        "trade_date": date(2026, 3, 11),
                        "value": 20.0,
                        "availability_time": date(2026, 3, 11),
                    },
                ],
            )
            research_catalog.save_spine_spec(
                ResearchSpineSpecRecord(
                    spine_id="spine.cn_stock.default",
                    universe_id="universe.cn.all",
                    calendar="cn_stock",
                    grain="1d",
                    entity_key="instrument_id",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )
            research_catalog.save_dataset_spec(
                ResearchDatasetSpecRecord(
                    dataset_id="research.alpha_flow",
                    spine_id="spine.cn_stock.default",
                    derived_ids=("factor.alpha",),
                    join_policy="left_preserving_pit",
                    known_at_policy="sample_time",
                    late_arrival_policy="require_rebuild",
                    description=None,
                    created_at="2026-03-14T12:00:00+08:00",
                )
            )
        finally:
            seed_container.close()

        mocker.patch(
            "ditto_apps.jobs.flows.research.create_materialization_bundle",
            side_effect=_materialization_bundle_context,
        )

        result = _invoke_research_build_flow(
            dataset_id="research.alpha_flow",
            start="2026-03-10",
            end="2026-03-11",
        )

        assert result["summary"]["dataset_id"] == "research.alpha_flow"
        assert result["summary"]["row_count"] == 2
        assert result["summary"]["spine_row_count"] == 2
        assert result["summary"]["null_counts"] == {"factor.alpha": 1}
        snapshot_path = tmp_path / result["results"][0]["data_path"]
        report_path = snapshot_path.parent / "build_report.json"
        assert report_path.exists() is True
        report = orjson.loads(report_path.read_bytes())
        assert report["row_count"] == 2
        assert report["null_counts"] == {"factor.alpha": 1}
        assert report["resolved_versions"] == {"factor.alpha": 2}
