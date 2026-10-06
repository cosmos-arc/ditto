"""Exact R2 live-evidence fixture shared by binding integration tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import orjson
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    _R2_HARD_DATASET_PROVIDER_CONTRACTS,
    R2LiveGateArtifactSource,
    R2LiveGateEvidenceSource,
)

# 跟随生产契约表（#529 收口：fixture 副本漂移曾使 #534 的 provider 面扩展
# 未同步到这里，ready 报告静默 fail closed）。
_R2_CONTRACTS = _R2_HARD_DATASET_PROVIDER_CONTRACTS


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact(root: Path, name: str) -> R2LiveGateArtifactSource:
    path = root / f"{name}.json"
    payload = orjson.dumps({"artifact": name, "status": "verified"})
    path.write_bytes(payload)
    return R2LiveGateArtifactSource(
        path=path,
        artifact_uri=path.resolve().as_uri(),
        expected_content_hash=_hash(payload),
    )


def ready_source(root: Path) -> R2LiveGateEvidenceSource:
    """Write one exact live-ready report and four distinct verified artifacts."""
    root.mkdir(parents=True, exist_ok=True)
    checked_at = "2026-07-31T12:00:00+00:00"
    products = [
        {
            "dataset_id": dataset_id,
            "provider_datasets": list(provider_datasets),
            "usable_provider_datasets": [provider_datasets[0]],
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
    report = {
        "mode": "live",
        "status": "ready",
        "checked_at": checked_at,
        "reason_codes": [],
        "preflight": {
            "status": "ready",
            "checked_at": checked_at,
            "contract_count": 22,
            "products": products,
            "reason_codes": [],
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
            "sqlite_table_row_counts": {"research_artifact": 1},
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
    report_path = root / "r2-live-acceptance.json"
    report_bytes = orjson.dumps(report, option=orjson.OPT_SORT_KEYS)
    report_path.write_bytes(report_bytes)
    return R2LiveGateEvidenceSource(
        report_path=report_path,
        report_uri=report_path.resolve().as_uri(),
        expected_report_hash=_hash(report_bytes),
        provider_entitlement_artifacts=(_artifact(root, "provider-entitlement"),),
        performance_artifacts=(_artifact(root, "performance"),),
        recoverability_artifacts=(_artifact(root, "recoverability"),),
        idempotency_artifacts=(_artifact(root, "idempotency"),),
    )
