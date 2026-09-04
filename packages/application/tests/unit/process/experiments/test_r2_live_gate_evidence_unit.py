"""Unit tests for content-verified R2 live-gate evidence input."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.evidence_collector import (
    project_r2_live_gate_fact,
)
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    FileR2LiveGateEvidenceReader,
    NullR2LiveGateEvidenceReader,
    R2LiveGateArtifactSource,
    R2LiveGateEvidenceReader,
    R2LiveGateEvidenceSource,
    VerifiedR2LiveGateEvidence,
)

_R2_CONTRACTS = {
    "stock_basic": ("tushare:stock_basic", "tushare:bak_basic"),
    "etf_basic": ("tushare:fund_basic",),
    "index_basic": ("tushare:index_basic",),
    "calendar": ("tushare:trade_cal",),
    "stock_daily": ("tushare:daily", "local_tdx:day"),
    "etf_daily": ("tushare:fund_daily", "local_tdx:day"),
    "index_daily": ("tushare:index_daily", "local_tdx:day"),
    "global_index_daily": ("tushare:index_global",),
    "stock_status": ("tushare:stock_st", "tushare:suspend_d", "tushare:bak_basic"),
    "adj_factor": ("tushare:adj_factor",),
    "fund_adj": ("tushare:fund_adj",),
    "balance_sheet": ("tushare:balancesheet",),
    "income_statement": ("tushare:income",),
    "cash_flow": ("tushare:cashflow",),
    "dividend": ("tushare:dividend",),
    "valuation_metrics": ("tushare:daily_basic",),
    "macro_indicators": (
        "tushare:cn_macro",
        "fred:series_observations",
        "alfred:vintages",
    ),
    "commodity_daily": ("fred:commodity_series", "tushare:commodity_reference"),
    "corporate_actions": ("tushare:corporate_actions",),
    "index_weight": ("tushare:index_weight",),
    "industry_classification": ("tushare:index_classify",),
    "industry_mapping": ("tushare:index_member_all",),
}


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ready_report(*, mode: str = "live", status: str = "ready") -> dict[str, object]:
    products = [
        {
            "dataset_id": dataset_id,
            "provider_datasets": list(provider_datasets),
            "usable_provider_datasets": [provider_datasets[0]],
            "license_record_ids": [f"license:{dataset_id}"],
            "certification_profile": "r2-modern-a-share-v1",
            "certification_report_id": f"certification:{dataset_id}:live",
            "certification_content_hash": "b" * 64,
            "certified_from": "2015-01-01",
            "certified_through": "2026-07-31",
            "ready": True,
            "reason_codes": [],
        }
        for dataset_id, provider_datasets in _R2_CONTRACTS.items()
    ]
    return {
        "mode": mode,
        "status": status,
        "checked_at": "2026-07-31T12:00:00+00:00",
        "reason_codes": [] if status == "ready" else ["entitlement_unverified"],
        "preflight": {
            "status": "ready" if status == "ready" else "configuration_blocked",
            "checked_at": "2026-07-31T12:00:00+00:00",
            "contract_count": 22,
            "products": products,
            "reason_codes": ([] if status == "ready" else ["entitlement_unverified"]),
            "performance": {
                "representative_datasets": [
                    "adj_factor",
                    "fund_adj",
                    "index_daily",
                    "stock_daily",
                ],
                "bootstrap_passed": True,
                "projected_bootstrap_seconds": 36_000.0,
                "bootstrap_limit_seconds": 86_400.0,
                "incremental_passed": True,
                "incremental_elapsed_seconds": 120.0,
                "incremental_limit_seconds": 1_800.0,
                "workbench_query_passed": True,
                "workbench_query_seconds": 0.4,
                "workbench_query_limit_seconds": 5.0,
                "reason_codes": [],
            },
        },
        "recoverability": {
            "passed": True,
            "sqlite_table_row_counts": {"artifact": 1},
            "payload_root_sha256": f"sha256:{'a' * 64}",
            "reason_codes": [],
        },
        "idempotency": {
            "first": {
                "durable_identity_count": 1,
                "write_attempt_count": 1,
                "snapshot_ids": ["snapshot-live-1"],
            },
            "second": {
                "durable_identity_count": 1,
                "write_attempt_count": 1,
                "snapshot_ids": ["snapshot-live-1"],
            },
            "second_run_write_attempts": 0,
            "passed": True,
            "reason_codes": [],
        },
    }


def _artifact_source(root: Path, name: str) -> R2LiveGateArtifactSource:
    path = root / f"{name}.json"
    payload = orjson.dumps({"artifact": name, "status": "verified"})
    path.write_bytes(payload)
    return R2LiveGateArtifactSource(
        path=path,
        artifact_uri=path.resolve().as_uri(),
        expected_content_hash=_hash(payload),
    )


def _source(
    root: Path,
    report: dict[str, object],
) -> R2LiveGateEvidenceSource:
    report_path = root / "live-acceptance.json"
    report_bytes = orjson.dumps(report, option=orjson.OPT_SORT_KEYS)
    report_path.write_bytes(report_bytes)
    return R2LiveGateEvidenceSource(
        report_path=report_path,
        report_uri=report_path.resolve().as_uri(),
        expected_report_hash=_hash(report_bytes),
        provider_entitlement_artifacts=(_artifact_source(root, "provider"),),
        performance_artifacts=(_artifact_source(root, "performance"),),
        recoverability_artifacts=(_artifact_source(root, "recoverability"),),
        idempotency_artifacts=(_artifact_source(root, "idempotency"),),
    )


def test_no_evidence_returns_not_evaluated() -> None:
    reader = NullR2LiveGateEvidenceReader()

    assert reader.read_verified_live_gate() is None
    fact = project_r2_live_gate_fact(reader)
    assert fact.satisfied is None
    assert fact.detail == {
        "status": "not_evaluated",
        "reason_code": "r2_live_evidence_unavailable",
    }


def test_fixture_report_cannot_close_live_gate(tmp_path: Path) -> None:
    reader = FileR2LiveGateEvidenceReader(
        _source(tmp_path, _ready_report(mode="fixture"))
    )

    assert reader.read_verified_live_gate() is None
    assert project_r2_live_gate_fact(reader).satisfied is None


def test_content_verified_ready_report_returns_typed_evidence(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())
    evidence = FileR2LiveGateEvidenceReader(source).read_verified_live_gate()

    assert type(evidence) is VerifiedR2LiveGateEvidence
    assert evidence is not None
    assert evidence.status == "ready"
    assert evidence.report_hash == source.expected_report_hash
    assert evidence.report_uri == source.report_uri
    assert evidence.checked_at.isoformat() == "2026-07-31T12:00:00+00:00"
    assert evidence.reason_codes == ()
    assert evidence.provider_entitlement_evidence_refs[0].artifact_uri.endswith(
        "/provider.json"
    )
    assert evidence.performance_evidence_refs[0].artifact_uri.endswith(
        "/performance.json"
    )
    assert evidence.recoverability_evidence_refs[0].artifact_uri.endswith(
        "/recoverability.json"
    )
    assert evidence.idempotency_evidence_refs[0].artifact_uri.endswith(
        "/idempotency.json"
    )


def test_verified_configuration_blocked_report_is_an_explicit_fail(
    tmp_path: Path,
) -> None:
    reader = FileR2LiveGateEvidenceReader(
        _source(tmp_path, _ready_report(status="configuration_blocked"))
    )

    evidence = reader.read_verified_live_gate()
    assert evidence is not None
    assert evidence.status == "configuration_blocked"
    fact = project_r2_live_gate_fact(reader)
    assert fact.satisfied is False
    assert fact.detail["status"] == "configuration_blocked"
    assert fact.detail["reason_codes"] == ("entitlement_unverified",)


@pytest.mark.parametrize(
    "missing_key",
    ["preflight", "recoverability", "idempotency"],
)
def test_ready_report_missing_required_section_fails_closed(
    tmp_path: Path,
    missing_key: str,
) -> None:
    report = _ready_report()
    report.pop(missing_key)

    reader = FileR2LiveGateEvidenceReader(_source(tmp_path, report))

    assert reader.read_verified_live_gate() is None
    assert project_r2_live_gate_fact(reader).satisfied is None


def test_ready_report_missing_performance_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    performance = cast("dict[str, object]", preflight["performance"])
    performance["incremental_passed"] = False
    performance["reason_codes"] = ["performance_evidence_missing"]

    reader = FileR2LiveGateEvidenceReader(_source(tmp_path, report))

    assert reader.read_verified_live_gate() is None


def test_ready_report_rejects_substituted_hard_scope_dataset(tmp_path: Path) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    products = cast("list[dict[str, object]]", preflight["products"])
    products[0]["dataset_id"] = "substituted_dataset"

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


def test_ready_report_rejects_provider_contract_drift(tmp_path: Path) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    products = cast("list[dict[str, object]]", preflight["products"])
    products[0]["provider_datasets"] = ["forged:provider"]
    products[0]["usable_provider_datasets"] = ["forged:provider"]

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


@pytest.mark.parametrize(
    "field",
    [
        "certification_report_id",
        "certification_content_hash",
        "certified_from",
        "certified_through",
    ],
)
def test_ready_report_requires_active_certified_history(
    tmp_path: Path,
    field: str,
) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    products = cast("list[dict[str, object]]", preflight["products"])
    products[0][field] = None

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


def test_ready_report_requires_measured_performance_fields(tmp_path: Path) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    performance = cast("dict[str, object]", preflight["performance"])
    performance.pop("workbench_query_seconds")

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


@pytest.mark.parametrize(
    ("limit_field", "drifted_limit"),
    [
        ("bootstrap_limit_seconds", 86_401.0),
        ("incremental_limit_seconds", 1_801.0),
        ("workbench_query_limit_seconds", 5.1),
    ],
)
def test_ready_report_rejects_frozen_performance_limit_drift(
    tmp_path: Path,
    limit_field: str,
    drifted_limit: float,
) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    performance = cast("dict[str, object]", preflight["performance"])
    performance[limit_field] = drifted_limit

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


@pytest.mark.parametrize(
    ("observed_field", "over_frozen_limit"),
    [
        ("projected_bootstrap_seconds", 86_400.1),
        ("incremental_elapsed_seconds", 1_800.1),
        ("workbench_query_seconds", 5.1),
    ],
)
def test_ready_report_rejects_observation_over_frozen_performance_limit(
    tmp_path: Path,
    observed_field: str,
    over_frozen_limit: float,
) -> None:
    report = _ready_report()
    preflight = cast("dict[str, object]", report["preflight"])
    performance = cast("dict[str, object]", preflight["performance"])
    performance[observed_field] = over_frozen_limit

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("second_run_write_attempts", False),
        ("second_run_write_attempts", -1),
        ("second.write_attempt_count", True),
        ("second.durable_identity_count", True),
    ],
)
def test_ready_report_rejects_idempotency_numeric_type_confusion(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    report = _ready_report()
    idempotency = cast("dict[str, object]", report["idempotency"])
    if field.startswith("second."):
        second = cast("dict[str, object]", idempotency["second"])
        second[field.removeprefix("second.")] = value
    else:
        idempotency[field] = value

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


def test_ready_report_rejects_non_hex_recoverability_hash(tmp_path: Path) -> None:
    report = _ready_report()
    recoverability = cast("dict[str, object]", report["recoverability"])
    recoverability["payload_root_sha256"] = f"sha256:{'z' * 64}"

    assert (
        FileR2LiveGateEvidenceReader(
            _source(tmp_path, report)
        ).read_verified_live_gate()
        is None
    )


def test_report_bytes_or_hash_drift_fails_closed(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())
    source.report_path.write_bytes(b"{}")

    reader = FileR2LiveGateEvidenceReader(source)

    assert reader.read_verified_live_gate() is None


def test_report_path_drift_fails_closed(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())
    drifted = replace(source, report_uri=(tmp_path / "other.json").resolve().as_uri())

    assert FileR2LiveGateEvidenceReader(drifted).read_verified_live_gate() is None


def test_special_file_report_fails_closed_without_blocking(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())
    fifo = tmp_path / "live-report.fifo"
    os.mkfifo(fifo)
    special = replace(
        source,
        report_path=fifo,
        report_uri=fifo.resolve().as_uri(),
    )

    assert FileR2LiveGateEvidenceReader(special).read_verified_live_gate() is None


def test_source_contract_rejects_noncanonical_report_hash_with_typed_error(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, _ready_report())

    with pytest.raises(AppProcessError) as exc_info:
        replace(source, expected_report_hash="A" * 64)

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "r2_live_report_hash_invalid",
    }


def test_required_artifact_hash_drift_fails_closed(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())
    source.performance_artifacts[0].path.write_bytes(b"drift")

    assert FileR2LiveGateEvidenceReader(source).read_verified_live_gate() is None


def test_one_artifact_cannot_satisfy_multiple_evidence_groups(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())
    shared = source.provider_entitlement_artifacts
    duplicated = replace(
        source,
        performance_artifacts=shared,
        recoverability_artifacts=shared,
        idempotency_artifacts=shared,
    )

    assert FileR2LiveGateEvidenceReader(duplicated).read_verified_live_gate() is None


def test_ready_projection_binds_report_and_all_evidence_refs(tmp_path: Path) -> None:
    source = _source(tmp_path, _ready_report())

    fact = project_r2_live_gate_fact(FileR2LiveGateEvidenceReader(source))

    assert fact.satisfied is True
    assert fact.detail["report_hash"] == str(source.expected_report_hash)
    assert fact.detail["checked_at"] == "2026-07-31T12:00:00+00:00"
    assert fact.detail["status"] == "ready"
    assert tuple(fact.detail) == (
        "report_uri",
        "report_hash",
        "checked_at",
        "status",
        "reason_codes",
        "provider_entitlement_evidence_refs",
        "performance_evidence_refs",
        "recoverability_evidence_refs",
        "idempotency_evidence_refs",
    )


class _InvalidBooleanReader:
    def read_verified_live_gate(self) -> object:
        return True


def test_hand_constructed_boolean_cannot_enter_gate_projection() -> None:
    reader = cast("R2LiveGateEvidenceReader", _InvalidBooleanReader())

    with pytest.raises(AppProcessError) as exc_info:
        project_r2_live_gate_fact(reader)

    assert exc_info.value.details["code"] == "EXPERIMENT_INTEGRITY_FAILED"
    assert exc_info.value.details["reason"] == "r2_live_gate_reader_contract_invalid"
