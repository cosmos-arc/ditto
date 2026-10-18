"""Unit tests for model-candidate planning, decoding, and bindings (#565 W2)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import cast

import orjson
import pytest
from ditto_analysis.experiments import canonical_payload
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    ModelKind,
    TrainFittedTransformSpec,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    MODEL_CANDIDATE_IMPLEMENTATION_KEY,
    ModelCandidateExecutionBinding,
)
from ditto_application.processes.experiments._planning_values import (
    BaselineInputValue,
)
from ditto_application.processes.experiments.model_candidate_folds import (
    ModelFoldInputEvidence,
)
from ditto_application.processes.experiments.model_candidate_plans import (
    decode_model_candidate_descriptor,
    model_descriptor_hash,
)
from ditto_application.processes.experiments.planning import (
    MODEL_PARAMETER_KEY,
    BaselineDescriptor,
    CandidateMatrixSpec,
    CandidateRole,
    ModelCandidateDescriptor,
    ParameterAxis,
    expand_candidate_matrix,
    inspect_candidate_matrix_size,
)
from ditto_application.processes.experiments.planning_document_codec import (
    candidate_matrix_spec_payload,
    decode_candidate_matrix_spec,
)

_SOURCE = "snap-model-1"


def _lineage(kind: ModelKind = ModelKind.LINEAR) -> ModelCandidateLineage:
    hyperparameters: dict[str, object] = (
        {"alpha": 1.0}
        if kind is ModelKind.LINEAR
        else {"ranking_feature": "momentum_20d"}
    )
    return ModelCandidateLineage(
        model_kind=kind,
        feature_names=("momentum_20d", "ep_ttm"),
        label_id="research.label.forward_return.next_open_hold5.v1",
        label_spec_hash="a" * 64,
        transform_spec=TrainFittedTransformSpec(),
        hyperparameters=hyperparameters,
        seed=7,
        code_environment={
            "implementation_key": "ditto_application.model_candidates.ridge.v1",
            "python": "3.13.14",
            "lockfile_sha256": "b" * 64,
        },
    )


def _input_payload(kind: str) -> dict[str, object]:
    digest = hashlib.sha256(kind.encode()).hexdigest()
    return {
        "input_id": f"model-input-{kind}",
        "content_hash": digest,
        "schema_hash": digest,
        "source_snapshot_ids": [_SOURCE],
    }


def _model_payload(
    lineage: ModelCandidateLineage | None = None,
    *,
    top_k: object = 3,
) -> Mapping[str, BaselineInputValue]:
    return cast(
        "dict[str, BaselineInputValue]",
        {
            "lineage": (lineage or _lineage()).canonical_payload(),
            "inputs": {
                "label_prices": _input_payload("label_prices"),
                "features": _input_payload("features"),
                "calendar": _input_payload("calendar"),
            },
            "top_k": top_k,
        },
    )


def _model_descriptor(
    payload: Mapping[str, BaselineInputValue] | None = None,
) -> ModelCandidateDescriptor:
    return ModelCandidateDescriptor(
        descriptor_type="linear",
        payload=payload if payload is not None else _model_payload(),
    )


def _baseline() -> BaselineDescriptor:
    return BaselineDescriptor(
        descriptor_type="etf-current-active",
        payload={"strategy_id": "seed_etf_rotation", "version": 2},
    )


def test_model_descriptor_freezes_canonical_json_and_validates_payload() -> None:
    descriptor = _model_descriptor()
    assert descriptor.canonical_json.startswith("{")
    assert (
        ModelCandidateDescriptor(
            descriptor_type="linear",
            payload=_model_payload(),
        ).canonical_json
        == descriptor.canonical_json
    )

    for bad_payload in (
        {"lineage": {}, "inputs": {}, "top_k": 1, "extra": 1},
        {"lineage": {}, "inputs": {}},
        {"lineage": {}, "inputs": {}, "top_k": 0},
        {"lineage": {}, "inputs": {}, "top_k": True},
        {"lineage": "not-a-mapping", "inputs": {}, "top_k": 1},
        {"lineage": {}, "inputs": "not-a-mapping", "top_k": 1},
    ):
        with pytest.raises(AppProcessError) as error:
            ModelCandidateDescriptor(
                descriptor_type="linear",
                payload=cast("Mapping[str, BaselineInputValue]", bad_payload),
            )
        reason = error.value.details["reason"]
        assert type(reason) is str
        assert reason.startswith("invalid_model_descriptor")

    with pytest.raises(AppProcessError) as error:
        ModelCandidateDescriptor(descriptor_type=" ", payload=_model_payload())
    assert error.value.details["reason"] == "invalid_model_descriptor_type"


def test_matrix_expands_model_candidates_after_binder_candidates() -> None:
    matrix = CandidateMatrixSpec(
        baseline=_baseline(),
        axes=(
            ParameterAxis(
                name="rebalance_sessions",
                values=(5, 10),
            ),
        ),
        model_candidates=(_model_descriptor(),),
    )
    plan = expand_candidate_matrix(matrix)

    assert [candidate.ordinal for candidate in plan.candidates] == [1, 2, 3, 4]
    model = plan.model_candidates[0]
    assert model.ordinal == 4
    assert model.role is CandidateRole.MODEL
    assert set(model.persistence_parameters) == {MODEL_PARAMETER_KEY}
    assert model.persistence_parameters[MODEL_PARAMETER_KEY] == (
        model.descriptor.canonical_json
    )
    assert plan.candidate_count == 4
    assert inspect_candidate_matrix_size(matrix).candidate_count == 4
    # The model hash depends on the envelope, so a changed payload changes it.
    other = expand_candidate_matrix(
        CandidateMatrixSpec(
            baseline=_baseline(),
            axes=(ParameterAxis(name="rebalance_sessions", values=(5, 10)),),
            model_candidates=(
                _model_descriptor(
                    _model_payload(top_k=4),
                ),
            ),
        )
    )
    assert other.model_candidates[0].candidate_hash != model.candidate_hash
    assert other.matrix_hash != plan.matrix_hash


def test_matrix_rejects_duplicate_and_reserved_model_envelopes() -> None:
    descriptor = _model_descriptor()
    with pytest.raises(AppProcessError) as error:
        CandidateMatrixSpec(
            baseline=_baseline(),
            model_candidates=(descriptor, _model_descriptor()),
        )
    assert error.value.details["reason"] == "duplicate_matrix_model_candidate"

    with pytest.raises(AppProcessError) as error:
        ParameterAxis(name=MODEL_PARAMETER_KEY, values=(1,))
    assert error.value.details["reason"] == "reserved_matrix_parameter_name"


def test_matrix_codec_round_trips_model_candidates_and_stays_v2_compatible() -> None:
    matrix = CandidateMatrixSpec(
        baseline=_baseline(),
        model_candidates=(_model_descriptor(),),
    )
    payload = candidate_matrix_spec_payload(matrix)
    assert "model_candidates" in payload
    # Documents always travel as canonical JSON; decode from decoded JSON.
    document = orjson.loads(canonical_payload(dict(payload)).json_bytes)
    decoded = decode_candidate_matrix_spec(document)
    assert decoded == matrix

    legacy_document = dict(document)
    del legacy_document["model_candidates"]
    legacy = decode_candidate_matrix_spec(legacy_document)
    assert legacy.model_candidates == ()
    # Empty matrices keep the legacy document shape (no key at all).
    assert "model_candidates" not in candidate_matrix_spec_payload(legacy)


def test_decode_model_candidate_descriptor_validates_every_layer() -> None:
    decoded = decode_model_candidate_descriptor(_model_descriptor())
    assert decoded.lineage.registration_hash == _lineage().registration_hash
    assert decoded.top_k == 3
    assert tuple(sorted(item.input_kind for item in decoded.inputs)) == (
        "calendar",
        "features",
        "label_prices",
    )
    assert decoded.inputs[0].source_snapshot_ids == (_SOURCE,)

    # descriptor_type must mirror the registered model kind.
    with pytest.raises(AppProcessError) as error:
        decode_model_candidate_descriptor(
            ModelCandidateDescriptor(
                descriptor_type="rule",
                payload=_model_payload(_lineage(ModelKind.LINEAR)),
            )
        )
    assert error.value.details["reason"] == "model_descriptor_type_drift"

    # Missing input kinds fail closed.
    payload = _model_payload()
    inputs = cast("dict[str, BaselineInputValue]", payload["inputs"])
    del inputs["calendar"]
    with pytest.raises(AppProcessError) as error:
        decode_model_candidate_descriptor(_model_descriptor(payload))
    assert error.value.details["reason"] == "model_inputs_kinds_invalid"

    # Invalid lineage payloads surface the analysis-layer reason.
    payload = _model_payload()
    lineage = cast("dict[str, object]", payload["lineage"])
    lineage["model_kind"] = "unknown-kind"
    with pytest.raises(AppProcessError) as error:
        decode_model_candidate_descriptor(_model_descriptor(payload))
    assert error.value.details["reason"] == "model_kind_invalid"


def test_model_candidate_execution_binding_freezes_the_claim_time_plan() -> None:
    lineage = _lineage()
    inputs = tuple(
        ModelFoldInputEvidence(
            input_kind=kind,
            input_id=f"model-input-{kind}",
            content_hash=hashlib.sha256(kind.encode()).hexdigest(),
            schema_hash=hashlib.sha256(kind.encode()).hexdigest(),
            source_snapshot_ids=(_SOURCE,),
        )
        for kind in ("label_prices", "features", "calendar")
    )
    binding = ModelCandidateExecutionBinding(
        model_kind="linear",
        lineage_hash=lineage.registration_hash,
        lineage_payload=lineage.canonical_payload(),
        inputs=inputs,
        top_k=3,
        trained_at_epoch_us=2_000,
        knowledge_cutoff_epoch_us=1_000,
        implementation_key=MODEL_CANDIDATE_IMPLEMENTATION_KEY,
        executor_contract_version=1,
    )
    assert len(binding.binding_hash) == 64
    assert [item.input_kind for item in binding.inputs] == [
        "calendar",
        "features",
        "label_prices",
    ]

    with pytest.raises(AppProcessError) as error:
        ModelCandidateExecutionBinding(
            model_kind="linear",
            lineage_hash=lineage.registration_hash,
            lineage_payload=lineage.canonical_payload(),
            inputs=inputs,
            top_k=3,
            trained_at_epoch_us=1_000,
            knowledge_cutoff_epoch_us=2_000,
            implementation_key=MODEL_CANDIDATE_IMPLEMENTATION_KEY,
            executor_contract_version=1,
        )
    assert error.value.details["reason"] == "invalid_model_candidate_binding"

    duplicated_ids = tuple(
        ModelFoldInputEvidence(
            input_kind=kind,
            input_id="same-input",
            content_hash=hashlib.sha256(kind.encode()).hexdigest(),
            schema_hash=hashlib.sha256(kind.encode()).hexdigest(),
            source_snapshot_ids=(_SOURCE,),
        )
        for kind in ("label_prices", "features", "calendar")
    )
    with pytest.raises(AppProcessError) as error:
        ModelCandidateExecutionBinding(
            model_kind="linear",
            lineage_hash=lineage.registration_hash,
            lineage_payload=lineage.canonical_payload(),
            inputs=duplicated_ids,
            top_k=3,
            trained_at_epoch_us=2_000,
            knowledge_cutoff_epoch_us=1_000,
            implementation_key=MODEL_CANDIDATE_IMPLEMENTATION_KEY,
            executor_contract_version=1,
        )
    assert error.value.details["reason"] == "invalid_model_candidate_binding"


def test_model_descriptor_hash_is_content_addressed() -> None:
    assert model_descriptor_hash(_model_descriptor()) == model_descriptor_hash(
        _model_descriptor()
    )
    assert model_descriptor_hash(_model_descriptor()) != model_descriptor_hash(
        _model_descriptor(_model_payload(top_k=4))
    )
