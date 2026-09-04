from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.approval_codec import (
    MAX_CONTINUATION_BYTES,
    InterruptionBinding,
    ModelRequestIdentity,
    ResumeEnvelope,
    decode_action_payload,
    decode_envelope,
    reject_sensitive_keys,
)
from ditto_agent.approval_errors import ApprovalRuntimeViolation
from ditto_agent.contracts.approval import ActionBudget, ApprovalAction, ApprovalRequest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelContinuation, ModelRequest

NOW = datetime(2026, 8, 16, 8, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


def _request() -> ModelRequest:
    return ModelRequest(
        run_id="run-codec",
        agent_name="approval-codec-test",
        instructions="Return only the governed result.",
        input_text="Resume the exact interrupted action.",
        max_turns=4,
        max_output_tokens=256,
        tools=(),
    )


def _envelope_payload() -> dict[str, object]:
    request = _request()
    envelope = ResumeEnvelope(
        run_id=request.run_id,
        request_identity=ModelRequestIdentity.from_request(request),
        continuation=ModelContinuation(
            provider="scripted",
            payload={"cursor": "provider-state", "positions": [1, 2]},
        ),
        interruptions=(
            InterruptionBinding(
                call_id="call-1",
                tool_name="author_save_strategy_draft",
                arguments_hash=HASH_A,
                request_id="approval-1",
                action_hash=HASH_B,
            ),
        ),
    )
    decoded = orjson.loads(canonical_bytes(envelope.payload()))
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=NOW,
            knowledge_cutoff=NOW - timedelta(minutes=5),
            publication_cutoff=NOW - timedelta(minutes=10),
            source_snapshot_id="snapshot-codec",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _approval_payload() -> dict[str, object]:
    request = ApprovalRequest.issue(
        request_id="approval-1",
        run_id="run-codec",
        action=ApprovalAction(
            action_kind="formal_author_write",
            tool_name="author_save_strategy_draft",
            parameters={"strategy_id": "strategy-1", "candidate_hash": HASH_A},
            subject_identity="strategy-1",
            required_authority="strategy.author",
            authority_hash=HASH_B,
            temporal_context=_context(),
            budget=ActionBudget(
                max_tool_calls=1,
                max_output_bytes=16_384,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.20"),
            ),
            expires_at=NOW + timedelta(minutes=15),
        ),
    )
    decoded = orjson.loads(canonical_bytes(request.action_payload()))
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)


def _section(payload: dict[str, object], name: str) -> dict[str, object]:
    section = payload[name]
    assert isinstance(section, dict)
    return cast(dict[str, object], section)


def _bindings(payload: dict[str, object]) -> list[dict[str, object]]:
    values = payload["interruptions"]
    assert isinstance(values, list)
    bindings = cast(list[object], values)
    assert all(isinstance(value, dict) for value in bindings)
    return cast(list[dict[str, object]], bindings)


def _assert_envelope_violation(
    payload: object,
    match: str,
    *,
    reason_code: str = "agent_continuation_invalid",
) -> None:
    with pytest.raises(ApprovalRuntimeViolation, match=match) as exc_info:
        decode_envelope(canonical_bytes(payload))
    assert exc_info.value.reason_code == reason_code


def _assert_action_violation(
    payload: object,
    match: str,
    *,
    reason_code: str = "agent_approval_action_invalid",
) -> None:
    with pytest.raises(ApprovalRuntimeViolation, match=match) as exc_info:
        decode_action_payload(canonical_bytes(payload))
    assert exc_info.value.reason_code == reason_code


def test_codec_round_trips_the_exact_request_action_and_provider_bindings() -> None:
    envelope_payload = _envelope_payload()
    envelope = decode_envelope(canonical_bytes(envelope_payload))

    assert canonical_bytes(envelope.payload()) == canonical_bytes(envelope_payload)
    assert envelope.request_identity == ModelRequestIdentity.from_request(_request())
    assert envelope.interruptions[0].payload() == _bindings(envelope_payload)[0]

    action_payload = _approval_payload()
    approval = decode_action_payload(canonical_bytes(action_payload))

    assert canonical_bytes(approval.action_payload()) == canonical_bytes(action_payload)
    assert approval.verify_action_hash()
    assert approval.action_hash == canonical_sha256(action_payload)


