"""Unit contracts for the shared durable mutation-idempotency value."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from ditto_application.commands.mutation_idempotency import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    MutationIdempotency,
    build_mutation_idempotency,
    canonical_request_hash,
    canonical_resource_id,
    find_mutation_receipt,
    mutation_event_id,
    mutation_receipt_detail,
    without_validated_mutation_receipt,
)
from ditto_application.exceptions import AppCommandError


def _identity(*, request_hash: str | None = None) -> MutationIdempotency:
    return build_mutation_idempotency(
        operation_id="research_pause_experiment",
        resource_id="experiment-1",
        raw_key="request.key-001",
        request_payload={"expected_revision": 7},
        request_hash=request_hash,
    )


def test_build_hashes_key_and_canonical_request_without_retaining_raw_key() -> None:
    value = _identity()

    assert value == MutationIdempotency(
        operation_id="research_pause_experiment",
        resource_id="experiment-1",
        key_hash=("be417d00ba4acc763aa3f66eb5df2720483c079b200f39dd473c0ae1f0b1f414"),
        request_hash=canonical_request_hash({"expected_revision": 7}),
    )
    assert "request.key-001" not in repr(value)
    assert "request.key-001" not in mutation_event_id(value)


@pytest.mark.parametrize(
    "raw_key",
    [
        "",
        " ",
        " padded",
        "padded ",
        "contains space",
        "unicode-é",
        True,
        "x" * (IDEMPOTENCY_KEY_MAX_LENGTH + 1),
    ],
)
def test_key_validation_rejects_blank_padded_non_ascii_bool_and_oversized(
    raw_key: object,
) -> None:
    with pytest.raises(AppCommandError) as exc_info:
        build_mutation_idempotency(
            operation_id="research_pause_experiment",
            resource_id="experiment-1",
            raw_key=raw_key,
            request_payload={"expected_revision": 7},
        )

    assert exc_info.value.details == {
        "code": "IDEMPOTENCY_KEY_INVALID",
        "reason": "idempotency_key_invalid",
    }
    if raw_key and str(raw_key).strip():
        assert str(raw_key) not in str(exc_info.value.details)


def test_request_hash_rejects_non_string_mapping_keys_and_non_finite_numbers() -> None:
    with pytest.raises(AppCommandError, match="canonical"):
        canonical_request_hash({1: "ambiguous"})  # type: ignore[dict-item]
    with pytest.raises(AppCommandError, match="canonical"):
        canonical_request_hash({"value": float("nan")})


def test_event_id_is_bound_to_operation_resource_and_key_hash() -> None:
    first = _identity()
    second = build_mutation_idempotency(
        operation_id=first.operation_id,
        resource_id=first.resource_id,
        raw_key="request.key-001",
        request_payload={"expected_revision": 999},
    )
    assert mutation_event_id(first) == mutation_event_id(second)
    assert mutation_event_id(first).startswith(
        "idempotency:v1:research_pause_experiment:"
    )
    assert mutation_event_id(first) != mutation_event_id(
        build_mutation_idempotency(
            operation_id="research_resume_experiment",
            resource_id=first.resource_id,
            raw_key="request.key-001",
            request_payload={"expected_revision": 7},
        )
    )


def test_resource_identity_has_no_delimiter_aliases() -> None:
    assert canonical_resource_id(
        "experiment_fold",
        {"experiment_id": "a/b", "candidate_id": "c", "fold_id": "d"},
    ) != canonical_resource_id(
        "experiment_fold",
        {"experiment_id": "a", "candidate_id": "b/c", "fold_id": "d"},
    )


def test_receipt_replays_exact_response_and_detects_request_hash_reuse() -> None:
    identity = _identity()
    response = {
        "experiment_id": "experiment-1",
        "status": "pause_requested",
        "revision": 8,
    }
    detail = mutation_receipt_detail(identity, response=response)

    replay = find_mutation_receipt(({"unrelated": True}, detail), identity)

    assert replay == response
    assert isinstance(replay, Mapping)
    assert "request.key-001" not in repr(detail)

    changed = _identity(request_hash=canonical_request_hash({"expected_revision": 8}))
    with pytest.raises(AppCommandError) as exc_info:
        find_mutation_receipt((detail,), changed)
    assert exc_info.value.details == {
        "code": "IDEMPOTENCY_KEY_REUSED",
        "reason": "idempotency_key_request_hash_mismatch",
        "operation_id": "research_pause_experiment",
        "resource_id": "experiment-1",
    }


def test_receipt_reader_fails_closed_on_duplicate_or_malformed_envelopes() -> None:
    identity = _identity()
    detail = mutation_receipt_detail(identity, response={"revision": 8})

    with pytest.raises(AppCommandError) as duplicate:
        find_mutation_receipt((detail, detail), identity)
    assert duplicate.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"

    malformed = dict(detail)
    malformed["mutation_idempotency"] = {"schema_version": 1}
    with pytest.raises(AppCommandError) as invalid:
        find_mutation_receipt((malformed,), identity)
    assert invalid.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"


def test_identity_free_receipt_validation_rejects_self_hashed_invalid_fields() -> None:
    detail = mutation_receipt_detail(_identity(), response={"revision": 8})
    envelope = dict(detail["mutation_idempotency"])  # type: ignore[arg-type]
    envelope["key_hash"] = "not-a-sha256"
    body = {key: value for key, value in envelope.items() if key != "receipt_hash"}
    envelope["receipt_hash"] = canonical_request_hash(body)

    with pytest.raises(AppCommandError) as invalid:
        without_validated_mutation_receipt({"mutation_idempotency": envelope})

    assert invalid.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"
