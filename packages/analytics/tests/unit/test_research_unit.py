"""Tests for research dataset models."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_analytics.research.domain import (
    DatasetSnapshot,
    LateArrivalError,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    SpineSnapshot,
    SpineSpec,
    _apply_late_arrival_policy,
    _detect_late_arrivals,
)
from ditto_data.errors import DerivedNotImplementedError


class TestSpineSpec:
    """Tests for SpineSpec."""

    def test_version_defaults_to_1(self) -> None:
        """SpineSpec version should default to 1."""
        spec = SpineSpec(
            spine_id="spine.cn_stock.default",
            universe_id="universe.cn.all",
        )

        assert spec.version == 1

    def test_custom_version_is_preserved(self) -> None:
        """SpineSpec should accept explicit version values."""
        spec = SpineSpec(
            spine_id="spine.cn_stock.default",
            universe_id="universe.cn.all",
            version=3,
        )

        assert spec.version == 3

    def test_validate_spec_accepts_cn_stock_daily_single_instrument(self) -> None:
        """V1 spine spec should support cn_stock 1d single-instrument spines."""
        spec = SpineSpec(
            spine_id="spine.cn_stock.default",
            universe_id="universe.cn.all",
        )

        spec.validate_spec()

    def test_validate_spec_rejects_non_cn_stock_calendar(self) -> None:
        """V1 spine spec should reject unsupported calendars."""
        spec = SpineSpec(
            spine_id="spine.us_stock.default",
            universe_id="universe.us.all",
            calendar="us_stock",
        )

        with pytest.raises(DerivedNotImplementedError, match="cn_stock"):
            spec.validate_spec()


class TestResearchDatasetSpec:
    """Tests for ResearchDatasetSpec."""

    def test_version_defaults_to_1(self) -> None:
        """ResearchDatasetSpec version should default to 1."""
        spec = ResearchDatasetSpec(
            dataset_id="research.market_close",
            spine_id="spine.cn_stock.default",
            derived_ids=("factor.alpha",),
        )

        assert spec.version == 1

    def test_custom_version_is_preserved(self) -> None:
        """ResearchDatasetSpec should accept explicit version values."""
        spec = ResearchDatasetSpec(
            dataset_id="research.market_close",
            spine_id="spine.cn_stock.default",
            derived_ids=("factor.alpha",),
            version=2,
        )

        assert spec.version == 2

    def test_validate_spec_requires_derived_inputs(self) -> None:
        """Research datasets should only accept derived ids in v1."""
        spec = ResearchDatasetSpec(
            dataset_id="research.market_close",
            spine_id="spine.cn_stock.default",
            derived_ids=("market.close",),
        )

        with pytest.raises(DerivedNotImplementedError, match="derived"):
            spec.validate_spec()

    def test_late_arrival_policy_defaults_to_require_rebuild(self) -> None:
        """Research dataset specs should default to require_rebuild semantics."""
        spec = ResearchDatasetSpec(
            dataset_id="research.market_close",
            spine_id="spine.cn_stock.default",
            derived_ids=("factor.alpha",),
        )

        assert spec.late_arrival_policy == LateArrivalPolicy.REQUIRE_REBUILD


class TestSpineSnapshot:
    """Tests for SpineSnapshot."""

    def test_version_defaults_to_1(self) -> None:
        """SpineSnapshot version should default to 1."""
        snapshot = SpineSnapshot(
            spine_snapshot_id="rsp-001",
            spine_id="spine.cn_stock.default",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="spines/spine.cn_stock.default/snapshots/rsp-001/data.parquet",
            manifest_hash="hash-001",
            created_at="2026-03-14T12:00:00+08:00",
        )

        assert snapshot.version == 1

    def test_custom_version_is_preserved(self) -> None:
        """SpineSnapshot should accept explicit version values."""
        snapshot = SpineSnapshot(
            spine_snapshot_id="rsp-001",
            spine_id="spine.cn_stock.default",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="spines/spine.cn_stock.default/snapshots/rsp-001/data.parquet",
            manifest_hash="hash-001",
            created_at="2026-03-14T12:00:00+08:00",
            version=2,
        )

        assert snapshot.version == 2


class TestDatasetSnapshot:
    """Tests for DatasetSnapshot."""

    def test_spine_spec_version_defaults_to_1(self) -> None:
        """DatasetSnapshot spine_spec_version should default to 1."""
        snapshot = DatasetSnapshot(
            snapshot_id="rds-001",
            dataset_id="research.alpha_beta",
            dataset_spec_version=1,
            spine_snapshot_id="rsp-001",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-001/data.parquet",
            manifest_hash="manifest-001",
            known_at_policy="sample_time",
            effective_cutoff=None,
        )

        assert snapshot.spine_spec_version == 1

    def test_custom_spine_spec_version_is_preserved(self) -> None:
        """DatasetSnapshot should accept explicit spine_spec_version values."""
        snapshot = DatasetSnapshot(
            snapshot_id="rds-001",
            dataset_id="research.alpha_beta",
            dataset_spec_version=2,
            spine_snapshot_id="rsp-001",
            spine_spec_version=3,
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-001/data.parquet",
            manifest_hash="manifest-001",
            known_at_policy="sample_time",
            effective_cutoff=None,
        )

        assert snapshot.spine_spec_version == 3
        assert snapshot.dataset_spec_version == 2

    def test_dataset_snapshot_records_both_spec_versions(self) -> None:
        """DatasetSnapshot should freeze both spec versions for auditability."""
        snapshot = DatasetSnapshot(
            snapshot_id="rds-001",
            dataset_id="research.alpha_beta",
            dataset_spec_version=2,
            spine_spec_version=1,
            spine_snapshot_id="rsp-001",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-001/data.parquet",
            manifest_hash="manifest-001",
            known_at_policy="sample_time",
            effective_cutoff=None,
        )

        assert snapshot.dataset_spec_version == 2
        assert snapshot.spine_spec_version == 1

    def test_dataset_snapshot_requires_precise_snapshot_contract_fields(self) -> None:
        """Snapshots should freeze exact inputs, cutoffs, and builder metadata."""
        snapshot = DatasetSnapshot(
            snapshot_id="rds-001",
            dataset_id="research.alpha_beta",
            dataset_spec_version=1,
            spine_snapshot_id="rsp-001",
            start="2026-03-10",
            end="2026-03-11",
            row_count=2,
            data_path="derived/research/datasets/research.alpha_beta/snapshots/rds-001/data.parquet",
            manifest_hash="manifest-001",
            known_at_policy="sample_time",
            effective_cutoff=None,
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
            created_at="2026-03-14T12:00:00+08:00",
        )

        assert snapshot.dataset_spec_version == 1
        assert snapshot.resolved_inputs[0]["derived_id"] == "factor.alpha"
        assert snapshot.source_snapshot_ids == (
            "market:20260310-001",
            "market:20260311-001",
        )
        assert snapshot.builder_version == "unified-derived-research-v1"


# ============ Late Arrival Detection & Policy Tests ============


class TestDetectLateArrivals:
    """Tests for _detect_late_arrivals function."""

    def test_detect_late_arrivals_flags_delayed_data(self) -> None:
        """当 availability_time > known_at 时应标记为延迟到达."""

        derived_id = "factor.alpha"
        availability_col = f"{derived_id}_availability_time"

        frame = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                ],
                "known_at": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                ],
                availability_col: [
                    date(2026, 3, 10),
                    date(2026, 3, 12),
                    date(2026, 3, 10),
                ],
                derived_id: [1.0, 2.0, 3.0],
            }
        )

        result = _detect_late_arrivals(frame, derived_id)

        # Row 0: availability (3/10) == known_at (3/10) -> not late
        # Row 1: availability (3/12) > known_at (3/11) -> late
        # Row 2: availability (3/10) == known_at (3/10) -> not late
        assert result.height == 3
        flags = result["is_late"].to_list()
        assert flags == [False, True, False]

    def test_detect_late_arrivals_handles_null_availability(self) -> None:
        """当 availability_time 为 null 时不应标记为延迟."""

        derived_id = "factor.alpha"
        availability_col = f"{derived_id}_availability_time"

        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "known_at": [date(2026, 3, 10)],
                availability_col: [None],
                derived_id: [None],
            },
        )

        result = _detect_late_arrivals(frame, derived_id)
        assert result["is_late"].to_list() == [False]

    def test_detect_late_arrivals_empty_frame(self) -> None:
        """空 DataFrame 应返回空结果."""

        frame = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "known_at": pl.Date,
                "factor.alpha": pl.Float64,
            }
        )

        result = _detect_late_arrivals(frame, "factor.alpha")
        assert result.is_empty()

    def test_detect_late_arrivals_no_availability_column(
        self,
    ) -> None:
        """当 availability_time 列不存在时，所有行都不应标记为延迟."""

        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 3, 10)],
                "known_at": [date(2026, 3, 10)],
                "factor.alpha": [1.0],
            }
        )

        result = _detect_late_arrivals(frame, "factor.alpha")
        assert result["is_late"].to_list() == [False]


class TestApplyLateArrivalPolicy:
    """Tests for _apply_late_arrival_policy function."""

    def test_apply_late_arrival_policy_exclude(
        self,
    ) -> None:
        """EXCLUDE 策略应过滤掉延迟到达的行."""

        frame = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                ],
                "factor.alpha": [1.0, 2.0, 3.0],
            }
        )
        late_flags = pl.Series([False, True, False])

        result = _apply_late_arrival_policy(
            frame,
            LateArrivalPolicy.EXCLUDE_FROM_CURRENT_SNAPSHOT,
            late_flags,
        )

        assert result.height == 2
        assert result["instrument_id"].to_list() == [1, 2]
        assert result["trade_date"].to_list() == [
            date(2026, 3, 10),
            date(2026, 3, 10),
        ]

    def test_apply_late_arrival_policy_shift_logs_warning(
        self,
    ) -> None:
        """SHIFT 策略应记录日志并原样返回（v1 暂不实现位移）."""

        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "factor.alpha": [1.0, 2.0],
            }
        )
        late_flags = pl.Series([True, False])

        result = _apply_late_arrival_policy(
            frame,
            LateArrivalPolicy.SHIFT_TO_NEXT_SNAPSHOT,
            late_flags,
        )

        # v1: SHIFT 原样返回，不修改
        assert result.height == 2
        assert result.equals(frame)

    def test_apply_late_arrival_policy_rebuild_raises(
        self,
    ) -> None:
        """REBUILD 策略应在存在延迟到达行时抛出 LateArrivalError."""

        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "factor.alpha": [1.0, 2.0],
            }
        )
        late_flags = pl.Series([True, False])

        with pytest.raises(LateArrivalError, match="Late arrival"):
            _apply_late_arrival_policy(
                frame,
                LateArrivalPolicy.REQUIRE_REBUILD,
                late_flags,
            )

    def test_apply_late_arrival_policy_rebuild_no_late_passes(
        self,
    ) -> None:
        """REBUILD 策略在无延迟行时应原样返回."""

        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "factor.alpha": [1.0, 2.0],
            }
        )
        late_flags = pl.Series([False, False])

        result = _apply_late_arrival_policy(
            frame,
            LateArrivalPolicy.REQUIRE_REBUILD,
            late_flags,
        )

        assert result.equals(frame)

    def test_apply_late_arrival_policy_exclude_all_late(
        self,
    ) -> None:
        """EXCLUDE 策略过滤全部延迟行时，应返回空 DataFrame."""

        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "factor.alpha": [1.0, 2.0],
            }
        )
        late_flags = pl.Series([True, True])

        result = _apply_late_arrival_policy(
            frame,
            LateArrivalPolicy.EXCLUDE_FROM_CURRENT_SNAPSHOT,
            late_flags,
        )

        assert result.is_empty()