def test_continuation_rejects_empty_oversized_malformed_and_noncanonical_bytes() -> (
    None
):
    for payload in (b"", b"0" * (MAX_CONTINUATION_BYTES + 1)):
        with pytest.raises(ApprovalRuntimeViolation, match="size") as exc_info:
            decode_envelope(payload)
        assert exc_info.value.reason_code == "agent_continuation_invalid"

    with pytest.raises(ApprovalRuntimeViolation, match="valid JSON") as malformed:
        decode_envelope(b"{")
    assert malformed.value.reason_code == "agent_continuation_invalid"

    valid = canonical_bytes(_envelope_payload())
    with pytest.raises(
        ApprovalRuntimeViolation, match="canonical JSON"
    ) as noncanonical:
        decode_envelope(valid + b"\n")
    assert noncanonical.value.reason_code == "agent_continuation_invalid"


def test_continuation_schema_and_provider_state_are_closed() -> None:
    _assert_envelope_violation([], "JSON object")

    payload = _envelope_payload()
    payload["schema_version"] = 2
    _assert_envelope_violation(
        payload,
        "version",
        reason_code="agent_continuation_version_unsupported",
    )

    payload = _envelope_payload()
    payload["continuation"] = []
    _assert_envelope_violation(payload, "continuation must be a JSON object")

    payload = _envelope_payload()
    _section(payload, "continuation")["payload"] = []
    _assert_envelope_violation(payload, "continuation.payload must be a JSON object")

    payload = _envelope_payload()
    _section(payload, "continuation")["provider"] = " padded "
    _assert_envelope_violation(payload, "provider must be non-empty text")


@pytest.mark.parametrize("value", [None, [], "not-a-list"])
def test_continuation_requires_at_least_one_binding(value: object) -> None:
    payload = _envelope_payload()
    payload["interruptions"] = value

    _assert_envelope_violation(payload, "at least one interruption")


def test_continuation_binding_identities_are_unique_and_authenticated() -> None:
    payload = _envelope_payload()
    payload["interruptions"] = ["invalid"]
    _assert_envelope_violation(payload, "interruption binding must be a JSON object")

    payload = _envelope_payload()
    original = _bindings(payload)[0]
    duplicate = dict(original)
    duplicate["request_id"] = "approval-2"
    payload["interruptions"] = [original, duplicate]
    _assert_envelope_violation(payload, "call IDs must be unique")

    payload = _envelope_payload()
    original = _bindings(payload)[0]
    duplicate = dict(original)
    duplicate["call_id"] = "call-2"
    payload["interruptions"] = [original, duplicate]
    _assert_envelope_violation(payload, "request IDs must be unique")

    payload = _envelope_payload()
    _bindings(payload)[0]["arguments_hash"] = "A" * 64
    _assert_envelope_violation(payload, "lowercase SHA-256")


def test_request_identity_rejects_ambiguous_text_limits_and_hashes() -> None:
    payload = _envelope_payload()
    _section(payload, "request_identity")["agent_name"] = " padded "
    _assert_envelope_violation(payload, "agent_name must be non-empty text")

    for invalid in (True, 0, -1):
        payload = _envelope_payload()
        _section(payload, "request_identity")["max_turns"] = invalid
        _assert_envelope_violation(payload, "max_turns must be a positive integer")

    payload = _envelope_payload()
    _section(payload, "request_identity")["input_hash"] = "0" * 63
    _assert_envelope_violation(payload, "lowercase SHA-256")


def test_nested_provider_secrets_and_non_text_keys_fail_closed() -> None:
    for sensitive_payload in (
        {"nested": [{"Authorization": "Bearer secret"}]},
        {"nested": {"API-KEY": "secret"}},
        {"password": "secret"},
    ):
        with pytest.raises(ApprovalRuntimeViolation, match="sensitive") as exc_info:
            reject_sensitive_keys(sensitive_payload)
        assert exc_info.value.reason_code == "agent_continuation_sensitive"

    with pytest.raises(ApprovalRuntimeViolation, match="non-text key") as non_text:
        reject_sensitive_keys({1: "not-json"})
    assert non_text.value.reason_code == "agent_continuation_invalid"


