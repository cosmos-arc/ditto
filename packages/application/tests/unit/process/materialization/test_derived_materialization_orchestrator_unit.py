"""Tests for the Phase 3 derived materialization service."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import MagicMock

import ditto_application.processes.materialization.orchestrator as orchestrator_module
import orjson
import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
    RuntimeDerivedInputProvider,
)
from ditto_application.processes.materialization.source_snapshot_resolver import (
    SourceSnapshotProvenance,
)
from ditto_application.processes.materialization.types import (
    InMemoryDerivedInputProvider,
    InputContext,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.sqlite_store import SQLiteDataLineage
from ditto_features.compile_cache import SQLiteCompileCache
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression import (
    Analysis,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_features.materialization import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
)
from ditto_features.materialization.models import (
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
    DerivedVersionStatus,
)
from ditto_features.materialization.publication import CompatibilityManifest
from ditto_features.models.derived import (
    DerivedCheckpointRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_features.services import (
    ArtifactPersistenceService,
    DerivedArtifactReader,
    DerivedCatalogService,
)
from ditto_features.storage.sqlite.derived import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)


def _spec(profile: MaterializationProfile) -> DerivedSpec:
    role = (
        DerivedRole.FACTOR
        if profile != MaterializationProfile.DERIVE
        else DerivedRole.FEATURE
    )
    return DerivedSpec(
        id=f"{profile.name.lower()}.alpha_simple",
        version=3,
        role=role,
        materialization_profile=profile,
        expression="ts_delta(close, 1)",
    )


def _input_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 10),
                date(2026, 3, 11),
            ],
            "close": [10.0, 11.0, 20.0, 18.0],
        }
    )


def _compiled_expression(spec: DerivedSpec) -> CompiledDerivedExpression:
    return CompiledDerivedExpression(
        derived_id=spec.id,
        version=spec.version,
        expr=pl.col("close"),
        analysis=Analysis(
            dependencies=("market.close",),
            operator_names=("identity",),
            lookback=0,
            requires_full_day=False,
            scope="cross_section",
        ),
        compile_identity=CompileIdentity(
            compile_input_hash="hash-input",
            operator_fingerprint="ops",
            compiler_fingerprint="compiler",
            cache_key="cache-key",
            engine_codegen_version="expr-v1",
            analysis_version="analysis-v1",
            polars_version=pl.__version__,
            expr_serialization_format="repr",
        ),
    )


def _write_market_truth_layers(data_root: Path) -> None:
    market_root = data_root / "market" / "stock"
    (market_root / "bars").mkdir(parents=True, exist_ok=True)
    (market_root / "adj").mkdir(parents=True, exist_ok=True)
    (market_root / "status").mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "close": [10.0, 11.0],
            "volume": [100.0, 110.0],
        }
    ).write_parquet(market_root / "bars" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "adj_factor": [1.0, 1.1],
        }
    ).write_parquet(market_root / "adj" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "is_suspended": [False, True],
            "suspend_timing": [None, None],
            "is_st": [False, False],
            "st_type": [None, None],
            "list_status": ["L", "L"],
            "source": ["test", "test"],
            "source_ticker": ["000001.SZ", "000001.SZ"],
        }
    ).write_parquet(market_root / "status" / "2026.parquet")


def _write_upstream_artifact(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    availability_offset_days: int,
) -> None:
    version_root = (
        data_root / "derived" / "artifacts" / "series" / derived_id / f"v{version}"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "value": [1.0, 2.0],
            "availability_time": [
                date(2026, 3, 10) + timedelta(days=availability_offset_days),
                date(2026, 3, 11) + timedelta(days=availability_offset_days),
            ],
        }
    ).write_parquet(version_root / "2026.parquet")


def _catalog_service(sqlite_client, artifact_root: Path) -> DerivedCatalogService:
    del artifact_root
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )


def _seed_spec(
    catalog_service: DerivedCatalogService,
    spec: DerivedSpec,
    *,
    status: str = DerivedVersionStatus.PUBLISHED,
    is_online: bool = True,
    is_primary: bool = True,
) -> None:
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=spec.id,
            version=spec.version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{spec.id}:v{spec.version}",
            spec_json=asdict(spec),
            created_at="2026-03-13T10:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=spec.id,
            version=spec.version,
            status=status,
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-13T10:00:00+08:00",
            updated_at=None,
        )
    )


def _read_publication_payload(
    catalog_service: DerivedCatalogService,
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    run_id: str,
) -> dict:
    """读取一次 run 的 artifact metadata publication 块（产物身份唯一载体）."""
    partition = catalog_service.list_partitions(derived_id, version, run_id)[0]
    metadata_path = (
        (data_root / partition.partition_path).parent
        / "_runs"
        / run_id
        / "artifact_metadata.json"
    )
    payload = orjson.loads(metadata_path.read_bytes())
    return payload["publication"]


class _StaticSourceSnapshotResolver:
    """Test resolver that returns DataCatalog-derived source provenance."""

    def __init__(self, snapshot_ids: tuple[str, ...]) -> None:
        self._snapshot_ids = snapshot_ids

    def resolve(self, context: InputContext) -> SourceSnapshotProvenance:
        del context
        return SourceSnapshotProvenance.from_ids(self._snapshot_ids)


def test_make_run_record_accepts_context_object() -> None:
    """Run record assembly should expose a single context-shaped API."""
    spec = _spec(MaterializationProfile.SERIES)
    request = DerivedMaterializationRequest(
        derived_id=spec.id,
        version=spec.version,
        mode=DerivedRunMode.INCREMENTAL,
        request_start="2026-03-10",
        request_end="2026-03-11",
        trigger=DerivedRunTrigger.SCHEDULED,
        source_snapshot_id="snapshot-main",
    )
    plan = DerivedExecutionPlan(
        derived_id=spec.id,
        version=spec.version,
        profile=spec.materialization_profile,
        mode=request.mode,
        request_start=request.request_start,
        request_end=request.request_end,
        compute_start="2026-03-09",
        compute_end="2026-03-11",
        partitions=("2026",),
        lookback=1,
        requires_full_day=False,
    )
    ctx = orchestrator_module.MaterializationRunRecordContext(
        run_id="drv-test",
        spec=spec,
        request=request,
        plan=plan,
        status=DerivedRunStatus.SUCCESS,
        rows_written=12,
        partitions_written=("2026",),
        created_at="2026-03-13T10:00:00+08:00",
        started_at="2026-03-13T10:00:00+08:00",
        finished_at="2026-03-13T10:01:00+08:00",
    )

    record = orchestrator_module._make_run_record(ctx)

    assert record.run_id == "drv-test"
    assert record.derived_id == spec.id
    assert record.mode == DerivedRunMode.INCREMENTAL.value
    assert record.trigger == DerivedRunTrigger.SCHEDULED.value
    assert record.compute_start == "2026-03-09"
    assert record.source_snapshot_id == "snapshot-main"
    assert record.status == DerivedRunStatus.SUCCESS.value
    assert record.rows_written == 12
    assert record.partitions_written == ("2026",)


def test_persist_materialized_data_accepts_context_object() -> None:
    """Materialized data persistence should expose one context-shaped API."""
    spec = _spec(MaterializationProfile.DERIVE)
    spec_record = DerivedSpecRecord(
        derived_id=spec.id,
        version=spec.version,
        role=spec.role.value,
        materialization_profile=spec.materialization_profile.value,
        spec_hash="hash",
        spec_json=asdict(spec),
        created_at="2026-03-13T10:00:00+08:00",
    )
    request = DerivedMaterializationRequest(
        derived_id=spec.id,
        version=spec.version,
        mode=DerivedRunMode.INCREMENTAL,
        request_start="2026-03-10",
        request_end="2026-03-11",
        trigger=DerivedRunTrigger.MANUAL,
        source_snapshot_id="snapshot-main",
    )
    plan = DerivedExecutionPlan(
        derived_id=spec.id,
        version=spec.version,
        profile=spec.materialization_profile,
        mode=request.mode,
        request_start=request.request_start,
        request_end=request.request_end,
        compute_start="2026-03-10",
        compute_end="2026-03-11",
        partitions=(),
        lookback=0,
        requires_full_day=False,
    )
    artifact_writer = MagicMock()
    service = DerivedMaterializationOrchestrator(
        orchestrator_module.MaterializationRuntimePorts(
            catalog_service=MagicMock(),
            compile_cache_service=MagicMock(),
            artifact_writer=artifact_writer,
            input_provider=MagicMock(),
        )
    )
    ctx = orchestrator_module.MaterializedDataPersistenceContext(
        spec=spec,
        spec_record=spec_record,
        request=request,
        plan=plan,
        compiled=_compiled_expression(spec),
        run=orchestrator_module._RunIdentity(
            "drv-test",
            "2026-03-13T10:00:00+08:00",
        ),
        materialized_frame=_input_frame(),
        source_snapshot_ids=("snapshot-main",),
    )

    result = service._persist_materialized_data(ctx)

    artifact_writer.write_ephemeral_result.assert_called_once()
    assert result.run_id == "drv-test"
    assert result.status == DerivedRunStatus.SUCCESS
    assert result.rows_written == 4


def test_orchestrator_accepts_runtime_ports_context() -> None:
    """Orchestrator construction should expose one runtime ports object."""
    catalog_service = MagicMock()
    compile_cache_service = MagicMock()
    artifact_writer = MagicMock()
    input_provider = MagicMock()
    ports = orchestrator_module.MaterializationRuntimePorts(
        catalog_service=catalog_service,
        compile_cache_service=compile_cache_service,
        artifact_writer=artifact_writer,
        input_provider=input_provider,
    )

    service = DerivedMaterializationOrchestrator(ports)

    assert service._catalog_service is catalog_service
    assert service._compile_cache_service is compile_cache_service
    assert service._artifact_writer is artifact_writer
    assert service._input_provider is input_provider


class TestDerivedMaterializationOrchestrator:
    """Tests for unified derived materialization."""

    def test_series_materialization_writes_artifact_and_runtime_metadata(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable profiles should write artifacts, checkpoint, and state."""
        spec = _spec(MaterializationProfile.SERIES)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        assert result.rows_written == 4
        assert result.partitions_written == ("2026",)
        state = catalog_service.get_state(spec.id)
        assert state is not None
        assert state.latest_run_status == "SUCCESS"
        partitions = catalog_service.list_partitions(spec.id, 3, result.run_id)
        assert len(partitions) == 1
        artifact_path = tmp_path / partitions[0].partition_path
        assert artifact_path.exists()
        metadata_path = (
            artifact_path.parent / "_runs" / result.run_id / "artifact_metadata.json"
        )
        assert metadata_path.exists()
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["compile_identity"]["cache_key"]

    def test_derive_materialization_is_ephemeral_only(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """DERIVE profile should keep runtime records without durable artifact/state."""
        spec = _spec(MaterializationProfile.DERIVE)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )

        assert result.partitions_written == ()
        assert catalog_service.get_state(spec.id) is None
        checkpoints = catalog_service.list_checkpoints(spec.id, 3)
        assert checkpoints == ()
        ephemeral_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / spec.id
            / "v3"
            / "_ephemeral"
        )
        assert ephemeral_root.exists()

    def test_checkpoint_rows_are_persisted(self, sqlite_client, tmp_path: Path) -> None:
        """Checkpoint rows should be visible after a durable run."""
        spec = _spec(MaterializationProfile.OFFLINE)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.SCHEDULED,
                source_snapshot_id="market:20260311-001",
            )
        )

        checkpoints = catalog_service.list_checkpoints(spec.id, 3)
        assert checkpoints == (
            DerivedCheckpointRecord(
                derived_id=spec.id,
                version=3,
                partition_key="2026",
                status="done",
                rows_written=4,
                checksum=checkpoints[0].checksum,
                error_message=None,
                started_at=checkpoints[0].started_at,
                completed_at=checkpoints[0].completed_at,
            ),
        )
        assert result.profile == MaterializationProfile.OFFLINE

    def test_runtime_input_provider_reads_market_truth_and_persists_refs(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Runtime input provider should read truth-layer parquet and persist refs."""
        spec = DerivedSpec(
            id="factor.market_truth_gate",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression=(
                "if_else("
                "market.is_suspended, "
                "market.close, "
                "market.close * market.adj_factor"
                ")"
            ),
        )
        _write_market_truth_layers(tmp_path)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "close": [10.0, 11.0],
                "open": [9.5, 10.5],
                "high": [10.5, 11.5],
                "low": [9.0, 10.0],
                "pre_close": [9.0, 10.0],
                "volume": [100.0, 110.0],
                "amount": [1000.0, 1100.0],
            }
        )
        mock_market.get_adj_factors.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "adj_factor": [1.0, 1.1],
            }
        )
        mock_market.get_stock_status.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "is_suspended": [False, True],
                "suspend_timing": [None, None],
                "is_st": [False, False],
                "st_type": [None, None],
                "list_status": ["L", "L"],
            }
        )
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=RuntimeDerivedInputProvider(
                    catalog_service=catalog_service,
                    market_service=mock_market,
                    artifact_root=tmp_path,
                ),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        stock_daily_edges = catalog_service.list_dependencies_by_ref(
            "market.stock_daily"
        )
        adj_factor_edges = catalog_service.list_dependencies_by_ref("market.adj_factor")
        stock_status_edges = catalog_service.list_dependencies_by_ref(
            "market.stock_status"
        )

        assert {(edge.derived_id, edge.version) for edge in stock_daily_edges} == {
            (spec.id, spec.version)
        }
        assert {(edge.derived_id, edge.version) for edge in adj_factor_edges} == {
            (spec.id, spec.version)
        }
        assert {(edge.derived_id, edge.version) for edge in stock_status_edges} == {
            (spec.id, spec.version)
        }

        partition = catalog_service.list_partitions(
            spec.id,
            spec.version,
            result.run_id,
        )[0]
        artifact = pl.read_parquet(tmp_path / partition.partition_path)
        assert "availability_time" in artifact.columns
        assert (
            artifact.select(pl.col("availability_time") == pl.col("trade_date"))
            .to_series()
            .all()
        )

    def test_materialization_records_persistent_data_lineage(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable materialization should write lineage for inputs and output."""
        spec = DerivedSpec(
            id="factor.market_lineage",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close * market.adj_factor",
        )
        _write_market_truth_layers(tmp_path)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        lineage = SQLiteDataLineage(sqlite_client)
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "close": [10.0, 11.0],
                "open": [9.5, 10.5],
                "high": [10.5, 11.5],
                "low": [9.0, 10.0],
                "pre_close": [9.0, 10.0],
                "volume": [100.0, 110.0],
                "amount": [1000.0, 1100.0],
            }
        )
        mock_market.get_adj_factors.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "adj_factor": [1.0, 1.1],
            }
        )
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=RuntimeDerivedInputProvider(
                    catalog_service=catalog_service,
                    market_service=mock_market,
                    artifact_root=tmp_path,
                ),
                artifact_writer=ArtifactPersistenceService(tmp_path),
                lineage_recorder=lineage,
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=spec.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        stock_daily_asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
        )
        output_asset = DataAssetRef(
            dataset_id=spec.id,
            namespace="derived",
            partition_keys=(f"version={spec.version}",),
        )
        stock_daily_events = lineage.list_events_for_asset(stock_daily_asset)
        output_events = lineage.list_events_for_asset(output_asset)

        assert len(stock_daily_events) == 1
        assert stock_daily_events == output_events
        event = stock_daily_events[0]
        assert event.run_id == result.run_id
        assert event.operation == "materialize"
        assert {ref.asset for ref in event.inputs} == {
            stock_daily_asset,
            DataAssetRef(dataset_id="adj_factor", namespace="market"),
        }
        assert event.outputs[0].asset == output_asset

    def test_runtime_input_provider_preserves_upstream_availability_time(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Derived upstream inputs should keep upstream availability time."""
        upstream = DerivedSpec(
            id="factor.alpha_upstream",
            version=4,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close",
        )
        downstream = DerivedSpec(
            id="factor.alpha_downstream",
            version=5,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="@factor.alpha_upstream + 1",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, upstream)
        _seed_spec(catalog_service, downstream)
        catalog_service.save_state(
            DerivedStateRecord(
                derived_id=upstream.id,
                active_version=upstream.version,
                coverage_start="2026-03-10",
                coverage_end="2026-03-11",
                watermark="2026-03-11",
                latest_run_id="drv-upstream",
                latest_run_status="SUCCESS",
                total_rows=2,
                updated_at="2026-03-13T10:00:00+08:00",
            )
        )
        _write_upstream_artifact(
            tmp_path,
            derived_id=upstream.id,
            version=upstream.version,
            availability_offset_days=1,
        )
        mock_market = MagicMock()
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=RuntimeDerivedInputProvider(
                    catalog_service=catalog_service,
                    market_service=mock_market,
                    artifact_root=tmp_path,
                ),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=downstream.id,
                version=downstream.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )

        upstream_edges = catalog_service.list_dependencies_by_ref(upstream.id)
        assert {(edge.derived_id, edge.version) for edge in upstream_edges} == {
            (downstream.id, downstream.version)
        }

        partition = catalog_service.list_partitions(
            downstream.id,
            downstream.version,
            result.run_id,
        )[0]
        artifact = pl.read_parquet(tmp_path / partition.partition_path)
        assert artifact["availability_time"].to_list() == [
            date(2026, 3, 11),
            date(2026, 3, 12),
        ]

    def test_materialization_persists_manifest(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable materialization should embed the manifest in one atomic write."""
        candidate = DerivedSpec(
            id="factor.alpha_publish",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(
            catalog_service,
            candidate,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider(
                    {candidate.id: _input_frame()}
                ),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=candidate.id,
                version=candidate.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        manifest_payload = _read_publication_payload(
            catalog_service,
            tmp_path,
            derived_id=candidate.id,
            version=candidate.version,
            run_id=result.run_id,
        )["compatibility_manifest"]
        manifest = CompatibilityManifest(**manifest_payload)
        assert manifest.is_complete() is True
        assert manifest.pit_policy == "knowledge_date_fail_closed"
        assert manifest.pit_time_column == "knowledge_date"
        assert manifest.unsafe_time_policy == ""
        assert manifest.source_snapshot_id == "market:20260311-001"

    def test_materialization_auto_propagates_resolved_source_snapshot_set(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Resolved source snapshots should flow into run, manifest, and metadata."""
        candidate = DerivedSpec(
            id="factor.alpha_snapshot_set",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(
            catalog_service,
            candidate,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        source_snapshot_ids = (
            "snapshot:tushare:stock_daily:2026-03-10:a",
            "snapshot:tushare:stock_daily:2026-03-11:b",
        )
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider(
                    {candidate.id: _input_frame()}
                ),
                artifact_writer=ArtifactPersistenceService(tmp_path),
                source_snapshot_resolver=_StaticSourceSnapshotResolver(
                    source_snapshot_ids
                ),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=candidate.id,
                version=candidate.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )

        run = catalog_service.get_run(candidate.id, candidate.version, result.run_id)
        assert run is not None
        assert run.source_snapshot_id is not None
        assert run.source_snapshot_id.startswith("snapshot-set:sha256:")

        publication = _read_publication_payload(
            catalog_service,
            tmp_path,
            derived_id=candidate.id,
            version=candidate.version,
            run_id=result.run_id,
        )
        manifest = CompatibilityManifest(**publication["compatibility_manifest"])
        assert manifest.source_snapshot_id == run.source_snapshot_id
        assert manifest.source_snapshot_ids == source_snapshot_ids

        partition = catalog_service.list_partitions(
            candidate.id,
            candidate.version,
            result.run_id,
        )[0]
        metadata_path = (
            (tmp_path / partition.partition_path).parent
            / "_runs"
            / result.run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["input_snapshots"] == list(source_snapshot_ids)
        assert payload["publication"]["compatibility_manifest"][
            "source_snapshot_ids"
        ] == list(source_snapshot_ids)

    def test_durable_materialization_persists_minimal_dq_summary(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable materialization should persist a passing minimal DQ summary."""
        spec = _spec(MaterializationProfile.SERIES)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=spec.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        summary = _read_publication_payload(
            catalog_service,
            tmp_path,
            derived_id=spec.id,
            version=spec.version,
            run_id=result.run_id,
        )["minimal_dq_summary"]

        assert summary["run_id"] == result.run_id
        assert summary["passed"] is True
        assert summary["error_count"] == 0
        assert summary["row_count"] == 4
        assert summary["null_value_count"] == 2
        assert summary["nan_value_count"] == 0
        assert summary["computable_value_count"] == 2
        assert summary["failed_checks"] == []

    def test_failing_minimal_dq_rejects_publish(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """必要 DQ 失败时拒绝发布：run 失败且不产生产物. (#444 直线发布判定)"""
        spec = DerivedSpec(
            id="series.alpha_invalid",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
        )
        invalid_frame = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                ],
                "close": [10.0, float("nan"), 20.0, 18.0],
            }
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec, status=DerivedVersionStatus.DRAFT)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: invalid_frame}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
            )
        )

        with pytest.raises(AppProcessError, match="minimal DQ failed"):
            service.materialize(
                DerivedMaterializationRequest(
                    derived_id=spec.id,
                    version=spec.version,
                    mode=DerivedRunMode.FULL,
                    request_start="2026-03-10",
                    request_end="2026-03-11",
                    trigger=DerivedRunTrigger.MANUAL,
                    source_snapshot_id="market:20260311-001",
                )
            )

        latest_run = catalog_service.get_latest_run(spec.id, spec.version)
        assert latest_run is not None
        assert latest_run.status == DerivedRunStatus.FAILED.value
        assert "value_has_no_nan" in (latest_run.error_message or "")
        assert (
            catalog_service.list_partitions(spec.id, spec.version, latest_run.run_id)
            == []
        )
        version_record = catalog_service.get_version(spec.id, spec.version)
        assert version_record is not None
        assert version_record.status == DerivedVersionStatus.DRAFT.value
        assert not (tmp_path / "derived" / "artifacts" / "series" / spec.id).exists()

    # ------------------------------------------------------------------
    # #444 直线发布：首版无基准可发布 / 新身份允许值变化 / 同身份异内容拒绝
    # ------------------------------------------------------------------

    def _materialize(
        self,
        service: DerivedMaterializationOrchestrator,
        spec: DerivedSpec,
        *,
        source_snapshot_id: str,
        frame: pl.DataFrame,
    ) -> object:
        return service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=spec.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=source_snapshot_id,
            )
        )

    def test_first_durable_run_publishes_without_baseline(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """① 首版无基准可发布，完成后原子推进 derived status."""
        spec = DerivedSpec(
            id="factor.alpha_first",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec, status=DerivedVersionStatus.DRAFT)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
                artifact_reader=DerivedArtifactReader(
                    catalog_service=catalog_service,
                    artifact_root=tmp_path,
                ),
            )
        )

        result = self._materialize(
            service,
            spec,
            source_snapshot_id="market:20260310-A",
            frame=_input_frame(),
        )

        assert result.status == DerivedRunStatus.SUCCESS
        version_record = catalog_service.get_version(spec.id, spec.version)
        assert version_record is not None
        assert version_record.status == DerivedVersionStatus.PUBLISHED.value
        assert version_record.is_primary is True
        assert version_record.is_online is True

    def test_new_input_identity_allows_value_change(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """② 新输入身份（新 snapshot）允许值变化且照常发布."""
        spec = DerivedSpec(
            id="factor.alpha_identity",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec, status=DerivedVersionStatus.DRAFT)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
                artifact_reader=DerivedArtifactReader(
                    catalog_service=catalog_service,
                    artifact_root=tmp_path,
                ),
            )
        )

        first = self._materialize(
            service,
            spec,
            source_snapshot_id="market:20260310-A",
            frame=_input_frame(),
        )
        first_hash = _read_publication_payload(
            catalog_service,
            tmp_path,
            derived_id=spec.id,
            version=spec.version,
            run_id=first.run_id,
        )["manifest_hash"]

        updated_frame = _input_frame().with_columns(
            pl.col("close") * 2.0,
        )
        service._input_provider = InMemoryDerivedInputProvider({spec.id: updated_frame})
        second = self._materialize(
            service,
            spec,
            source_snapshot_id="market:20260311-B",
            frame=updated_frame,
        )
        second_hash = _read_publication_payload(
            catalog_service,
            tmp_path,
            derived_id=spec.id,
            version=spec.version,
            run_id=second.run_id,
        )["manifest_hash"]

        assert second.status == DerivedRunStatus.SUCCESS
        assert second_hash != first_hash

    def test_same_identity_retry_with_different_content_rejected(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """③ 相同输入身份的重试内容必须一致：拒绝且不动已发布产物."""
        spec = DerivedSpec(
            id="factor.alpha_retry",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec, status=DerivedVersionStatus.DRAFT)
        service = DerivedMaterializationOrchestrator(
            orchestrator_module.MaterializationRuntimePorts(
                catalog_service=catalog_service,
                compile_cache_service=SQLiteCompileCache(sqlite_client),
                input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
                artifact_writer=ArtifactPersistenceService(tmp_path),
                artifact_reader=DerivedArtifactReader(
                    catalog_service=catalog_service,
                    artifact_root=tmp_path,
                ),
            )
        )

        first = self._materialize(
            service,
            spec,
            source_snapshot_id="market:20260310-A",
            frame=_input_frame(),
        )
        partition = catalog_service.list_partitions(
            spec.id,
            spec.version,
            first.run_id,
        )[0]
        published_path = tmp_path / partition.partition_path
        checksum_before = sha256(published_path.read_bytes()).hexdigest()

        # 同一 snapshot 身份、同一编译身份，但输入帧被污染 → 非确定性重试。
        polluted_frame = _input_frame().with_columns(
            pl.col("close") + 5.0,
        )
        service._input_provider = InMemoryDerivedInputProvider(
            {spec.id: polluted_frame}
        )
        with pytest.raises(AppProcessError, match="deterministic retry mismatch"):
            self._materialize(
                service,
                spec,
                source_snapshot_id="market:20260310-A",
                frame=polluted_frame,
            )

        assert sha256(published_path.read_bytes()).hexdigest() == checksum_before
        latest_run = catalog_service.get_latest_run(spec.id, spec.version)
        assert latest_run is not None
        assert latest_run.status == DerivedRunStatus.FAILED.value
        version_record = catalog_service.get_version(spec.id, spec.version)
        assert version_record is not None
        assert version_record.status == DerivedVersionStatus.PUBLISHED.value
