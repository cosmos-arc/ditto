"""Opaque cursor codec for one immutable candidate-evidence resource."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, cast

import orjson

from ditto_application.exceptions import AppProcessError

__all__ = [
    "CandidateEvidenceCursor",
    "CandidateEvidenceResourceKind",
    "decode_candidate_evidence_cursor",
    "encode_candidate_evidence_cursor",
]

_HASH_LENGTH = 64


class CandidateEvidenceResourceKind(StrEnum):
    """Stable page namespaces; a cursor cannot cross these boundaries."""

    SELECTIONS = "selections"
    EXCLUSIONS = "exclusions"
    FACTOR_CONTRIBUTIONS = "factor_contributions"


def _error(code: str, reason: str, message: str, **details: object) -> NoReturn:
    raise AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


def _require_hash(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != _HASH_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
            field=field,
        )
    return value


def _typed_kind(value: object) -> CandidateEvidenceResourceKind:
    if type(value) is not CandidateEvidenceResourceKind:
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_kind_invalid",
            "candidate evidence cursor is invalid",
        )
    return value


@dataclass(frozen=True, slots=True)
class CandidateEvidenceCursor:
    """Decoded cursor identity bound to one immutable bundle resource."""

    content_hash: str
    resource_kind: CandidateEvidenceResourceKind
    offset: int

    def __post_init__(self) -> None:
        """Validate the cursor's immutable resource identity and offset."""
        _require_hash(self.content_hash, field="content_hash")
        _typed_kind(self.resource_kind)
        if type(self.offset) is not int or self.offset < 0:
            _error(
                "INVALID_CANDIDATE_EVIDENCE_CURSOR",
                "candidate_evidence_cursor_offset_invalid",
                "candidate evidence cursor is invalid",
            )


def encode_candidate_evidence_cursor(
    *,
    content_hash: str,
    resource_kind: CandidateEvidenceResourceKind,
    offset: int,
) -> str:
    """Encode a canonical base64url cursor without retaining mutable identity."""
    cursor = CandidateEvidenceCursor(content_hash, resource_kind, offset)
    payload = orjson.dumps(
        {
            "content_hash": cursor.content_hash,
            "offset": cursor.offset,
            "resource_kind": cursor.resource_kind.value,
            "schema_version": 1,
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_candidate_evidence_cursor(
    value: str,
    *,
    expected_content_hash: str,
    expected_resource_kind: CandidateEvidenceResourceKind,
) -> CandidateEvidenceCursor:
    """Decode and validate kind/hash affinity, distinguishing stale evidence."""
    if type(value) is not str or not value:
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
        )
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = orjson.loads(raw)
    except (ValueError, TypeError, orjson.JSONDecodeError):
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
        )
    if not isinstance(payload, dict):
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
        )
    cursor_payload = cast("dict[str, object]", payload)
    if set(cursor_payload) != {
        "content_hash",
        "offset",
        "resource_kind",
        "schema_version",
    }:
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
        )
    raw_kind = cursor_payload.get("resource_kind")
    raw_hash = cursor_payload.get("content_hash")
    raw_offset = cursor_payload.get("offset")
    raw_schema_version = cursor_payload.get("schema_version")
    if (
        type(raw_kind) is not str
        or type(raw_hash) is not str
        or type(raw_offset) is not int
        or type(raw_schema_version) is not int
    ):
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
        )
    try:
        kind = CandidateEvidenceResourceKind(raw_kind)
    except ValueError:
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_invalid",
            "candidate evidence cursor is invalid",
        )
    cursor = CandidateEvidenceCursor(
        content_hash=raw_hash,
        resource_kind=kind,
        offset=raw_offset,
    )
    if raw_schema_version != 1 or kind is not expected_resource_kind:
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_resource_mismatch",
            "candidate evidence cursor cannot be used for this resource",
        )
    if cursor.content_hash != _require_hash(
        expected_content_hash,
        field="expected_content_hash",
    ):
        _error(
            "EVIDENCE_STALE",
            "candidate_evidence_cursor_hash_stale",
            "candidate evidence cursor references a stale bundle",
            cursor_content_hash=cursor.content_hash,
            current_content_hash=expected_content_hash,
        )
    return cursor
