"""Tests for runtime record models (migrated from ditto_kernel.research)."""

from __future__ import annotations

import orjson
import pytest
from ditto_analysis.errors import ResearchDatasetError
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


# ===========================================================================
# from_row() 验证工厂测试
# ===========================================================================


# ---- Helpers: 模拟数据库行字典 ----


def _spine_spec_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "spine_id": "spine.cn_stock.default",
        "universe_id": "universe.cn.all",
        "calendar": "cn_stock",
        "grain": "1d",
        "entity_key": "instrument_id",
        "description": None,
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return defaults


def _dataset_spec_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "dataset_id": "research.alpha_beta",
        "spine_id": "spine.cn_stock.default",
        "derived_ids": orjson.dumps(["factor.alpha", "factor.beta"]).decode(),
        "join_policy": "left_preserving_pit",
        "known_at_policy": "sample_time",
        "late_arrival_policy": "require_rebuild",
        "description": None,
        "created_at": "2026-01-01T00:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return defaults


def _spine_snapshot_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "spine_snapshot_id": "rsp-001",
        "spine_id": "spine.cn_stock.default",
        "snapshot_start": "2026-03-10",
        "snapshot_end": "2026-03-11",
        "row_count": 100,
        "data_path": "spines/data.parquet",
        "manifest_hash": "abc123",
        "created_at": "2026-03-14T12:00:00+08:00",
        "version": 1,
    }
    defaults.update(overrides)
    return defaults


