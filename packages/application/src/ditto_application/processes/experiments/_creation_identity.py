"""Canonical revision-0 launch identity and preflight-free DRAFT fencing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from ditto_analysis.experiments import (
    CanonicalPayload,
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentReaderProtocol,
    ExperimentStage,
    ExperimentStatus,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "ExperimentCreationIdentity",
    "compile_creation_identity",
    "fence_durable_draft_launch",
    "verify_creation_identity_payload",
]

_CREATION_IDENTITY_SCHEMA_VERSION = 1
_CREATION_IDENTITY_KEYS = frozenset({"schema_version", "request_hash", "plan_hash"})
_SHA256_HEX_LENGTH = 64
_STABLE_DRAFT_READ_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ExperimentCreationIdentity:
    """Complete request and confirmed-plan fence persisted at revision zero."""

    request_hash: str
    plan_hash: str


def _identity_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        f"experiment launch saga is inconsistent: {reason}",
        details={
            "code": "EXPERIMENT_LAUNCH_CONFLICT",
            "reason": reason,
            **details,
        },
    )


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def compile_creation_identity(
    *,
    request_hash: str,
    plan_hash: str,
) -> tuple[Mapping[str, object], CanonicalPayload]:
    """Encode the exact modern creation-event detail."""
    if not _is_sha256(request_hash) or not _is_sha256(plan_hash):
        raise _identity_error("creation_identity_hash_invalid")
    detail: dict[str, object] = {
        "schema_version": _CREATION_IDENTITY_SCHEMA_VERSION,
        "request_hash": request_hash,
        "plan_hash": plan_hash,
    }
    payload = canonical_payload(detail)
    return MappingProxyType(detail), payload


def _decode_creation_identity(
    detail: Mapping[str, object],
    *,
    detail_hash: ContentHash,
    experiment_id: ExperimentId | None,
) -> ExperimentCreationIdentity | None:
    try:
        payload = canonical_payload(detail)
    except Exception as exc:
        raise _identity_error(
            "durable_creation_identity_invalid",
            experiment_id=None if experiment_id is None else str(experiment_id),
        ) from exc
    if payload.content_hash != detail_hash:
        raise _identity_error(
            "durable_creation_identity_invalid",
            experiment_id=None if experiment_id is None else str(experiment_id),
        )
    copied = dict(detail)
    if not copied:
        return None
    if (
        frozenset(copied) != _CREATION_IDENTITY_KEYS
        or type(copied.get("schema_version")) is not int
        or copied["schema_version"] != _CREATION_IDENTITY_SCHEMA_VERSION
        or not _is_sha256(copied.get("request_hash"))
        or not _is_sha256(copied.get("plan_hash"))
    ):
        raise _identity_error(
            "durable_creation_identity_invalid",
            experiment_id=None if experiment_id is None else str(experiment_id),
        )
    return ExperimentCreationIdentity(
        request_hash=cast("str", copied["request_hash"]),
        plan_hash=cast("str", copied["plan_hash"]),
    )


def verify_creation_identity_payload(
    *,
    detail: Mapping[str, object],
    detail_json: bytes,
    detail_hash: ContentHash,
    expected_request_hash: object,
    expected_plan_hash: str,
) -> None:
    """Verify prepared canonical bytes and their request/plan cross-links."""
    identity = _decode_creation_identity(
        detail,
        detail_hash=detail_hash,
        experiment_id=None,
    )
    if (
        identity is None
        or canonical_payload(detail).json_bytes != detail_json
        or identity.request_hash != expected_request_hash
        or identity.plan_hash != expected_plan_hash
    ):
        raise _identity_error("prepared_creation_identity_invalid")


def _creation_event(
    events: tuple[StatusEventRecord, ...],
    *,
    experiment_id: ExperimentId,
) -> StatusEventRecord:
    matches = tuple(
        event
        for event in events
        if event.subject_type is StatusSubjectType.EXPERIMENT
        and event.subject_revision == 0
    )
    if len(matches) != 1:
        raise _identity_error(
            "durable_creation_event_invalid",
            experiment_id=str(experiment_id),
            creation_event_count=len(matches),
        )
    event = matches[0]
    if (
        event.experiment_id != experiment_id
        or event.candidate_id is not None
        or event.fold_id is not None
        or event.attempt_id is not None
        or event.previous_status is not None
        or event.status is not ExperimentStatus.DRAFT
        or event.desired_state is not ExperimentDesiredState.RUN
        or event.stage is not ExperimentStage.PREFLIGHT
        or event.failure_code is not None
        or event.reason_code != "experiment_created"
    ):
        raise _identity_error(
            "durable_creation_event_invalid",
            experiment_id=str(experiment_id),
        )
    return event


def fence_durable_draft_launch(
    *,
    reader: ExperimentReaderProtocol,
    experiment_id: str,
    confirmed_plan_hash: str,
    request_hash: str,
) -> None:
    """Fence modern DRAFT identity before probes; legacy empty detail falls back."""
    typed_experiment_id = ExperimentId(experiment_id)
    for _ in range(_STABLE_DRAFT_READ_ATTEMPTS):
        before = reader.get_experiment_projection(typed_experiment_id)
        if before is None or before.record.status is not ExperimentStatus.DRAFT:
            return
        events = reader.list_status_events(typed_experiment_id)
        after = reader.get_experiment_projection(typed_experiment_id)
        if after is None or after != before:
            continue
        if before.revision != 0 or before.queue_ordinal is not None:
            raise _identity_error(
                "experiment_not_replayable",
                experiment_id=experiment_id,
                status=before.record.status.value,
                revision=before.revision,
            )
        event = _creation_event(events, experiment_id=typed_experiment_id)
        identity = _decode_creation_identity(
            event.detail,
            detail_hash=event.detail_hash,
            experiment_id=typed_experiment_id,
        )
        if identity is None:
            return
        if identity.request_hash != request_hash:
            raise AppProcessError(
                "experiment already exists with a different planning request",
                details={
                    "code": "EXPERIMENT_ALREADY_EXISTS",
                    "reason": "durable_launch_request_mismatch",
                    "durable_request_hash": identity.request_hash,
                    "caller_request_hash": request_hash,
                },
            )
        if identity.plan_hash != confirmed_plan_hash:
            raise AppProcessError(
                "confirmed experiment plan hash is stale",
                details={
                    "code": "PLAN_HASH_MISMATCH",
                    "expected_plan_hash": identity.plan_hash,
                    "confirmed_plan_hash": confirmed_plan_hash,
                },
            )
        return
    raise _identity_error(
        "concurrent_experiment_update",
        experiment_id=experiment_id,
    )
