"""Tests for DerivedArtifactWriter."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import orjson
import polars as pl
import pytest
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression import Analysis, CompileIdentity
from ditto_features.models.derived import DerivedSpecRecord, PartitionInfo
from ditto_features.publication_safety_records import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)
from ditto_features.storage.derived_artifact_writer import (
    ArtifactMetadataParams,
    ArtifactMetadataUpdateParams,
)

_TIME_KEY = "trade_date"


def _make_spec_record(
    *,
    profile: MaterializationProfile = MaterializationProfile.SERIES,
    derived_id: str = "factor.test_factor",
    version: int = 1,
) -> DerivedSpecRecord:
    """Build a DerivedSpecRecord for writer tests."""
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


def _make_compile_identity() -> CompileIdentity:
    return CompileIdentity(
        compile_input_hash="hash-abc",
        operator_fingerprint="op-fp",
        compiler_fingerprint="cc-fp",
        cache_key="cache-key",
        engine_codegen_version="codegen-v1",
        analysis_version="analysis-v1",
        polars_version="0.x",
        expr_serialization_format="expr-v1",
    )


def _make_compile_identity_dict() -> dict[str, object]:
    return asdict(_make_compile_identity())


def _make_analysis() -> Analysis:
    return Analysis(
        dependencies=("close",),
        operator_names=("rolling_mean",),
        lookback=20,
        requires_full_day=True,
        scope="per_instrument",
    )


def _make_analysis_dict() -> dict[str, object]:
    return asdict(_make_analysis())


def _make_frame(*, years: tuple[str, ...] = ("2024", "2025")) -> pl.DataFrame:
    rows: list[dict[str, str | float]] = []
    for year in years:
        rows.append(
            {
                "instrument_id": "000001.SZ",
                "trade_date": f"{year}-06-15",
                "value": 1.0,
            }
        )
    return pl.DataFrame(rows)


def _make_partitions() -> tuple[PartitionInfo, ...]:
    return (
        PartitionInfo(
            partition_key="2024",
            partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
            row_count=1,
            checksum="sha-2024",
        ),
    )


def _make_manifest_record() -> CompatibilityManifestRecord:
    return CompatibilityManifestRecord(
        derived_id="factor.test_factor",
        version=1,
        manifest_hash="manifest-hash-001",
        payload={"engine_codegen_version": "v1"},
        created_at="2026-03-17T00:00:00+00:00",
    )


def _make_minimal_dq_record(
    *,
    run_id: str = "drv-test",
) -> DerivedMinimalDQSummaryRecord:
    return DerivedMinimalDQSummaryRecord(
        derived_id="factor.test_factor",
        version=1,
        run_id=run_id,
        passed=True,
        error_count=0,
        payload={"row_count": 10},
        created_at="2026-03-17T00:00:00+00:00",
    )


class TestWriteEphemeralResult:
    """Tests for write_ephemeral_result."""

    def test_write_ephemeral_result_creates_parquet(self, tmp_path: Path) -> None:
        """write_ephemeral_result should create parquet in ephemeral directory."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()
        run_id = "drv-test-run-001"

        writer.write_ephemeral_result(
            spec=spec_record,
            run_id=run_id,
            frame=frame,
        )

        ephemeral_dir = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / "factor.test_factor"
            / "v1"
            / "_ephemeral"
            / run_id
        )
        assert ephemeral_dir.exists()
        parquet_file = ephemeral_dir / "result.parquet"
        assert parquet_file.exists()

        loaded = pl.read_parquet(parquet_file)
        assert loaded.height == frame.height
        assert set(loaded.columns) == set(frame.columns)


