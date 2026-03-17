"""Prefect flows for derived materialization, repair, and migration."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from ditto_core.engine.publication_safety import CertificationStage
from prefect import flow

from ditto_port.registry import create_materialization_bundle

__all__ = [
    "certify_publication_flow",
    "daily_materialization_flow",
    "deprecate_publication_flow",
    "promote_publication_flow",
    "repair_from_invalidation_flow",
    "rollback_publication_flow",
    "shadow_compare_flow",
    "shadow_publish_flow",
]


def _normalize_results(results: tuple[object, ...]) -> list[dict[str, Any] | object]:
    normalized: list[dict[str, Any] | object] = []
    for result in results:
        if is_dataclass(result) and not isinstance(result, type):
            normalized.append(asdict(result))
            continue
        normalized.append(result)
    return normalized


@flow(name="daily-materialization", description="每日 durable profile 物化流程")
def daily_materialization_flow(
    trade_date: str,
    mode: str = "incremental",
    derived_ids: list[str] | None = None,
) -> dict[str, object]:
    """Schedule durable derived materialization for one trade date."""
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


@flow(
    name="repair-from-invalidation",
    description="消费 pending invalidation 并触发修复",
)
def repair_from_invalidation_flow(limit: int = 100) -> dict[str, object]:
    """Repair pending invalidations in batch order."""
    with create_materialization_bundle() as bundle:
        results = bundle.invalidation_service.repair_pending(limit=limit)
    return {
        "results": _normalize_results(results),
        "summary": {
            "repaired_count": len(results),
        },
    }


@flow(
    name="derived-shadow-publish",
    description="注册 candidate 版本进入 shadow slot",
)
def shadow_publish_flow(
    *,
    derived_id: str,
    candidate_version: int,
    baseline_version: int | None = None,
) -> dict[str, object]:
    """Register one active shadow candidate slot."""
    with create_materialization_bundle() as bundle:
        result = bundle.publication_facade.shadow_publish(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
        )
    return {
        "results": _normalize_results((result,)),
        "summary": {
            "derived_id": derived_id,
            "candidate_version": candidate_version,
            "baseline_version": baseline_version,
        },
    }


@flow(
    name="derived-shadow-compare",
    description="执行 candidate 与 baseline 的 shadow compare 审计",
)
def shadow_compare_flow(
    *,
    derived_id: str,
    start: str,
    end: str,
    candidate_version: int | None = None,
    baseline_version: int | None = None,
) -> dict[str, object]:
    """Run one explicit shadow compare batch audit."""
    with create_materialization_bundle() as bundle:
        result = bundle.publication_facade.run_shadow_compare(
            derived_id=derived_id,
            start=start,
            end=end,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
        )
    return {
        "results": _normalize_results((result,)),
        "summary": {
            "derived_id": derived_id,
            "candidate_version": candidate_version,
            "baseline_version": baseline_version,
            "start": start,
            "end": end,
        },
    }


@flow(
    name="derived-publication-certify",
    description="执行 derived candidate 的 publish gate 认证",
)
def certify_publication_flow(
    *,
    derived_id: str,
    version: int,
    stage: str,
) -> dict[str, object]:
    """Run one explicit publication certification gate."""
    with create_materialization_bundle() as bundle:
        result = bundle.publication_facade.certify(
            derived_id=derived_id,
            version=version,
            stage=CertificationStage(stage),
        )
    return {
        "results": _normalize_results((result,)),
        "summary": {
            "derived_id": derived_id,
            "version": version,
            "stage": stage,
        },
    }


@flow(
    name="derived-publication-promote",
    description="将 publish_ready candidate 原子提升为 primary/online",
)
def promote_publication_flow(
    *,
    derived_id: str,
    candidate_version: int,
) -> dict[str, object]:
    """Promote one candidate version after publication gates pass."""
    with create_materialization_bundle() as bundle:
        result = bundle.publication_facade.promote(
            derived_id=derived_id,
            candidate_version=candidate_version,
        )
    return {
        "results": _normalize_results((result,)),
        "summary": {
            "derived_id": derived_id,
            "candidate_version": candidate_version,
        },
    }


@flow(
    name="derived-publication-rollback",
    description="将 primary 指针回滚到已发布目标版本",
)
def rollback_publication_flow(
    *,
    derived_id: str,
    target_version: int,
) -> dict[str, object]:
    """Move the primary pointer back to one published target version."""
    with create_materialization_bundle() as bundle:
        result = bundle.publication_facade.rollback(
            derived_id=derived_id,
            target_version=target_version,
        )
    return {
        "results": _normalize_results((result,)),
        "summary": {
            "derived_id": derived_id,
            "target_version": target_version,
        },
    }


@flow(
    name="derived-publication-deprecate",
    description="将已发布非主版本标记为 deprecated/offline",
)
def deprecate_publication_flow(
    *,
    derived_id: str,
    version: int,
) -> dict[str, object]:
    """Mark one published non-primary version as deprecated and offline."""
    with create_materialization_bundle() as bundle:
        result = bundle.publication_facade.deprecate(
            derived_id=derived_id,
            version=version,
        )
    return {
        "results": _normalize_results((result,)),
        "summary": {
            "derived_id": derived_id,
            "version": version,
        },
    }
