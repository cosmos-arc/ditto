"""Integration tests for research dataset build flow."""

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import orjson
import polars as pl
import pytest
from dishka import Provider, Scope, make_container, provide
from ditto_analysis.errors import ExperimentConflictError, ResearchDatasetError
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.domain import (
    ResearchDatasetSpecRecord,
    ResearchSpineSpecRecord,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_application.processes.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_application.processes.research_dataset import ResearchDatasetBuildProcess
from ditto_application.queries.research import ResearchDatasetQuery
from ditto_apps.jobs.flows.research import research_dataset_build_flow
from ditto_apps.registry import ConfigProvider
from ditto_apps.registry.contexts.bundle import MaterializationBundle
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.source import DataSources
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.errors import DerivedNotFoundError
from ditto_features.materialization.models import DerivedVersionStatus
from ditto_features.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_features.services import DerivedCatalogService
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
            research_dataset_build=container.get(ResearchDatasetBuildProcess),
            research_dataset_query=container.get(ResearchDatasetQuery),
        )
    finally:
        container.close()


def _persisted_state(root: Path) -> dict[str, str | None]:
    # SQLite -shm contains transient reader locks, not durable database content.
    # Retain its directory entry; compare database, WAL and all artifacts bytewise.
    return {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        if p.is_file() and not p.name.endswith("-shm")
        else None
        for p in root.rglob("*")
    }


@contextmanager
def _build_failure(monkeypatch, failure_stage: str):
    publish = ResearchArtifactService.publish_immutable_artifact

    def fail_publish(self, relative_path, payload):
        filename = {
            "data": "data.parquet",
            "report": "build_report.json",
            "manifest": "metadata.json",
        }.get(failure_stage)
        if "/datasets/" in relative_path and relative_path.endswith(str(filename)):
            raise OSError("injected publication failure")
        return publish(self, relative_path, payload)

    execute = SQLiteClient.execute
    commit = SQLiteClient.commit
    pending_dataset = False

    def execute_with_fault(self, sql, parameters=None):
        nonlocal pending_dataset
        if "INSERT OR REPLACE INTO research_dataset_snapshot" in sql:
            pending_dataset = True
            if failure_stage == "catalog_execute":
                raise sqlite3.OperationalError("injected database lock")
        return execute(self, sql, parameters)

    def commit_with_fault(self):
        if pending_dataset:
            raise sqlite3.OperationalError("injected database commit failure")
        return commit(self)

    with monkeypatch.context() as fault:
        if failure_stage.startswith("catalog"):
            fault.setattr(SQLiteClient, "execute", execute_with_fault)
            if failure_stage == "catalog_commit":
                fault.setattr(SQLiteClient, "commit", commit_with_fault)
        else:
            fault.setattr(
                ResearchArtifactService, "publish_immutable_artifact", fail_publish
            )
        yield