class TestWriteDurablePartitions:
    """Tests for write_durable_partitions."""

    def test_write_durable_partitions_creates_yearly_parquets(
        self, tmp_path: Path
    ) -> None:
        """write_durable_partitions should create per-year parquet files."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)
        frame = _make_frame(years=("2024", "2025"))

        partitions = writer.write_durable_partitions(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-test-run-002",
            frame=frame,
            request_start="2024-01-01",
            request_end="2025-12-31",
            source_snapshot_id=None,
        )

        assert len(partitions) == 2
        partition_keys = {p.partition_key for p in partitions}
        assert partition_keys == {"2024", "2025"}

        # Verify parquet files exist
        for partition in partitions:
            parquet_path = tmp_path / partition.partition_path
            assert parquet_path.exists()

    def test_write_durable_partitions_computes_checksums(self, tmp_path: Path) -> None:
        """Each partition should have a SHA256 checksum."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        frame = _make_frame(years=("2024",))

        partitions = writer.write_durable_partitions(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-test-run-003",
            frame=frame,
            request_start="2024-01-01",
            request_end="2024-12-31",
            source_snapshot_id="snap-001",
        )

        assert len(partitions) == 1
        partition = partitions[0]
        assert partition.checksum is not None

        # Verify checksum matches
        parquet_bytes = (tmp_path / partition.partition_path).read_bytes()
        expected_checksum = sha256(parquet_bytes).hexdigest()
        assert partition.checksum == expected_checksum

    def test_write_durable_partitions_uses_atomic_write(self, tmp_path: Path) -> None:
        """Partitions should be written atomically (tmp then rename)."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        frame = _make_frame(years=("2024",))

        writer.write_durable_partitions(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-test-run-004",
            frame=frame,
            request_start="2024-01-01",
            request_end="2024-12-31",
            source_snapshot_id=None,
        )

        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.test_factor" / "v1"
        )
        # .tmp file should not remain after write
        assert not list(version_root.glob("*.tmp.parquet"))


class TestWriteArtifactMetadata:
    """Tests for write_artifact_metadata."""

    def test_write_artifact_metadata_writes_metadata(self, tmp_path: Path) -> None:
        """write_artifact_metadata should write artifact_metadata.json."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        run_id = "drv-test-run-005"
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()
        partitions = (
            PartitionInfo(
                partition_key="2024",
                partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
                row_count=1,
                checksum="abc123",
            ),
        )

        writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                analysis=analysis,
                partitions=partitions,
                request_start="2024-01-01",
                request_end="2024-12-31",
                source_snapshot_id="snap-001",
            ),
        )

        metadata_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )
        assert metadata_path.exists()

        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["run_id"] == run_id
        assert payload["coverage"]["start"] == "2024-01-01"
        assert payload["coverage"]["end"] == "2024-12-31"
        assert payload["input_snapshots"] == ["snap-001"]
        assert len(payload["partitions_written"]) == 1
        assert payload["partitions_written"][0]["partition_key"] == "2024"
        assert payload["compile_identity"]["cache_key"] == "cache-key"
        # orjson deserializes tuples as lists
        assert payload["analysis"]["dependencies"] == ["close"]

    def test_write_artifact_metadata_empty_source_snapshot(
        self, tmp_path: Path
    ) -> None:
        """source_snapshot_id=None should produce empty input_snapshots list."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()

        writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id="drv-test-run-006",
                compile_identity=compile_identity,
                analysis=analysis,
                partitions=(),
                request_start="2024-01-01",
                request_end="2024-12-31",
                source_snapshot_id=None,
            ),
        )

        metadata_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / "drv-test-run-006"
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["input_snapshots"] == []
        assert payload["partitions_written"] == []


class TestUpdateArtifactMetadata:
    """Tests for update_artifact_metadata."""

    def test_update_artifact_metadata_injects_publication(self, tmp_path: Path) -> None:
        """update_artifact_metadata should read existing JSON and inject publication."""

        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        run_id = "drv-test-run-007"
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()
        partitions = (
            PartitionInfo(
                partition_key="2024",
                partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
                row_count=10,
                checksum="sha-checksum",
            ),
        )

        # First write initial metadata
        writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                analysis=analysis,
                partitions=partitions,
                request_start="2024-01-01",
                request_end="2024-12-31",
                source_snapshot_id="snap-002",
            ),
        )

        # Now update with publication info
        manifest_record = CompatibilityManifestRecord(
            derived_id="factor.test_factor",
            version=1,
            manifest_hash="manifest-hash-001",
            payload={"engine_codegen_version": "v1"},
            created_at="2026-03-17T00:00:00+00:00",
        )
        minimal_dq_record = DerivedMinimalDQSummaryRecord(
            derived_id="factor.test_factor",
            version=1,
            run_id=run_id,
            passed=True,
            error_count=0,
            payload={"row_count": 10},
            created_at="2026-03-17T00:00:00+00:00",
        )

        writer.update_artifact_metadata(
            ArtifactMetadataUpdateParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                partitions=partitions,
                source_snapshot_id="snap-002",
                manifest_record=manifest_record,
                minimal_dq_record=minimal_dq_record,
            )
        )

        metadata_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())

        # Publication section should be injected
        assert "publication" in payload
        assert payload["publication"]["manifest_hash"] == "manifest-hash-001"
        assert payload["publication"]["compatibility_manifest"] == {
            "engine_codegen_version": "v1"
        }
        assert payload["publication"]["minimal_dq_summary"]["passed"] is True
        assert payload["publication"]["minimal_dq_summary"]["error_count"] == 0
        assert payload["publication"]["minimal_dq_summary"]["run_id"] == run_id

        # Compile identity and partitions should be refreshed
        assert payload["compile_identity"]["cache_key"] == "cache-key"
        assert payload["input_snapshots"] == ["snap-002"]
        assert len(payload["partitions_written"]) == 1

    def test_update_artifact_metadata_none_source_snapshot(
        self, tmp_path: Path
    ) -> None:
        """source_snapshot_id=None should produce empty input_snapshots on update."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        run_id = "drv-test-run-008"
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()

        writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                analysis=analysis,
                partitions=(),
                request_start="2024-01-01",
                request_end="2024-12-31",
                source_snapshot_id=None,
            ),
        )

        manifest_record = CompatibilityManifestRecord(
            derived_id="factor.test_factor",
            version=1,
            manifest_hash="hash",
            payload={},
            created_at="2026-03-17T00:00:00+00:00",
        )
        minimal_dq_record = DerivedMinimalDQSummaryRecord(
            derived_id="factor.test_factor",
            version=1,
            run_id=run_id,
            passed=True,
            error_count=0,
            payload={},
            created_at="2026-03-17T00:00:00+00:00",
        )

        writer.update_artifact_metadata(
            ArtifactMetadataUpdateParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                partitions=(),
                source_snapshot_id=None,
                manifest_record=manifest_record,
                minimal_dq_record=minimal_dq_record,
            )
        )

        metadata_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["input_snapshots"] == []

    def test_update_artifact_metadata_accepts_params_object(
        self, tmp_path: Path
    ) -> None:
        """update_artifact_metadata should accept one context-shaped object."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        run_id = "drv-test-run-params"
        compile_identity = _make_compile_identity_dict()
        partitions = _make_partitions()

        writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                analysis=_make_analysis_dict(),
                partitions=partitions,
                request_start="2024-01-01",
                request_end="2024-12-31",
                source_snapshot_id="snap-old",
            ),
        )

        writer.update_artifact_metadata(
            ArtifactMetadataUpdateParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                partitions=partitions,
                source_snapshot_id="snap-params",
                manifest_record=_make_manifest_record(),
                minimal_dq_record=_make_minimal_dq_record(run_id=run_id),
            )
        )

        metadata_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["input_snapshots"] == ["snap-params"]
        assert payload["publication"]["manifest_hash"] == "manifest-hash-001"


class TestExtractPartitionKeys:
    """Tests for extract_partition_keys."""

    def test_extracts_unique_years(self) -> None:
        """Should extract unique year keys from the time column."""
        from ditto_features.storage.derived_artifact_writer import (
            extract_partition_keys,
        )

        frame = _make_frame(years=("2023", "2024", "2024", "2025"))

        keys = extract_partition_keys(frame, _TIME_KEY)

        assert keys == ("2023", "2024", "2025")

    def test_single_year(self) -> None:
        """Should return single key for single-year data."""
        from ditto_features.storage.derived_artifact_writer import (
            extract_partition_keys,
        )

        frame = _make_frame(years=("2024",))

        keys = extract_partition_keys(frame, _TIME_KEY)

        assert keys == ("2024",)


class TestTwoPhaseCommit:
    """Tests for two-phase commit in write_durable_partitions (MAT-M-5)."""

    def test_multi_partition_all_or_nothing(self, tmp_path: Path) -> None:
        """Mid-write failure should leave NO final parquet files on disk."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)
        frame = _make_frame(years=("2024", "2025", "2026"))

        # Make write_parquet fail on the 2nd partition (2025)
        original_write_parquet = pl.DataFrame.write_parquet
        call_count = 0

        def _failing_write_parquet(self, path, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            # Fail on the 2nd partition write (2025).
            if call_count == 2:
                raise RuntimeError("disk full on second partition")
            original_write_parquet(self, path, **kwargs)

        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.test_factor" / "v1"
        )

        with pytest.raises(RuntimeError, match="disk full on second partition"):
            with patch.object(pl.DataFrame, "write_parquet", _failing_write_parquet):
                writer.write_durable_partitions(
                    spec=spec_record,
                    time_key=_TIME_KEY,
                    run_id="drv-test-run-fail-001",
                    frame=frame,
                    request_start="2024-01-01",
                    request_end="2026-12-31",
                    source_snapshot_id=None,
                )

        # No final parquet files should exist (all-or-nothing)
        final_files = list(version_root.glob("*.parquet"))
        assert final_files == [], (
            f"Expected no final parquet files after failure, got: {final_files}"
        )

    def test_multi_partition_temp_files_cleaned_up(self, tmp_path: Path) -> None:
        """After successful write, no .tmp.parquet files should remain."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)
        frame = _make_frame(years=("2024", "2025"))

        writer.write_durable_partitions(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-test-run-ok-001",
            frame=frame,
            request_start="2024-01-01",
            request_end="2025-12-31",
            source_snapshot_id=None,
        )

        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.test_factor" / "v1"
        )
        # No temp files should remain
        temp_files = list(version_root.glob("*.tmp.parquet"))
        assert temp_files == [], (
            f"Expected no temp files after success, got: {temp_files}"
        )

        # Both final files should exist
        final_files = sorted(version_root.glob("*.parquet"))
        assert len(final_files) == 2


class TestEphemeralAtomicWrite:
    """Tests for atomic write in write_ephemeral_result (MAT-M-8)."""

    def test_ephemeral_result_uses_atomic_write(self, tmp_path: Path) -> None:
        """write_ephemeral_result should delegate to atomic_write."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()
        run_id = "drv-test-run-atomic-001"

        expected_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / "factor.test_factor"
            / "v1"
            / "_ephemeral"
            / run_id
            / "result.parquet"
        )

        with patch(
            "ditto_features.storage.derived_artifact_writer.atomic_write"
        ) as mock_atomic:
            writer.write_ephemeral_result(
                spec=spec_record,
                run_id=run_id,
                frame=frame,
            )
            mock_atomic.assert_called_once_with(
                frame, expected_path, compression="zstd"
            )

    def test_ephemeral_result_writes_readable_parquet(self, tmp_path: Path) -> None:
        """write_ephemeral_result should produce a readable parquet file."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()
        run_id = "drv-test-run-atomic-002"

        writer.write_ephemeral_result(
            spec=spec_record,
            run_id=run_id,
            frame=frame,
        )

        ephemeral_dir = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / "factor.test_factor"
            / "v1"
            / "_ephemeral"
            / run_id
        )
        parquet_file = ephemeral_dir / "result.parquet"
        assert parquet_file.exists()
        loaded = pl.read_parquet(parquet_file)
        assert loaded.height == frame.height


class TestMetadataAtomicWrite:
    """Tests for atomic write in metadata methods (MAT-M-8)."""

    def test_artifact_metadata_uses_atomic_write(self, tmp_path: Path) -> None:
        """write_artifact_metadata should delegate to atomic_bytes_write."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        run_id = "drv-test-run-meta-001"
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()
        partitions = (
            PartitionInfo(
                partition_key="2024",
                partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
                row_count=1,
                checksum="abc123",
            ),
        )

        expected_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )

        with patch(
            "ditto_features.storage.derived_artifact_writer.atomic_bytes_write"
        ) as mock_atomic:
            writer.write_artifact_metadata(
                ArtifactMetadataParams(
                    spec=spec_record,
                    run_id=run_id,
                    compile_identity=compile_identity,
                    analysis=analysis,
                    partitions=partitions,
                    request_start="2024-01-01",
                    request_end="2024-12-31",
                    source_snapshot_id="snap-001",
                ),
            )
            mock_atomic.assert_called_once()
            # Verify the first positional arg is bytes (orjson output)
            call_args = mock_atomic.call_args
            assert isinstance(call_args[0][0], bytes)
            assert call_args[0][1] == expected_path

    def test_update_artifact_metadata_uses_atomic_write(self, tmp_path: Path) -> None:
        """update_artifact_metadata should delegate to atomic_bytes_write."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record()
        run_id = "drv-test-run-upd-001"
        compile_identity = _make_compile_identity_dict()
        analysis = _make_analysis_dict()
        partitions = (
            PartitionInfo(
                partition_key="2024",
                partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
                row_count=10,
                checksum="sha-checksum",
            ),
        )

        # First write initial metadata
        writer.write_artifact_metadata(
            ArtifactMetadataParams(
                spec=spec_record,
                run_id=run_id,
                compile_identity=compile_identity,
                analysis=analysis,
                partitions=partitions,
                request_start="2024-01-01",
                request_end="2024-12-31",
                source_snapshot_id="snap-002",
            ),
        )

        manifest_record = CompatibilityManifestRecord(
            derived_id="factor.test_factor",
            version=1,
            manifest_hash="manifest-hash-001",
            payload={"engine_codegen_version": "v1"},
            created_at="2026-03-17T00:00:00+00:00",
        )
        minimal_dq_record = DerivedMinimalDQSummaryRecord(
            derived_id="factor.test_factor",
            version=1,
            run_id=run_id,
            passed=True,
            error_count=0,
            payload={"row_count": 10},
            created_at="2026-03-17T00:00:00+00:00",
        )

        expected_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.test_factor"
            / "v1"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )

        with patch(
            "ditto_features.storage.derived_artifact_writer.atomic_bytes_write"
        ) as mock_atomic:
            writer.update_artifact_metadata(
                ArtifactMetadataUpdateParams(
                    spec=spec_record,
                    run_id=run_id,
                    compile_identity=compile_identity,
                    partitions=partitions,
                    source_snapshot_id="snap-002",
                    manifest_record=manifest_record,
                    minimal_dq_record=minimal_dq_record,
                )
            )
            mock_atomic.assert_called_once()
            call_args = mock_atomic.call_args
            assert isinstance(call_args[0][0], bytes)
            assert call_args[0][1] == expected_path

            # Verify the payload contains publication info
            payload = orjson.loads(call_args[0][0])
            assert "publication" in payload
            assert payload["publication"]["manifest_hash"] == "manifest-hash-001"


class TestPartitionInfo:
    """Tests for PartitionInfo dataclass."""

    def test_is_frozen(self) -> None:
        info = PartitionInfo(
            partition_key="2024",
            partition_path="some/path.parquet",
            row_count=10,
            checksum="sha",
        )

        with pytest.raises(AttributeError):
            info.partition_key = "2025"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Incremental partition merge tests (MAT-M-6)
# ---------------------------------------------------------------------------


class TestIncrementalPartitionMerge:
    """Tests for write_incremental_partition -- merge into existing year partitions."""

    def test_incremental_partition_creates_new_if_missing(self, tmp_path: Path) -> None:
        """No existing file -> just writes the new partition data."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)
        new_frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-06-15", "2024-06-16"],
                "value": [10.0, 20.0],
            }
        )

        partitions = writer.write_incremental_partition(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-incr-001",
            frame=new_frame,
            source_snapshot_id=None,
        )

        assert len(partitions) == 1
        assert partitions[0].partition_key == "2024"
        assert partitions[0].row_count == 2

        # Verify file exists and contains the correct data
        parquet_path = tmp_path / partitions[0].partition_path
        assert parquet_path.exists()
        loaded = pl.read_parquet(parquet_path)
        assert loaded.height == 2

    def test_incremental_partition_merges_with_existing(self, tmp_path: Path) -> None:
        """existing + new -> merged with both datasets present."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)

        # Pre-existing partition data
        existing_frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0],
            }
        )
        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.test_factor" / "v1"
        )
        version_root.mkdir(parents=True, exist_ok=True)
        existing_frame.write_parquet(version_root / "2024.parquet")

        # New incremental data
        new_frame = pl.DataFrame(
            {
                "instrument_id": [3],
                "trade_date": ["2024-01-04"],
                "value": [30.0],
            }
        )

        partitions = writer.write_incremental_partition(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-incr-002",
            frame=new_frame,
            source_snapshot_id="snap-002",
        )

        assert len(partitions) == 1
        assert partitions[0].row_count == 3

        # Verify merged content
        parquet_path = tmp_path / partitions[0].partition_path
        loaded = pl.read_parquet(parquet_path).sort("instrument_id", "trade_date")
        assert loaded.height == 3
        assert loaded["instrument_id"].to_list() == [1, 2, 3]

    def test_incremental_partition_new_overwrites_old(self, tmp_path: Path) -> None:
        """Duplicate (instrument_id, trade_date) -> new value overwrites old."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)

        # Pre-existing: instrument_id=1 on 2024-01-02 with value=10.0
        existing_frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "value": [10.0],
            }
        )
        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.test_factor" / "v1"
        )
        version_root.mkdir(parents=True, exist_ok=True)
        existing_frame.write_parquet(version_root / "2024.parquet")

        # New data: same (instrument_id, trade_date) but updated value=99.0
        new_frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "value": [99.0],
            }
        )

        partitions = writer.write_incremental_partition(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-incr-003",
            frame=new_frame,
            source_snapshot_id="snap-003",
        )

        assert len(partitions) == 1
        assert partitions[0].row_count == 1

        # Verify the new value overwrote the old one
        parquet_path = tmp_path / partitions[0].partition_path
        loaded = pl.read_parquet(parquet_path)
        assert loaded.height == 1
        assert loaded["value"][0] == 99.0

    def test_incremental_partition_multi_year(self, tmp_path: Path) -> None:
        """Incremental data spanning multiple years merges each independently."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)

        # Pre-existing 2024 data
        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.test_factor" / "v1"
        )
        version_root.mkdir(parents=True, exist_ok=True)
        existing_2024 = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-06-01"],
                "value": [5.0],
            }
        )
        existing_2024.write_parquet(version_root / "2024.parquet")

        # New data spanning 2024 and 2025
        new_frame = pl.DataFrame(
            {
                "instrument_id": [2, 3],
                "trade_date": ["2024-06-15", "2025-01-05"],
                "value": [15.0, 25.0],
            }
        )

        partitions = writer.write_incremental_partition(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-incr-004",
            frame=new_frame,
            source_snapshot_id=None,
        )

        assert len(partitions) == 2
        partition_keys = {p.partition_key for p in partitions}
        assert partition_keys == {"2024", "2025"}

        # 2024 should have 2 rows (existing + new)
        p2024 = next(p for p in partitions if p.partition_key == "2024")
        loaded_2024 = pl.read_parquet(tmp_path / p2024.partition_path).sort(
            "instrument_id"
        )
        assert loaded_2024.height == 2

        # 2025 should have 1 row (new only)
        p2025 = next(p for p in partitions if p.partition_key == "2025")
        loaded_2025 = pl.read_parquet(tmp_path / p2025.partition_path)
        assert loaded_2025.height == 1


# ---------------------------------------------------------------------------
# Configurable compression tests (MAT-M-9)
# ---------------------------------------------------------------------------


class TestConfigurableCompression:
    """Tests for configurable compression in DerivedArtifactWriter (MAT-M-9)."""

    def test_default_compression_zstd_ephemeral(self, tmp_path: Path) -> None:
        """Default compression should be zstd for ephemeral writes."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec_record = _make_spec_record(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()
        run_id = "drv-comp-zstd-001"

        writer.write_ephemeral_result(
            spec=spec_record,
            run_id=run_id,
            frame=frame,
        )

        ephemeral_dir = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / "factor.test_factor"
            / "v1"
            / "_ephemeral"
            / run_id
        )
        parquet_file = ephemeral_dir / "result.parquet"
        assert parquet_file.exists()
        loaded = pl.read_parquet(parquet_file)
        assert loaded.equals(frame)

    def test_configurable_compression_snappy_ephemeral(self, tmp_path: Path) -> None:
        """Snappy compression should produce readable parquet for ephemeral writes."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path, compression="snappy")
        spec_record = _make_spec_record(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()
        run_id = "drv-comp-snappy-001"

        writer.write_ephemeral_result(
            spec=spec_record,
            run_id=run_id,
            frame=frame,
        )

        ephemeral_dir = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / "factor.test_factor"
            / "v1"
            / "_ephemeral"
            / run_id
        )
        parquet_file = ephemeral_dir / "result.parquet"
        assert parquet_file.exists()
        loaded = pl.read_parquet(parquet_file)
        assert loaded.equals(frame)

    def test_configurable_compression_snappy_durable(self, tmp_path: Path) -> None:
        """Snappy compression should be used in durable partition writes."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path, compression="snappy")
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)
        frame = _make_frame(years=("2024", "2025"))

        partitions = writer.write_durable_partitions(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-comp-snappy-002",
            frame=frame,
            request_start="2024-01-01",
            request_end="2025-12-31",
            source_snapshot_id=None,
        )

        assert len(partitions) == 2
        for partition in partitions:
            parquet_path = tmp_path / partition.partition_path
            assert parquet_path.exists()
            loaded = pl.read_parquet(parquet_path)
            assert loaded.height == 1

    def test_configurable_compression_snappy_incremental(self, tmp_path: Path) -> None:
        """Snappy compression should be used in incremental partition writes."""
        from ditto_features.storage.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path, compression="snappy")
        spec_record = _make_spec_record(profile=MaterializationProfile.SERIES)
        new_frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-06-15"],
                "value": [10.0],
            }
        )

        partitions = writer.write_incremental_partition(
            spec=spec_record,
            time_key=_TIME_KEY,
            run_id="drv-comp-snappy-003",
            frame=new_frame,
            source_snapshot_id=None,
        )

        assert len(partitions) == 1
        parquet_path = tmp_path / partitions[0].partition_path
        assert parquet_path.exists()
        loaded = pl.read_parquet(parquet_path)
        assert loaded.equals(new_frame)
