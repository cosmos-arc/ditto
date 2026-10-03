"""Bind server-derived consumed selection inputs to durable snapshot evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace

from ditto_application.exceptions import AppProcessError
from ditto_application.queries.snapshot_readiness import (
    SnapshotReadiness,
    SnapshotReadinessQuery,
    SnapshotReadinessReport,
    SnapshotReadinessRequest,
)


def missing_field(name: str, reason: str) -> SnapshotReadiness:
    """Represent an unmet input requirement alongside actual field findings."""
    return SnapshotReadiness(
        dataset_id="",
        field=name,
        snapshot_id="",
        consumer_field=name,
        reason_codes=(reason,),
    )


def assess_selection_readiness(
    query: SnapshotReadinessQuery,
    request: SnapshotReadinessRequest,
    *,
    consumed_fields: frozenset[str],
    snapshot_bindings: Mapping[str, tuple[str, frozenset[str]]],
    qualified_selection_sources: frozenset[str] = frozenset(),
) -> SnapshotReadinessReport:
    """
    Ignore unrelated inputs and refuse omitted or foreign dependencies.

    Each consumed input binds to its stage's identity and may only be served
    by that stage's declared sources, never by the other stage's list; usage
    is tracked per stage identity, so a declared source must be claimed by a
    binding of its own stage even when both stages declare the same set.
    """
    bound = tuple(
        item for item in request.fields if item.consumer_field in consumed_fields
    )
    missing = [
        missing_field(name, "CONSUMER_BINDING_MISSING")
        for name in sorted(consumed_fields - {item.consumer_field for item in bound})
    ]
    declared = dict(snapshot_bindings.values())
    referenced: dict[str, set[str]] = {}
    for item in bound:
        stage = snapshot_bindings[item.consumer_field][0]
        referenced.setdefault(stage, set()).add(item.snapshot_id)
    missing.extend(
        missing_field(snapshot_id, "SNAPSHOT_UNBOUND")
        for stage, sources in declared.items()
        if sources
        for snapshot_id in sorted(
            sources
            - referenced.get(stage, set())
            - (qualified_selection_sources if stage == "selection" else frozenset())
        )
    )
    if not bound:
        return SnapshotReadinessReport(
            False,
            tuple(missing) or (missing_field("inputs", "FIELD_EVIDENCE_MISSING"),),
        )
    report = query.assess(replace(request, fields=bound))
    assessed = tuple(
        item
        if item.snapshot_id
        in snapshot_bindings.get(item.consumer_field, ("", frozenset()))[1]
        else replace(item, reason_codes=(*item.reason_codes, "SNAPSHOT_CONFLICT"))
        for item in report.fields
    ) + tuple(missing)
    return replace(
        report,
        fields=assessed,
        ready=all(item.ready for item in assessed),
    )


def observed_fields(
    value: object, *, prefix: str, exclude: frozenset[str] = frozenset()
) -> set[str]:
    """
    List strategy-consumed input facts for one observation.

    A null on a required input is an explicitly consumed missing value, not
    an absent observation; its binding must stay.
    """
    if not is_dataclass(value) or isinstance(value, type):
        raise AppProcessError("selection observation must be a dataclass")
    return {
        f"{prefix}.{field.name}" for field in fields(value) if field.name not in exclude
    }
