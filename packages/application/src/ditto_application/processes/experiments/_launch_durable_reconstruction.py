"""Reconstruct a prepared launch from one durable enqueue event."""

from __future__ import annotations

from typing import cast

import orjson
from ditto_analysis.experiments import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentReaderProtocol,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldPersistenceSpec,
    GateEvaluationRecord,
    StatusEventRecord,
    canonical_payload,
    encode_launch_spec,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import (
    without_validated_mutation_receipt,
)
from ditto_application.processes.experiments._creation_identity import (
    compile_creation_identity,
)
from ditto_application.processes.experiments._launch_contracts import (
    PreparedExperimentLaunch,
)
from ditto_application.processes.experiments._preflight_codec import (
    DecodedPreflightReport,
    decode_preflight_report,
)


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        f"experiment launch saga is inconsistent: {reason}",
        details={
            "code": "EXPERIMENT_LAUNCH_CONFLICT",
            "reason": reason,
            **details,
        },
    )


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _error("durable_enqueue_detail_invalid", field=field_name)
    return cast("dict[str, object]", value)


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise _error("durable_enqueue_detail_invalid", field=field_name)
    items = cast("list[object]", value)
    if not all(type(item) is str for item in items):
        raise _error("durable_enqueue_detail_invalid", field=field_name)
    return cast("tuple[str, ...]", tuple(items))


def _confirmed_detail(
    event: StatusEventRecord,
    *,
    confirmed_plan_hash: str,
    request_hash: str,
) -> tuple[dict[str, object], DecodedPreflightReport]:
    encoded = canonical_payload(event.detail)
    detail = _mapping(orjson.loads(encoded.json_bytes), "enqueue_detail")
    base = without_validated_mutation_receipt(detail)
    durable_plan_hash = base.get("plan_hash")
    if type(durable_plan_hash) is str and durable_plan_hash != confirmed_plan_hash:
        raise AppProcessError(
            "confirmed experiment plan hash is stale",
            details={
                "code": "PLAN_HASH_MISMATCH",
                "expected_plan_hash": durable_plan_hash,
                "confirmed_plan_hash": confirmed_plan_hash,
            },
        )
    report = decode_preflight_report(
        base,
        expected_policy_version="r3-experiment-preflight-v1",
    )
    preflight = _mapping(base.get("preflight"), "preflight")
    identities = _mapping(preflight.get("identities"), "identities")
    if report.plan_hash != confirmed_plan_hash:
        raise AppProcessError(
            "confirmed experiment plan hash is stale",
            details={
                "code": "PLAN_HASH_MISMATCH",
                "expected_plan_hash": report.plan_hash,
                "confirmed_plan_hash": confirmed_plan_hash,
            },
        )
    if identities.get("request_hash") != request_hash:
        raise AppProcessError(
            "experiment already exists with a different planning request",
            details={
                "code": "EXPERIMENT_ALREADY_EXISTS",
                "reason": "durable_launch_request_mismatch",
                "durable_request_hash": identities.get("request_hash"),
                "caller_request_hash": request_hash,
            },
        )
    return detail, report


def _ordered_gates(
    reader: ExperimentReaderProtocol,
    experiment_id: ExperimentId,
    hashes: tuple[str, ...],
) -> tuple[GateEvaluationRecord, ...]:
    actual = reader.list_gate_evaluations(experiment_id)
    by_hash = {str(item.payload_hash): item for item in actual}
    if len(by_hash) != len(actual) or not set(hashes).issubset(by_hash):
        raise _error(
            "gate_readback_set_mismatch",
            expected_gate_count=len(hashes),
            actual_gate_count=len(actual),
        )
    return tuple(by_hash[value] for value in hashes)


def _ordered_folds(
    reader: ExperimentReaderProtocol,
    experiment_id: ExperimentId,
    hashes: tuple[str, ...],
) -> tuple[FoldPersistenceSpec, ...]:
    actual = tuple(view.spec for view in reader.list_folds(experiment_id))
    by_hash = {str(item.payload_hash): item for item in actual}
    if (
        len(by_hash) != len(actual)
        or len(actual) != len(hashes)
        or set(hashes) != set(by_hash)
    ):
        raise _error(
            "fold_readback_set_mismatch",
            expected_fold_count=len(hashes),
            actual_fold_count=len(actual),
        )
    return tuple(by_hash[value] for value in hashes)


def reconstruct_prepared_launch(
    *,
    reader: ExperimentReaderProtocol,
    event: StatusEventRecord,
    confirmed_plan_hash: str,
    request_hash: str,
) -> tuple[PreparedExperimentLaunch, DecodedPreflightReport]:
    """Rebuild every immutable launch row referenced by the enqueue detail."""
    experiment_id = event.experiment_id
    detail, report = _confirmed_detail(
        event,
        confirmed_plan_hash=confirmed_plan_hash,
        request_hash=request_hash,
    )
    cycle = reader.get_research_cycle_identity(experiment_id)
    spec = reader.get_launch_spec(experiment_id)
    if cycle is None or spec is None:
        raise _error("partial_experiment_root", experiment_id=str(experiment_id))
    plan_preimage = _mapping(detail.get("plan_preimage"), "plan_preimage")
    gates = _ordered_gates(
        reader,
        experiment_id,
        _string_list(
            plan_preimage.get("gate_payload_hashes"),
            "plan_preimage.gate_payload_hashes",
        ),
    )
    folds = _ordered_folds(
        reader,
        experiment_id,
        _string_list(
            plan_preimage.get("fold_payload_hashes"),
            "plan_preimage.fold_payload_hashes",
        ),
    )
    launch_spec = encode_launch_spec(spec)
    preflight_payload = canonical_payload(
        _mapping(detail.get("preflight"), "preflight")
    )
    plan_preimage_payload = canonical_payload(plan_preimage)
    detail_payload = canonical_payload(detail)
    creation_detail, creation_payload = compile_creation_identity(
        request_hash=request_hash,
        plan_hash=report.plan_hash,
    )
    return (
        PreparedExperimentLaunch(
            cycle=cycle,
            spec=spec,
            initial_record=ExperimentRecord(
                experiment_id,
                ExperimentStatus.DRAFT,
                ExperimentDesiredState.RUN,
                ExperimentStage.PREFLIGHT,
                spec.created_at,
            ),
            gates=gates,
            folds=folds,
            launch_spec_json=launch_spec.json_bytes,
            launch_spec_hash=launch_spec.content_hash,
            gate_payload_hashes=tuple(item.payload_hash for item in gates),
            fold_payload_hashes=tuple(item.payload_hash for item in folds),
            preflight_json=preflight_payload.json_bytes,
            preflight_hash=preflight_payload.content_hash,
            plan_preimage_json=plan_preimage_payload.json_bytes,
            plan_hash=report.plan_hash,
            creation_detail=creation_detail,
            creation_detail_json=creation_payload.json_bytes,
            creation_detail_hash=creation_payload.content_hash,
            enqueue_detail=detail,
            enqueue_detail_json=detail_payload.json_bytes,
            enqueue_detail_hash=detail_payload.content_hash,
        ),
        report,
    )


__all__ = ["reconstruct_prepared_launch"]