@pytest.fixture
def research_state(monkeypatch, mocker, tmp_path: Path) -> Path:
    """Seed a real research catalog and isolated derived input files."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_STATE_ROOT", tmp_path.as_posix())

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

    return tmp_path


@pytest.mark.integration
class TestResearchDatasetBuildFlowIntegration:
    """Exercise build and read through the actual job and DI graph."""

    def test_flow_builds_snapshot_and_reads_without_writes(
        self, research_state: Path
    ) -> None:
        tmp_path = research_state
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

        replay = _invoke_research_build_flow(
            dataset_id="research.alpha_flow",
            start="2026-03-10",
            end="2026-03-11",
        )
        assert replay == result

        # Queries use the saved identity, and do not modify files or directories.
        reader_container = _make_test_container()
        try:
            query = reader_container.get(ResearchDatasetQuery)
            snapshot = query.get_snapshot(result["summary"]["snapshot_id"])
            before = _persisted_state(tmp_path)
            assert query.get_snapshot(snapshot.snapshot_id) == snapshot
            assert query.load_build_report(snapshot) == report
            assert query.load_build_report(snapshot) == report
            assert _persisted_state(tmp_path) == before
        finally:
            reader_container.close()

    @pytest.mark.parametrize(
        "failure_stage",
        ["data", "report", "manifest", "catalog_execute", "catalog_commit"],
    )
    def test_failed_build_recovers_without_republishing(
        self,
        research_state: Path,
        monkeypatch,
        failure_stage: str,
    ) -> None:
        tmp_path = research_state
        result = _invoke_research_build_flow(
            dataset_id="research.alpha_flow", start="2026-03-10", end="2026-03-11"
        )
        snapshot_path = tmp_path / result["results"][0]["data_path"]
        report = orjson.loads((snapshot_path.parent / "build_report.json").read_bytes())
        container = _make_test_container()
        try:
            snapshot = container.get(ResearchDatasetQuery).get_snapshot(
                result["summary"]["snapshot_id"]
            )
        finally:
            container.close()
        # A different cutoff creates a new identity, but a failed build is invisible.
        with _build_failure(monkeypatch, failure_stage):
            with pytest.raises(
                (AppProcessError, ResearchDatasetError), match="injected"
            ) as failure:
                _invoke_research_build_flow(
                    dataset_id="research.alpha_flow",
                    start="2026-03-10",
                    end="2026-03-11",
                    explicit_cutoff="2026-03-11",
                )
        assert failure.value.details["stage"] == (
            "dataset_catalog_commit"
            if failure_stage.startswith("catalog")
            else "dataset_publication"
        )
        assert failure.value.details["recoverable"] is True
        reader_container = _make_test_container()
        try:
            catalog = reader_container.get(ResearchCatalogService)
            query = reader_container.get(ResearchDatasetQuery)
            latest = catalog.get_latest_dataset_snapshot("research.alpha_flow")
            assert latest is not None
            assert latest.snapshot_id == snapshot.snapshot_id
            assert query.load_build_report(snapshot) == report
            for directory in snapshot_path.parent.parent.iterdir():
                if directory.name != snapshot.snapshot_id:
                    with pytest.raises(DerivedNotFoundError):
                        query.get_snapshot(directory.name)
        finally:
            reader_container.close()
        frozen = {
            str(p): p.read_bytes()
            for p in snapshot_path.parent.rglob("*")
            if p.is_file()
        }
        partial = {
            str(p): p.read_bytes()
            for p in snapshot_path.parent.parent.rglob("*")
            if p.is_file()
        }
        recovered = _invoke_research_build_flow(
            dataset_id="research.alpha_flow",
            start="2026-03-10",
            end="2026-03-11",
            explicit_cutoff="2026-03-11",
        )
        assert recovered["summary"]["snapshot_id"] != snapshot.snapshot_id
        assert recovered["summary"]["null_counts"] == {"factor.alpha": 0}
        assert all(
            Path(name).read_bytes() == content for name, content in partial.items()
        )
        assert all(
            Path(name).read_bytes() == content for name, content in frozen.items()
        )
        assert (
            _invoke_research_build_flow(
                dataset_id="research.alpha_flow",
                start="2026-03-10",
                end="2026-03-11",
                explicit_cutoff="2026-03-11",
            )
            == recovered
        )
        assert len(list(snapshot_path.parent.parent.iterdir())) == 2

    def test_old_snapshot_identity_remains_readable(self, research_state: Path) -> None:
        result = _invoke_research_build_flow(
            dataset_id="research.alpha_flow", start="2026-03-10", end="2026-03-11"
        )
        container = _make_test_container()
        try:
            catalog = container.get(ResearchCatalogService)
            artifacts = container.get(ResearchArtifactService)
            query = container.get(ResearchDatasetQuery)
            saved = catalog.get_dataset_snapshot(result["summary"]["snapshot_id"])
            assert saved is not None
            old = replace(
                saved,
                snapshot_id="rds-legacy",
                manifest_hash="old-manifest",
                data_path="derived/research/datasets/research.alpha_flow/snapshots/rds-legacy/data.parquet",
            )
            artifacts.write_parquet(
                old.data_path, artifacts.read_parquet(saved.data_path)
            )
            artifacts.write_json(
                old.data_path.replace("data.parquet", "build_report.json"),
                {"row_count": 2},
            )
            catalog.save_dataset_snapshot(old)
            before = _persisted_state(research_state)
            loaded = query.get_snapshot("rds-legacy")
            assert loaded.manifest_hash == "old-manifest"
            assert loaded.data_path == old.data_path
            assert query.load_build_report(loaded) == {"row_count": 2}
            assert _persisted_state(research_state) == before
        finally:
            container.close()

    def test_conflicting_published_bytes_are_not_overwritten(
        self, research_state: Path
    ) -> None:
        result = _invoke_research_build_flow(
            dataset_id="research.alpha_flow", start="2026-03-10", end="2026-03-11"
        )
        path = research_state / result["results"][0]["data_path"]
        path.write_bytes(b"conflicting-content")
        with pytest.raises(ExperimentConflictError) as failure:
            _invoke_research_build_flow(
                dataset_id="research.alpha_flow", start="2026-03-10", end="2026-03-11"
            )
        assert failure.value.details["stage"] == "dataset_publication"
        assert failure.value.details["reason_code"] == "immutable_artifact_conflict"
        assert path.read_bytes() == b"conflicting-content"

    @pytest.mark.pit
    def test_future_input_is_excluded_until_declared_cutoff(
        self, research_state: Path
    ) -> None:
        baseline = _invoke_research_build_flow(
            dataset_id="research.alpha_flow",
            start="2026-03-10",
            end="2026-03-11",
            explicit_cutoff="2026-03-11",
        )
        source_path = (
            research_state / "derived/artifacts/series/factor.alpha/v2/2026.parquet"
        )
        source = pl.read_parquet(source_path)
        pl.concat(
            [
                source,
                pl.DataFrame(
                    {
                        "instrument_id": [1],
                        "trade_date": [date(2026, 3, 11)],
                        "value": [1e9],
                        "availability_time": [date(2026, 3, 12)],
                    }
                ),
            ]
        ).write_parquet(source_path)
        excluded = _invoke_research_build_flow(
            dataset_id="research.alpha_flow",
            start="2026-03-10",
            end="2026-03-11",
            explicit_cutoff="2026-03-11",
        )
        assert excluded == baseline
        included = _invoke_research_build_flow(
            dataset_id="research.alpha_flow",
            start="2026-03-10",
            end="2026-03-11",
            explicit_cutoff="2026-03-12",
        )
        frame = pl.read_parquet(research_state / included["results"][0]["data_path"])
        assert frame["factor.alpha"].to_list() == [1e9, 1e9]
        assert included["results"][0]["source_snapshot_ids"] == ("market:20260311-001",)

    @pytest.mark.parametrize("cutoff", [None, "not-a-date"])
    def test_invalid_cutoff_writes_nothing(
        self, research_state: Path, cutoff: str | None
    ) -> None:
        container = _make_test_container()
        try:
            catalog = container.get(ResearchCatalogService)
            spec = catalog.get_dataset_spec("research.alpha_flow")
            assert spec is not None
            catalog.save_dataset_spec(replace(spec, known_at_policy="explicit_cutoff"))
            process = container.get(ResearchDatasetBuildProcess)
            before = _persisted_state(research_state)
            with pytest.raises((ValueError, AppProcessError)):
                process.build(
                    dataset_id="research.alpha_flow",
                    start="2026-03-10",
                    end="2026-03-11",
                    explicit_cutoff=cutoff,
                )
            assert _persisted_state(research_state) == before
        finally:
            container.close()
