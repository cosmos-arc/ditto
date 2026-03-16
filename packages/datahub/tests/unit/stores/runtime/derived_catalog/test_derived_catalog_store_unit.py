"""Tests for derived catalog runtime stores."""

from pathlib import Path

from ditto_core.engine.materialization.models import DerivedVersionStatus
from ditto_datahub.models.derived import (
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.stores.runtime.derived_catalog import (
    DerivedCatalogReader,
    DerivedCatalogWriter,
)


class TestDerivedCatalogStore:
    """Tests for derived catalog runtime reader/writer."""

    def test_spec_and_version_roundtrip(self, tmp_path: Path) -> None:
        """Spec and version metadata should roundtrip by derived/version."""
        writer = DerivedCatalogWriter(base_path=tmp_path)
        reader = DerivedCatalogReader(base_path=tmp_path)
        spec = DerivedSpecRecord(
            derived_id="factor.momentum_20d",
            version=3,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="spec-hash-v3",
            spec_json={
                "id": "factor.momentum_20d",
                "version": 3,
                "expression": "ts_mean(close, 20)",
            },
            created_at="2026-03-13T16:00:00+08:00",
        )
        version = DerivedVersionRecord(
            derived_id="factor.momentum_20d",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-13T16:00:00+08:00",
            updated_at="2026-03-13T16:05:00+08:00",
        )

        writer.write_spec(spec)
        writer.write_version(version)

        assert reader.read_spec("factor.momentum_20d", 3) == spec
        assert reader.read_version("factor.momentum_20d", 3) == version

    def test_run_state_and_partitions_roundtrip(self, tmp_path: Path) -> None:
        """Run, state, and partitions should roundtrip and preserve ordering."""
        writer = DerivedCatalogWriter(base_path=tmp_path)
        reader = DerivedCatalogReader(base_path=tmp_path)
        run = DerivedRunRecord(
            run_id="run-001",
            derived_id="factor.momentum_20d",
            version=3,
            mode="incremental",
            trigger="manual",
            request_start="2026-03-01",
            request_end="2026-03-13",
            compute_start="2026-02-10",
            compute_end="2026-03-13",
            source_snapshot_id="market:20260313-001",
            status="SUCCESS",
            rows_written=240,
            partitions_written=("2026-03",),
            error_message=None,
            created_at="2026-03-13T16:10:00+08:00",
            started_at="2026-03-13T16:10:05+08:00",
            finished_at="2026-03-13T16:10:55+08:00",
        )
        state = DerivedStateRecord(
            derived_id="factor.momentum_20d",
            active_version=3,
            coverage_start="2025-01-01",
            coverage_end="2026-03-13",
            watermark="2026-03-13",
            latest_run_id="run-001",
            latest_run_status="SUCCESS",
            total_rows=240,
            updated_at="2026-03-13T16:11:00+08:00",
        )
        partitions = (
            DerivedPartitionRecord(
                run_id="run-001",
                derived_id="factor.momentum_20d",
                version=3,
                partition_key="2026-02",
                partition_path="factors/style/momentum_20d/2026-02.parquet",
                row_count=120,
                checksum="sha256:part-02",
                written_at="2026-03-13T16:10:40+08:00",
            ),
            DerivedPartitionRecord(
                run_id="run-001",
                derived_id="factor.momentum_20d",
                version=3,
                partition_key="2026-03",
                partition_path="factors/style/momentum_20d/2026-03.parquet",
                row_count=120,
                checksum="sha256:part-03",
                written_at="2026-03-13T16:10:50+08:00",
            ),
        )

        writer.write_run(run)
        writer.write_state(state)
        writer.write_partitions(partitions)

        assert reader.read_run("factor.momentum_20d", 3, "run-001") == run
        assert reader.get_latest_run("factor.momentum_20d", 3) == run
        assert reader.read_state("factor.momentum_20d") == state
        assert reader.list_partitions("factor.momentum_20d", 3, "run-001") == [
            partitions[0],
            partitions[1],
        ]

    def test_missing_records_return_none_or_empty(self, tmp_path: Path) -> None:
        """Missing records should return None or an empty collection."""
        reader = DerivedCatalogReader(base_path=tmp_path)

        assert reader.read_spec("factor.momentum_20d", 9) is None
        assert reader.read_version("factor.momentum_20d", 9) is None
        assert reader.read_run("factor.momentum_20d", 9, "run-x") is None
        assert reader.get_latest_run("factor.momentum_20d", 9) is None
        assert reader.read_state("factor.momentum_20d") is None
        assert reader.list_partitions("factor.momentum_20d", 9, "run-x") == []
