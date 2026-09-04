from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments._preflight_authority_identity import (
    HoldoutConsumptionAuthority,
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments._preflight_authority_identity import (
    canonical_string as _string,
)
from ditto_analysis.experiments._preflight_authority_identity import (
    invalid_preflight_authority as _invalid,
)
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import DateWindow, canonical_payload

__all__ = [
    "PREFLIGHT_HARD_GATE_RULE_IDS",
    "DecodedPreflightAuthority",
    "HoldoutConsumptionAuthority",
    "PreflightCheckAuthority",
    "PreflightFoldAuthority",
    "canonical_research_cycle_hash",
    "decode_preflight_authority",
]

PREFLIGHT_HARD_GATE_RULE_IDS = (
    "matrix",
    "executor",
    "authority",
    "history",
    "certification",
    "budget",
)

_DETAIL_KEYS = {"plan_hash", "plan_preimage", "preflight", "preflight_hash"}
_MUTATION_RECEIPT_KEY = "mutation_idempotency"
_MUTATION_RECEIPT_KEYS = {
    "schema_version",
    "kind",
    "operation_id",
    "resource_id",
    "key_hash",
    "request_hash",
    "response",
    "receipt_hash",
}
_MUTATION_RECEIPT_KIND = "ditto_mutation_receipt"
_MUTATION_OPERATION_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PREFLIGHT_KEYS = {
    "schema_version",
    "policy_version",
    "status",
    "checks",
    "counts",
    "validation",
    "work",
    "executor",
    "authority",
    "identities",
}
_PLAN_PREIMAGE_KEYS_V1 = {
    "schema_version",
    "launch_spec_hash",
    "gate_payload_hashes",
    "fold_payload_hashes",
    "research_cycle_id",
    "research_cycle_hash",
    "request_hash",
    "snapshot_evidence",
    "dataset_requirements",
    "validation",
    "validation_authority",
    "work_plan_hash",
    "node_registry_manifest_hash",
    "factor_registry_manifest_hash",
    "factor_binding_hashes",
    "baseline_ref",
    "baseline_descriptor_hash",
    "baseline_registry_manifest_hash",
    "baseline_exact_strategy_hash",
    "baseline_runtime",
    "executor_candidates",
    "certification",
    "preflight_hash",
}
_PLAN_PREIMAGE_KEYS_V2 = _PLAN_PREIMAGE_KEYS_V1 | {"context_input_refs"}
_IDENTITY_KEYS = {
    "request_hash",
    "research_cycle_id",
    "research_cycle_hash",
    "strategy_id",
    "strategy_version",
    "snapshot_identity",
    "dataset_requirements",
    "certification",
}
_CERTIFICATION_KEYS = {
    "ready",
    "profile",
    "required_from",
    "required_to",
    "dataset_ids",
    "report_ids",
    "reason_codes",
    "snapshot_evidence",
}
_SNAPSHOT_KEYS = {
    "snapshot_id",
    "dataset_id",
    "manifest_hash",
    "source_snapshot_ids",
    "snapshot_start",
    "snapshot_end",
    "known_at_policy",
    "builder_version",
}
_VALIDATION_KEYS = {"protocol", "plan", "fold_protocol"}
_VALIDATION_PLAN_KEYS = {
    "eligibility",
    "reason_codes",
    "coverage_policy",
    "calendar_complete_month_count",
    "eligible_months",
    "isolation_width_sessions",
    "folds",
    "reserved_holdout",
}
_HOLDOUT_KEYS = {
    "train_window",
    "test_window",
    "purge_sessions",
    "embargo_sessions",
}
_FOLD_KEYS = _HOLDOUT_KEYS | {"ordinal", "role"}
_CHECK_KEYS = {
    "rule_id",
    "outcome",
    "code",
    "reason",
    "remediation",
    "observed",
    "policy",
}


def _mapping(
    value: object, name: str, keys: set[str] | None = None
) -> dict[str, object]:
    if type(value) is not dict:
        raise _invalid(f"{name} must be an object")
    result = cast("dict[str, object]", value)
    if keys is not None and set(result) != keys:
        raise _invalid(f"{name} has an invalid shape")
    return result


def _list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise _invalid(f"{name} must be an array")
    return cast("list[object]", value)


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise _invalid(f"{name} must be an integer")
    return value


def _optional_string(value: object, name: str) -> str | None:
    return None if value is None else _string(value, name)


def _hash(value: object, name: str) -> ContentHash:
    try:
        return ContentHash(_string(value, name))
    except Exception as exc:
        raise _invalid(f"{name} must be a canonical content hash") from exc


def _date(value: object, name: str) -> date:
    try:
        return date.fromisoformat(_string(value, name))
    except ValueError as exc:
        raise _invalid(f"{name} must be an ISO date") from exc


def _window(value: object, name: str) -> DateWindow:
    payload = _mapping(value, name, {"start", "end"})
    try:
        return DateWindow(
            _date(payload.get("start"), f"{name}.start"),
            _date(payload.get("end"), f"{name}.end"),
        )
    except Exception as exc:
        raise _invalid(f"{name} is invalid") from exc


def _same(left: object, right: object) -> bool:
    try:
        return (
            canonical_payload({"value": left}).json_bytes
            == canonical_payload({"value": right}).json_bytes
        )
    except Exception as exc:
        raise _invalid("preflight cross-link is not canonical JSON") from exc


def _hashes(
    value: object, name: str, *, allow_empty: bool = False
) -> tuple[ContentHash, ...]:
    values = _list(value, name)
    if not values and not allow_empty:
        raise _invalid(f"{name} must not be empty")
    return tuple(_hash(item, f"{name}[]") for item in values)


def _detail_root(
    detail: Mapping[str, object],
) -> tuple[dict[str, object], ContentHash]:
    full = _mapping(cast("object", detail), "detail")
    keys = set(full)
    if keys == _DETAIL_KEYS:
        return full, canonical_payload(full).content_hash
    if keys != _DETAIL_KEYS | {_MUTATION_RECEIPT_KEY}:
        raise _invalid("detail has an invalid shape")

    receipt = _mapping(
        full.get(_MUTATION_RECEIPT_KEY),
        "detail.mutation_idempotency",
        _MUTATION_RECEIPT_KEYS,
    )
    body = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    operation_id = _string(
        receipt.get("operation_id"),
        "detail.mutation_idempotency.operation_id",
    )
    if (
        _integer(
            receipt.get("schema_version"),
            "detail.mutation_idempotency.schema_version",
        )
        != 1
        or receipt.get("kind") != _MUTATION_RECEIPT_KIND
        or _MUTATION_OPERATION_PATTERN.fullmatch(operation_id) is None
    ):
        raise _invalid("detail mutation receipt identity is invalid")
    _string(
        receipt.get("resource_id"),
        "detail.mutation_idempotency.resource_id",
    )
    _hash(receipt.get("key_hash"), "detail.mutation_idempotency.key_hash")
    _hash(receipt.get("request_hash"), "detail.mutation_idempotency.request_hash")
    _mapping(receipt.get("response"), "detail.mutation_idempotency.response")
    if (
        _hash(
            receipt.get("receipt_hash"),
            "detail.mutation_idempotency.receipt_hash",
        )
        != canonical_payload(body).content_hash
    ):
        raise _invalid("detail mutation receipt hash does not match its payload")

    root = {key: full[key] for key in _DETAIL_KEYS}
    return root, canonical_payload(full).content_hash


@dataclass(frozen=True, slots=True)
class PreflightCheckAuthority:
    """Canonical check fields that must match one immutable hard-gate row."""

    rule_id: str
    outcome: str
    code: str | None
    reason: str | None
    remediation: str | None
    observed_json: str
    policy_json: str


@dataclass(frozen=True, slots=True)
class PreflightFoldAuthority:
    """One validation-plan fold projected into every persisted candidate row."""

    ordinal: int
    role: str
    train_window: DateWindow | None
    test_window: DateWindow
    purge_sessions: int
    embargo_sessions: int


@dataclass(frozen=True, slots=True)
class DecodedPreflightAuthority:
    """Canonical fields needed by both planning reconstruction and holdout storage."""

    detail_hash: ContentHash
    status: str
    policy_version: str
    plan_hash: ContentHash
    preflight_hash: ContentHash
    launch_spec_hash: ContentHash
    gate_checks: tuple[PreflightCheckAuthority, ...]
    gate_payload_hashes: tuple[ContentHash, ...]
    fold_payload_hashes: tuple[ContentHash, ...]
    fold_authorities: tuple[PreflightFoldAuthority, ...]
    research_cycle_id: str
    research_cycle_hash: ContentHash
    strategy_family_id: str
    strategy_version: int
    snapshot_id: str
    snapshot_manifest_hash: ContentHash
    certification_required_to: date
    consumption: HoldoutConsumptionAuthority
    holdout_train_window: DateWindow
    holdout_purge_sessions: int
    holdout_embargo_sessions: int
    fold_protocol_id: str
    fold_protocol_version: int
    fold_protocol_hash: ContentHash


@dataclass(frozen=True, slots=True)
class _IdentityLinks:
    identities: Mapping[str, object]
    certification: Mapping[str, object]
    snapshot: Mapping[str, object]
    strategy_family_id: str
    strategy_version: int
    research_cycle_hash: ContentHash


@dataclass(frozen=True, slots=True)
class _ConsumptionLinks:
    validation: Mapping[str, object]
    consumption: HoldoutConsumptionAuthority
    certification_required_to: date
    holdout_train_window: DateWindow
    holdout_purge_sessions: int
    holdout_embargo_sessions: int
    fold_authorities: tuple[PreflightFoldAuthority, ...]


@dataclass(frozen=True, slots=True)
class _ProtocolLinks:
    gate_payload_hashes: tuple[ContentHash, ...]
    fold_payload_hashes: tuple[ContentHash, ...]
    protocol_id: str
    protocol_version: int
    protocol_hash: ContentHash


def _check_authority(value: object) -> PreflightCheckAuthority:
    check = _mapping(value, "preflight.check", _CHECK_KEYS)
    outcome = _string(check.get("outcome"), "preflight.check.outcome")
    if outcome not in {"pass", "warn", "fail"}:
        raise _invalid("preflight check outcome is invalid")
    code = _optional_string(check.get("code"), "preflight.check.code")
    reason = _optional_string(check.get("reason"), "preflight.check.reason")
    remediation = _optional_string(
        check.get("remediation"), "preflight.check.remediation"
    )
    if outcome == "pass" and any(
        value is not None for value in (code, reason, remediation)
    ):
        raise _invalid("passing preflight check carries failure explanation")
    observed = _mapping(check.get("observed"), "preflight.check.observed")
    policy = _mapping(check.get("policy"), "preflight.check.policy")
    return PreflightCheckAuthority(
        rule_id=_string(check.get("rule_id"), "preflight.check.rule_id"),
        outcome=outcome,
        code=code,
        reason=reason,
        remediation=remediation,
        observed_json=canonical_payload(observed).json_bytes.decode("utf-8"),
        policy_json=canonical_payload(policy).json_bytes.decode("utf-8"),
    )


def _fold_authority(value: object, name: str) -> PreflightFoldAuthority:
    fold = _mapping(value, name, _FOLD_KEYS)
    ordinal = _integer(fold.get("ordinal"), f"{name}.ordinal")
    role = _string(fold.get("role"), f"{name}.role")
    train_value = fold.get("train_window")
    train_window = (
        None if train_value is None else _window(train_value, f"{name}.train_window")
    )
    purge_sessions = _integer(fold.get("purge_sessions"), f"{name}.purge_sessions")
    embargo_sessions = _integer(
        fold.get("embargo_sessions"), f"{name}.embargo_sessions"
    )
    if (
        ordinal <= 0
        or role not in {"exploration", "walk_forward"}
        or (role == "exploration") != (train_window is None)
        or purge_sessions < 0
        or embargo_sessions < 0
    ):
        raise _invalid(f"{name} has invalid fold semantics")
    return PreflightFoldAuthority(
        ordinal=ordinal,
        role=role,
        train_window=train_window,
        test_window=_window(fold.get("test_window"), f"{name}.test_window"),
        purge_sessions=purge_sessions,
        embargo_sessions=embargo_sessions,
    )


def _fold_authorities(
    validation_plan: Mapping[str, object],
    holdout: Mapping[str, object],
) -> tuple[PreflightFoldAuthority, ...]:
    regular = tuple(
        _fold_authority(item, "validation.plan.fold")
        for item in _list(validation_plan.get("folds"), "validation.plan.folds")
    )
    if (
        not regular
        or tuple(item.ordinal for item in regular) != tuple(range(1, len(regular) + 1))
        or regular[0].role != "exploration"
        or any(item.role != "walk_forward" for item in regular[1:])
    ):
        raise _invalid("validation plan folds are incomplete or out of order")
    purge_sessions = _integer(
        holdout.get("purge_sessions"), "reserved_holdout.purge_sessions"
    )
    embargo_sessions = _integer(
        holdout.get("embargo_sessions"), "reserved_holdout.embargo_sessions"
    )
    if purge_sessions < 0 or embargo_sessions < 0:
        raise _invalid("reserved holdout isolation is invalid")
    return (
        *regular,
        PreflightFoldAuthority(
            ordinal=len(regular) + 1,
            role="holdout",
            train_window=_window(
                holdout.get("train_window"), "reserved_holdout.train_window"
            ),
            test_window=_window(
                holdout.get("test_window"), "reserved_holdout.test_window"
            ),
            purge_sessions=purge_sessions,
            embargo_sessions=embargo_sessions,
        ),
    )


def _verify_plan_links(
    plan: Mapping[str, object],
    preflight: Mapping[str, object],
) -> None:
    validation = _mapping(preflight.get("validation"), "validation", _VALIDATION_KEYS)
    work = _mapping(preflight.get("work"), "work")
    executor = _mapping(preflight.get("executor"), "executor")
    authority = _mapping(preflight.get("authority"), "authority")
    identities = _mapping(preflight.get("identities"), "identities", _IDENTITY_KEYS)
    certification = _mapping(
        identities.get("certification"), "identities.certification", _CERTIFICATION_KEYS
    )
    checks = _list(preflight.get("checks"), "preflight.checks")
    counts = _mapping(preflight.get("counts"), "preflight.counts")
    authority_preimage = _mapping(
        plan.get("validation_authority"), "plan_preimage.validation_authority"
    )
    expected_authority = {
        key: authority.get(key)
        for key in (
            "payload_hash",
            "runtime_evidence_hash",
            "universe_membership_hash",
            "membership_projection_hash",
            "requires_pit_universe",
            "dataset_bindings",
        )
    }
    expected_certification = {
        key: certification.get(key)
        for key in (
            "profile",
            "required_from",
            "required_to",
            "report_ids",
            "reason_codes",
        )
    }
    if not (
        plan.get("research_cycle_id") == identities.get("research_cycle_id")
        and plan.get("research_cycle_hash") == identities.get("research_cycle_hash")
        and plan.get("request_hash") == identities.get("request_hash")
        and _same(plan.get("snapshot_evidence"), certification.get("snapshot_evidence"))
        and _same(
            plan.get("dataset_requirements"), identities.get("dataset_requirements")
        )
        and _same(plan.get("validation"), validation.get("plan"))
        and _same(authority_preimage, expected_authority)
        and plan.get("work_plan_hash") == work.get("plan_hash")
        and plan.get("node_registry_manifest_hash")
        == executor.get("node_registry_manifest_hash")
        and plan.get("factor_registry_manifest_hash")
        == executor.get("factor_registry_manifest_hash")
        and _same(
            plan.get("factor_binding_hashes"), executor.get("factor_binding_hashes")
        )
        and plan.get("baseline_ref") == executor.get("baseline_ref")
        and plan.get("baseline_descriptor_hash")
        == executor.get("baseline_descriptor_hash")
        and plan.get("baseline_registry_manifest_hash")
        == executor.get("baseline_registry_manifest_hash")
        and plan.get("baseline_exact_strategy_hash")
        == executor.get("baseline_exact_strategy_hash")
        and _same(plan.get("baseline_runtime"), executor.get("baseline_runtime"))
        and _same(plan.get("executor_candidates"), executor.get("candidates"))
        and _same(plan.get("certification"), expected_certification)
        and len(_list(plan.get("gate_payload_hashes"), "plan gate hashes"))
        == len(checks)
        and len(_list(plan.get("fold_payload_hashes"), "plan fold hashes"))
        == _integer(counts.get("planned_fold_count"), "counts.planned_fold_count")
    ):
        raise _invalid("plan preimage does not match preflight")


def _identity_links(preflight: Mapping[str, object]) -> _IdentityLinks:
    identities = _mapping(preflight.get("identities"), "identities", _IDENTITY_KEYS)
    certification = _mapping(
        identities.get("certification"), "certification", _CERTIFICATION_KEYS
    )
    snapshot = _mapping(
        certification.get("snapshot_evidence"), "snapshot_evidence", _SNAPSHOT_KEYS
    )
    identity_snapshot = _mapping(
        identities.get("snapshot_identity"),
        "identities.snapshot_identity",
        {"snapshot_id", "manifest_hash"},
    )
    authority = _mapping(preflight.get("authority"), "authority")
    authority_snapshot = _mapping(
        authority.get("snapshot_identity"),
        "authority.snapshot_identity",
        {"snapshot_id", "manifest_hash"},
    )
    if not (
        _same(identity_snapshot, authority_snapshot)
        and snapshot.get("snapshot_id") == identity_snapshot.get("snapshot_id")
        and snapshot.get("manifest_hash") == identity_snapshot.get("manifest_hash")
    ):
        raise _invalid("snapshot identities do not cross-link")
    return _IdentityLinks(
        identities=identities,
        certification=certification,
        snapshot=snapshot,
        strategy_family_id=_string(
            identities.get("strategy_id"), "identities.strategy_id"
        ),
        strategy_version=_integer(
            identities.get("strategy_version"), "identities.strategy_version"
        ),
        research_cycle_hash=_hash(
            identities.get("research_cycle_hash"), "research_cycle_hash"
        ),
    )


def _consumption_links(
    preflight: Mapping[str, object],
    identity: _IdentityLinks,
    *,
    require_canonical_cycle_hash: bool,
) -> _ConsumptionLinks:
    validation = _mapping(preflight.get("validation"), "validation", _VALIDATION_KEYS)
    validation_plan = _mapping(
        validation.get("plan"), "validation.plan", _VALIDATION_PLAN_KEYS
    )
    holdout = _mapping(
        validation_plan.get("reserved_holdout"),
        "validation.plan.reserved_holdout",
        _HOLDOUT_KEYS,
    )
    fold_authorities = _fold_authorities(validation_plan, holdout)
    holdout_train = _window(
        holdout.get("train_window"), "reserved_holdout.train_window"
    )
    oos_window = _window(holdout.get("test_window"), "reserved_holdout.test_window")
    required_to = _date(
        identity.certification.get("required_to"), "certification.required_to"
    )
    cutoff = _date(
        identity.snapshot.get("snapshot_end"), "snapshot_evidence.snapshot_end"
    )
    if required_to != oos_window.end or cutoff < required_to:
        raise _invalid("certification cutoff does not cover the reserved holdout")
    consumption = HoldoutConsumptionAuthority(
        identity.strategy_family_id,
        cutoff,
        oos_window,
    )
    if (
        require_canonical_cycle_hash
        and identity.research_cycle_hash != consumption.content_hash
    ):
        raise _invalid("research cycle hash is not derived from durable authority")
    return _ConsumptionLinks(
        validation=validation,
        consumption=consumption,
        certification_required_to=required_to,
        holdout_train_window=holdout_train,
        holdout_purge_sessions=_integer(
            holdout.get("purge_sessions"), "reserved_holdout.purge_sessions"
        ),
        holdout_embargo_sessions=_integer(
            holdout.get("embargo_sessions"), "reserved_holdout.embargo_sessions"
        ),
        fold_authorities=fold_authorities,
    )


def _protocol_links(
    validation: Mapping[str, object],
    plan: Mapping[str, object],
) -> _ProtocolLinks:
    validation_plan = _mapping(
        validation.get("plan"), "validation.plan", _VALIDATION_PLAN_KEYS
    )
    fold_protocol = _mapping(
        validation.get("fold_protocol"),
        "validation.fold_protocol",
        {"protocol_id", "protocol_version", "protocol_hash"},
    )
    protocol_hash = _hash(fold_protocol.get("protocol_hash"), "protocol_hash")
    if protocol_hash != canonical_payload(validation_plan).content_hash:
        raise _invalid("fold protocol hash does not match validation plan")
    return _ProtocolLinks(
        gate_payload_hashes=_hashes(
            plan.get("gate_payload_hashes"),
            "plan_preimage.gate_payload_hashes",
            allow_empty=True,
        ),
        fold_payload_hashes=_hashes(
            plan.get("fold_payload_hashes"), "plan_preimage.fold_payload_hashes"
        ),
        protocol_id=_string(fold_protocol.get("protocol_id"), "protocol_id"),
        protocol_version=_integer(
            fold_protocol.get("protocol_version"), "protocol_version"
        ),
        protocol_hash=protocol_hash,
    )


def _validate_status_semantics(
    status: str,
    validation: Mapping[str, object],
    certification: Mapping[str, object],
    checks: tuple[PreflightCheckAuthority, ...],
) -> None:
    plan = _mapping(validation.get("plan"), "validation.plan", _VALIDATION_PLAN_KEYS)
    eligibility = _string(plan.get("eligibility"), "validation.plan.eligibility")
    expected_status = {
        "promotion_eligible": "ready",
        "research_only": "research_only",
    }.get(eligibility)
    if expected_status != status:
        raise _invalid("preflight status does not match validation eligibility")
    if certification.get("ready") is not True:
        raise _invalid("launchable preflight lacks ready certification")
    if tuple(check.rule_id for check in checks) != PREFLIGHT_HARD_GATE_RULE_IDS:
        raise _invalid("preflight hard gates are incomplete or out of order")
    if any(check.outcome == "fail" for check in checks):
        raise _invalid("launchable preflight contains a failed hard gate")
    if status == "ready" and any(check.outcome != "pass" for check in checks):
        raise _invalid("ready preflight contains a non-passing hard gate")


def _validate_certification_check_preimage(
    identity: _IdentityLinks,
    checks: tuple[PreflightCheckAuthority, ...],
) -> None:
    matches = tuple(check for check in checks if check.rule_id == "certification")
    if len(matches) != 1 or matches[0].outcome != "pass":
        raise _invalid("certification hard gate is missing or non-passing")
    certification = identity.certification
    expected_observed = {
        "ready": certification.get("ready"),
        "profile": certification.get("profile"),
        "dataset_ids": certification.get("dataset_ids"),
        "report_ids": certification.get("report_ids"),
        "reason_codes": certification.get("reason_codes"),
        "snapshot_evidence": certification.get("snapshot_evidence"),
        "snapshot_evidence_valid": True,
    }
    expected_policy = {
        "profile": certification.get("profile"),
        "required_from": certification.get("required_from"),
        "required_to": certification.get("required_to"),
        "requirements": identity.identities.get("dataset_requirements"),
        "snapshot_identity": identity.identities.get("snapshot_identity"),
    }
    check = matches[0]
    if check.observed_json != canonical_payload(expected_observed).json_bytes.decode(
        "utf-8"
    ) or check.policy_json != canonical_payload(expected_policy).json_bytes.decode(
        "utf-8"
    ):
        raise _invalid("certification hard gate does not match authority evidence")


def decode_preflight_authority(
    detail: Mapping[str, object],
    *,
    require_canonical_cycle_hash: bool = True,
) -> DecodedPreflightAuthority:
    """Decode hashes, exact shapes, and authority cross-links without app imports."""
    try:
        root, detail_hash = _detail_root(detail)
        preflight = _mapping(root.get("preflight"), "preflight", _PREFLIGHT_KEYS)
        plan = _mapping(root.get("plan_preimage"), "plan_preimage")
        plan_schema_version = _integer(
            plan.get("schema_version"), "plan_preimage.schema_version"
        )
        expected_plan_keys = (
            _PLAN_PREIMAGE_KEYS_V1
            if plan_schema_version == 1
            else _PLAN_PREIMAGE_KEYS_V2
        )
        if plan_schema_version not in {1, 2} or set(plan) != expected_plan_keys:
            raise _invalid("plan_preimage has an invalid shape")
        plan_hash = _hash(root.get("plan_hash"), "detail.plan_hash")
        preflight_hash = _hash(root.get("preflight_hash"), "detail.preflight_hash")
        if canonical_payload(preflight).content_hash != preflight_hash:
            raise _invalid("preflight hash does not match its payload")
        if canonical_payload(plan).content_hash != plan_hash:
            raise _invalid("plan hash does not match its payload")
        if (
            _integer(preflight.get("schema_version"), "preflight.schema_version") != 1
            or plan_schema_version not in {1, 2}
            or _hash(plan.get("preflight_hash"), "plan_preimage.preflight_hash")
            != preflight_hash
        ):
            raise _invalid("preflight schema or plan link is invalid")
        status = _string(preflight.get("status"), "preflight.status")
        if status not in {"ready", "research_only"}:
            raise _invalid("preflight status is invalid")
        checks = _list(preflight.get("checks"), "preflight.checks")
        checked = tuple(_check_authority(item) for item in checks)
        _verify_plan_links(plan, preflight)

        identity = _identity_links(preflight)
        consumption = _consumption_links(
            preflight,
            identity,
            require_canonical_cycle_hash=require_canonical_cycle_hash,
        )
        _validate_status_semantics(
            status,
            consumption.validation,
            identity.certification,
            checked,
        )
        _validate_certification_check_preimage(identity, checked)
        protocol = _protocol_links(consumption.validation, plan)
        return DecodedPreflightAuthority(
            detail_hash=detail_hash,
            status=status,
            policy_version=_string(preflight.get("policy_version"), "policy_version"),
            plan_hash=plan_hash,
            preflight_hash=preflight_hash,
            launch_spec_hash=_hash(plan.get("launch_spec_hash"), "launch_spec_hash"),
            gate_checks=checked,
            gate_payload_hashes=protocol.gate_payload_hashes,
            fold_payload_hashes=protocol.fold_payload_hashes,
            fold_authorities=consumption.fold_authorities,
            research_cycle_id=_string(
                identity.identities.get("research_cycle_id"), "research_cycle_id"
            ),
            research_cycle_hash=identity.research_cycle_hash,
            strategy_family_id=identity.strategy_family_id,
            strategy_version=identity.strategy_version,
            snapshot_id=_string(identity.snapshot.get("snapshot_id"), "snapshot_id"),
            snapshot_manifest_hash=_hash(
                identity.snapshot.get("manifest_hash"), "manifest_hash"
            ),
            certification_required_to=consumption.certification_required_to,
            consumption=consumption.consumption,
            holdout_train_window=consumption.holdout_train_window,
            holdout_purge_sessions=consumption.holdout_purge_sessions,
            holdout_embargo_sessions=consumption.holdout_embargo_sessions,
            fold_protocol_id=protocol.protocol_id,
            fold_protocol_version=protocol.protocol_version,
            fold_protocol_hash=protocol.protocol_hash,
        )
    except ExperimentIntegrityError:
        raise
    except Exception as exc:
        raise _invalid("preflight authority cannot be reconstructed") from exc
