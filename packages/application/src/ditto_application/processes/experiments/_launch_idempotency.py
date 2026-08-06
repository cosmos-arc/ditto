"""Idempotency binding and pre-probe replay for experiment launch."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import orjson
from ditto_analysis.experiments import (
    ExperimentId,
    ExperimentReaderProtocol,
    ExperimentStatus,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
)

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    canonical_resource_id,
    find_mutation_receipt,
    mutation_receipt_detail,
    without_validated_mutation_receipt,
)
from ditto_application.processes.experiments._creation_identity import (
    compile_creation_identity,
)
from ditto_application.processes.experiments._launch_contracts import (
    DurableLaunchReplay,
    PreparedExperimentLaunch,
)
from ditto_application.processes.experiments._launch_saga import (
    replay_verified_durable_enqueue,
    verify_prepared_launch,
)

_STABLE_READ_ATTEMPTS = 3


def _error(reason: str, *, experiment_id: str) -> AppProcessError:
    return AppProcessError(
        f"experiment launch saga is inconsistent: {reason}",
        details={
            "code": "EXPERIMENT_LAUNCH_CONFLICT",
            "reason": reason,
            "experiment_id": experiment_id,
        },
    )


def _mapping(value: object, *, experiment_id: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _error("durable_enqueue_receipt_invalid", experiment_id=experiment_id)
    return cast("dict[str, object]", value)


def bind_prepared_launch_idempotency(
    prepared: PreparedExperimentLaunch,
    identity: MutationIdempotency,
) -> PreparedExperimentLaunch:
    """Bind the partial DRAFT fence and final enqueue receipt before writing."""
    experiment_id = str(prepared.spec.experiment_id)
    if (
        identity.operation_id != "research_launch_experiment"
        or identity.resource_id
        != canonical_resource_id(
            "experiment",
            {"experiment_id": experiment_id},
        )
    ):
        raise _error(
            "prepared_launch_idempotency_target_mismatch",
            experiment_id=experiment_id,
        )
    plan_preimage = _mapping(
        orjson.loads(prepared.plan_preimage_json),
        experiment_id=experiment_id,
    )
    request_hash = plan_preimage.get("request_hash")
    if type(request_hash) is not str:
        raise _error(
            "prepared_launch_request_hash_missing",
            experiment_id=experiment_id,
        )
    creation_detail, creation_payload = compile_creation_identity(
        request_hash=request_hash,
        plan_hash=prepared.plan_hash,
        idempotency=identity,
    )
    enqueue_detail = mutation_receipt_detail(
        identity,
        response={
            "experiment_id": experiment_id,
            "status": ExperimentStatus.QUEUED.value,
            "revision": 1,
            "candidate_count": len(prepared.spec.candidates),
            "fold_count": len(prepared.folds),
            "plan_hash": prepared.plan_hash,
        },
        detail=prepared.enqueue_detail,
    )
    enqueue_payload = canonical_payload(enqueue_detail)
    bound = replace(
        prepared,
        creation_detail=creation_detail,
        creation_detail_json=creation_payload.json_bytes,
        creation_detail_hash=creation_payload.content_hash,
        enqueue_detail=enqueue_detail,
        enqueue_detail_json=enqueue_payload.json_bytes,
        enqueue_detail_hash=enqueue_payload.content_hash,
        idempotency=identity,
    )
    verify_prepared_launch(bound)
    return bound


def _matching_receipt(
    events: tuple[StatusEventRecord, ...],
    identity: MutationIdempotency,
    *,
    experiment_id: str,
) -> tuple[StatusEventRecord, Mapping[str, object]] | None:
    matches: list[tuple[StatusEventRecord, Mapping[str, object]]] = []
    for event in events:
        try:
            receipt = find_mutation_receipt((event.detail,), identity)
        except AppCommandError as exc:
            raise AppProcessError(str(exc), details=exc.details) from exc
        if receipt is not None:
            matches.append((event, receipt))
    if len(matches) > 1:
        raise _error("durable_enqueue_receipt_duplicate", experiment_id=experiment_id)
    return None if not matches else matches[0]


def try_replay_idempotent_launch(
    *,
    reader: ExperimentReaderProtocol,
    experiment_id: str,
    identity: MutationIdempotency | None,
) -> DurableLaunchReplay | None:
    """Replay the original enqueue receipt before any planning provider is called."""
    if identity is None:
        return None
    if (
        identity.operation_id != "research_launch_experiment"
        or identity.resource_id
        != canonical_resource_id(
            "experiment",
            {"experiment_id": experiment_id},
        )
    ):
        raise _error(
            "durable_enqueue_receipt_target_mismatch",
            experiment_id=experiment_id,
        )
    typed_experiment_id = ExperimentId(experiment_id)
    for _ in range(_STABLE_READ_ATTEMPTS):
        before = reader.get_experiment_projection(typed_experiment_id)
        if before is None or before.record.status is ExperimentStatus.DRAFT:
            return None
        match = _matching_receipt(
            reader.list_status_events(typed_experiment_id),
            identity,
            experiment_id=experiment_id,
        )
        if match is None:
            return None
        event, receipt = match
        expected_keys = {
            "experiment_id",
            "status",
            "revision",
            "candidate_count",
            "fold_count",
            "plan_hash",
        }
        if (
            set(receipt) != expected_keys
            or receipt["experiment_id"] != experiment_id
            or receipt["status"] != ExperimentStatus.QUEUED.value
            or receipt["revision"] != 1
            or type(receipt["candidate_count"]) is not int
            or type(receipt["fold_count"]) is not int
            or type(receipt["plan_hash"]) is not str
            or event.subject_type is not StatusSubjectType.EXPERIMENT
            or event.subject_revision != 1
            or event.experiment_id != typed_experiment_id
            or event.previous_status is not ExperimentStatus.DRAFT
            or event.status is not ExperimentStatus.QUEUED
            or event.reason_code != "preflight_passed"
        ):
            raise _error(
                "durable_enqueue_receipt_invalid",
                experiment_id=experiment_id,
            )
        base_detail = without_validated_mutation_receipt(event.detail)
        preflight = _mapping(
            base_detail.get("preflight"),
            experiment_id=experiment_id,
        )
        identities = _mapping(
            preflight.get("identities"),
            experiment_id=experiment_id,
        )
        request_hash = identities.get("request_hash")
        if type(request_hash) is not str:
            raise _error(
                "durable_enqueue_receipt_invalid",
                experiment_id=experiment_id,
            )
        replay = replay_verified_durable_enqueue(
            reader=reader,
            event=event,
            confirmed_plan_hash=receipt["plan_hash"],
            request_hash=request_hash,
            idempotency=identity,
        )
        if (
            replay.plan_hash != receipt["plan_hash"]
            or replay.candidate_count != receipt["candidate_count"]
            or replay.fold_count != receipt["fold_count"]
            or replay.projection.record.status is not ExperimentStatus.QUEUED
            or replay.projection.revision != 1
            or replay.projection.queue_ordinal is None
        ):
            raise _error(
                "durable_enqueue_receipt_invalid",
                experiment_id=experiment_id,
            )
        return replay
    raise _error("concurrent_experiment_update", experiment_id=experiment_id)


__all__ = [
    "bind_prepared_launch_idempotency",
    "try_replay_idempotent_launch",
]
