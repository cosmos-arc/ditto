"""Tests for publication safety records in kernel."""

from __future__ import annotations

import dataclasses

from ditto_kernel.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    DerivedShadowSlotRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)


def test_all_records_are_frozen_dataclasses() -> None:
    for cls in (
        CompatibilityManifestRecord,
        DerivedMinimalDQSummaryRecord,
        ShadowDiffReportRecord,
        ShadowTraceRecordRecord,
        CertificationReportRecord,
        DerivedShadowSlotRecord,
    ):
        assert dataclasses.is_dataclass(cls)
        assert hasattr(cls, "__dataclass_params__")
        assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_compatibility_manifest_round_trip() -> None:
    record = CompatibilityManifestRecord(
        derived_id="test",
        version=1,
        manifest_hash="abc",
        payload={"key": "value"},
        created_at="2026-01-01",
    )
    json_dict = record.to_json_dict()
    restored = CompatibilityManifestRecord.from_json_dict(json_dict)
    assert restored == record


def test_derived_shadow_slot_optional_fields() -> None:
    record = DerivedShadowSlotRecord(
        derived_id="test",
        candidate_version=2,
        baseline_version=None,
        activated_at="2026-01-01",
        disabled_at=None,
    )
    assert record.baseline_version is None
    assert record.disabled_at is None


def test_certification_report_round_trip() -> None:
    record = CertificationReportRecord(
        report_id="r1",
        derived_id="d1",
        version=3,
        stage="certified",
        pack_id="p1",
        manifest_hash="hash",
        payload={"result": "pass"},
        created_at="2026-02-01",
    )
    json_dict = record.to_json_dict()
    restored = CertificationReportRecord.from_json_dict(json_dict)
    assert restored == record


def test_shadow_diff_report_round_trip() -> None:
    record = ShadowDiffReportRecord(
        report_id="r2",
        derived_id="d2",
        candidate_version=5,
        baseline_version=4,
        error_count=1,
        warning_count=2,
        info_count=3,
        payload={"diff": True},
        created_at="2026-03-01",
    )
    json_dict = record.to_json_dict()
    restored = ShadowDiffReportRecord.from_json_dict(json_dict)
    assert restored == record


def test_shadow_trace_record_round_trip() -> None:
    record = ShadowTraceRecordRecord(
        trace_id="t1",
        report_id="r3",
        derived_id="d3",
        payload={"trace": "data"},
        sampled_at="2026-04-01",
    )
    json_dict = record.to_json_dict()
    restored = ShadowTraceRecordRecord.from_json_dict(json_dict)
    assert restored == record


def test_minimal_dq_summary_round_trip() -> None:
    record = DerivedMinimalDQSummaryRecord(
        derived_id="d4",
        version=1,
        run_id="run1",
        passed=True,
        error_count=0,
        payload={"checks": 10},
        created_at="2026-05-01",
    )
    json_dict = record.to_json_dict()
    restored = DerivedMinimalDQSummaryRecord.from_json_dict(json_dict)
    assert restored == record
