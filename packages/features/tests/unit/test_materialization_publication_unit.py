"""Tests for derived materialization publication records (#444 直线化后的承重件)."""

from __future__ import annotations

import dataclasses

from ditto_features.materialization.publication import (
    CompatibilityManifest,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummary,
    DerivedMinimalDQSummaryRecord,
)


def _manifest(**overrides: object) -> CompatibilityManifest:
    defaults: dict[str, object] = {
        "engine_codegen_version": "codegen-v1",
        "analysis_version": "analysis-v1",
        "polars_version": "1.30.0",
        "expr_serialization_format": "expr-json-v1",
        "operator_fingerprint": "operator-fingerprint",
        "global_compile_flags": {"pushdown": True},
        "calendar_id": "cn_xshg",
        "timezone": "Asia/Shanghai",
        "time_semantics_version": "time-v1",
    }
    return CompatibilityManifest(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestCompatibilityManifest:
    """CompatibilityManifest 产物身份完整性与 PIT 显式语义."""

    def test_complete_manifest_has_no_missing_fields(self) -> None:
        assert _manifest().is_complete() is True
        assert _manifest().missing_required_fields() == ()

    def test_reports_missing_required_fields(self) -> None:
        manifest = _manifest(engine_codegen_version=None)
        assert manifest.is_complete() is False
        assert manifest.missing_required_fields() == ("engine_codegen_version",)

    def test_requires_pit_policy_fields(self) -> None:
        manifest = _manifest(pit_policy=None, pit_time_column=None)
        assert manifest.is_complete() is False
        assert manifest.missing_required_fields() == ("pit_policy", "pit_time_column")

    def test_snapshot_ids_normalized_to_tuple(self) -> None:
        manifest = _manifest(source_snapshot_ids=["a", "b"])
        assert manifest.source_snapshot_ids == ("a", "b")


class TestDerivedMinimalDQSummary:
    """最小 DQ 摘要的发布判定语义."""

    def test_failed_checks_block(self) -> None:
        summary = DerivedMinimalDQSummary(
            row_count=10,
            primary_key_columns=("instrument_id", "trade_date"),
            failed_checks=("value_has_no_nan",),
        )
        assert summary.is_passed() is False
        assert summary.error_count() == 1

    def test_clean_summary_passes(self) -> None:
        summary = DerivedMinimalDQSummary(
            row_count=10,
            primary_key_columns=("instrument_id", "trade_date"),
        )
        assert summary.is_passed() is True


def test_records_are_frozen_dataclasses() -> None:
    for cls in (CompatibilityManifestRecord, DerivedMinimalDQSummaryRecord):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]
