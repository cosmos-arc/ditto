"""Recoverable persistence saga for a fully prepared experiment launch."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import cast

import orjson
from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentReaderProtocol,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    ExperimentWriterProtocol,
    FoldProjection,
    ResearchCycleIdentity,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments.enqueue_fence import ExperimentEnqueueFence

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    find_mutation_receipt,
    without_validated_mutation_receipt,
)
from ditto_application.processes.experiments._creation_identity import (
    fence_durable_draft_launch,
    verify_creation_identity_payload,
    verify_durable_creation_identity,
)
from ditto_application.processes.experiments._launch_contracts import (
    DurableLaunchReplay,
    PreparedExperimentLaunch,
)
from ditto_application.processes.experiments._launch_durable_reconstruction import (
    reconstruct_prepared_launch,
)
from ditto_application.processes.experiments._launch_reconstruction import (
    validate_prepared_launch_rows,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)

__all__ = [
    "DurableLaunchReplay",
    "PreparedExperimentLaunch",
    "persist_prepared_launch",
    "replay_verified_durable_enqueue",
    "try_replay_durable_launch",
    "verify_prepared_launch",
]

_STABLE_ROOT_READ_ATTEMPTS = 3
_STABLE_AGGREGATE_READ_ATTEMPTS = 3


def _saga_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        f"experiment launch saga is inconsistent: {reason}",
        details={
            "code": "EXPERIMENT_LAUNCH_CONFLICT",
            "reason": reason,
            **details,
        },
    )


def _canonical_decoded_mapping(payload: bytes) -> Mapping[str, object]:
    decoded = cast("object", orjson.loads(payload))
    if type(decoded) is not dict:
        raise experiment_process_error("canonical payload root must be an object")
    mapping = cast("dict[str, object]", decoded)
    if canonical_payload(mapping).json_bytes != payload:
        raise experiment_process_error("payload bytes are not canonical")
    return mapping


def _content_hash(payload: bytes) -> ContentHash:
    return ContentHash(hashlib.sha256(payload).hexdigest())


def _verify_prepared_payloads(prepared: PreparedExperimentLaunch) -> None:
    launch = encode_launch_spec(prepared.spec)
    if (
        launch.json_bytes != prepared.launch_spec_json
        or launch.content_hash != prepared.launch_spec_hash
    ):
        raise experiment_process_error("launch_spec")
    preflight = _canonical_decoded_mapping(prepared.preflight_json)
    if _content_hash(prepared.preflight_json) != prepared.preflight_hash:
        raise experiment_process_error("preflight_hash")
    plan_preimage = _canonical_decoded_mapping(prepared.plan_preimage_json)
    if (
        _content_hash(prepared.plan_preimage_json).value != prepared.plan_hash
        or plan_preimage.get("launch_spec_hash") != str(prepared.launch_spec_hash)
        or plan_preimage.get("gate_payload_hashes")
        != [str(value) for value in prepared.gate_payload_hashes]
        or plan_preimage.get("fold_payload_hashes")
        != [str(value) for value in prepared.fold_payload_hashes]
        or plan_preimage.get("research_cycle_id") != prepared.cycle.cycle_id
        or plan_preimage.get("research_cycle_hash") != str(prepared.cycle.cycle_hash)
        or plan_preimage.get("preflight_hash") != str(prepared.preflight_hash)
    ):
        raise experiment_process_error("plan_preimage")
    verify_creation_identity_payload(
        detail=prepared.creation_detail,
        detail_json=prepared.creation_detail_json,
        detail_hash=prepared.creation_detail_hash,
        expected_request_hash=plan_preimage.get("request_hash"),
        expected_plan_hash=prepared.plan_hash,
        expected_idempotency=prepared.idempotency,
    )
    enqueue_detail = _canonical_decoded_mapping(prepared.enqueue_detail_json)
    preflight_from_detail = enqueue_detail.get("preflight")
    plan_preimage_from_detail = enqueue_detail.get("plan_preimage")
    if not isinstance(preflight_from_detail, Mapping):
        raise experiment_process_error("enqueue_preflight")
    if not isinstance(plan_preimage_from_detail, Mapping):
        raise experiment_process_error("enqueue_plan_preimage")
    if (
        canonical_payload(
            cast("Mapping[str, object]", preflight_from_detail)
        ).json_bytes
        != prepared.preflight_json
        or preflight_from_detail != preflight
        or canonical_payload(
            cast("Mapping[str, object]", plan_preimage_from_detail)
        ).json_bytes
        != prepared.plan_preimage_json
        or plan_preimage_from_detail != plan_preimage
        or enqueue_detail.get("preflight_hash") != str(prepared.preflight_hash)
        or enqueue_detail.get("plan_hash") != prepared.plan_hash
        or _content_hash(prepared.enqueue_detail_json) != prepared.enqueue_detail_hash
        or canonical_payload(prepared.enqueue_detail).json_bytes
        != prepared.enqueue_detail_json
    ):
        raise experiment_process_error("enqueue_detail")
    reconstruction_detail = without_validated_mutation_receipt(enqueue_detail)
    if prepared.idempotency is not None:
        try:
            receipt = find_mutation_receipt(
                (enqueue_detail,),
                prepared.idempotency,
            )
        except AppCommandError as exc:
            raise AppProcessError(str(exc), details=exc.details) from exc
        if receipt is None:
            raise experiment_process_error("enqueue_idempotency_receipt")
    validate_prepared_launch_rows(prepared, reconstruction_detail)


def _verify_prepared_initial_record(prepared: PreparedExperimentLaunch) -> None:
    initial = prepared.initial_record
    if (
        initial.experiment_id != prepared.spec.experiment_id
        or initial.status is not ExperimentStatus.DRAFT
        or initial.desired_state is not ExperimentDesiredState.RUN
        or initial.stage is not ExperimentStage.PREFLIGHT
        or initial.failure_code is not None
        or initial.created_at != prepared.spec.created_at
    ):
        raise experiment_process_error("initial_record")


def _verify_prepared_identity(prepared: PreparedExperimentLaunch) -> None:
    """Recompute every cross-linked identity before the first writer call."""
    try:
        _verify_prepared_payloads(prepared)
        _verify_prepared_initial_record(prepared)
    except Exception as exc:
        raise _saga_error(
            "prepared_launch_identity_mismatch",
            experiment_id=str(prepared.spec.experiment_id),
            identity_component=str(exc),
        ) from exc


def verify_prepared_launch(prepared: PreparedExperimentLaunch) -> None:
    """Public narrow verifier used by the orthogonal idempotency binder."""
    _verify_prepared_identity(prepared)


def _verify_immutable_root(
    *,
    projection: ExperimentProjection,
    cycle: ResearchCycleIdentity | None,
    spec: ExperimentLaunchSpec | None,
    prepared: PreparedExperimentLaunch,
) -> None:
    experiment_id = prepared.spec.experiment_id
    if cycle is None or spec is None:
        raise _saga_error(
            "partial_experiment_root",
            experiment_id=str(experiment_id),
        )
    encoded_spec = encode_launch_spec(spec)
    if (
        cycle.cycle_id != prepared.cycle.cycle_id
        or cycle.cycle_hash != prepared.cycle.cycle_hash
        or encoded_spec.json_bytes != prepared.launch_spec_json
        or encoded_spec.content_hash != prepared.launch_spec_hash
        or projection.record.experiment_id != experiment_id
        or projection.record.created_at != prepared.spec.created_at
    ):
        raise AppProcessError(
            "experiment already exists with a different immutable planning identity",
            details={
                "code": "EXPERIMENT_ALREADY_EXISTS",
                "reason": "immutable_experiment_replay_drift",
                "experiment_id": str(experiment_id),
            },
        )


def _stable_root(
    reader: ExperimentReaderProtocol,
    prepared: PreparedExperimentLaunch,
) -> ExperimentProjection | None:
    """Read one root through a bounded revision bracket."""
    experiment_id = prepared.spec.experiment_id
    for _ in range(_STABLE_ROOT_READ_ATTEMPTS):
        before = reader.get_experiment_projection(experiment_id)
        if before is None:
            # A concurrent exact creator is arbitrated by create_experiment.
            return None
        cycle = reader.get_research_cycle_identity(experiment_id)
        spec = reader.get_launch_spec(experiment_id)
        after = reader.get_experiment_projection(experiment_id)
        if after is None or before != after:
            continue
        _verify_immutable_root(
            projection=after,
            cycle=cycle,
            spec=spec,
            prepared=prepared,
        )
        return after
    raise _saga_error(
        "concurrent_experiment_update",
        experiment_id=str(experiment_id),
    )


def _verify_children(
    reader: ExperimentReaderProtocol,
    prepared: PreparedExperimentLaunch,
    *,
    require_initial_projection: bool,
) -> None:
    actual_gates = reader.list_gate_evaluations(prepared.spec.experiment_id)
    actual_gates_by_id = {gate.evaluation_id: gate for gate in actual_gates}
    expected_gates_by_id = {gate.evaluation_id: gate for gate in prepared.gates}
    actual_ids = set(actual_gates_by_id)
    expected_ids = set(expected_gates_by_id)
    valid_set = (
        actual_ids == expected_ids
        if require_initial_projection
        else expected_ids.issubset(actual_ids)
    )
    if len(actual_gates_by_id) != len(actual_gates) or not valid_set:
        raise _saga_error(
            "gate_readback_set_mismatch",
            expected_gate_count=len(expected_ids),
            actual_gate_count=len(actual_ids),
        )
    expected_hash_by_id = {
        gate.evaluation_id: payload_hash
        for gate, payload_hash in zip(
            prepared.gates, prepared.gate_payload_hashes, strict=True
        )
    }
    for evaluation_id, expected_hash in expected_hash_by_id.items():
        actual = actual_gates_by_id.get(evaluation_id)
        if actual is None or actual.payload_hash != expected_hash:
            raise _saga_error(
                "gate_readback_mismatch",
                evaluation_id=evaluation_id,
            )
    actual_folds = reader.list_folds(prepared.spec.experiment_id)
    actual_by_key = {view.spec.key: view for view in actual_folds}
    expected_by_key = {fold.key: fold for fold in prepared.folds}
    if set(actual_by_key) != set(expected_by_key):
        raise _saga_error(
            "fold_readback_set_mismatch",
            expected_fold_count=len(expected_by_key),
            actual_fold_count=len(actual_by_key),
        )
    for key, expected in expected_by_key.items():
        actual = actual_by_key[key]
        immutable_matches = (
            actual.spec.key == key
            and actual.spec.canonical_payload == expected.canonical_payload
            and actual.spec.payload_hash == expected.payload_hash
            and actual.projection.key == key
            and type(actual.projection.revision) is int
            and actual.projection.revision >= 0
        )
        initial_matches = (
            actual.projection.status is ExperimentStatus.QUEUED
            and actual.projection.claim_owner_token is None
            and actual.projection.created_at == prepared.spec.created_at
            and actual.projection.updated_at == prepared.spec.created_at
            and actual.projection.revision == 0
        )
        if not immutable_matches or (
            require_initial_projection and not initial_matches
        ):
            raise _saga_error(
                "fold_readback_mismatch",
                fold_id=str(key.fold_id),
            )


def _verify_enqueue_event(
    reader: ExperimentReaderProtocol,
    prepared: PreparedExperimentLaunch,
) -> StatusEventRecord:
    experiment_id = prepared.spec.experiment_id
    events = tuple(
        event
        for event in reader.list_status_events(experiment_id)
        if event.subject_type is StatusSubjectType.EXPERIMENT
        and event.subject_revision == 1
    )
    if len(events) != 1:
        raise _saga_error(
            "enqueue_event_missing_or_duplicate",
            experiment_id=str(experiment_id),
            event_count=len(events),
        )
    event = events[0]
    detail = canonical_payload(event.detail)
    if (
        detail.json_bytes != prepared.enqueue_detail_json
        or detail.content_hash != prepared.enqueue_detail_hash
        or event.detail_hash != prepared.enqueue_detail_hash
    ):
        raise _saga_error(
            "enqueue_event_preflight_detail_mismatch",
            experiment_id=str(experiment_id),
        )
    if (
        event.experiment_id != experiment_id
        or event.candidate_id is not None
        or event.fold_id is not None
        or event.attempt_id is not None
        or event.previous_status is not ExperimentStatus.DRAFT
        or event.status is not ExperimentStatus.QUEUED
        or event.desired_state is not ExperimentDesiredState.RUN
        or event.stage is not ExperimentStage.PREFLIGHT
        or event.failure_code is not None
        or event.reason_code != "preflight_passed"
        or event.occurred_at != prepared.spec.created_at
    ):
        raise _saga_error(
            "enqueue_event_readback_mismatch",
            experiment_id=str(experiment_id),
        )
    return event


def _is_progressed(projection: ExperimentProjection) -> bool:
    return (
        projection.record.status
        not in {ExperimentStatus.DRAFT, ExperimentStatus.BLOCKED}
        and projection.queue_ordinal is not None
        and projection.revision >= 1
    )


def _original_enqueue_projection(
    *,
    current: ExperimentProjection,
    event: StatusEventRecord,
    prepared: PreparedExperimentLaunch,
) -> ExperimentProjection:
    if current.queue_ordinal is None:
        raise _saga_error(
            "queued_projection_mismatch",
            experiment_id=str(prepared.spec.experiment_id),
            status=current.record.status.value,
        )
    return ExperimentProjection(
        record=ExperimentRecord(
            experiment_id=prepared.spec.experiment_id,
            status=ExperimentStatus.QUEUED,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=prepared.spec.created_at,
        ),
        queue_ordinal=current.queue_ordinal,
        revision=1,
        updated_at=event.occurred_at,
    )


def _replay_progressed_aggregate(
    reader: ExperimentReaderProtocol,
    prepared: PreparedExperimentLaunch,
) -> ExperimentProjection:
    experiment_id = prepared.spec.experiment_id
    for _ in range(_STABLE_AGGREGATE_READ_ATTEMPTS):
        before = _stable_root(reader, prepared)
        if before is None or not _is_progressed(before):
            raise _saga_error(
                "experiment_not_replayable",
                experiment_id=str(experiment_id),
                status=("missing" if before is None else before.record.status.value),
                revision=(-1 if before is None else before.revision),
            )
        _verify_children(
            reader,
            prepared,
            require_initial_projection=False,
        )
        event = _verify_enqueue_event(reader, prepared)
        after = _stable_root(reader, prepared)
        if after is not None and after == before:
            return _original_enqueue_projection(
                current=after,
                event=event,
                prepared=prepared,
            )
    raise _saga_error(
        "concurrent_experiment_update",
        experiment_id=str(experiment_id),
    )


def _require_draft(
    projection: ExperimentProjection,
    prepared: PreparedExperimentLaunch,
) -> None:
    if (
        projection.record.status is not ExperimentStatus.DRAFT
        or projection.revision != 0
        or projection.queue_ordinal is not None
    ):
        raise _saga_error(
            "experiment_not_replayable",
            experiment_id=str(prepared.spec.experiment_id),
            status=projection.record.status.value,
            revision=projection.revision,
        )


def _verify_draft_children_or_replay(
    reader: ExperimentReaderProtocol,
    prepared: PreparedExperimentLaunch,
) -> ExperimentProjection | None:
    try:
        _verify_children(reader, prepared, require_initial_projection=True)
    except AppProcessError:
        concurrent = _stable_root(reader, prepared)
        if concurrent is None or not _is_progressed(concurrent):
            raise
        return _replay_progressed_aggregate(reader, prepared)
    return None


def _first_enqueue_event(
    reader: ExperimentReaderProtocol,
    experiment_id: ExperimentId,
) -> StatusEventRecord:
    events = tuple(
        event
        for event in reader.list_status_events(experiment_id)
        if event.subject_type is StatusSubjectType.EXPERIMENT
        and event.subject_revision == 1
    )
    if len(events) != 1:
        raise _saga_error(
            "enqueue_event_missing_or_duplicate",
            experiment_id=str(experiment_id),
            event_count=len(events),
        )
    return events[0]


def replay_verified_durable_enqueue(
    *,
    reader: ExperimentReaderProtocol,
    event: StatusEventRecord,
    confirmed_plan_hash: str,
    request_hash: str,
    idempotency: MutationIdempotency | None = None,
) -> DurableLaunchReplay:
    """Reconstruct and strictly verify the complete durable launch aggregate."""
    verify_durable_creation_identity(
        events=reader.list_status_events(event.experiment_id),
        experiment_id=event.experiment_id,
        expected_request_hash=request_hash,
        expected_plan_hash=confirmed_plan_hash,
        expected_idempotency=idempotency,
    )
    prepared, report = reconstruct_prepared_launch(
        reader=reader,
        event=event,
        confirmed_plan_hash=confirmed_plan_hash,
        request_hash=request_hash,
    )
    _verify_prepared_identity(prepared)
    return DurableLaunchReplay(
        projection=_replay_progressed_aggregate(reader, prepared),
        candidate_count=report.candidate_count,
        fold_count=report.planned_fold_count,
        plan_hash=report.plan_hash,
    )


def try_replay_durable_launch(
    *,
    reader: ExperimentReaderProtocol,
    experiment_id: str,
    confirmed_plan_hash: str,
    request_hash_factory: Callable[[], str],
    idempotency: MutationIdempotency | None = None,
) -> DurableLaunchReplay | None:
    """Replay a committed enqueue before any external planning probe is called."""
    typed_experiment_id = ExperimentId(experiment_id)
    request_hash: str | None = None
    for _ in range(_STABLE_AGGREGATE_READ_ATTEMPTS):
        before = reader.get_experiment_projection(typed_experiment_id)
        if before is None:
            return None
        if before.record.status is ExperimentStatus.DRAFT:
            if request_hash is None:
                request_hash = request_hash_factory()
            if fence_durable_draft_launch(
                reader=reader,
                experiment_id=experiment_id,
                confirmed_plan_hash=confirmed_plan_hash,
                request_hash=request_hash,
                idempotency=idempotency,
            ):
                return None
            continue
        if not _is_progressed(before):
            raise _saga_error(
                "experiment_not_replayable",
                experiment_id=experiment_id,
                status=before.record.status.value,
                revision=before.revision,
            )
        if request_hash is None:
            request_hash = request_hash_factory()
        event = _first_enqueue_event(reader, typed_experiment_id)
        replay = replay_verified_durable_enqueue(
            reader=reader,
            event=event,
            confirmed_plan_hash=confirmed_plan_hash,
            request_hash=request_hash,
            idempotency=idempotency,
        )
        after = reader.get_experiment_projection(typed_experiment_id)
        if after is None or after != before:
            continue
        return replay
    raise _saga_error(
        "concurrent_experiment_update",
        experiment_id=experiment_id,
    )


def persist_prepared_launch(
    *,
    reader: ExperimentReaderProtocol,
    writer: ExperimentWriterProtocol,
    prepared: PreparedExperimentLaunch,
) -> ExperimentProjection:
    """Replay DRAFT assembly exactly and make enqueue the final mutation."""
    experiment_id = prepared.spec.experiment_id
    _verify_prepared_identity(prepared)
    existing = _stable_root(reader, prepared)
    if existing is not None and _is_progressed(existing):
        return _replay_progressed_aggregate(reader, prepared)
    if existing is not None:
        _require_draft(existing, prepared)

    writer.create_experiment(
        prepared.cycle,
        prepared.spec,
        prepared.initial_record,
        creation_detail=prepared.creation_detail,
    )
    for gate in prepared.gates:
        writer.add_gate_evaluation(gate)
    for fold in prepared.folds:
        writer.add_fold(
            fold,
            FoldProjection(
                key=fold.key,
                status=ExperimentStatus.QUEUED,
                claim_owner_token=None,
                created_at=prepared.spec.created_at,
                updated_at=prepared.spec.created_at,
                revision=0,
            ),
        )

    projection = _stable_root(reader, prepared)
    if projection is None:
        raise _saga_error(
            "experiment_missing_before_enqueue",
            experiment_id=str(experiment_id),
        )
    if _is_progressed(projection):
        return _replay_progressed_aggregate(reader, prepared)
    _require_draft(projection, prepared)
    replay = _verify_draft_children_or_replay(reader, prepared)
    if replay is not None:
        return replay

    try:
        writer.enqueue_experiment(
            experiment_id,
            expected_revision=0,
            occurred_at=prepared.spec.created_at,
            reason_code="preflight_passed",
            detail=prepared.enqueue_detail,
            launch_fence=ExperimentEnqueueFence.create(
                gates=prepared.gates,
                folds=prepared.folds,
            ),
        )
    except AnalysisError:
        concurrent = _stable_root(reader, prepared)
        if concurrent is None or not _is_progressed(concurrent):
            raise
        return _replay_progressed_aggregate(reader, prepared)
    return _replay_progressed_aggregate(reader, prepared)
