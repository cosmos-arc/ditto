"""Unit tests for models/derived.py.

Tests serialization round-trips (to_json_dict / from_json_dict) for all
record types and validation edge cases.
"""

from __future__ import annotations

import pytest
from ditto_features.models.derived import (
    CompiledExpressionCacheRecord,
    CompiledExpressionOperatorRecord,
    DerivedCheckpointRecord,
    DerivedDependencyRecord,
    DerivedInvalidationRecord,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
    PartitionInfo,
)

# ---------------------------------------------------------------------------
# DerivedSpecRecord
# ---------------------------------------------------------------------------


class TestDerivedSpecRecord:
    """Tests for DerivedSpecRecord."""

    def _make_record(self) -> DerivedSpecRecord:
        return DerivedSpecRecord(
            derived_id="factor_a",
            version=2,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="abc123",
            spec_json={"expression": "market.close + 1"},
            created_at="2024-01-01T00:00:00",
        )

    def test_roundtrip(self) -> None:
        """to_json_dict -> from_json_dict produces equal record."""
        record = self._make_record()
        json_dict = record.to_json_dict()
        restored = DerivedSpecRecord.from_json_dict(json_dict)
        assert restored == record

    def test_to_json_dict_keys(self) -> None:
        """to_json_dict has expected keys."""
        record = self._make_record()
        d = record.to_json_dict()
        assert "derived_id" in d
        assert "version" in d
        assert "role" in d
        assert "spec_hash" in d
        assert "spec_json" in d

    def test_from_json_dict_missing_required_key(self) -> None:
        """from_json_dict raises on missing required field."""
        with pytest.raises((KeyError, TypeError)):
            DerivedSpecRecord.from_json_dict({"derived_id": "test"})

    def test_frozen(self) -> None:
        """Record is frozen."""
        record = self._make_record()
        with pytest.raises(AttributeError):
            record.derived_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DerivedVersionRecord
# ---------------------------------------------------------------------------


class TestDerivedVersionRecord:
    """Tests for DerivedVersionRecord."""

    def _make_record(self) -> DerivedVersionRecord:
        return DerivedVersionRecord(
            derived_id="factor_a",
            version=2,
            status="published",
            engine_version="1.0",
            is_online=True,
            is_primary=True,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-06-01T00:00:00",
        )

    def test_roundtrip(self) -> None:
        """Roundtrip preserves all fields."""
        record = self._make_record()
        d = record.to_json_dict()
        restored = DerivedVersionRecord.from_json_dict(d)
        assert restored == record

    def test_null_updated_at(self) -> None:
        """updated_at can be None."""
        record = DerivedVersionRecord(
            derived_id="f",
            version=1,
            status="draft",
            engine_version="1.0",
            is_online=False,
            is_primary=False,
            created_at="2024-01-01",
            updated_at=None,
        )
        d = record.to_json_dict()
        restored = DerivedVersionRecord.from_json_dict(d)
        assert restored.updated_at is None


# ---------------------------------------------------------------------------
# DerivedRunRecord
# ---------------------------------------------------------------------------


class TestDerivedRunRecord:
    """Tests for DerivedRunRecord."""

    def _make_record(self) -> DerivedRunRecord:
        return DerivedRunRecord(
            run_id="run_001",
            derived_id="factor_a",
            version=2,
            mode="full",
            trigger="manual",
            request_start="2024-01-01",
            request_end="2024-12-31",
            compute_start="2024-01-01",
            compute_end="2024-12-31",
            source_snapshot_id=None,
            status="SUCCESS",
            rows_written=1000,
            partitions_written=("2024",),
            error_message=None,
            created_at="2024-01-01T00:00:00",
            started_at="2024-01-01T00:00:01",
            finished_at="2024-01-01T00:01:00",
        )

    def test_roundtrip(self) -> None:
        """Roundtrip preserves all fields."""
        record = self._make_record()
        d = record.to_json_dict()
        restored = DerivedRunRecord.from_json_dict(d)
        assert restored == record

    def test_partitions_written_as_list(self) -> None:
        """to_json_dict converts tuple to list."""
        record = self._make_record()
        d = record.to_json_dict()
        assert isinstance(d["partitions_written"], list)
        assert d["partitions_written"] == ["2024"]

    def test_with_error_message(self) -> None:
        """Run record can carry an error message."""
        record = DerivedRunRecord(
            run_id="run_002",
            derived_id="factor_b",
            version=1,
            mode="incremental",
            trigger="cascade",
            request_start="2024-01-01",
            request_end="2024-01-31",
            compute_start="2024-01-01",
            compute_end="2024-01-31",
            source_snapshot_id="snap_1",
            status="FAILED",
            rows_written=0,
            partitions_written=(),
            error_message="Division by zero",
            created_at="2024-01-01",
            started_at="2024-01-01",
            finished_at="2024-01-01",
        )
        d = record.to_json_dict()
        restored = DerivedRunRecord.from_json_dict(d)
        assert restored.error_message == "Division by zero"
        assert restored.status == "FAILED"

    def test_invalid_partitions_written_type(self) -> None:
        """Non-list partitions_written raises TypeError."""
        data = self._make_record().to_json_dict()
        data["partitions_written"] = "not_a_list"
        with pytest.raises(TypeError, match="list of strings"):
            DerivedRunRecord.from_json_dict(data)


