"""Tests for ArtifactPersistenceService."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
from ditto_features.expression import Analysis, CompileIdentity
from ditto_features.models.derived import DerivedSpecRecord, PartitionInfo
from ditto_features.storage.derived_artifact_writer import (
    ArtifactMetadataParams,
)
from ditto_kernel.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile


def _make_spec_record(
    *,
    profile: MaterializationProfile = MaterializationProfile.SERIES,
    derived_id: str = "factor.test_factor",
    version: int = 1,
) -> DerivedSpecRecord:
    """Build a DerivedSpecRecord for service tests."""
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=profile,
        expression="close_20",
    )
    return DerivedSpecRecord(
        derived_id=derived_id,
        version=version,
        role=spec.role.value,
        materialization_profile=profile.value,
        spec_hash="test-hash",
        spec_json=asdict(spec),
        created_at="2026-03-20T00:00:00+00:00",
    )


def _make_compile_identity_dict() -> dict[str, object]:
    return asdict(
        CompileIdentity(
            compile_input_hash="hash-abc",
            operator_fingerprint="op-fp",
            compiler_fingerprint="cc-fp",
            cache_key="cache-key",
            engine_codegen_version="codegen-v1",
            analysis_version="analysis-v1",
            polars_version="0.x",
            expr_serialization_format="expr-v1",
        )
    )


def _make_analysis_dict() -> dict[str, object]:
    return asdict(
        Analysis(
            dependencies=("close",),
            operator_names=("rolling_mean",),
            lookback=20,
            requires_full_day=True,
            scope="per_instrument",
        )
    )


def _make_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": ["000001.SZ", "000001.SZ"],
            "trade_date": ["2024-06-15", "2025-06-15"],
            "value": [1.0, 2.0],
        }
    )


def _make_partitions() -> tuple[PartitionInfo, ...]:
    return (
        PartitionInfo(
            partition_key="2024",
            partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
            row_count=1,
            checksum="sha-2024",
        ),
        PartitionInfo(
            partition_key="2025",
            partition_path="derived/artifacts/series/factor.test_factor/v1/2025.parquet",
            row_count=1,
            checksum="sha-2025",
        ),
    )


def _make_manifest_record() -> CompatibilityManifestRecord:
    return CompatibilityManifestRecord(
        derived_id="factor.test_factor",
        version=1,
        manifest_hash="manifest-hash",
        payload={"engine_codegen_version": "v1"},
        created_at="2026-03-18T00:00:00+00:00",
    )


def _make_minimal_dq_record() -> DerivedMinimalDQSummaryRecord:
    return DerivedMinimalDQSummaryRecord(
        derived_id="factor.test_factor",
        version=1,
        run_id="drv-test",
        passed=True,
        error_count=0,
        payload={"row_count": 10},
        created_at="2026-03-18T00:00:00+00:00",
    )


class TestServiceDelegatesWriteEphemeralResult:
    """Tests for write_ephemeral_result delegation."""

    def test_service_delegates_write_ephemeral_result(self) -> None:
        """Should delegate write_ephemeral_result to the underlying writer."""
        from ditto_features.services.derived.artifact_persistence_service import (
            ArtifactPersistenceService,
        )

        mock_writer = MagicMock()
        service = ArtifactPersistenceService(
            artifact_root=Path("/tmp/data"),
            _writer=mock_writer,
        )
        spec_record = _make_spec_record(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()

        service.write_ephemeral_result(
            spec=spec_record,
            run_id="drv-ephemeral-001",
            frame=frame,
        )

        mock_writer.write_ephemeral_result.assert_called_once_with(
            spec=spec_record,
            run_id="drv-ephemeral-001",
            frame=frame,
        )


class TestServiceDelegatesWriteDurablePartitions:
    """Tests for write_durable_partitions delegation."""

    def test_service_delegates_write_durable_partitions_returns_partition_info(
        self,
    ) -> None:
        """Should delegate write_durable_partitions and return PartitionInfo tuple."""
        from ditto_features.services.derived.artifact_persistence_service import (
            ArtifactPersistenceService,
        )

        partitions = _make_partitions()
        mock_writer = MagicMock()
        mock_writer.write_durable_partitions.return_value = partitions
        service = ArtifactPersistenceService(
            artifact_root=Path("/tmp/data"),
            _writer=mock_writer,
        )
        spec_record = _make_spec_record()
        frame = _make_frame()

        result = service.write_durable_partitions(
            spec=spec_record,
            time_key="trade_date",
            run_id="drv-durable-001",
            frame=frame,
            request_start="2024-01-01",
            request_end="2025-12-31",
            source_snapshot_id="snap-001",
        )

        mock_writer.write_durable_partitions.assert_called_once_with(
            spec=spec_record,
            time_key="trade_date",
            run_id="drv-durable-001",
            frame=frame,
            request_start="2024-01-01",
            request_end="2025-12-31",
            source_snapshot_id="snap-001",
        )
        assert result is partitions
        assert isinstance(result[0], PartitionInfo)
        assert result[0].partition_key == "2024"


class TestServiceDelegatesWriteArtifactMetadata:
    """Tests for write_artifact_metadata delegation."""

    def test_service_delegates_write_artifact_metadata(self) -> None:
        """Should delegate write_artifact_metadata to the underlying writer."""
        from ditto_features.services.derived.artifact_persistence_service import (
            ArtifactPersistenceService,
        )

        mock_writer = MagicMock()
        service = ArtifactPersistenceService(
            artifact_root=Path("/tmp/data"),
            _writer=mock_writer,
        )
        spec_record = _make_spec_record()
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()
        partitions = _make_partitions()

        service.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id="drv-meta-001",
                compile_identity=compile_identity,
                analysis=analysis,
                partitions=partitions,
                request_start="2024-01-01",
                request_end="2025-12-31",
                source_snapshot_id="snap-001",
            ),
        )

        mock_writer.write_artifact_metadata.assert_called_once()


class TestServiceDelegatesUpdateArtifactMetadata:
    """Tests for update_artifact_metadata delegation."""

    def test_service_update_artifact_metadata(self) -> None:
        """Should delegate update_artifact_metadata to the underlying writer."""
        from ditto_features.services.derived.artifact_persistence_service import (
            ArtifactPersistenceService,
        )

        mock_writer = MagicMock()
        service = ArtifactPersistenceService(
            artifact_root=Path("/tmp/data"),
            _writer=mock_writer,
        )
        spec_record = _make_spec_record()
        compile_identity = _make_compile_identity_dict()
        partitions = _make_partitions()
        manifest_record = _make_manifest_record()
        minimal_dq_record = _make_minimal_dq_record()

        service.update_artifact_metadata(
            spec=spec_record,
            run_id="drv-update-001",
            compile_identity=compile_identity,
            partitions=partitions,
            source_snapshot_id="snap-001",
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
        )

        mock_writer.update_artifact_metadata.assert_called_once_with(
            spec=spec_record,
            run_id="drv-update-001",
            compile_identity=compile_identity,
            partitions=partitions,
            source_snapshot_id="snap-001",
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
        )
