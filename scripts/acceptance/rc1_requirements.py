"""Business-level RC-1 launch requirement validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import orjson

LAUNCH_DATASETS: tuple[str, ...] = (
    "stock_basic",
    "stock_daily",
    "stock_status",
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "valuation_metrics",
    "etf_basic",
    "etf_daily",
    "index_basic",
    "index_daily",
    "adj_factor",
    "fund_adj",
    "macro_indicators",
)

ACCEPTED_PROMOTION_STATUSES: frozenset[str] = frozenset({"ready", "promoted"})
ACCEPTED_MATURITIES: frozenset[str] = frozenset({"initial-focus", "stable"})
ACCEPTED_FRESHNESS: frozenset[str] = frozenset({"fresh", "not_applicable"})


@dataclass(frozen=True)
class RequirementValidation:
    ok: bool
    failures: tuple[str, ...]


def _dataset_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("datasets")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("ingestion_status")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def validate_maturity_status(
    payload: dict[str, Any],
    *,
    required_datasets: tuple[str, ...] = LAUNCH_DATASETS,
) -> RequirementValidation:
    rows_by_dataset = {
        str(row.get("dataset")): row
        for row in _dataset_rows(payload)
        if row.get("dataset") is not None
    }
    failures: list[str] = []
    for dataset in required_datasets:
        row = rows_by_dataset.get(dataset)
        if row is None:
            failures.append(f"{dataset} missing from maturity status")
            continue

        promotion_status = str(row.get("dataset_promotion_status") or "")
        maturity = str(row.get("dataset_maturity") or "")
        freshness = str(row.get("catalog_freshness_status") or "")
        storage_uri = row.get("catalog_storage_uri")
        schema_hash = row.get("catalog_schema_hash")
        row_count = row.get("catalog_row_count")

        promotion_accepted = promotion_status in ACCEPTED_PROMOTION_STATUSES or (
            promotion_status == "not_applicable" and maturity in ACCEPTED_MATURITIES
        )
        if not promotion_accepted:
            failures.append(
                f"{dataset} promotion status is {promotion_status or 'missing'}"
            )
        if maturity not in ACCEPTED_MATURITIES:
            failures.append(f"{dataset} maturity is {maturity or 'missing'}")
        if not storage_uri:
            failures.append(f"{dataset} catalog storage uri is missing")
        if not schema_hash:
            failures.append(f"{dataset} catalog schema hash is missing")
        if row_count is None or int(row_count) <= 0:
            failures.append(f"{dataset} catalog row count is missing or zero")
        if freshness not in ACCEPTED_FRESHNESS:
            failures.append(f"{dataset} freshness is {freshness or 'missing'}")

    return RequirementValidation(ok=not failures, failures=tuple(failures))


def validate_maturity_status_from_stdout(stdout: str) -> RequirementValidation:
    try:
        payload = orjson.loads(stdout)
    except orjson.JSONDecodeError:
        return RequirementValidation(
            ok=False,
            failures=("maturity status stdout is not valid JSON",),
        )
    if not isinstance(payload, dict):
        return RequirementValidation(
            ok=False,
            failures=("maturity status stdout JSON is not an object",),
        )
    return validate_maturity_status(payload)
