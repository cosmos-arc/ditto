"""Bind server-derived consumed selection inputs to reviewed field evidence."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace

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
    snapshot_ids: frozenset[str],
) -> FieldAdmissionReport:
    """Ignore unrelated inputs and refuse omitted or foreign dependencies."""
    bound = tuple(
        item for item in request.fields if item.consumer_field in consumed_fields
    )
    missing = [
        missing_field(name, "CONSUMER_BINDING_MISSING")
        for name in sorted(consumed_fields - {item.consumer_field for item in bound})
    ]
    if not bound or not instrument_ids:
        return FieldAdmissionReport(
            False,
            "formal_research",
            tuple(missing) or (missing_field("inputs", "FIELD_EVIDENCE_MISSING"),),
        )
    report = query.assess(replace(request, fields=bound))
    assessed = tuple(
        item
        if item.snapshot_id in snapshot_ids
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
        raise TypeError("selection observation must be a dataclass")
    return {
        f"{prefix}.{field.name}"
        for field in fields(value)
        if field.name not in exclude and getattr(value, field.name) is not None
    }
