"""Tests for DerivedArtifactWriter."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_core.engine.materialization import Analysis, CompileIdentity
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_datahub.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)


def _make_spec(
    *,
    profile: MaterializationProfile = MaterializationProfile.SERIES,
    derived_id: str = "factor.test_factor",
    version: int = 1,
) -> DerivedSpec:
    return DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=profile,
        expression="close_20",
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


def _make_analysis() -> Analysis:
    return Analysis(
        dependencies=("close",),
        operator_names=("rolling_mean",),
        lookback=20,
        requires_full_day=True,
        scope="per_instrument",
    )


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


class TestWriteEphemeralResult:
    """Tests for write_ephemeral_result."""

    def test_write_ephemeral_result_creates_parquet(self, tmp_path: Path) -> None:
        """write_ephemeral_result should create parquet in ephemeral directory."""
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec(profile=MaterializationProfile.DERIVE)
        frame = _make_frame()
        run_id = "drv-test-run-001"

        writer.write_ephemeral_result(
            spec=spec,
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
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec(profile=MaterializationProfile.SERIES)
        frame = _make_frame(years=("2024", "2025"))

        partitions = writer.write_durable_partitions(
            spec=spec,
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
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec()
        frame = _make_frame(years=("2024",))

        partitions = writer.write_durable_partitions(
            spec=spec,
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
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec()
        frame = _make_frame(years=("2024",))

        writer.write_durable_partitions(
            spec=spec,
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
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
            PartitionInfo,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec()
        run_id = "drv-test-run-005"
        compile_identity = _make_compile_identity()
        analysis = _make_analysis()
        partitions = (
            PartitionInfo(
                partition_key="2024",
                partition_path="derived/artifacts/series/factor.test_factor/v1/2024.parquet",
                row_count=1,
                checksum="abc123",
            ),
        )

        writer.write_artifact_metadata(
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            analysis=analysis,
            partitions=partitions,
            request_start="2024-01-01",
            request_end="2024-12-31",
            source_snapshot_id="snap-001",
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
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec()
        compile_identity = _make_compile_identity()
        analysis = _make_analysis()

        writer.write_artifact_metadata(
            spec=spec,
            run_id="drv-test-run-006",
            compile_identity=compile_identity,
            analysis=analysis,
            partitions=(),
            request_start="2024-01-01",
            request_end="2024-12-31",
            source_snapshot_id=None,
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

        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
            PartitionInfo,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec()
        run_id = "drv-test-run-007"
        compile_identity = _make_compile_identity()
        analysis = _make_analysis()
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
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            analysis=analysis,
            partitions=partitions,
            request_start="2024-01-01",
            request_end="2024-12-31",
            source_snapshot_id="snap-002",
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
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            partitions=partitions,
            source_snapshot_id="snap-002",
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
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
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            DerivedArtifactWriter,
        )

        writer = DerivedArtifactWriter(artifact_root=tmp_path)
        spec = _make_spec()
        run_id = "drv-test-run-008"
        compile_identity = _make_compile_identity()
        analysis = _make_analysis()

        writer.write_artifact_metadata(
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            analysis=analysis,
            partitions=(),
            request_start="2024-01-01",
            request_end="2024-12-31",
            source_snapshot_id=None,
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
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            partitions=(),
            source_snapshot_id=None,
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
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


class TestExtractPartitionKeys:
    """Tests for extract_partition_keys."""

    def test_extracts_unique_years(self) -> None:
        """Should extract unique year keys from the time column."""
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            extract_partition_keys,
        )

        spec = _make_spec()
        frame = _make_frame(years=("2023", "2024", "2024", "2025"))

        keys = extract_partition_keys(frame, spec)

        assert keys == ("2023", "2024", "2025")

    def test_single_year(self) -> None:
        """Should return single key for single-year data."""
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            extract_partition_keys,
        )

        spec = _make_spec()
        frame = _make_frame(years=("2024",))

        keys = extract_partition_keys(frame, spec)

        assert keys == ("2024",)


class TestPartitionInfo:
    """Tests for PartitionInfo dataclass."""

    def test_is_frozen(self) -> None:
        from ditto_datahub.stores.runtime.derived_artifact_writer import (
            PartitionInfo,
        )

        info = PartitionInfo(
            partition_key="2024",
            partition_path="some/path.parquet",
            row_count=10,
            checksum="sha",
        )

        with pytest.raises(AttributeError):
            info.partition_key = "2025"  # type: ignore[misc]
