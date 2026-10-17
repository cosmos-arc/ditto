"""
Decode model-candidate planning envelopes into execution identities (#565 W2).

Single authority shared by the executor probe, the durable resolver, and the
model fold runner: one ``ModelCandidateDescriptor`` payload becomes exactly
one validated lineage, one set of three content-addressed training inputs,
and one top-k control. Every consumer decodes through here so the envelope
contract has one frozen interpretation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ditto_analysis.errors import AnalysisError, ExperimentSpecError
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    model_candidate_lineage_from_payload,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    MODEL_FOLD_INPUT_KINDS,
    ModelFoldInputEvidence,
)
from ditto_application.processes.experiments.planning import (
    ModelCandidateDescriptor,
)

__all__ = [
    "DecodedModelCandidatePlan",
    "decode_model_candidate_descriptor",
    "model_descriptor_hash",
]


def _plan_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model candidate planning envelope is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


def model_descriptor_hash(descriptor: ModelCandidateDescriptor) -> str:
    """Return the canonical content identity of one model descriptor."""
    return hashlib.sha256(
        descriptor.canonical_json.encode("utf-8"),
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class DecodedModelCandidatePlan:
    """Validated execution identity decoded from one planning envelope."""

    lineage: ModelCandidateLineage
    inputs: tuple[ModelFoldInputEvidence, ...]
    top_k: int


def _decode_input_evidence(
    kind: str,
    raw: object,
) -> ModelFoldInputEvidence:
    if not isinstance(raw, Mapping):
        raise _plan_error("model_input_evidence_invalid", input_kind=kind)
    payload = cast("Mapping[str, object]", raw)
    sources = payload.get("source_snapshot_ids")
    if type(sources) not in (list, tuple) or any(
        type(item) is not str for item in cast("tuple[object, ...]", sources)
    ):
        raise _plan_error(
            "model_input_source_snapshots_invalid",
            input_kind=kind,
        )
    try:
        return ModelFoldInputEvidence(
            input_kind=kind,
            input_id=cast("str", payload.get("input_id")),
            content_hash=cast("str", payload.get("content_hash")),
            schema_hash=cast("str", payload.get("schema_hash")),
            source_snapshot_ids=tuple(cast("tuple[str, ...]", sources)),
        )
    except AppProcessError as error:
        reason = error.details.get("reason")
        raise _plan_error(
            str(reason) if type(reason) is str else "model_input_evidence_invalid",
            input_kind=kind,
        ) from error


def decode_model_candidate_descriptor(
    descriptor: ModelCandidateDescriptor,
) -> DecodedModelCandidatePlan:
    """Decode and fully validate one model-candidate planning envelope."""
    if type(cast("object", descriptor)) is not ModelCandidateDescriptor:
        raise _plan_error("model_descriptor_invalid")
    payload = descriptor.payload
    raw_lineage = payload.get("lineage")
    if not isinstance(raw_lineage, Mapping):
        raise _plan_error("model_lineage_payload_invalid")
    try:
        lineage = model_candidate_lineage_from_payload(
            cast("Mapping[str, object]", raw_lineage),
        )
    except (AnalysisError, ExperimentSpecError) as error:
        reason = error.details.get("reason")
        raise _plan_error(
            str(reason) if type(reason) is str else "model_lineage_invalid",
        ) from error
    if lineage.model_kind.value != descriptor.descriptor_type:
        raise _plan_error(
            "model_descriptor_type_drift",
            descriptor_type=descriptor.descriptor_type,
            model_kind=lineage.model_kind.value,
        )
    raw_inputs = payload.get("inputs")
    if not isinstance(raw_inputs, Mapping):
        raise _plan_error("model_inputs_payload_invalid")
    inputs_payload = cast("Mapping[str, object]", raw_inputs)
    if set(inputs_payload) != set(MODEL_FOLD_INPUT_KINDS):
        raise _plan_error(
            "model_inputs_kinds_invalid",
            expected=sorted(MODEL_FOLD_INPUT_KINDS),
        )
    inputs = tuple(
        _decode_input_evidence(kind, inputs_payload.get(kind))
        for kind in sorted(MODEL_FOLD_INPUT_KINDS)
    )
    top_k = payload.get("top_k")
    if type(top_k) is not int or top_k <= 0:
        raise _plan_error("model_top_k_invalid")
    return DecodedModelCandidatePlan(
        lineage=lineage,
        inputs=inputs,
        top_k=top_k,
    )
