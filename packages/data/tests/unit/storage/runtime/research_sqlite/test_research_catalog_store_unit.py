"""Tests for SQLite-backed research catalog stores."""

from ditto_analytics.models.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_data.storage.runtime.research_sqlite import (
    SQLiteResearchCatalogReader,
    SQLiteResearchCatalogWriter,
)


class TestSQLiteResearchCatalogStore:
    """Tests for research catalog SQLite reader/writer."""

    def test_roundtrip_preserves_extended_dataset_snapshot_contract(
        self,
        sqlite_client,
    ) -> None:
        """Dataset snapshots should roundtrip the full frozen contract payload."""
        reader = SQLiteResearchCatalogReader(sqlite_client)
        writer = SQLiteResearchCatalogWriter(sqlite_client)
        writer.write_spine_spec(
            ResearchSpineSpecRecord(
                spine_id="spine.cn_stock.default",
                universe_id="universe.cn.all",
                version=1,
                calendar="cn_stock",
                grain="1d",
                entity_key="instrument_id",
                description=None,
                created_at="2026-03-14T12:00:00+08:00",
            )
        )
        writer.write_dataset_spec(
            ResearchDatasetSpecRecord(
                dataset_id="research.alpha_beta",
                spine_id="spine.cn_stock.default",
                version=1,
                derived_ids=("factor.alpha", "factor.beta"),
                join_policy="left_preserving_pit",
                known_at_policy="sample_time",
                late_arrival_policy="require_rebuild",
                description=None,
                created_at="2026-03-14T12:00:00+08:00",
            )
        )
        writer.write_spine_snapshot(
            ResearchSpineSnapshotRecord(
                spine_snapshot_id="rsp-001",
                spine_id="spine.cn_stock.default",
                version=1,
                snapshot_start="2026-03-10",
                snapshot_end="2026-03-11",
                row_count=2,
                data_path="derived/research/spines/spine.cn_stock.default/snapshots/rsp-001/data.parquet",
                manifest_hash="manifest-spine-001",
                created_at="2026-03-14T12:10:00+08:00",
            )
        )
        record = ResearchDatasetSnapshotRecord(
            snapshot_id="rds-001",
            dataset_id="research.alpha_beta",
            dataset_spec_version=1,
            spine_snapshot_id="rsp-001",
            snapshot_start="2026-03-10",
            snapshot_end="2026-03-11",
            row_count=2,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-001/data.parquet",
            manifest_hash="manifest-dataset-001",
            known_at_policy="sample_time",
            effective_cutoff=None,
            spine_spec_version=1,
            resolved_versions={"factor.alpha": 2, "factor.beta": 1},
            resolved_inputs=(
                {
                    "derived_id": "factor.alpha",
                    "version": 2,
                    "artifact_path": "derived/artifacts/series/factor.alpha/v2",
                },
                {
                    "derived_id": "factor.beta",
                    "version": 1,
                    "artifact_path": "derived/artifacts/series/factor.beta/v1",
                },
            ),
            source_snapshot_ids=("market:20260310-001", "market:20260311-001"),
            builder_version="unified-derived-research-v1",
            created_at="2026-03-14T12:20:00+08:00",
        )

        writer.write_dataset_snapshot(record)

        assert reader.read_dataset_snapshot("rds-001") == record
        assert reader.get_latest_dataset_snapshot("research.alpha_beta") == record

    def test_roundtrip_preserves_non_default_versions(
        self,
        sqlite_client,
    ) -> None:
        """Version fields should roundtrip non-default values correctly."""
        reader = SQLiteResearchCatalogReader(sqlite_client)
        writer = SQLiteResearchCatalogWriter(sqlite_client)
        writer.write_spine_spec(
            ResearchSpineSpecRecord(
                spine_id="spine.cn_stock.v2",
                universe_id="universe.cn.all",
                version=2,
                calendar="cn_stock",
                grain="1d",
                entity_key="instrument_id",
                description="v2 spine",
                created_at="2026-03-14T12:00:00+08:00",
            )
        )

        spine_record = reader.read_spine_spec("spine.cn_stock.v2")
        assert spine_record is not None
        assert spine_record.version == 2

    def test_roundtrip_preserves_spec_versions_through_dataset_snapshot(
        self,
        sqlite_client,
    ) -> None:
        """Dataset snapshot should roundtrip both spec versions."""
        reader = SQLiteResearchCatalogReader(sqlite_client)
        writer = SQLiteResearchCatalogWriter(sqlite_client)
        writer.write_spine_spec(
            ResearchSpineSpecRecord(
                spine_id="spine.cn_stock.default",
                universe_id="universe.cn.all",
                version=1,
                calendar="cn_stock",
                grain="1d",
                entity_key="instrument_id",
                description=None,
                created_at="2026-03-14T12:00:00+08:00",
            )
        )
        writer.write_dataset_spec(
            ResearchDatasetSpecRecord(
                dataset_id="research.alpha_v2",
                spine_id="spine.cn_stock.default",
                version=2,
                derived_ids=("factor.alpha",),
                join_policy="left_preserving_pit",
                known_at_policy="sample_time",
                late_arrival_policy="require_rebuild",
                description=None,
                created_at="2026-03-14T12:00:00+08:00",
            )
        )
        writer.write_spine_snapshot(
            ResearchSpineSnapshotRecord(
                spine_snapshot_id="rsp-002",
                spine_id="spine.cn_stock.default",
                version=1,
                snapshot_start="2026-03-11",
                snapshot_end="2026-03-11",
                row_count=1,
                data_path="derived/research/spines/spine.cn_stock.default/snapshots/rsp-002/data.parquet",
                manifest_hash="manifest-spine-002",
                created_at="2026-03-14T12:15:00+08:00",
            )
        )
        record = ResearchDatasetSnapshotRecord(
            snapshot_id="rds-v2",
            dataset_id="research.alpha_v2",
            dataset_spec_version=2,
            spine_spec_version=1,
            spine_snapshot_id="rsp-002",
            snapshot_start="2026-03-11",
            snapshot_end="2026-03-11",
            row_count=1,
            data_path="derived/research/datasets/research.alpha_v2/snapshots/rds-v2/data.parquet",
            manifest_hash="manifest-dataset-v2",
            known_at_policy="sample_time",
            effective_cutoff=None,
            resolved_versions={"factor.alpha": 1},
            resolved_inputs=(
                {
                    "derived_id": "factor.alpha",
                    "version": 1,
                    "artifact_path": "derived/artifacts/series/factor.alpha/v1",
                },
            ),
            source_snapshot_ids=(),
            builder_version="unified-derived-research-v1",
            created_at="2026-03-14T12:25:00+08:00",
        )

        writer.write_dataset_snapshot(record)

        read_back = reader.read_dataset_snapshot("rds-v2")
        assert read_back == record
        assert read_back.dataset_spec_version == 2
        assert read_back.spine_spec_version == 1
