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

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    find_mutation_fence,
    mutation_fence_detail,
    validate_mutation_fence_detail,
)

__all__ = [
    "ExperimentCreationIdentity",
    "compile_creation_identity",
    "fence_durable_draft_launch",
    "verify_creation_identity_payload",
    "verify_durable_creation_identity",
]

_CREATION_IDENTITY_SCHEMA_VERSION = 1
_IDEMPOTENT_CREATION_IDENTITY_SCHEMA_VERSION = 2
_CREATION_IDENTITY_KEYS = frozenset({"schema_version", "request_hash", "plan_hash"})
_IDEMPOTENT_CREATION_IDENTITY_KEYS = frozenset(
    {*_CREATION_IDENTITY_KEYS, "mutation_idempotency_fence"}
)
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
    idempotency: MutationIdempotency | None = None,
) -> tuple[Mapping[str, object], CanonicalPayload]:
    """Encode the exact modern creation-event detail."""
    if not _is_sha256(request_hash) or not _is_sha256(plan_hash):
        raise _identity_error("creation_identity_hash_invalid")
    detail: dict[str, object] = {
        "schema_version": (
            _CREATION_IDENTITY_SCHEMA_VERSION
            if idempotency is None
            else _IDEMPOTENT_CREATION_IDENTITY_SCHEMA_VERSION
        ),
        "request_hash": request_hash,
        "plan_hash": plan_hash,
    }
    if idempotency is not None:
        detail = mutation_fence_detail(idempotency, detail=detail)
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
        frozenset(copied)
        not in {_CREATION_IDENTITY_KEYS, _IDEMPOTENT_CREATION_IDENTITY_KEYS}
        or type(copied.get("schema_version")) is not int
        or copied["schema_version"]
        not in {
            _CREATION_IDENTITY_SCHEMA_VERSION,
            _IDEMPOTENT_CREATION_IDENTITY_SCHEMA_VERSION,
        }
        or (
            copied["schema_version"] == _CREATION_IDENTITY_SCHEMA_VERSION
            and frozenset(copied) != _CREATION_IDENTITY_KEYS
        )
        or (
            copied["schema_version"] == _IDEMPOTENT_CREATION_IDENTITY_SCHEMA_VERSION
            and frozenset(copied) != _IDEMPOTENT_CREATION_IDENTITY_KEYS
        )
        or not _is_sha256(copied.get("request_hash"))
        or not _is_sha256(copied.get("plan_hash"))
    ):
        raise _identity_error(
            "durable_creation_identity_invalid",
            experiment_id=None if experiment_id is None else str(experiment_id),
        )
    if copied["schema_version"] == _IDEMPOTENT_CREATION_IDENTITY_SCHEMA_VERSION:
        try:
            validate_mutation_fence_detail(copied)
        except AppCommandError as exc:
            raise _identity_error(
                "durable_creation_identity_invalid",
                experiment_id=None if experiment_id is None else str(experiment_id),
            ) from exc
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
    expected_idempotency: MutationIdempotency | None = None,
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
        or (
            expected_idempotency is not None
            and not find_mutation_fence((detail,), expected_idempotency)
        )
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


def verify_durable_creation_identity(
    *,
    events: tuple[StatusEventRecord, ...],
    experiment_id: ExperimentId,
    expected_request_hash: str,
    expected_plan_hash: str,
    expected_idempotency: MutationIdempotency | None = None,
) -> None:
    """Cross-link the unique revision-zero event to launch request and plan."""
    event = _creation_event(events, experiment_id=experiment_id)
    identity = _decode_creation_identity(
        event.detail,
        detail_hash=event.detail_hash,
        experiment_id=experiment_id,
    )
    if identity is None:
        if expected_idempotency is not None:
            raise _identity_error(
                "durable_creation_identity_invalid",
                experiment_id=str(experiment_id),
            )
        return
    if identity.request_hash != expected_request_hash:
        raise AppProcessError(
            "experiment already exists with a different planning request",
            details={
                "code": "EXPERIMENT_ALREADY_EXISTS",
                "reason": "durable_launch_request_mismatch",
                "durable_request_hash": identity.request_hash,
                "caller_request_hash": expected_request_hash,
            },
        )
    if identity.plan_hash != expected_plan_hash:
        raise AppProcessError(
            "confirmed experiment plan hash is stale",
            details={
                "code": "PLAN_HASH_MISMATCH",
                "expected_plan_hash": identity.plan_hash,
                "confirmed_plan_hash": expected_plan_hash,
            },
        )
    if expected_idempotency is not None:
        try:
            fenced = find_mutation_fence((event.detail,), expected_idempotency)
        except AppCommandError as exc:
            raise AppProcessError(str(exc), details=exc.details) from exc
        if (
            event.detail.get("schema_version")
            != _IDEMPOTENT_CREATION_IDENTITY_SCHEMA_VERSION
            or not fenced
        ):
            raise _identity_error(
                "durable_creation_identity_invalid",
                experiment_id=str(experiment_id),
            )


def fence_durable_draft_launch(
    *,
    reader: ExperimentReaderProtocol,
    experiment_id: str,
    confirmed_plan_hash: str,
    request_hash: str,
    idempotency: MutationIdempotency | None = None,
) -> bool:
    """Return true for stable DRAFT; signal advanced state for reclassification."""
    typed_experiment_id = ExperimentId(experiment_id)
    for _ in range(_STABLE_DRAFT_READ_ATTEMPTS):
        before = reader.get_experiment_projection(typed_experiment_id)
        if before is None:
            raise _identity_error(
                "concurrent_experiment_update",
                experiment_id=experiment_id,
            )
        if before.record.status is not ExperimentStatus.DRAFT:
            return False
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
        verify_durable_creation_identity(
            events=events,
            experiment_id=typed_experiment_id,
            expected_request_hash=request_hash,
            expected_plan_hash=confirmed_plan_hash,
            expected_idempotency=idempotency,
        )
        return True
    raise _identity_error(
        "concurrent_experiment_update",
        experiment_id=experiment_id,
    )
