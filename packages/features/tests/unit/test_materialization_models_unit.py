"""Comprehensive tests for materialization/models.py.

Tests all enum values, dataclass creation, and method behavior for
DerivedVersionStatus, DerivedRunMode, DerivedRunTrigger, DerivedRunStatus,
DerivedVersion, DerivedRun, DerivedPartition, and DerivedState.
"""

from __future__ import annotations

import pytest
from ditto_features.materialization.models import (
    DerivedPartition,
    DerivedRun,
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
    DerivedState,
    DerivedVersion,
    DerivedVersionStatus,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestDerivedVersionStatus:
    """Tests for DerivedVersionStatus enum."""

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

    def test_is_str_enum(self) -> None:
        """DerivedVersionStatus is a string enum."""
        assert isinstance(DerivedVersionStatus.DRAFT, str)

    @pytest.mark.parametrize(
        "status",
        ["draft", "materialized", "published", "deprecated", "archived"],
    )
    def test_construct_from_string(self, status: str) -> None:
        """Can construct from string value."""
        assert DerivedVersionStatus(status) == status


class TestDerivedRunMode:
    """Tests for DerivedRunMode enum."""

    def test_all_values(self) -> None:
        """All expected mode values exist."""
        assert DerivedRunMode.FULL == "full"
        assert DerivedRunMode.INCREMENTAL == "incremental"

    def test_two_members(self) -> None:
        """Exactly two run modes exist."""
        assert len(list(DerivedRunMode)) == 2


class TestDerivedRunTrigger:
    """Tests for DerivedRunTrigger enum."""

    def test_all_values(self) -> None:
        """All expected trigger values exist."""
        assert DerivedRunTrigger.MANUAL == "manual"
        assert DerivedRunTrigger.SCHEDULED == "scheduled"
        assert DerivedRunTrigger.CASCADE == "cascade"

    def test_three_members(self) -> None:
        """Exactly three triggers exist."""
        assert len(list(DerivedRunTrigger)) == 3


class TestDerivedRunStatus:
    """Tests for DerivedRunStatus enum."""

    def test_all_values(self) -> None:
        """All expected status values exist."""
        assert DerivedRunStatus.RUNNING == "RUNNING"
        assert DerivedRunStatus.SUCCESS == "SUCCESS"
        assert DerivedRunStatus.FAILED == "FAILED"

    def test_uppercase_values(self) -> None:
        """Run status values are uppercase."""
        for status in DerivedRunStatus:
            assert status.value == status.value.upper()


# ---------------------------------------------------------------------------
# DerivedVersion
# ---------------------------------------------------------------------------


class TestDerivedVersion:
    """Tests for DerivedVersion dataclass."""

    def _make_version(
        self,
        status: DerivedVersionStatus = DerivedVersionStatus.PUBLISHED,
        is_online: bool = True,
    ) -> DerivedVersion:
        return DerivedVersion(
            derived_id="factor_a",
            version=2,
            spec_hash="abc123",
            engine_version="1.0",
            status=status,
            is_online=is_online,
            is_primary=True,
            created_at="2024-01-01",
        )

    def test_creation(self) -> None:
        """Version can be created with all fields."""
        version = self._make_version()
        assert version.derived_id == "factor_a"
        assert version.version == 2
        assert version.spec_hash == "abc123"

    def test_is_active_returns_true_for_published_version(self) -> None:
        """Published versions should report active state."""
        version = self._make_version(
            status=DerivedVersionStatus.PUBLISHED, is_online=True
        )
        assert version.is_active() is True

    @pytest.mark.parametrize(
        "status",
        [
            DerivedVersionStatus.DRAFT,
            DerivedVersionStatus.MATERIALIZED,
            DerivedVersionStatus.DEPRECATED,
            DerivedVersionStatus.ARCHIVED,
        ],
    )
    def test_is_active_returns_false_for_non_published(
        self, status: DerivedVersionStatus
    ) -> None:
        """Non-published statuses report inactive state."""
        version = self._make_version(status=status)
        assert version.is_active() is False

    def test_optional_updated_at_default(self) -> None:
        """updated_at is optional (defaults to None)."""
        version = self._make_version()
        assert version.updated_at is None

    def test_custom_updated_at(self) -> None:
        """Custom updated_at value is accepted."""
        version = DerivedVersion(
            derived_id="f",
            version=1,
            spec_hash="abc",
            engine_version="1.0",
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
            created_at="2024-01-01",
            updated_at="2024-06-01",
        )
        assert version.updated_at == "2024-06-01"

    def test_frozen(self) -> None:
        """Version is frozen."""
        version = self._make_version()
        with pytest.raises(AttributeError):
            version.status = DerivedVersionStatus.DRAFT  # type: ignore[misc]

    def test_is_online_false(self) -> None:
        """is_online can be False."""
        version = self._make_version(is_online=False)
        assert version.is_online is False

    def test_is_primary_false(self) -> None:
        """is_primary can be False."""
        version = DerivedVersion(
            derived_id="f",
            version=1,
            spec_hash="abc",
            engine_version="1.0",
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=False,
            created_at="2024-01-01",
        )
        assert version.is_primary is False


# ---------------------------------------------------------------------------
# DerivedRun
# ---------------------------------------------------------------------------


class TestDerivedRun:
    """Tests for DerivedRun dataclass."""

    def _make_run(
        self,
        status: DerivedRunStatus = DerivedRunStatus.SUCCESS,
    ) -> DerivedRun:
        return DerivedRun(
            run_id="run_001",
            derived_id="factor_a",
            version=2,
            mode=DerivedRunMode.FULL,
            trigger=DerivedRunTrigger.MANUAL,
            request_start="2024-01-01",
            request_end="2024-12-31",
            compute_start="2024-01-01",
            compute_end="2024-12-31",
            source_snapshot_id=None,
            status=status,
            rows_written=1000,
            partitions_written=("2024",),
            created_at="2024-01-01",
        )

    def test_creation(self) -> None:
        """Run can be created with all fields."""
        run = self._make_run()
        assert run.run_id == "run_001"
        assert run.rows_written == 1000

    def test_is_finished_returns_true_for_success_run(self) -> None:
        """Terminal run status should report finished state."""
        run = self._make_run(status=DerivedRunStatus.SUCCESS)
        assert run.is_finished() is True

    def test_is_finished_returns_true_for_failed(self) -> None:
        """FAILED status is also terminal."""
        run = self._make_run(status=DerivedRunStatus.FAILED)
        assert run.is_finished() is True

    def test_is_finished_returns_false_for_running(self) -> None:
        """RUNNING status is not terminal."""
        run = self._make_run(status=DerivedRunStatus.RUNNING)
        assert run.is_finished() is False

    def test_optional_fields_default_none(self) -> None:
        """Optional fields default to None."""
        run = self._make_run()
        assert run.started_at is None
        assert run.finished_at is None
        assert run.error_message is None

    @pytest.mark.parametrize("mode", list(DerivedRunMode))
    def test_all_modes(self, mode: DerivedRunMode) -> None:
        """Both FULL and INCREMENTAL modes work."""
        run = DerivedRun(
            run_id="r",
            derived_id="f",
            version=1,
            mode=mode,
            trigger=DerivedRunTrigger.MANUAL,
            request_start="2024-01-01",
            request_end="2024-12-31",
            compute_start="2024-01-01",
            compute_end="2024-12-31",
            source_snapshot_id=None,
            status=DerivedRunStatus.RUNNING,
            rows_written=0,
            partitions_written=(),
            created_at="2024-01-01",
        )
        assert run.mode == mode

    @pytest.mark.parametrize("trigger", list(DerivedRunTrigger))
    def test_all_triggers(self, trigger: DerivedRunTrigger) -> None:
        """All trigger types work."""
        run = DerivedRun(
            run_id="r",
            derived_id="f",
            version=1,
            mode=DerivedRunMode.FULL,
            trigger=trigger,
            request_start="2024-01-01",
            request_end="2024-12-31",
            compute_start="2024-01-01",
            compute_end="2024-12-31",
            source_snapshot_id=None,
            status=DerivedRunStatus.RUNNING,
            rows_written=0,
            partitions_written=(),
            created_at="2024-01-01",
        )
        assert run.trigger == trigger

    def test_failed_run_with_error(self) -> None:
        """Failed run can carry error message."""
        run = DerivedRun(
            run_id="run_002",
            derived_id="f",
            version=1,
            mode=DerivedRunMode.INCREMENTAL,
            trigger=DerivedRunTrigger.CASCADE,
            request_start="2024-01-01",
            request_end="2024-01-31",
            compute_start="2024-01-01",
            compute_end="2024-01-31",
            source_snapshot_id="snap_1",
            status=DerivedRunStatus.FAILED,
            rows_written=0,
            partitions_written=(),
            created_at="2024-01-01",
            started_at="2024-01-01T00:00:01",
            finished_at="2024-01-01T00:00:10",
            error_message="OOM killed",
        )
        assert run.is_finished() is True
        assert run.error_message == "OOM killed"
        assert run.source_snapshot_id == "snap_1"

    def test_empty_partitions(self) -> None:
        """Run with no partitions written."""
        run = self._make_run()
        assert run.partitions_written == ("2024",)

    def test_multiple_partitions(self) -> None:
        """Run with multiple partitions."""
        run = DerivedRun(
            run_id="r",
            derived_id="f",
            version=1,
            mode=DerivedRunMode.FULL,
            trigger=DerivedRunTrigger.MANUAL,
            request_start="2023-07-01",
            request_end="2024-06-30",
            compute_start="2023-07-01",
            compute_end="2024-06-30",
            source_snapshot_id=None,
            status=DerivedRunStatus.SUCCESS,
            rows_written=2000,
            partitions_written=("2023", "2024"),
            created_at="2024-01-01",
        )
        assert len(run.partitions_written) == 2

    def test_frozen(self) -> None:
        """Run is frozen."""
        run = self._make_run()
        with pytest.raises(AttributeError):
            run.status = DerivedRunStatus.FAILED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DerivedPartition
# ---------------------------------------------------------------------------


class TestDerivedPartition:
    """Tests for DerivedPartition dataclass."""

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
        assert partition.partition_key == "2026-03"
        assert partition.row_count == 120

    def test_null_checksum(self) -> None:
        """checksum can be None."""
        partition = DerivedPartition(
            run_id="r",
            derived_id="f",
            version=1,
            partition_key="2024",
            partition_path="/data/2024.parquet",
            row_count=100,
            checksum=None,
            written_at="2024-01-01",
        )
        assert partition.checksum is None

    def test_frozen(self) -> None:
        """Partition is frozen."""
        partition = DerivedPartition(
            run_id="r",
            derived_id="f",
            version=1,
            partition_key="2024",
            partition_path="/data/2024.parquet",
            row_count=100,
            checksum=None,
            written_at="2024-01-01",
        )
        with pytest.raises(AttributeError):
            partition.row_count = 200  # type: ignore[misc]

    def test_zero_row_count(self) -> None:
        """Partition can have zero rows."""
        partition = DerivedPartition(
            run_id="r",
            derived_id="f",
            version=1,
            partition_key="2024",
            partition_path="/data/2024.parquet",
            row_count=0,
            checksum=None,
            written_at="2024-01-01",
        )
        assert partition.row_count == 0


# ---------------------------------------------------------------------------
# DerivedState
# ---------------------------------------------------------------------------


class TestDerivedState:
    """Tests for DerivedState dataclass."""

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

    def test_no_coverage_start(self) -> None:
        """has_coverage is False when start is None."""
        state = DerivedState(
            derived_id="f",
            active_version=1,
            coverage_start=None,
            coverage_end="2024-12-31",
            watermark="2024-12-31",
            latest_run_id="run_001",
            latest_run_status=DerivedRunStatus.SUCCESS,
            total_rows=10000,
            updated_at="2024-12-31",
        )
        assert state.has_coverage() is False

    def test_no_coverage_end(self) -> None:
        """has_coverage is False when end is None."""
        state = DerivedState(
            derived_id="f",
            active_version=1,
            coverage_start="2024-01-01",
            coverage_end=None,
            watermark=None,
            latest_run_id=None,
            latest_run_status=None,
            total_rows=0,
            updated_at="2024-01-01",
        )
        assert state.has_coverage() is False

    def test_no_active_version(self) -> None:
        """State with no active version."""
        state = DerivedState(
            derived_id="new_factor",
            active_version=None,
            coverage_start=None,
            coverage_end=None,
            watermark=None,
            latest_run_id=None,
            latest_run_status=None,
            total_rows=0,
            updated_at="2024-01-01",
        )
        assert state.active_version is None
        assert state.has_coverage() is False

    def test_all_fields(self) -> None:
        """All fields are accessible."""
        state = DerivedState(
            derived_id="f",
            active_version=3,
            coverage_start="2023-01-01",
            coverage_end="2024-12-31",
            watermark="2024-12-31",
            latest_run_id="run_100",
            latest_run_status=DerivedRunStatus.SUCCESS,
            total_rows=50000,
            updated_at="2024-12-31T23:59:59",
        )
        assert state.derived_id == "f"
        assert state.active_version == 3
        assert state.total_rows == 50000
        assert state.watermark == "2024-12-31"
        assert state.latest_run_status == DerivedRunStatus.SUCCESS

    def test_frozen(self) -> None:
        """State is frozen."""
        state = DerivedState(
            derived_id="f",
            active_version=1,
            coverage_start="2024-01-01",
            coverage_end="2024-12-31",
            watermark="2024-12-31",
            latest_run_id="r1",
            latest_run_status=DerivedRunStatus.SUCCESS,
            total_rows=100,
            updated_at="2024-12-31",
        )
        with pytest.raises(AttributeError):
            state.total_rows = 200  # type: ignore[misc]

    def test_running_status(self) -> None:
        """State can track a running job."""
        state = DerivedState(
            derived_id="f",
            active_version=1,
            coverage_start="2024-01-01",
            coverage_end="2024-06-30",
            watermark="2024-06-30",
            latest_run_id="run_in_progress",
            latest_run_status=DerivedRunStatus.RUNNING,
            total_rows=5000,
            updated_at="2024-07-01",
        )
        assert state.latest_run_status == DerivedRunStatus.RUNNING
