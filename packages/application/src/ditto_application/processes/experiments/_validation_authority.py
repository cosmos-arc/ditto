"""Fail-closed validation-authority assessment for experiment planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ditto_application.processes.experiments._planning_evidence import canonical_text
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
    PreflightOutcome,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityProbe,
    ResearchValidationAuthorityRequest,
    ResearchValidationAuthorityResult,
    RuntimeValidationEvidence,
    validation_authority_facts_match,
)
from ditto_application.research_validation_protocol import (
    ValidationProtocolPlan,
    canonical_validation_protocol_hash,
    compile_validation_protocol,
)

__all__ = ["ValidationAuthorityAssessment", "assess_validation_authority"]


@dataclass(frozen=True, slots=True)
class ValidationAuthorityAssessment:
    """Validated authority result and its compiled protocol, if usable."""

    check: ExperimentPreflightCheck
    evidence: ResearchValidationAuthorityEvidence | None
    validation: ValidationProtocolPlan | None


@dataclass(frozen=True, slots=True)
class _ValidatedRequestIdentity:
    """One exact request fingerprint computed around the probe call."""

    fingerprint: str
    declared_protocol_hash: str


def _check(
    outcome: PreflightOutcome,
    *,
    code: str | None,
    reason: str | None,
    remediation: str | None,
    observed: Mapping[str, object],
) -> ExperimentPreflightCheck:
    return ExperimentPreflightCheck(
        "authority",
        outcome,
        code,
        reason,
        remediation,
        observed,
        {
            "authority_protocol_required": True,
            "runtime_evidence_binding_required": True,
            "caller_assertion_must_match_exactly": True,
        },
    )


def _invalid_assessment(reason: str) -> ValidationAuthorityAssessment:
    return ValidationAuthorityAssessment(
        _check(
            PreflightOutcome.FAIL,
            code="VALIDATION_AUTHORITY_INVALID",
            reason=reason,
            remediation="return one typed, content-addressed authority result",
            observed={"ready": False, "authority_payload_hash": None},
        ),
        None,
        None,
    )


def _probe_result(
    probe: ResearchValidationAuthorityProbe,
    request: ResearchValidationAuthorityRequest,
) -> ResearchValidationAuthorityResult | None:
    try:
        raw_result = cast("object", probe.probe(request))
        if (
            type(raw_result) is not ResearchValidationAuthorityResult
            or type(raw_result.ready) is not bool
        ):
            return None
    except Exception:  # Authority is an untrusted fail-closed boundary.
        return None
    return raw_result


def _blocked_assessment(
    result: ResearchValidationAuthorityResult,
) -> ValidationAuthorityAssessment:
    if (
        not canonical_text(result.code)
        or not canonical_text(result.reason)
        or not canonical_text(result.remediation)
        or result.evidence is not None
    ):
        return _invalid_assessment("invalid_validation_authority_blocker")
    return ValidationAuthorityAssessment(
        _check(
            PreflightOutcome.FAIL,
            code=result.code,
            reason=result.reason,
            remediation=result.remediation,
            observed={"ready": False, "authority_payload_hash": None},
        ),
        None,
        None,
    )


def _validated_request_identity(
    request: ResearchValidationAuthorityRequest,
) -> _ValidatedRequestIdentity | None:
    try:
        if (
            type(request) is not ResearchValidationAuthorityRequest
            or not request.is_valid()
        ):
            return None
        compile_validation_protocol(request.declared_protocol)
        protocol_hash = canonical_validation_protocol_hash(request.declared_protocol)
        return _ValidatedRequestIdentity(
            request.fingerprint(declared_protocol_hash=protocol_hash),
            protocol_hash,
        )
    except Exception:
        return None


def _compile_authoritative_protocol(
    evidence: ResearchValidationAuthorityEvidence,
) -> tuple[ValidationProtocolPlan, str] | None:
    try:
        validation = compile_validation_protocol(evidence.protocol)
        return validation, canonical_validation_protocol_hash(evidence.protocol)
    except Exception:  # Malformed authority protocols fail closed at this boundary.
        return None


def _compiled_authority_summaries(
    evidence: ResearchValidationAuthorityEvidence,
    validation: ValidationProtocolPlan,
) -> Mapping[str, Mapping[str, object]] | None:
    """Bind persisted eligibility counts to the compiler's continuous suffix."""
    raw_summaries = cast("object", evidence.summaries)
    if not isinstance(raw_summaries, Mapping):
        return None
    summaries = cast("Mapping[object, object]", raw_summaries)
    raw_eligibility = summaries.get("eligibility")
    if not isinstance(raw_eligibility, Mapping):
        return None
    typed: dict[str, Mapping[str, object]] = {}
    for key in ("calendar", "membership", "eligibility", "policy", "semantics"):
        raw_section = summaries.get(key)
        if not isinstance(raw_section, Mapping):
            return None
        typed[key] = dict(cast("Mapping[str, object]", raw_section))
    typed["eligibility"] = {
        **typed["eligibility"],
        "eligible_month_count": len(validation.eligible_months),
    }
    return typed


