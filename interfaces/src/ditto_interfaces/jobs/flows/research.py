"""Prefect flows for research dataset snapshot builds."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from prefect import flow

from ditto_interfaces.registry import create_materialization_bundle

__all__ = ["research_dataset_build_flow"]


def _normalize_results(results: tuple[object, ...]) -> list[dict[str, Any] | object]:
    normalized: list[dict[str, Any] | object] = []
    for result in results:
        if is_dataclass(result) and not isinstance(result, type):
            normalized.append(asdict(result))
            continue
        normalized.append(result)
    return normalized


@flow(
    name="research-dataset-build",
    description="构建 research dataset immutable snapshot 并持久化 build report",
)
def research_dataset_build_flow(
    *,
    dataset_id: str,
    start: str,
    end: str,
    version_overrides: dict[str, int] | None = None,
    explicit_cutoff: str | None = None,
) -> dict[str, object]:
    """Build one immutable research dataset snapshot."""
    with create_materialization_bundle() as bundle:
        snapshot = bundle.research_dataset_facade.build(
            dataset_id=dataset_id,
            start=start,
            end=end,
            version_overrides=version_overrides,
            explicit_cutoff=explicit_cutoff,
        )
        build_report = bundle.research_dataset_facade.load_build_report(snapshot)

    return {
        "results": _normalize_results((snapshot,)),
        "summary": {
            "dataset_id": dataset_id,
            "snapshot_id": snapshot.snapshot_id,
            "row_count": build_report["row_count"],
            "spine_row_count": build_report["spine_row_count"],
            "null_counts": build_report["null_counts"],
            "resolved_versions": build_report["resolved_versions"],
            "known_at_policy": build_report["known_at_policy"],
        },
    }
