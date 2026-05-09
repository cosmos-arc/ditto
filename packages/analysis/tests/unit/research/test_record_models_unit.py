"""Tests for runtime record models (migrated from ditto_kernel.research)."""

from __future__ import annotations

import pytest
from ditto_analysis.research.domain import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)

# ---------------------------------------------------------------------------
# ResearchSpineSpecRecord
# ---------------------------------------------------------------------------


class TestResearchSpineSpecRecord:
    """ResearchSpineSpecRecord frozen dataclass 测试."""

    def _make(self, **overrides: object) -> ResearchSpineSpecRecord:
        base: dict[str, object] = {
            "spine_id": "spine_001",
            "universe_id": "hs300",
            "calendar": "cn_stock",
            "grain": "1d",
            "entity_key": "instrument_id",
            "description": "沪深300日线",
            "created_at": "2026-01-01T00:00:00Z",
        }
        base.update(overrides)
        return ResearchSpineSpecRecord(**base)  # type: ignore[arg-type]

    def test_required_fields(self) -> None:
        """必填字段正确赋值."""
        rec = self._make()
        assert rec.spine_id == "spine_001"
        assert rec.universe_id == "hs300"

    def test_version_default(self) -> None:
        """version 默认为 1."""
        assert self._make().version == 1

    def test_version_custom(self) -> None:
        """自定义 version 赋值."""
        assert self._make(version=3).version == 3

    def test_description_can_be_none(self) -> None:
        """description 可为 None."""
        assert self._make(description=None).description is None

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        rec = self._make()
        with pytest.raises(AttributeError):
            rec.spine_id = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        assert self._make() == self._make()

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        assert self._make() != self._make(spine_id="spine_002")


# ---------------------------------------------------------------------------
# ResearchDatasetSpecRecord
# ---------------------------------------------------------------------------


class TestResearchDatasetSpecRecord:
    """ResearchDatasetSpecRecord frozen dataclass 测试."""

    def _make(self, **overrides: object) -> ResearchDatasetSpecRecord:
        base: dict[str, object] = {
            "dataset_id": "ds_001",
            "spine_id": "spine_001",
            "derived_ids": ("factor_a", "factor_b"),
            "join_policy": "left",
            "known_at_policy": "event_time",
            "late_arrival_policy": "drop",
            "description": "因子数据集",
            "created_at": "2026-01-01T00:00:00Z",
        }
        base.update(overrides)
        return ResearchDatasetSpecRecord(**base)  # type: ignore[arg-type]

    def test_required_fields(self) -> None:
        """必填字段正确赋值."""
        rec = self._make()
        assert rec.dataset_id == "ds_001"
        assert rec.derived_ids == ("factor_a", "factor_b")

    def test_version_default(self) -> None:
        """version 默认为 1."""
        assert self._make().version == 1

    def test_derived_ids_empty_tuple(self) -> None:
        """derived_ids 可为空元组."""
        assert self._make(derived_ids=()).derived_ids == ()

    def test_description_can_be_none(self) -> None:
        """description 可为 None."""
        assert self._make(description=None).description is None

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        rec = self._make()
        with pytest.raises(AttributeError):
            rec.dataset_id = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        assert self._make() == self._make()

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        assert self._make() != self._make(dataset_id="ds_002")


# ---------------------------------------------------------------------------
# ResearchSpineSnapshotRecord
# ---------------------------------------------------------------------------


class TestResearchSpineSnapshotRecord:
    """ResearchSpineSnapshotRecord frozen dataclass 测试."""

    def _make(self, **overrides: object) -> ResearchSpineSnapshotRecord:
        base: dict[str, object] = {
            "spine_snapshot_id": "snap_001",
            "spine_id": "spine_001",
            "snapshot_start": "2025-01-01",
            "snapshot_end": "2025-12-31",
            "row_count": 1000,
            "data_path": "/data/spine/snap_001.parquet",
            "manifest_hash": "abc123",
            "created_at": "2026-01-01T00:00:00Z",
        }
        base.update(overrides)
        return ResearchSpineSnapshotRecord(**base)  # type: ignore[arg-type]

    def test_required_fields(self) -> None:
        """必填字段正确赋值."""
        rec = self._make()
        assert rec.spine_snapshot_id == "snap_001"
        assert rec.row_count == 1000

    def test_version_default(self) -> None:
        """version 默认为 1."""
        assert self._make().version == 1

    def test_row_count_zero(self) -> None:
        """row_count 可为 0（空快照）."""
        assert self._make(row_count=0).row_count == 0

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        rec = self._make()
        with pytest.raises(AttributeError):
            rec.spine_snapshot_id = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        assert self._make() == self._make()

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        assert self._make() != self._make(row_count=999)


# ---------------------------------------------------------------------------
# ResearchDatasetSnapshotRecord
# ---------------------------------------------------------------------------


class TestResearchDatasetSnapshotRecord:
    """ResearchDatasetSnapshotRecord frozen dataclass 测试."""

    def _make(self, **overrides: object) -> ResearchDatasetSnapshotRecord:
        base: dict[str, object] = {
            "snapshot_id": "ds_snap_001",
            "dataset_id": "ds_001",
            "dataset_spec_version": 2,
            "spine_snapshot_id": "snap_001",
            "snapshot_start": "2025-01-01",
            "snapshot_end": "2025-12-31",
            "row_count": 5000,
            "data_path": "/data/dataset/ds_snap_001.parquet",
            "manifest_hash": "def456",
            "known_at_policy": "event_time",
            "effective_cutoff": None,
        }
        base.update(overrides)
        return ResearchDatasetSnapshotRecord(**base)  # type: ignore[arg-type]

    def test_required_fields(self) -> None:
        """必填字段正确赋值."""
        rec = self._make()
        assert rec.snapshot_id == "ds_snap_001"
        assert rec.row_count == 5000

    def test_spine_spec_version_default(self) -> None:
        """spine_spec_version 默认为 1."""
        assert self._make().spine_spec_version == 1

    def test_resolved_versions_default_empty(self) -> None:
        """resolved_versions 默认为空字典."""
        assert self._make().resolved_versions == {}

    def test_resolved_inputs_default_empty(self) -> None:
        """resolved_inputs 默认为空元组."""
        assert self._make().resolved_inputs == ()

    def test_effective_cutoff_can_be_none(self) -> None:
        """effective_cutoff 可为 None."""
        assert self._make().effective_cutoff is None

    def test_all_optional_fields_custom(self) -> None:
        """所有可选字段自定义赋值."""
        rec = self._make(
            spine_spec_version=3,
            resolved_versions={"factor_a": 5},
            resolved_inputs=({"derived_id": "factor_a", "version": 5},),
            source_snapshot_ids=("snap_a", "snap_b"),
            builder_version="1.2.3",
            created_at="2026-04-18T12:00:00Z",
            effective_cutoff="2026-04-18",
        )
        assert rec.spine_spec_version == 3
        assert rec.resolved_versions == {"factor_a": 5}
        assert rec.source_snapshot_ids == ("snap_a", "snap_b")

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        rec = self._make()
        with pytest.raises(AttributeError):
            rec.snapshot_id = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        assert self._make() == self._make()

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        assert self._make() != self._make(dataset_id="ds_002")

    def test_resolved_versions_default_is_independent(self) -> None:
        """每个实例的 resolved_versions 默认值应是独立字典."""
        assert self._make().resolved_versions is not self._make().resolved_versions