def assess_validation_authority(  # noqa: C901, PLR0911 - fail-closed authority fence
    probe: ResearchValidationAuthorityProbe,
    request: ResearchValidationAuthorityRequest,
) -> ValidationAuthorityAssessment:
    """Validate, bind, compare, and compile only authority-owned protocol facts."""
    initial_identity = _validated_request_identity(request)
    if initial_identity is None:
        return _invalid_assessment("invalid_validation_authority_request")
    result = _probe_result(probe, request)
    returned_identity = _validated_request_identity(request)
    if (
        returned_identity is None
        or returned_identity.fingerprint != initial_identity.fingerprint
    ):
        return _invalid_assessment("validation_authority_request_mutated")
    if result is None:
        return _invalid_assessment("invalid_validation_authority_result")
    if not result.ready:
        try:
            return _blocked_assessment(result)
        except Exception:
            return _invalid_assessment("invalid_validation_authority_blocker")
    try:
        evidence = result.evidence
        runtime = request.runtime_validation
        if (
            result.code is not None
            or result.reason is not None
            or result.remediation is not None
            or type(evidence) is not ResearchValidationAuthorityEvidence
            or not evidence.is_valid()
            or type(runtime) is not RuntimeValidationEvidence
            or not runtime.is_valid()
            or evidence.runtime_evidence_hash != runtime.payload_hash
        ):
            return _invalid_assessment("invalid_validation_authority_evidence")

        # Compilation validates the entire protocol graph before any summary property
        # is read from authority-owned evidence.
        compiled_authority = _compile_authoritative_protocol(evidence)
        if compiled_authority is None:
            return _invalid_assessment("authoritative_protocol_compile_failed")
        validation, authority_protocol_hash = compiled_authority
        summaries = _compiled_authority_summaries(evidence, validation)
        if summaries is None:
            return _invalid_assessment("invalid_validation_authority_summaries")

        observed = {
            "ready": True,
            "authority_payload_hash": evidence.payload_hash,
            "runtime_evidence_hash": evidence.runtime_evidence_hash,
            "authority_protocol_hash": authority_protocol_hash,
            "declared_protocol_hash": initial_identity.declared_protocol_hash,
            "summaries": summaries,
        }
        facts_match = validation_authority_facts_match(
            evidence,
            runtime,
            snapshot_identity=request.snapshot_identity,
            dataset_requirements=request.declared_requirements,
        )
        if (
            not facts_match
            or authority_protocol_hash != initial_identity.declared_protocol_hash
        ):
            return ValidationAuthorityAssessment(
                _check(
                    PreflightOutcome.FAIL,
                    code="VALIDATION_AUTHORITY_MISMATCH",
                    reason="caller_or_authority_fact_assertion_drifted",
                    remediation=(
                        "submit the exact authority protocol, snapshot, per-dataset "
                        "bindings, PIT requirements, and isolation semantics"
                    ),
                    observed=observed,
                ),
                None,
                None,
            )
        return ValidationAuthorityAssessment(
            _check(
                PreflightOutcome.PASS,
                code=None,
                reason=None,
                remediation=None,
                observed=observed,
            ),
            evidence,
            validation,
        )
    except Exception:  # Every malformed property/hash access fails closed.
        return _invalid_assessment("invalid_validation_authority_evidence")
