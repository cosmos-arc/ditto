"""Prefect flow for derived materialization."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from prefect import flow

from ditto_apps.registry import create_materialization_bundle

__all__ = [
    "daily_materialization_flow",
]


def _normalize_results(results: tuple[object, ...]) -> list[dict[str, Any] | object]:
    normalized: list[dict[str, Any] | object] = []
    for result in results:
        if is_dataclass(result) and not isinstance(result, type):
            normalized.append(asdict(result))
            continue
        normalized.append(result)
    return normalized


def run_daily_materialization(
    trade_date: str,
    mode: str = "incremental",
    derived_ids: list[str] | None = None,
) -> dict[str, object]:
    """执行单日 durable 物化业务，供 Prefect flow 与同步 CLI 共用。"""
    with create_materialization_bundle() as bundle:
        results = bundle.materialization_service.materialize_daily(
            trade_date=trade_date,
            mode=mode,
            derived_ids=derived_ids,
        )
    return {
        "trade_date": trade_date,
        "results": _normalize_results(results),
        "summary": {
            "trade_date": trade_date,
            "materialized_count": len(results),
        },
    }


@flow(name="daily-materialization", description="每日 durable profile 物化流程")
def daily_materialization_flow(
    trade_date: str,
    mode: str = "incremental",
    derived_ids: list[str] | None = None,
) -> dict[str, object]:
    """Schedule durable derived materialization for one trade date."""
    return run_daily_materialization(
        trade_date=trade_date,
        mode=mode,
        derived_ids=derived_ids,
    )
