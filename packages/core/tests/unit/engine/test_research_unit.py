"""Tests for research dataset models."""

from __future__ import annotations

import pytest
from ditto_core.engine.research import (
    DatasetSnapshot,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    SpineSnapshot,
    SpineSpec,
)


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

        with pytest.raises(NotImplementedError, match="cn_stock"):
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

        with pytest.raises(NotImplementedError, match="derived"):
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