def test_approval_rejects_malformed_or_noncanonical_bytes() -> None:
    with pytest.raises(ApprovalRuntimeViolation, match="valid JSON") as malformed:
        decode_action_payload(b"{")
    assert malformed.value.reason_code == "agent_approval_action_invalid"

    valid = canonical_bytes(_approval_payload())
    with pytest.raises(
        ApprovalRuntimeViolation, match="canonical JSON"
    ) as noncanonical:
        decode_action_payload(valid + b"\n")
    assert noncanonical.value.reason_code == "agent_approval_action_invalid"


def test_approval_requires_a_typed_universe_and_campaign_identity_pair() -> None:
    payload = _approval_payload()
    _section(payload, "temporal_context")["allowed_universe"] = "510300.SH"
    _assert_action_violation(payload, "allowed_universe is invalid")

    payload = _approval_payload()
    _section(payload, "temporal_context")["allowed_universe"] = ["510300.SH", 1]
    _assert_action_violation(payload, "allowed_universe is invalid")

    payload = _approval_payload()
    _section(payload, "temporal_context")["campaign_authorization_id"] = 1
    _assert_action_violation(payload, "campaign authorization ID is invalid")

    payload = _approval_payload()
    _section(payload, "temporal_context")["campaign_authority_hash"] = 1
    _assert_action_violation(payload, "campaign authority hash is invalid")

    payload = _approval_payload()
    _section(payload, "temporal_context")["campaign_authorization_id"] = "campaign-1"
    _assert_action_violation(payload, "temporal context is invalid")


def test_approval_temporal_values_must_be_parseable_aware_and_pit_safe() -> None:
    payload = _approval_payload()
    _section(payload, "temporal_context")["execution_eligible_at"] = "tomorrow"
    _assert_action_violation(payload, "ISO datetime")

    payload = _approval_payload()
    _section(payload, "temporal_context")["execution_eligible_at"] = (
        "2026-08-16T08:00:00"
    )
    _assert_action_violation(payload, "offset-aware")

    payload = _approval_payload()
    _section(payload, "temporal_context")["egress_class"] = "unknown"
    _assert_action_violation(payload, "temporal context is invalid")

    payload = _approval_payload()
    context = _section(payload, "temporal_context")
    context["knowledge_cutoff"] = context["decision_time"]
    context["publication_cutoff"] = "2026-08-16T08:01:00.000000Z"
    _assert_action_violation(payload, "temporal context is invalid")


def test_approval_accepts_explicit_execution_and_campaign_authority() -> None:
    payload = _approval_payload()
    context = _section(payload, "temporal_context")
    context["execution_eligible_at"] = "2026-08-16T08:30:00.000000Z"
    context["campaign_authorization_id"] = "campaign-1"
    context["campaign_authority_hash"] = HASH_A

    approval = decode_action_payload(canonical_bytes(payload))

    assert approval.temporal_context.execution_eligible_at == NOW + timedelta(
        minutes=30
    )
    assert approval.temporal_context.campaign_authorization_id == "campaign-1"
    assert approval.temporal_context.campaign_authority_hash == HASH_A


def test_approval_budget_and_action_contract_fail_closed() -> None:
    payload = _approval_payload()
    payload["parameters"] = []
    _assert_action_violation(
        payload,
        "approval parameters must be a JSON object",
        reason_code="agent_continuation_invalid",
    )

    payload = _approval_payload()
    _section(payload, "budget")["max_tool_calls"] = True
    _assert_action_violation(
        payload,
        "max_tool_calls must be a positive integer",
        reason_code="agent_continuation_invalid",
    )

    payload = _approval_payload()
    _section(payload, "budget")["max_model_spend_usd"] = "NaN"
    _assert_action_violation(payload, "action contract is invalid")

    payload = _approval_payload()
    payload["expires_at"] = "2026-08-16T07:59:00.000000Z"
    _assert_action_violation(payload, "action contract is invalid")