# ---------------------------------------------------------------------------
# DerivedPartitionRecord
# ---------------------------------------------------------------------------


class TestDerivedPartitionRecord:
    """Tests for DerivedPartitionRecord."""

    def test_roundtrip(self) -> None:
        """Roundtrip preserves all fields."""
        record = DerivedPartitionRecord(
            run_id="run_001",
            derived_id="factor_a",
            version=1,
            partition_key="2024",
            partition_path="/data/factor_a/2024.parquet",
            row_count=500,
            checksum="sha256:abc",
            written_at="2024-01-01T00:01:00",
        )
        d = record.to_json_dict()
        restored = DerivedPartitionRecord.from_json_dict(d)
        assert restored == record

    def test_null_checksum(self) -> None:
        """checksum can be None."""
        record = DerivedPartitionRecord(
            run_id="run_001",
            derived_id="factor_a",
            version=1,
            partition_key="2024",
            partition_path="/data/factor_a/2024.parquet",
            row_count=500,
            checksum=None,
            written_at="2024-01-01",
        )
        d = record.to_json_dict()
        restored = DerivedPartitionRecord.from_json_dict(d)
        assert restored.checksum is None


# ---------------------------------------------------------------------------
# DerivedStateRecord
# ---------------------------------------------------------------------------


class TestDerivedStateRecord:
    """Tests for DerivedStateRecord."""

    def test_roundtrip(self) -> None:
        """Roundtrip preserves all fields."""
        record = DerivedStateRecord(
            derived_id="factor_a",
            active_version=2,
            coverage_start="2024-01-01",
            coverage_end="2024-12-31",
            watermark="2024-12-31",
            latest_run_id="run_001",
            latest_run_status="SUCCESS",
            total_rows=10000,
            updated_at="2024-12-31T23:59:59",
        )
        d = record.to_json_dict()
        restored = DerivedStateRecord.from_json_dict(d)
        assert restored == record

    def test_all_null_optional_fields(self) -> None:
        """All optional fields can be None."""
        record = DerivedStateRecord(
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
        d = record.to_json_dict()
        restored = DerivedStateRecord.from_json_dict(d)
        assert restored.active_version is None
        assert restored.coverage_start is None
        assert restored.total_rows == 0

    def test_invalid_total_rows_type(self) -> None:
        """Non-int total_rows raises TypeError."""
        data: dict[str, str | int | None] = {
            "derived_id": "f",
            "active_version": None,
            "coverage_start": None,
            "coverage_end": None,
            "watermark": None,
            "latest_run_id": None,
            "latest_run_status": None,
            "total_rows": "not_an_int",
            "updated_at": "2024-01-01",
        }
        with pytest.raises(TypeError, match="total_rows must be an int"):
            DerivedStateRecord.from_json_dict(data)

    def test_invalid_active_version_type(self) -> None:
        """Non-int/non-null active_version raises TypeError."""
        data: dict[str, str | int | None] = {
            "derived_id": "f",
            "active_version": "not_int",
            "coverage_start": None,
            "coverage_end": None,
            "watermark": None,
            "latest_run_id": None,
            "latest_run_status": None,
            "total_rows": 100,
            "updated_at": "2024-01-01",
        }
        with pytest.raises(TypeError, match="active_version must be an int"):
            DerivedStateRecord.from_json_dict(data)

    def test_bool_total_rows_rejected(self) -> None:
        """Boolean total_rows is rejected (bool is int subclass)."""
        data: dict[str, str | int | bool | None] = {
            "derived_id": "f",
            "active_version": None,
            "coverage_start": None,
            "coverage_end": None,
            "watermark": None,
            "latest_run_id": None,
            "latest_run_status": None,
            "total_rows": True,
            "updated_at": "2024-01-01",
        }
        with pytest.raises(TypeError, match="total_rows must be an int"):
            DerivedStateRecord.from_json_dict(data)


# ---------------------------------------------------------------------------
# Simple frozen records (no serialization methods)
# ---------------------------------------------------------------------------


class TestDerivedCheckpointRecord:
    """Tests for DerivedCheckpointRecord."""

    def test_creation(self) -> None:
        """Record can be created with all fields."""
        record = DerivedCheckpointRecord(
            derived_id="f",
            version=1,
            partition_key="2024",
            status="COMPLETED",
            rows_written=100,
            checksum="sha256:abc",
            error_message=None,
            started_at="2024-01-01",
            completed_at="2024-01-01",
        )
        assert record.derived_id == "f"
        assert record.rows_written == 100

    def test_frozen(self) -> None:
        """Record is frozen."""
        record = DerivedCheckpointRecord(
            derived_id="f",
            version=1,
            partition_key="2024",
            status="RUNNING",
            rows_written=0,
            checksum=None,
            error_message=None,
            started_at="2024-01-01",
            completed_at=None,
        )
        with pytest.raises(AttributeError):
            record.status = "DONE"  # type: ignore[misc]


class TestDerivedDependencyRecord:
    """Tests for DerivedDependencyRecord."""

    def test_creation(self) -> None:
        """Record can be created with all fields."""
        record = DerivedDependencyRecord(
            derived_id="f",
            version=1,
            dependency_kind="source",
            dependency_ref="market.close",
            created_at="2024-01-01",
        )
        assert record.dependency_kind == "source"
        assert record.dependency_ref == "market.close"


class TestDerivedInvalidationRecord:
    """Tests for DerivedInvalidationRecord."""

    def test_creation_with_defaults(self) -> None:
        """Record uses default values for optional fields."""
        record = DerivedInvalidationRecord(
            invalidation_id="inv_1",
            derived_id="f",
            version=1,
            source_domain="market",
            source_dataset="close_prices",
            change_date="2024-06-15",
            affected_start="2024-06-15",
            affected_end="2024-06-15",
            source_snapshot_id=None,
            root_dependency_ref="market.close",
            status="PENDING",
            created_at="2024-06-15",
            processed_at=None,
        )
        assert record.depth == 0
        assert record.retry_count == 0
        assert record.error_message is None
        assert record.dead_letter_at is None
        assert record.role == "factor"

    def test_custom_depth_and_retry(self) -> None:
        """Custom depth and retry_count values."""
        record = DerivedInvalidationRecord(
            invalidation_id="inv_2",
            derived_id="f",
            version=1,
            source_domain="market",
            source_dataset="close",
            change_date="2024-01-01",
            affected_start="2024-01-01",
            affected_end="2024-01-31",
            source_snapshot_id="snap_1",
            root_dependency_ref="market.close",
            status="FAILED",
            created_at="2024-01-01",
            processed_at="2024-01-01",
            depth=3,
            retry_count=2,
            error_message="Timeout",
            dead_letter_at="2024-01-01",
        )
        assert record.depth == 3
        assert record.retry_count == 2


class TestCompiledExpressionCacheRecord:
    """Tests for CompiledExpressionCacheRecord."""

    def test_creation(self) -> None:
        """Record can be created with all fields."""
        record = CompiledExpressionCacheRecord(
            cache_key="key_abc",
            derived_id="f",
            version=1,
            compiler_fingerprint="fp_1",
            compile_input_hash="hash_123",
            analysis_json={"lookback": 10},
            compile_identity_json={"engine": "1.0"},
            expression_repr="market.close + 1",
            created_at="2024-01-01",
        )
        assert record.cache_key == "key_abc"
        assert record.analysis_json == {"lookback": 10}


class TestCompiledExpressionOperatorRecord:
    """Tests for CompiledExpressionOperatorRecord."""

    def test_creation(self) -> None:
        """Record can be created."""
        record = CompiledExpressionOperatorRecord(
            cache_key="key_abc",
            operator_name="ts_mean",
            operator_version="1.0",
        )
        assert record.operator_name == "ts_mean"


class TestPartitionInfo:
    """Tests for PartitionInfo."""

    def test_creation(self) -> None:
        """Record can be created with all fields."""
        info = PartitionInfo(
            partition_key="2024",
            partition_path="/data/2024.parquet",
            row_count=1000,
            checksum="sha256:abc",
        )
        assert info.partition_key == "2024"
        assert info.row_count == 1000

    def test_null_checksum(self) -> None:
        """checksum can be None."""
        info = PartitionInfo(
            partition_key="2024",
            partition_path="/data/2024.parquet",
            row_count=1000,
            checksum=None,
        )
        assert info.checksum is None