def _dataset_snapshot_row(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "snapshot_id": "rds-001",
        "dataset_id": "research.alpha_beta",
        "dataset_spec_version": 1,
        "spine_snapshot_id": "rsp-001",
        "snapshot_start": "2026-03-10",
        "snapshot_end": "2026-03-11",
        "row_count": 50,
        "data_path": "datasets/data.parquet",
        "manifest_hash": "def456",
        "known_at_policy": "sample_time",
        "effective_cutoff": None,
        "spine_spec_version": 1,
        "resolved_versions": orjson.dumps({"factor.alpha": 2}).decode(),
        "resolved_inputs": orjson.dumps(
            [{"derived_id": "factor.alpha", "version": 2}]
        ).decode(),
        "source_snapshot_ids": orjson.dumps(["snap_001"]).decode(),
        "builder_version": "v1",
        "created_at": "2026-03-14T12:00:00+08:00",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# ResearchSpineSpecRecord.from_row
# ---------------------------------------------------------------------------


class TestSpineSpecFromRow:
    """ResearchSpineSpecRecord.from_row() 验证工厂测试."""

    def test_constructs_from_full_row(self) -> None:
        """从完整行字典正确构造记录."""
        row = _spine_spec_row()
        rec = ResearchSpineSpecRecord.from_row(row)
        assert isinstance(rec, ResearchSpineSpecRecord)
        assert rec.spine_id == "spine.cn_stock.default"
        assert rec.universe_id == "universe.cn.all"
        assert rec.calendar == "cn_stock"
        assert rec.grain == "1d"
        assert rec.entity_key == "instrument_id"
        assert rec.description is None
        assert rec.created_at == "2026-01-01T00:00:00+08:00"
        assert rec.version == 1

    def test_version_defaults_to_1(self) -> None:
        """缺少 version 时默认为 1."""
        row = _spine_spec_row(version=1)
        del row["version"]
        rec = ResearchSpineSpecRecord.from_row(row)
        assert rec.version == 1

    def test_description_none_when_missing(self) -> None:
        """缺少 description 时默认为 None."""
        row = _spine_spec_row()
        del row["description"]
        rec = ResearchSpineSpecRecord.from_row(row)
        assert rec.description is None

    def test_raises_on_missing_spine_id(self) -> None:
        """spine_id 缺失时抛出 ResearchDatasetError."""
        row = _spine_spec_row()
        del row["spine_id"]
        with pytest.raises(ResearchDatasetError, match="spine_id"):
            ResearchSpineSpecRecord.from_row(row)

    def test_raises_on_empty_spine_id(self) -> None:
        """spine_id 为空字符串时抛出 ResearchDatasetError."""
        row = _spine_spec_row(spine_id="")
        with pytest.raises(ResearchDatasetError, match="spine_id"):
            ResearchSpineSpecRecord.from_row(row)

    def test_raises_on_non_string_spine_id(self) -> None:
        """spine_id 为非字符串类型时抛出 ResearchDatasetError."""
        row = _spine_spec_row(spine_id=123)
        with pytest.raises(ResearchDatasetError, match="spine_id"):
            ResearchSpineSpecRecord.from_row(row)

    def test_raises_on_none_spine_id(self) -> None:
        """spine_id 为 None 时抛出 ResearchDatasetError."""
        row = _spine_spec_row(spine_id=None)
        with pytest.raises(ResearchDatasetError, match="spine_id"):
            ResearchSpineSpecRecord.from_row(row)

    def test_custom_version(self) -> None:
        """自定义 version 正确赋值."""
        row = _spine_spec_row(version=5)
        rec = ResearchSpineSpecRecord.from_row(row)
        assert rec.version == 5

    def test_raises_on_non_int_version(self) -> None:
        """version 为非 int 类型时抛出 ResearchDatasetError."""
        row = _spine_spec_row(version="bad")
        with pytest.raises(ResearchDatasetError, match="version"):
            ResearchSpineSpecRecord.from_row(row)


# ---------------------------------------------------------------------------
# ResearchDatasetSpecRecord.from_row
# ---------------------------------------------------------------------------


class TestDatasetSpecFromRow:
    """ResearchDatasetSpecRecord.from_row() 验证工厂测试."""

    def test_constructs_from_full_row(self) -> None:
        """从完整行字典正确构造记录，含 orjson 反序列化."""
        row = _dataset_spec_row()
        rec = ResearchDatasetSpecRecord.from_row(row)
        assert isinstance(rec, ResearchDatasetSpecRecord)
        assert rec.dataset_id == "research.alpha_beta"
        assert rec.spine_id == "spine.cn_stock.default"
        assert rec.derived_ids == ("factor.alpha", "factor.beta")
        assert rec.join_policy == "left_preserving_pit"
        assert rec.known_at_policy == "sample_time"
        assert rec.late_arrival_policy == "require_rebuild"
        assert rec.description is None
        assert rec.created_at == "2026-01-01T00:00:00+08:00"
        assert rec.version == 1

    def test_derived_ids_from_tuple(self) -> None:
        """derived_ids 已经是 tuple 时直接使用."""
        row = _dataset_spec_row(derived_ids=("factor.x",))
        rec = ResearchDatasetSpecRecord.from_row(row)
        assert rec.derived_ids == ("factor.x",)

    def test_derived_ids_empty_json_array(self) -> None:
        """derived_ids 为空 JSON 数组时反序列化为空 tuple."""
        row = _dataset_spec_row(derived_ids="[]")
        rec = ResearchDatasetSpecRecord.from_row(row)
        assert rec.derived_ids == ()

    def test_version_defaults_to_1(self) -> None:
        """缺少 version 时默认为 1."""
        row = _dataset_spec_row(version=1)
        del row["version"]
        rec = ResearchDatasetSpecRecord.from_row(row)
        assert rec.version == 1

    def test_raises_on_missing_dataset_id(self) -> None:
        """dataset_id 缺失时抛出 ResearchDatasetError."""
        row = _dataset_spec_row()
        del row["dataset_id"]
        with pytest.raises(ResearchDatasetError, match="dataset_id"):
            ResearchDatasetSpecRecord.from_row(row)

    def test_raises_on_empty_dataset_id(self) -> None:
        """dataset_id 为空字符串时抛出 ResearchDatasetError."""
        row = _dataset_spec_row(dataset_id="")
        with pytest.raises(ResearchDatasetError, match="dataset_id"):
            ResearchDatasetSpecRecord.from_row(row)

    def test_raises_on_non_string_dataset_id(self) -> None:
        """dataset_id 为非字符串类型时抛出 ResearchDatasetError."""
        row = _dataset_spec_row(dataset_id=42)
        with pytest.raises(ResearchDatasetError, match="dataset_id"):
            ResearchDatasetSpecRecord.from_row(row)

    def test_raises_on_non_int_version(self) -> None:
        """version 为非 int 类型时抛出 ResearchDatasetError."""
        row = _dataset_spec_row(version="bad")
        with pytest.raises(ResearchDatasetError, match="version"):
            ResearchDatasetSpecRecord.from_row(row)


# ---------------------------------------------------------------------------
# ResearchSpineSnapshotRecord.from_row
# ---------------------------------------------------------------------------


class TestSpineSnapshotFromRow:
    """ResearchSpineSnapshotRecord.from_row() 验证工厂测试."""

    def test_constructs_from_full_row(self) -> None:
        """从完整行字典正确构造记录."""
        row = _spine_snapshot_row()
        rec = ResearchSpineSnapshotRecord.from_row(row)
        assert isinstance(rec, ResearchSpineSnapshotRecord)
        assert rec.spine_snapshot_id == "rsp-001"
        assert rec.spine_id == "spine.cn_stock.default"
        assert rec.snapshot_start == "2026-03-10"
        assert rec.snapshot_end == "2026-03-11"
        assert rec.row_count == 100
        assert rec.data_path == "spines/data.parquet"
        assert rec.manifest_hash == "abc123"
        assert rec.created_at == "2026-03-14T12:00:00+08:00"
        assert rec.version == 1

    def test_version_defaults_to_1(self) -> None:
        """缺少 version 时默认为 1."""
        row = _spine_snapshot_row(version=1)
        del row["version"]
        rec = ResearchSpineSnapshotRecord.from_row(row)
        assert rec.version == 1

    def test_raises_on_missing_spine_snapshot_id(self) -> None:
        """spine_snapshot_id 缺失时抛出 ResearchDatasetError."""
        row = _spine_snapshot_row()
        del row["spine_snapshot_id"]
        with pytest.raises(ResearchDatasetError, match="spine_snapshot_id"):
            ResearchSpineSnapshotRecord.from_row(row)

    def test_raises_on_empty_spine_snapshot_id(self) -> None:
        """spine_snapshot_id 为空字符串时抛出 ResearchDatasetError."""
        row = _spine_snapshot_row(spine_snapshot_id="")
        with pytest.raises(ResearchDatasetError, match="spine_snapshot_id"):
            ResearchSpineSnapshotRecord.from_row(row)

    def test_raises_on_non_string_spine_snapshot_id(self) -> None:
        """spine_snapshot_id 为非字符串类型时抛出 ResearchDatasetError."""
        row = _spine_snapshot_row(spine_snapshot_id=99)
        with pytest.raises(ResearchDatasetError, match="spine_snapshot_id"):
            ResearchSpineSnapshotRecord.from_row(row)

    def test_raises_on_non_int_row_count(self) -> None:
        """row_count 为非 int 类型时抛出 ResearchDatasetError."""
        row = _spine_snapshot_row(row_count="bad")
        with pytest.raises(ResearchDatasetError, match="row_count"):
            ResearchSpineSnapshotRecord.from_row(row)

    def test_raises_on_non_int_version(self) -> None:
        """version 为非 int 类型时抛出 ResearchDatasetError."""
        row = _spine_snapshot_row(version="bad")
        with pytest.raises(ResearchDatasetError, match="version"):
            ResearchSpineSnapshotRecord.from_row(row)


# ---------------------------------------------------------------------------
# ResearchDatasetSnapshotRecord.from_row
# ---------------------------------------------------------------------------


class TestDatasetSnapshotFromRow:
    """ResearchDatasetSnapshotRecord.from_row() 验证工厂测试."""

    def test_constructs_from_full_row(self) -> None:
        """从完整行字典正确构造记录，含 orjson 反序列化."""
        row = _dataset_snapshot_row()
        rec = ResearchDatasetSnapshotRecord.from_row(row)
        assert isinstance(rec, ResearchDatasetSnapshotRecord)
        assert rec.snapshot_id == "rds-001"
        assert rec.dataset_id == "research.alpha_beta"
        assert rec.dataset_spec_version == 1
        assert rec.spine_snapshot_id == "rsp-001"
        assert rec.snapshot_start == "2026-03-10"
        assert rec.snapshot_end == "2026-03-11"
        assert rec.row_count == 50
        assert rec.data_path == "datasets/data.parquet"
        assert rec.manifest_hash == "def456"
        assert rec.known_at_policy == "sample_time"
        assert rec.effective_cutoff is None
        assert rec.spine_spec_version == 1
        assert rec.resolved_versions == {"factor.alpha": 2}
        assert rec.resolved_inputs == ({"derived_id": "factor.alpha", "version": 2},)
        assert rec.source_snapshot_ids == ("snap_001",)
        assert rec.builder_version == "v1"
        assert rec.created_at == "2026-03-14T12:00:00+08:00"

    def test_resolved_versions_from_dict(self) -> None:
        """resolved_versions 已经是 dict 时直接使用."""
        row = _dataset_snapshot_row(resolved_versions={"factor.x": 3})
        rec = ResearchDatasetSnapshotRecord.from_row(row)
        assert rec.resolved_versions == {"factor.x": 3}

    def test_resolved_versions_empty_json(self) -> None:
        """resolved_versions 为空 JSON 对象时反序列化为空字典."""
        row = _dataset_snapshot_row(resolved_versions="{}")
        rec = ResearchDatasetSnapshotRecord.from_row(row)
        assert rec.resolved_versions == {}

    def test_resolved_inputs_from_tuple(self) -> None:
        """resolved_inputs 已经是 tuple 时直接使用."""
        row = _dataset_snapshot_row(
            resolved_inputs=({"derived_id": "x", "version": 1},)
        )
        rec = ResearchDatasetSnapshotRecord.from_row(row)
        assert rec.resolved_inputs == ({"derived_id": "x", "version": 1},)

    def test_source_snapshot_ids_from_tuple(self) -> None:
        """source_snapshot_ids 已经是 tuple 时直接使用."""
        row = _dataset_snapshot_row(source_snapshot_ids=("snap_a",))
        rec = ResearchDatasetSnapshotRecord.from_row(row)
        assert rec.source_snapshot_ids == ("snap_a",)

    def test_defaults_when_missing(self) -> None:
        """可选字段缺失时使用默认值."""
        row = _dataset_snapshot_row()
        # 删除可选字段，验证默认值
        for key in (
            "spine_spec_version",
            "resolved_versions",
            "resolved_inputs",
            "source_snapshot_ids",
            "builder_version",
            "created_at",
        ):
            del row[key]
        rec = ResearchDatasetSnapshotRecord.from_row(row)
        assert rec.spine_spec_version == 1
        assert rec.resolved_versions == {}
        assert rec.resolved_inputs == ()
        assert rec.source_snapshot_ids == ()
        assert rec.builder_version == ""
        assert rec.created_at == ""

    def test_raises_on_missing_snapshot_id(self) -> None:
        """snapshot_id 缺失时抛出 ResearchDatasetError."""
        row = _dataset_snapshot_row()
        del row["snapshot_id"]
        with pytest.raises(ResearchDatasetError, match="snapshot_id"):
            ResearchDatasetSnapshotRecord.from_row(row)

    def test_raises_on_empty_snapshot_id(self) -> None:
        """snapshot_id 为空字符串时抛出 ResearchDatasetError."""
        row = _dataset_snapshot_row(snapshot_id="")
        with pytest.raises(ResearchDatasetError, match="snapshot_id"):
            ResearchDatasetSnapshotRecord.from_row(row)

    def test_raises_on_non_string_snapshot_id(self) -> None:
        """snapshot_id 为非字符串类型时抛出 ResearchDatasetError."""
        row = _dataset_snapshot_row(snapshot_id=100)
        with pytest.raises(ResearchDatasetError, match="snapshot_id"):
            ResearchDatasetSnapshotRecord.from_row(row)

    def test_raises_on_non_int_dataset_spec_version(self) -> None:
        """dataset_spec_version 为非 int 类型时抛出 ResearchDatasetError."""
        row = _dataset_snapshot_row(dataset_spec_version="bad")
        with pytest.raises(ResearchDatasetError, match="dataset_spec_version"):
            ResearchDatasetSnapshotRecord.from_row(row)

    def test_raises_on_non_int_row_count(self) -> None:
        """row_count 为非 int 类型时抛出 ResearchDatasetError."""
        row = _dataset_snapshot_row(row_count="bad")
        with pytest.raises(ResearchDatasetError, match="row_count"):
            ResearchDatasetSnapshotRecord.from_row(row)

    def test_raises_on_non_int_spine_spec_version(self) -> None:
        """spine_spec_version 为非 int 类型时抛出 ResearchDatasetError."""
        row = _dataset_snapshot_row(spine_spec_version="bad")
        with pytest.raises(ResearchDatasetError, match="spine_spec_version"):
            ResearchDatasetSnapshotRecord.from_row(row)
