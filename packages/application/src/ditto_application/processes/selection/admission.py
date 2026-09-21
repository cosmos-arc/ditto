"""Bind server-derived consumed selection inputs to reviewed field evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from typing import Any, cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.queries.field_admission import (
    FieldAdmission,
    FieldAdmissionQuery,
    FieldAdmissionReport,
    FieldAdmissionRequest,
)


def missing_field(name: str, reason: str) -> FieldAdmission:
    """Represent an unmet input requirement alongside actual field findings."""
    return FieldAdmission(
        dataset_id="",
        field=name,
        snapshot_id="",
        consumer_field=name,
        allowed_uses=(),
        reason_codes=(reason,),
        license_record_id=None,
        certification_report_id=None,
        covered_from=None,
        covered_to=None,
        time_precision="unknown",
        evidence_uri=None,
    )


def assess_selection_fields(
    query: FieldAdmissionQuery,
    request: FieldAdmissionRequest,
    *,
    consumed_fields: frozenset[str],
    instrument_ids: tuple[int, ...],
    snapshot_bindings: Mapping[str, frozenset[str]],
) -> FieldAdmissionReport:
    """
    Ignore unrelated inputs and refuse omitted or foreign dependencies.

    Each consumed input may only be served by the snapshot sources its own
    stage declared for the saved run, never by the other stage's list; each
    declared source must in turn be claimed by a binding of its own stage.
    """
    bound = tuple(
        item for item in request.fields if item.consumer_field in consumed_fields
    )
    missing = [
        missing_field(name, "CONSUMER_BINDING_MISSING")
        for name in sorted(consumed_fields - {item.consumer_field for item in bound})
    ]
    referenced: dict[frozenset[str], set[str]] = {}
    for item in bound:
        stage = snapshot_bindings.get(item.consumer_field, frozenset())
        referenced.setdefault(stage, set()).add(item.snapshot_id)
    missing.extend(
        missing_field(snapshot_id, "SNAPSHOT_UNBOUND")
        for stage in set(snapshot_bindings.values())
        if stage
        for snapshot_id in sorted(stage - referenced.get(stage, set()))
    )
    if not bound or not instrument_ids:
        return FieldAdmissionReport(
            False,
            "formal_research",
            tuple(missing) or (missing_field("inputs", "FIELD_EVIDENCE_MISSING"),),
        )
    report = query.assess(replace(request, fields=bound))
    assessed = tuple(
        item
        if item.snapshot_id in snapshot_bindings.get(item.consumer_field, frozenset())
        else replace(
            item,
            allowed_uses=(),
            reason_codes=(*item.reason_codes, "SNAPSHOT_CONFLICT"),
        )
        for item in report.fields
    ) + tuple(missing)
    return replace(
        report,
        fields=assessed,
        allowed=all("formal_research" in item.allowed_uses for item in assessed),
    )


def observed_fields(
    value: object, *, prefix: str, exclude: frozenset[str] = frozenset()
) -> set[str]:
    """Find present dataclass input facts; never infer absent observations."""
    if not is_dataclass(value) or isinstance(value, type):
        raise AppProcessError("selection observation must be a dataclass")
    return {
        f"{prefix}.{field.name}"
        for field in fields(value)
        if field.name not in exclude and getattr(value, field.name) is not None
    }


def selection_field_payload(request: object, consumer_field: str) -> dict[str, object]:
    """
    Freeze the actual normalized values, context and whole dependency group.

    Policy weights, ranking limits and seed are not data facts. Unconsumed input
    fields do not enter this field's identity. Certification tools retain these
    payloads in the reviewed consumer artifact; HTTP clients cannot grant them.
    """
    value = cast(dict[str, Any], orjson.loads(orjson.dumps(request)))
    parts = consumer_field.split(".", 2)
    observed: object = value.get(consumer_field)
    if parts[0] in {"instruments", "industries"}:
        key = "instrument_id" if parts[0] == "instruments" else "industry_id"
        rows: list[tuple[object, object]] = []
        for item in value[parts[0]]:
            fact = item.get(parts[1])
            if parts[1] == "factor_values":
                fact = next(
                    (
                        factor["value"]
                        for factor in item["factor_values"]
                        if factor["name"] == parts[2]
                    ),
                    None,
                )
            if isinstance(fact, (int, float)) and not isinstance(fact, bool):
                fact = float(fact)
            rows.append((item[key], fact))
        observed = sorted(rows, key=lambda pair: str(pair[0]))
    return {
        "consumer_field": consumer_field,
        "observed": observed,
        "context": {
            key: value[key]
            for key in (
                "as_of",
                "knowledge_cutoff",
                "publication_cutoff",
                "data_from",
                "data_to",
                "universe_snapshot_id",
                "membership_version",
                "market_context_feature_set_id",
            )
        },
        "dependencies": sorted(
            (item["dataset_id"], item["field"], item["snapshot_id"])
            for item in value["data_fields"]
            if item["consumer_field"] == consumer_field
        ),
    }
