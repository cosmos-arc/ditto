"""Durable, schema-free application mutation-idempotency primitives."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import orjson

from ditto_application.exceptions import AppCommandError

IDEMPOTENCY_KEY_MAX_LENGTH = 128
_KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]+")
_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_RECEIPT_KEY = "mutation_idempotency"
_FENCE_KEY = "mutation_idempotency_fence"
_RECEIPT_KIND = "ditto_mutation_receipt"
_FENCE_KIND = "ditto_mutation_fence"
_REASON_KIND = "ditto_governance_reason"
_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "operation_id",
        "resource_id",
        "key_hash",
        "request_hash",
        "response",
        "receipt_hash",
    }
)
_FENCE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "operation_id",
        "resource_id",
        "key_hash",
        "request_hash",
        "fence_hash",
    }
)

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def _error(
    *,
    code: str,
    reason: str,
    message: str,
    identity: MutationIdempotency | None = None,
) -> AppCommandError:
    details: dict[str, object] = {"code": code, "reason": reason}
    if identity is not None:
        details.update(
            operation_id=identity.operation_id,
            resource_id=identity.resource_id,
        )
    return AppCommandError(message, details=details)


def _validate_json(value: object, *, path: str = "$") -> JsonValue:
    if value is None or type(value) in {str, bool, int}:  # bool must precede int.
        return cast("JsonScalar", value)
    if type(value) is float:
        if not math.isfinite(value):
            raise _error(
                code="IDEMPOTENCY_REQUEST_INVALID",
                reason="request_not_canonical_json",
                message=f"idempotency request is not canonical JSON at {path}",
            )
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        normalized: dict[str, JsonValue] = {}
        for key, item in mapping.items():
            if type(key) is not str:
                raise _error(
                    code="IDEMPOTENCY_REQUEST_INVALID",
                    reason="request_not_canonical_json",
                    message=f"idempotency request is not canonical JSON at {path}",
                )
            normalized[key] = _validate_json(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        sequence = cast("Sequence[object]", value)
        return [
            _validate_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(sequence)
        ]
    raise _error(
        code="IDEMPOTENCY_REQUEST_INVALID",
        reason="request_not_canonical_json",
        message=f"idempotency request is not canonical JSON at {path}",
    )


def _canonical_bytes(value: object) -> bytes:
    return orjson.dumps(_validate_json(value), option=orjson.OPT_SORT_KEYS)


def canonical_request_hash(payload: object) -> str:
    """Hash strict canonical JSON without Python bool/key ambiguity."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def canonical_resource_id(
    resource_kind: str,
    components: Mapping[str, object],
) -> str:
    """Build a delimiter-safe, bounded opaque identity for one mutation target."""
    if type(resource_kind) is not str or _ID_PATTERN.fullmatch(resource_kind) is None:
        raise ValueError("resource_kind is invalid")
    digest = canonical_request_hash(
        {"resource_kind": resource_kind, "components": components}
    )
    return f"{resource_kind}:v1:{digest}"


