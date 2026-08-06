"""Exact R2 live-evidence fixture shared by binding integration tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import orjson
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    R2LiveGateArtifactSource,
    R2LiveGateEvidenceSource,
)

_R2_CONTRACTS = {
    "stock_basic": ("tushare:stock_basic", "tushare:bak_basic"),
    "etf_basic": ("tushare:fund_basic",),
    "index_basic": ("tushare:index_basic",),
    "calendar": ("tushare:trade_cal",),
    "stock_daily": ("tushare:daily", "local_tdx:day"),
    "etf_daily": ("tushare:fund_daily", "local_tdx:day"),
    "index_daily": ("tushare:index_daily", "local_tdx:day"),
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
}


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
    report = {
        "mode": "live",
        "status": "ready",
        "checked_at": checked_at,
        "reason_codes": [],
        "preflight": {
            "status": "ready",
            "checked_at": checked_at,
            "contract_count": 19,
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
