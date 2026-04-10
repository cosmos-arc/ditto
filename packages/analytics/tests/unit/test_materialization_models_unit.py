"""Tests for derived materialization models."""

from ditto_analytics.materialization.models import (
    DerivedPartition,
    DerivedRun,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
    DerivedState,
    DerivedVersion,
    DerivedVersionStatus,
)


class TestDerivedVersionStatus:
    """Tests for DerivedVersionStatus enum — unified lifecycle vocabulary."""

    def test_enum_values_are_lowercase(self) -> None:
        """All enum values must be lowercase for consistent persistence."""
        assert DerivedVersionStatus.DRAFT.value == "draft"
        assert DerivedVersionStatus.MATERIALIZED.value == "materialized"
        assert DerivedVersionStatus.PUBLISHED.value == "published"
        assert DerivedVersionStatus.DEPRECATED.value == "deprecated"
        assert DerivedVersionStatus.ARCHIVED.value == "archived"

    def test_str_enum_comparison(self) -> None:
        """StrEnum members compare equal to their lowercase string value."""
        assert DerivedVersionStatus.PUBLISHED == "published"
        assert DerivedVersionStatus.PUBLISHED != "PUBLISHED"
        assert DerivedVersionStatus.DEPRECATED == "deprecated"
        assert DerivedVersionStatus.DEPRECATED != "DEPRECATED"

    def test_all_expected_members_exist(self) -> None:
        """The enum must contain exactly five lifecycle members."""
        members = list(DerivedVersionStatus)
        assert len(members) == 5
        assert DerivedVersionStatus.DRAFT in members
        assert DerivedVersionStatus.MATERIALIZED in members
        assert DerivedVersionStatus.PUBLISHED in members
        assert DerivedVersionStatus.DEPRECATED in members
        assert DerivedVersionStatus.ARCHIVED in members


class TestDerivedVersion:
    """Tests for DerivedVersion."""

    def test_is_active_returns_true_for_published_version(self) -> None:
        """Published versions should report active state."""
        version = DerivedVersion(
            derived_id="factor.momentum_20d",
            version=3,
            spec_hash="spec-hash-v3",
            engine_version="expr-v1",
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
            created_at="2026-03-13T16:00:00+08:00",
        )

        assert version.is_active() is True

    def test_is_active_returns_false_for_non_published_version(self) -> None:
        """Non-published versions should not report active state."""
        version = DerivedVersion(
            derived_id="factor.momentum_20d",
            version=3,
            spec_hash="spec-hash-v3",
            engine_version="expr-v1",
            status=DerivedVersionStatus.MATERIALIZED,
            is_online=False,
            is_primary=False,
            created_at="2026-03-13T16:00:00+08:00",
        )

        assert version.is_active() is False


class TestDerivedRun:
    """Tests for DerivedRun."""

    def test_is_finished_returns_true_for_success_run(self) -> None:
        """Terminal run status should report finished state."""
        run = DerivedRun(
            run_id="run-001",
            derived_id="factor.momentum_20d",
            version=3,
            mode=DerivedRunMode.INCREMENTAL,
            trigger=DerivedRunTrigger.MANUAL,
            request_start="2026-03-01",
            request_end="2026-03-13",
            compute_start="2026-02-10",
            compute_end="2026-03-13",
            source_snapshot_id="market:20260313-001",
            status=DerivedRunStatus.SUCCESS,
            rows_written=240,
            partitions_written=("2026-03",),
            created_at="2026-03-13T16:10:00+08:00",
            started_at="2026-03-13T16:10:05+08:00",
            finished_at="2026-03-13T16:10:55+08:00",
        )

        assert run.is_finished() is True


class TestDerivedState:
    """Tests for DerivedState."""

    def test_has_coverage_returns_true_when_state_has_range(self) -> None:
        """Coverage should be considered present when start/end exist."""
        state = DerivedState(
            derived_id="factor.momentum_20d",
            active_version=3,
            coverage_start="2025-01-01",
            coverage_end="2026-03-13",
            watermark="2026-03-13",
            latest_run_id="run-001",
            latest_run_status=DerivedRunStatus.SUCCESS,
            total_rows=240,
            updated_at="2026-03-13T16:11:00+08:00",
        )

        assert state.has_coverage() is True


class TestDerivedPartition:
    """Smoke tests for DerivedPartition."""

    def test_partition_keeps_checksum(self) -> None:
        """Partition metadata should preserve checksum field."""
        partition = DerivedPartition(
            run_id="run-001",
            derived_id="factor.momentum_20d",
            version=3,
            partition_key="2026-03",
            partition_path="factors/style/momentum_20d/2026-03.parquet",
            row_count=120,
            checksum="sha256:part-03",
            written_at="2026-03-13T16:10:50+08:00",
        )

        assert partition.checksum == "sha256:part-03"