def _validate_hash(value: object, *, field: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 hex digest")
    return value


@dataclass(frozen=True, slots=True)
class MutationIdempotency:
    """Canonical application-boundary identity; never retains the raw key."""

    operation_id: str
    resource_id: str
    key_hash: str
    request_hash: str

    def __post_init__(self) -> None:
        """Reject identities that did not cross the canonical Apps boundary."""
        if (
            type(self.operation_id) is not str
            or _ID_PATTERN.fullmatch(self.operation_id) is None
        ):
            raise ValueError("operation_id is invalid")
        if type(self.resource_id) is not str or not self.resource_id:
            raise ValueError("resource_id is invalid")
        _validate_hash(self.key_hash, field="key_hash")
        _validate_hash(self.request_hash, field="request_hash")


def build_mutation_idempotency(
    *,
    operation_id: str,
    resource_id: str,
    raw_key: object,
    request_payload: object,
    request_hash: str | None = None,
) -> MutationIdempotency:
    """Validate a transport key and immediately discard its raw representation."""
    if (
        type(raw_key) is not str
        or not raw_key
        or len(raw_key) > IDEMPOTENCY_KEY_MAX_LENGTH
        or _KEY_PATTERN.fullmatch(raw_key) is None
    ):
        raise _error(
            code="IDEMPOTENCY_KEY_INVALID",
            reason="idempotency_key_invalid",
            message="Idempotency-Key is invalid",
        )
    resolved_request_hash = (
        canonical_request_hash(request_payload)
        if request_hash is None
        else _validate_hash(request_hash, field="request_hash")
    )
    return MutationIdempotency(
        operation_id=operation_id,
        resource_id=resource_id,
        key_hash=hashlib.sha256(raw_key.encode("ascii")).hexdigest(),
        request_hash=resolved_request_hash,
    )


def mutation_event_id(identity: MutationIdempotency) -> str:
    """Return a deterministic, bounded event id without exposing resource/key."""
    resource_hash = hashlib.sha256(identity.resource_id.encode()).hexdigest()[:24]
    return f"idempotency:v1:{identity.operation_id}:{resource_hash}:{identity.key_hash}"


def _receipt_body(
    identity: MutationIdempotency,
    *,
    response: Mapping[str, object],
) -> dict[str, JsonValue]:
    normalized = _validate_json(response)
    if not isinstance(normalized, dict):
        raise ValueError("idempotency receipt response must be a JSON object")
    return {
        "schema_version": 1,
        "kind": _RECEIPT_KIND,
        "operation_id": identity.operation_id,
        "resource_id": identity.resource_id,
        "key_hash": identity.key_hash,
        "request_hash": identity.request_hash,
        "response": normalized,
    }


def mutation_receipt_detail(
    identity: MutationIdempotency,
    *,
    response: Mapping[str, object],
    detail: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Embed a versioned, self-hashed receipt into an event detail."""
    result = dict(detail or {})
    if _RECEIPT_KEY in result:
        raise ValueError("mutation receipt detail key is reserved")
    body = _receipt_body(identity, response=response)
    result[_RECEIPT_KEY] = {
        **body,
        "receipt_hash": hashlib.sha256(_canonical_bytes(body)).hexdigest(),
    }
    return result


def mutation_receipt_reason(
    identity: MutationIdempotency,
    *,
    response: Mapping[str, object],
    human_reason: str,
) -> str:
    """Encode a receipt beside, rather than inside, the human-authored reason."""
    detail = mutation_receipt_detail(identity, response=response)
    return orjson.dumps(
        {
            "schema_version": 1,
            "kind": _REASON_KIND,
            "human_reason": human_reason,
            _RECEIPT_KEY: detail[_RECEIPT_KEY],
        },
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def mutation_fence_detail(
    identity: MutationIdempotency,
    *,
    detail: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Embed a request fence when the final response is not available yet."""
    result = dict(detail or {})
    if _FENCE_KEY in result:
        raise ValueError("mutation fence detail key is reserved")
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": _FENCE_KIND,
        "operation_id": identity.operation_id,
        "resource_id": identity.resource_id,
        "key_hash": identity.key_hash,
        "request_hash": identity.request_hash,
    }
    result[_FENCE_KEY] = {
        **body,
        "fence_hash": hashlib.sha256(_canonical_bytes(body)).hexdigest(),
    }
    return result


def _invalid_receipt(
    identity: MutationIdempotency | None = None,
) -> AppCommandError:
    return _error(
        code="IDEMPOTENCY_RECEIPT_INVALID",
        reason="idempotency_receipt_invalid",
        message="durable idempotency receipt is invalid",
        identity=identity,
    )


def _has_exact_string_keys(
    value: Mapping[object, object],
    expected: frozenset[str],
) -> bool:
    keys = tuple(value)
    return (
        all(type(key) is str for key in keys)
        and cast("frozenset[str]", frozenset(keys)) == expected
    )


def _parse_receipt(
    raw: object,
    *,
    identity: MutationIdempotency | None,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise _invalid_receipt(identity)
    receipt = cast("Mapping[object, object]", raw)
    if not _has_exact_string_keys(receipt, _RECEIPT_KEYS):
        raise _invalid_receipt(identity)
    typed_receipt = cast("Mapping[str, object]", receipt)
    body = {key: value for key, value in typed_receipt.items() if key != "receipt_hash"}
    try:
        receipt_hash = _validate_hash(
            typed_receipt["receipt_hash"],
            field="receipt_hash",
        )
        actual_hash = hashlib.sha256(_canonical_bytes(body)).hexdigest()
        _validate_hash(typed_receipt["key_hash"], field="key_hash")
        _validate_hash(typed_receipt["request_hash"], field="request_hash")
        normalized_response = _validate_json(typed_receipt["response"])
    except (AppCommandError, ValueError, TypeError) as exc:
        raise _invalid_receipt(identity) from exc
    if (
        type(typed_receipt["schema_version"]) is not int
        or typed_receipt["schema_version"] != 1
        or typed_receipt["kind"] != _RECEIPT_KIND
        or receipt_hash != actual_hash
        or type(typed_receipt["operation_id"]) is not str
        or _ID_PATTERN.fullmatch(typed_receipt["operation_id"]) is None
        or type(typed_receipt["resource_id"]) is not str
        or not typed_receipt["resource_id"]
        or not isinstance(normalized_response, dict)
    ):
        raise _invalid_receipt(identity)
    return dict(typed_receipt)


def find_mutation_receipt(
    details: Sequence[Mapping[str, object]],
    identity: MutationIdempotency,
) -> Mapping[str, object] | None:
    """Find the one exact receipt for an identity, failing closed on corruption."""
    matches: list[dict[str, object]] = []
    for detail in details:
        if _RECEIPT_KEY not in detail:
            continue
        receipt = _parse_receipt(detail[_RECEIPT_KEY], identity=identity)
        if (
            receipt["operation_id"] != identity.operation_id
            or receipt["resource_id"] != identity.resource_id
            or receipt["key_hash"] != identity.key_hash
        ):
            continue
        if receipt["request_hash"] != identity.request_hash:
            raise _error(
                code="IDEMPOTENCY_KEY_REUSED",
                reason="idempotency_key_request_hash_mismatch",
                message="Idempotency-Key was reused with a different request",
                identity=identity,
            )
        matches.append(receipt)
    if len(matches) > 1:
        raise _invalid_receipt(identity)
    if not matches:
        return None
    response = matches[0]["response"]
    if not isinstance(response, Mapping):
        raise _invalid_receipt(identity)
    return cast(
        "Mapping[str, object]",
        _validate_json(cast("Mapping[object, object]", response)),
    )


def find_mutation_receipt_in_reasons(
    reasons: Sequence[str],
    identity: MutationIdempotency,
) -> Mapping[str, object] | None:
    """Read receipts from versioned governance reason wrappers."""
    details: list[Mapping[str, object]] = []
    for reason in reasons:
        try:
            value = cast("object", orjson.loads(reason))
        except orjson.JSONDecodeError:
            continue
        if not isinstance(value, Mapping) or _RECEIPT_KEY not in value:
            continue
        wrapper = cast("Mapping[object, object]", value)
        if (
            set(wrapper)
            != {
                "schema_version",
                "kind",
                "human_reason",
                _RECEIPT_KEY,
            }
            or type(wrapper["schema_version"]) is not int
            or wrapper["schema_version"] != 1
            or wrapper["kind"] != _REASON_KIND
            or type(wrapper["human_reason"]) is not str
        ):
            raise _invalid_receipt(identity)
        details.append({_RECEIPT_KEY: wrapper[_RECEIPT_KEY]})
    return find_mutation_receipt(details, identity)


def without_mutation_receipt(detail: Mapping[str, object]) -> dict[str, object]:
    """Return the legacy payload after removing exactly the reserved envelope."""
    result = dict(detail)
    result.pop(_RECEIPT_KEY, None)
    return result


def without_validated_mutation_receipt(
    detail: Mapping[str, object],
) -> dict[str, object]:
    """Validate an optional envelope without caller identity before stripping it."""
    if _RECEIPT_KEY in detail:
        _parse_receipt(detail[_RECEIPT_KEY], identity=None)
    return without_mutation_receipt(detail)


def _parse_fence(
    raw: object,
    *,
    identity: MutationIdempotency | None,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise _invalid_receipt(identity)
    fence = cast("Mapping[object, object]", raw)
    if not _has_exact_string_keys(fence, _FENCE_KEYS):
        raise _invalid_receipt(identity)
    typed_fence = cast("Mapping[str, object]", fence)
    body = {key: value for key, value in typed_fence.items() if key != "fence_hash"}
    try:
        fence_hash = _validate_hash(
            typed_fence["fence_hash"],
            field="fence_hash",
        )
        actual_hash = hashlib.sha256(_canonical_bytes(body)).hexdigest()
        _validate_hash(typed_fence["key_hash"], field="key_hash")
        _validate_hash(typed_fence["request_hash"], field="request_hash")
    except (AppCommandError, ValueError, TypeError) as exc:
        raise _invalid_receipt(identity) from exc
    if (
        type(typed_fence["schema_version"]) is not int
        or typed_fence["schema_version"] != 1
        or typed_fence["kind"] != _FENCE_KIND
        or fence_hash != actual_hash
        or type(typed_fence["operation_id"]) is not str
        or _ID_PATTERN.fullmatch(typed_fence["operation_id"]) is None
        or type(typed_fence["resource_id"]) is not str
        or not typed_fence["resource_id"]
    ):
        raise _invalid_receipt(identity)
    return dict(typed_fence)


def validate_mutation_fence_detail(
    detail: Mapping[str, object],
) -> None:
    """Validate an optional partial-write fence without a caller identity."""
    if _FENCE_KEY in detail:
        _parse_fence(detail[_FENCE_KEY], identity=None)


def without_validated_mutation_fence(
    detail: Mapping[str, object],
) -> dict[str, object]:
    """Validate and remove the optional request fence from an event detail."""
    validate_mutation_fence_detail(detail)
    result = dict(detail)
    result.pop(_FENCE_KEY, None)
    return result


def find_mutation_fence(
    details: Sequence[Mapping[str, object]],
    identity: MutationIdempotency,
) -> bool:
    """Find one exact partial-write fence or reject key reuse/corruption."""
    matches = 0
    for detail in details:
        if _FENCE_KEY not in detail:
            continue
        raw = _parse_fence(detail[_FENCE_KEY], identity=identity)
        if (
            raw["operation_id"] != identity.operation_id
            or raw["resource_id"] != identity.resource_id
            or raw["key_hash"] != identity.key_hash
        ):
            continue
        if raw["request_hash"] != identity.request_hash:
            raise _error(
                code="IDEMPOTENCY_KEY_REUSED",
                reason="idempotency_key_request_hash_mismatch",
                message="Idempotency-Key was reused with a different request",
                identity=identity,
            )
        matches += 1
    if matches > 1:
        raise _invalid_receipt(identity)
    return matches == 1


__all__ = [
    "IDEMPOTENCY_KEY_MAX_LENGTH",
    "MutationIdempotency",
    "build_mutation_idempotency",
    "canonical_request_hash",
    "canonical_resource_id",
    "find_mutation_fence",
    "find_mutation_receipt",
    "find_mutation_receipt_in_reasons",
    "mutation_event_id",
    "mutation_fence_detail",
    "mutation_receipt_detail",
    "mutation_receipt_reason",
    "validate_mutation_fence_detail",
    "without_mutation_receipt",
    "without_validated_mutation_fence",
    "without_validated_mutation_receipt",
]
