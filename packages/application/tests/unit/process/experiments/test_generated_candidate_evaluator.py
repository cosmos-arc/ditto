"""Generated research-code host contract and trusted evaluator tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from io import BytesIO
from typing import cast

import numpy as np
import orjson
import polars as pl
import pytest
from ditto_analysis.experiments.campaign import (
    EvaluationResult,
    ExperimentPlan,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxResourceLimits,
    canonical_research_ast_hash,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    SnapshotId,
)
from ditto_analysis.experiments.specs import CandidateSpec, FoldProtocolSpec
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    generated_candidate_evaluator as evaluator_module,
)
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    FrozenSandboxArtifact,
    FrozenSandboxWindow,
    SandboxArtifactFormat,
    SandboxExecutionResult,
    SandboxFitRequest,
    SandboxScoreKey,
    SandboxScoreRequest,
    build_successful_sandbox_result,
    freeze_sandbox_artifact,
)
from ditto_application.processes.experiments.generated_candidate_evaluator import (
    CandidateScoreRow,
    GeneratedCandidateEvaluationRequest,
    GeneratedCandidateEvaluator,
    TrustedCandidateEvaluationPort,
    TrustedCandidateEvaluationRequest,
)

INPUT_SCHEMA_HASH = ContentHash("1" * 64)
OUTPUT_SCHEMA_HASH = ContentHash("2" * 64)
STATE_SCHEMA_HASH = ContentHash("3" * 64)
SNAPSHOT_ID = SnapshotId("snapshot-r5-generated-code")
SEED = 41
SOURCE = (
    "def fit(training_stream):\n"
    "    return {'mean': 0.0}\n"
    "def score(visible_window, immutable_model_state):\n"
    "    return [{'entity_id': row['entity_id'], "
    "'event_time_epoch_us': row['event_time_epoch_us'], 'score': 0.5} "
    "for row in visible_window]\n"
)


def _hash(value: bytes | str) -> ContentHash:
    raw = value.encode() if isinstance(value, str) else value
    return ContentHash(hashlib.sha256(raw).hexdigest())


def _code(source: str = SOURCE) -> ResearchCodeArtifact:
    return ResearchCodeArtifact(
        source_code=source,
        source_hash=_hash(source),
        canonical_ast_hash=canonical_research_ast_hash(source),
        dependency_lock_hash=ContentHash("5" * 64),
        dependencies=("numpy==2.3.2", "polars==1.32.2"),
        image_digest=ContentHash("6" * 64),
        input_schema_hash=INPUT_SCHEMA_HASH,
        output_schema_hash=OUTPUT_SCHEMA_HASH,
    )


def _artifact(
    payload: object,
    *,
    schema_hash: ContentHash,
    row_count: int,
) -> FrozenSandboxArtifact:
    return freeze_sandbox_artifact(
        orjson.dumps(payload, option=orjson.OPT_SORT_KEYS),
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=schema_hash,
        row_count=row_count,
    )


def _window() -> FrozenSandboxWindow:
    keys = (
        SandboxScoreKey(
            "510300.SH",
            1_700_000_000_000_000,
            1_699_999_000_000_000,
            1_699_998_000_000_000,
            1_700_001_000_000_000,
        ),
        SandboxScoreKey(
            "510500.SH",
            1_700_000_000_000_000,
            1_699_999_100_000_000,
            1_699_998_100_000_000,
            1_700_001_000_000_000,
        ),
    )
    return FrozenSandboxWindow(
        artifact=_artifact(
            {
                "schema_id": "r5-visible-window",
                "schema_version": 1,
                "rows": [
                    {
                        "entity_id": key.entity_id,
                        "event_time_epoch_us": key.event_time_epoch_us,
                        "known_at_epoch_us": key.known_at_epoch_us,
                        "value": index + 1.0,
                    }
                    for index, key in enumerate(keys)
                ],
            },
            schema_hash=INPUT_SCHEMA_HASH,
            row_count=2,
        ),
        snapshot_id=SNAPSHOT_ID,
        decision_time_epoch_us=1_700_000_000_000_000,
        knowledge_cutoff_epoch_us=1_700_000_000_000_000,
        publication_cutoff_epoch_us=1_699_999_000_000_000,
        score_keys=keys,
    )


def _candidate(code: ResearchCodeArtifact) -> ResearchCandidateSpec:
    return ResearchCandidateSpec(
        candidate=CandidateSpec(
            candidate_id=CandidateId("candidate-generated-1"),
            ordinal=1,
            is_baseline=False,
            parameters={"lookback": 20},
        ),
        search_axis=SearchAxis.FACTOR_CODE,
        parent_candidate_id=CandidateId("candidate-baseline"),
        factor_code_hash=code.artifact_hash,
        model_code_hash=None,
        data_requirement_hashes=(ContentHash("7" * 64),),
    )


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        fold_protocol=FoldProtocolSpec(
            protocol_id="walk-forward-r5",
            protocol_version=1,
            protocol_hash=ContentHash("8" * 64),
        ),
        snapshot_id=SNAPSHOT_ID,
        validation_objective_hash=ContentHash("9" * 64),
        cost_model_hash=ContentHash("a" * 64),
        seed=SEED,
        purge_sessions=5,
        embargo_sessions=2,
    )


def _score_payload(*, extra: dict[str, object] | None = None) -> object:
    rows = [
        {
            "entity_id": key.entity_id,
            "event_time_epoch_us": key.event_time_epoch_us,
            "score": 0.5 + index * 0.1,
            **(extra or {}),
        }
        for index, key in enumerate(_window().score_keys)
    ]
    return {
        "schema_id": "r5-candidate-score-frame",
        "schema_version": 1,
        "rows": rows,
    }


class _FakeSandbox(CandidateSandboxPort):
    def __init__(
        self,
        *,
        score_payloads: tuple[object, ...] | None = None,
        output_schema_hash: ContentHash = OUTPUT_SCHEMA_HASH,
        declared_row_count: int = 2,
    ) -> None:
        self.score_payloads = score_payloads or (_score_payload(), _score_payload())
        self.output_schema_hash = output_schema_hash
        self.declared_row_count = declared_row_count
        self.fit_requests: list[SandboxFitRequest] = []
        self.score_requests: list[SandboxScoreRequest] = []

    def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
        self.fit_requests.append(request)
        state = _artifact(
            {"schema_id": "r5-model-state", "schema_version": 1, "mean": 0.0},
            schema_hash=STATE_SCHEMA_HASH,
            row_count=1,
        )
        return build_successful_sandbox_result(request, state)

    def score(self, request: SandboxScoreRequest) -> SandboxExecutionResult:
        self.score_requests.append(request)
        index = min(len(self.score_requests) - 1, len(self.score_payloads) - 1)
        output = _artifact(
            self.score_payloads[index],
            schema_hash=self.output_schema_hash,
            row_count=self.declared_row_count,
        )
        return build_successful_sandbox_result(request, output)


class _RawScoreSandbox(_FakeSandbox):
    def __init__(self, output: FrozenSandboxArtifact) -> None:
        super().__init__()
        self._output = output

    def score(self, request: SandboxScoreRequest) -> SandboxExecutionResult:
        self.score_requests.append(request)
        return build_successful_sandbox_result(request, self._output)


class _RawStateSandbox(_FakeSandbox):
    def __init__(self, state: FrozenSandboxArtifact) -> None:
        super().__init__()
        self._state = state

    def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
        self.fit_requests.append(request)
        return build_successful_sandbox_result(request, self._state)


class _TrustedEvaluator(TrustedCandidateEvaluationPort):
    def __init__(self) -> None:
        self.requests: list[TrustedCandidateEvaluationRequest] = []

    def evaluate(self, request: TrustedCandidateEvaluationRequest) -> EvaluationResult:
        self.requests.append(request)
        return EvaluationResult(
            candidate_id=request.candidate_id,
            candidate_hash=request.candidate_hash,
            validation_protocol_hash=request.validation_protocol_hash,
            evaluation_input_hash=request.evaluation_input_hash,
            metrics_artifact_hash=ContentHash("b" * 64),
            constraints_passed=True,
            significance_evidence_hash=ContentHash("c" * 64),
            failure_classification=None,
            evidence_refs=(request.score_artifact_hash,),
        )


def _request(
    *,
    code: ResearchCodeArtifact | None = None,
    window: FrozenSandboxWindow | None = None,
) -> GeneratedCandidateEvaluationRequest:
    artifact = code or _code()
    visible = window or _window()
    return GeneratedCandidateEvaluationRequest(
        candidate=_candidate(artifact),
        experiment_plan=_plan(),
        code_artifact=artifact,
        training_stream=visible,
        visible_window=visible,
        resource_limits=SandboxResourceLimits(output_bytes=64 * 1024),
        seed=SEED,
    )


def _reason(exc_info: pytest.ExceptionInfo[AppProcessError]) -> object:
    return exc_info.value.details["reason"]


def test_trusted_evaluator_owns_metrics_after_exact_deterministic_score() -> None:
    sandbox = _FakeSandbox()
    trusted = _TrustedEvaluator()

    result = GeneratedCandidateEvaluator(sandbox=sandbox, trusted=trusted).evaluate(
        _request()
    )

    assert result.metrics_artifact_hash == ContentHash("b" * 64)
    assert len(sandbox.fit_requests) == 1
    assert len(sandbox.score_requests) == 2
    assert sandbox.score_requests[0] == sandbox.score_requests[1]
    assert len(trusted.requests) == 1
    trusted_request = trusted.requests[0]
    assert result.evaluation_input_hash == trusted_request.evaluation_input_hash
    assert [row.entity_id for row in trusted_request.scores] == [
        "510300.SH",
        "510500.SH",
    ]
    assert not hasattr(trusted_request.scores[0], "sharpe_ratio")


@pytest.mark.parametrize("field", ["return", "weight", "order", "sharpe_ratio"])
def test_candidate_financial_or_execution_output_is_rejected_before_evaluation(
    field: str,
) -> None:
    sandbox = _FakeSandbox(score_payloads=(_score_payload(extra={field: 1.0}),) * 2)
    trusted = _TrustedEvaluator()

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(sandbox=sandbox, trusted=trusted).evaluate(
            _request()
        )

    assert _reason(exc_info) == "sandbox_score_schema_invalid"
    assert trusted.requests == []


def test_schema_and_declared_size_mismatch_fail_before_trusted_evaluation() -> None:
    trusted = _TrustedEvaluator()
    evaluator = GeneratedCandidateEvaluator(
        sandbox=_FakeSandbox(output_schema_hash=ContentHash("d" * 64)),
        trusted=trusted,
    )
    with pytest.raises(AppProcessError) as schema_error:
        evaluator.evaluate(_request())
    assert _reason(schema_error) == "sandbox_output_schema_mismatch"

    evaluator = GeneratedCandidateEvaluator(
        sandbox=_FakeSandbox(declared_row_count=3), trusted=trusted
    )
    with pytest.raises(AppProcessError) as size_error:
        evaluator.evaluate(_request())
    assert _reason(size_error) == "sandbox_output_row_count_mismatch"
    assert trusted.requests == []


def test_same_input_state_digest_and_seed_must_be_deterministic() -> None:
    second = cast("dict[str, object]", _score_payload())
    second = {**second, "rows": [*cast("list[object]", second["rows"])]}
    cast("dict[str, object]", cast("list[object]", second["rows"])[0])["score"] = 0.9
    trusted = _TrustedEvaluator()

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_FakeSandbox(score_payloads=(_score_payload(), second)),
            trusted=trusted,
        ).evaluate(_request())

    assert _reason(exc_info) == "sandbox_nondeterministic_output"
    assert trusted.requests == []


def test_future_visible_row_fails_closed_before_sandbox_execution() -> None:
    window = _window()
    future_key = replace(
        window.score_keys[0],
        known_at_epoch_us=window.knowledge_cutoff_epoch_us + 1,
    )

    with pytest.raises(AppProcessError) as exc_info:
        FrozenSandboxWindow(
            artifact=window.artifact,
            snapshot_id=window.snapshot_id,
            decision_time_epoch_us=window.decision_time_epoch_us,
            knowledge_cutoff_epoch_us=window.knowledge_cutoff_epoch_us,
            publication_cutoff_epoch_us=window.publication_cutoff_epoch_us,
            score_keys=(future_key, window.score_keys[1]),
        )

    assert _reason(exc_info) == "sandbox_window_future_visibility"


def test_training_and_visible_windows_cannot_use_different_temporal_contexts() -> None:
    sandbox = _FakeSandbox()
    request = _request()
    drifted_training = replace(
        request.training_stream,
        decision_time_epoch_us=request.training_stream.decision_time_epoch_us + 1,
    )

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=sandbox,
            trusted=_TrustedEvaluator(),
        ).evaluate(replace(request, training_stream=drifted_training))

    assert _reason(exc_info) == "sandbox_window_temporal_context_mismatch"
    assert sandbox.fit_requests == []


def test_invalid_signature_is_rejected_before_sandbox_execution() -> None:
    source = (
        "def fit(frame):\n    return {}\n"
        "def score(visible_window, immutable_model_state):\n    return []\n"
    )
    sandbox = _FakeSandbox()

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=sandbox, trusted=_TrustedEvaluator()
        ).evaluate(_request(code=_code(source)))

    assert _reason(exc_info) == "generated_code_contract_invalid"
    assert sandbox.fit_requests == []


def test_manifest_seed_or_image_drift_is_rejected_before_trusted_evaluation() -> None:
    class _DriftedSandbox(_FakeSandbox):
        def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
            result = super().fit(request)
            return SandboxExecutionResult(
                output=result.output,
                manifest=replace(result.manifest, seed=request.seed + 1),
            )

    trusted = _TrustedEvaluator()
    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_DriftedSandbox(), trusted=trusted
        ).evaluate(_request())

    assert _reason(exc_info) == "sandbox_execution_attestation_mismatch"
    assert trusted.requests == []


def test_trusted_result_cannot_drift_candidate_or_validation_identity() -> None:
    class _DriftedTrusted(_TrustedEvaluator):
        def evaluate(
            self, request: TrustedCandidateEvaluationRequest
        ) -> EvaluationResult:
            result = super().evaluate(request)
            return replace(result, candidate_id=CandidateId("candidate-forged"))

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_FakeSandbox(), trusted=_DriftedTrusted()
        ).evaluate(_request())

    assert _reason(exc_info) == "trusted_evaluation_identity_mismatch"


def test_trusted_result_cannot_drift_complete_evaluation_input_identity() -> None:
    class _DriftedTrusted(_TrustedEvaluator):
        def evaluate(
            self, request: TrustedCandidateEvaluationRequest
        ) -> EvaluationResult:
            result = super().evaluate(request)
            return replace(result, evaluation_input_hash=ContentHash("f" * 64))

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_FakeSandbox(), trusted=_DriftedTrusted()
        ).evaluate(_request())

    assert _reason(exc_info) == "trusted_evaluation_identity_mismatch"


def test_pickle_capable_artifact_is_rejected_by_contract() -> None:
    payload = orjson.dumps({"state": "opaque"})

    with pytest.raises(AppProcessError) as exc_info:
        FrozenSandboxArtifact(
            payload=payload,
            serialization=SandboxArtifactFormat.NUMPY_NPY,
            content_hash=_hash(payload),
            schema_hash=STATE_SCHEMA_HASH,
            row_count=1,
            allow_pickle=True,
        )

    assert _reason(exc_info) == "sandbox_pickle_forbidden"


@pytest.mark.parametrize("serialization", ["arrow", "numpy"])
def test_arrow_and_numpy_score_artifacts_are_strictly_decoded(
    serialization: str,
) -> None:
    keys = _window().score_keys
    if serialization == "arrow":
        sink = BytesIO()
        pl.DataFrame(
            {
                "entity_id": [item.entity_id for item in keys],
                "event_time_epoch_us": [item.event_time_epoch_us for item in keys],
                "score": [0.5, 0.6],
            },
            schema={
                "entity_id": pl.String,
                "event_time_epoch_us": pl.Int64,
                "score": pl.Float64,
            },
        ).write_ipc(sink)
        payload = sink.getvalue()
        artifact_format = SandboxArtifactFormat.ARROW_IPC
    else:
        values = np.array(
            [
                (keys[0].entity_id, keys[0].event_time_epoch_us, 0.5),
                (keys[1].entity_id, keys[1].event_time_epoch_us, 0.6),
            ],
            dtype=[
                ("entity_id", "U16"),
                ("event_time_epoch_us", "<i8"),
                ("score", "<f8"),
            ],
        )
        sink = BytesIO()
        np.save(sink, values, allow_pickle=False)
        payload = sink.getvalue()
        artifact_format = SandboxArtifactFormat.NUMPY_NPY
    output = freeze_sandbox_artifact(
        payload,
        serialization=artifact_format,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    trusted = _TrustedEvaluator()

    result = GeneratedCandidateEvaluator(
        sandbox=_RawScoreSandbox(output), trusted=trusted
    ).evaluate(_request())

    assert result.constraints_passed is True
    assert [row.score for row in trusted.requests[0].scores] == [0.5, 0.6]


def test_numpy_object_array_cannot_trigger_pickle_loading() -> None:
    sink = BytesIO()
    np.save(
        sink,
        np.array([{"order": "BUY"}, {"order": "SELL"}], dtype=object),
        allow_pickle=True,
    )
    output = freeze_sandbox_artifact(
        sink.getvalue(),
        serialization=SandboxArtifactFormat.NUMPY_NPY,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    trusted = _TrustedEvaluator()

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_RawScoreSandbox(output), trusted=trusted
        ).evaluate(_request())

    assert _reason(exc_info) == "sandbox_score_schema_invalid"
    assert trusted.requests == []


def test_numpy_header_shape_is_rejected_before_array_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = BytesIO()
    dtype = np.dtype(
        [
            ("entity_id", "U16"),
            ("event_time_epoch_us", "<i8"),
            ("score", "<f8"),
        ]
    )
    np.lib.format.write_array_header_1_0(
        sink,
        {
            "descr": np.lib.format.dtype_to_descr(dtype),
            "fortran_order": False,
            "shape": (1_000_000_000,),
        },
    )
    output = freeze_sandbox_artifact(
        sink.getvalue(),
        serialization=SandboxArtifactFormat.NUMPY_NPY,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )

    def _allocation_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not run for an impossible header shape")

    monkeypatch.setattr(evaluator_module.np, "load", _allocation_forbidden)

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_RawScoreSandbox(output), trusted=_TrustedEvaluator()
        ).evaluate(_request())

    assert _reason(exc_info) == "sandbox_output_shape_mismatch"


def test_seed_drift_from_preregistered_plan_fails_before_sandbox() -> None:
    sandbox = _FakeSandbox()

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=sandbox, trusted=_TrustedEvaluator()
        ).evaluate(replace(_request(), seed=SEED + 1))

    assert _reason(exc_info) == "generated_candidate_seed_mismatch"
    assert sandbox.fit_requests == []


def test_numpy_model_state_shape_is_rejected_before_array_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = BytesIO()
    np.lib.format.write_array_header_1_0(
        sink,
        {
            "descr": np.lib.format.dtype_to_descr(np.dtype("<f8")),
            "fortran_order": False,
            "shape": (1_000_000_000,),
        },
    )
    state = freeze_sandbox_artifact(
        sink.getvalue(),
        serialization=SandboxArtifactFormat.NUMPY_NPY,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )

    def _allocation_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not run for an oversized model state")

    monkeypatch.setattr(evaluator_module.np, "load", _allocation_forbidden)

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_RawStateSandbox(state), trusted=_TrustedEvaluator()
        ).evaluate(_request())

    assert _reason(exc_info) == "sandbox_model_state_shape_invalid"


def test_json_model_state_declared_row_count_must_match_payload_shape() -> None:
    state = _artifact(
        {"schema_id": "r5-model-state", "schema_version": 1, "mean": 0.0},
        schema_hash=STATE_SCHEMA_HASH,
        row_count=2,
    )

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_RawStateSandbox(state), trusted=_TrustedEvaluator()
        ).evaluate(_request())

    assert _reason(exc_info) == "sandbox_model_state_shape_invalid"


def _trusted_request() -> TrustedCandidateEvaluationRequest:
    code = _code()
    candidate = _candidate(code)
    window = _window()
    return TrustedCandidateEvaluationRequest(
        candidate_id=candidate.candidate.candidate_id,
        candidate_hash=candidate.candidate_hash,
        validation_protocol_hash=_plan().validation_protocol_hash,
        snapshot_id=window.snapshot_id,
        decision_time_epoch_us=window.decision_time_epoch_us,
        knowledge_cutoff_epoch_us=window.knowledge_cutoff_epoch_us,
        publication_cutoff_epoch_us=window.publication_cutoff_epoch_us,
        code_artifact_hash=code.artifact_hash,
        score_artifact_hash=ContentHash("d" * 64),
        scores=tuple(
            CandidateScoreRow(
                entity_id=key.entity_id,
                event_time_epoch_us=key.event_time_epoch_us,
                score=0.5 + index * 0.1,
            )
            for index, key in enumerate(window.score_keys)
        ),
        score_keys=window.score_keys,
    )


def _raw_artifact(
    payload: bytes,
    *,
    serialization: SandboxArtifactFormat,
    schema_hash: ContentHash,
    row_count: int,
) -> FrozenSandboxArtifact:
    return freeze_sandbox_artifact(
        payload,
        serialization=serialization,
        schema_hash=schema_hash,
        row_count=row_count,
    )


def _assert_score_artifact_rejected(
    artifact: FrozenSandboxArtifact,
    *,
    reason: str,
    request: GeneratedCandidateEvaluationRequest | None = None,
) -> None:
    trusted = _TrustedEvaluator()
    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidateEvaluator(
            sandbox=_RawScoreSandbox(artifact),
            trusted=trusted,
        ).evaluate(request or _request())

    assert _reason(exc_info) == reason
    assert trusted.requests == []


def test_score_row_contract_rejects_ambiguous_runtime_scalars() -> None:
    with pytest.raises(AppProcessError) as identity_error:
        CandidateScoreRow(entity_id=" ", event_time_epoch_us=1, score=0.5)
    assert _reason(identity_error) == "sandbox_score_identity_invalid"

    with pytest.raises(AppProcessError) as time_error:
        CandidateScoreRow(
            entity_id="510300.SH",
            event_time_epoch_us=cast("int", True),
            score=0.5,
        )
    assert _reason(time_error) == "sandbox_score_time_invalid"

    with pytest.raises(AppProcessError) as score_error:
        CandidateScoreRow(
            entity_id="510300.SH",
            event_time_epoch_us=1,
            score=float("nan"),
        )
    assert _reason(score_error) == "sandbox_score_value_invalid"


def test_trusted_request_rejects_untyped_identity_cutoffs_and_sequences() -> None:
    request = _trusted_request()

    with pytest.raises(AppProcessError) as identity_error:
        replace(request, candidate_id=cast("CandidateId", "candidate-forged"))
    assert _reason(identity_error) == "trusted_evaluation_request_identity_invalid"

    with pytest.raises(AppProcessError) as cutoff_error:
        replace(request, decision_time_epoch_us=cast("int", True))
    assert _reason(cutoff_error) == "trusted_evaluation_request_cutoff_invalid"

    with pytest.raises(AppProcessError) as order_error:
        replace(
            request,
            publication_cutoff_epoch_us=request.knowledge_cutoff_epoch_us + 1,
        )
    assert _reason(order_error) == "trusted_evaluation_request_cutoff_invalid"

    with pytest.raises(AppProcessError) as scores_container_error:
        replace(
            request,
            scores=cast("tuple[CandidateScoreRow, ...]", "forged"),
        )
    assert _reason(scores_container_error) == "trusted_evaluation_scores_invalid"

    with pytest.raises(AppProcessError) as empty_scores_error:
        replace(request, scores=())
    assert _reason(empty_scores_error) == "trusted_evaluation_scores_invalid"

    with pytest.raises(AppProcessError) as keys_container_error:
        replace(
            request,
            score_keys=cast("tuple[SandboxScoreKey, ...]", b"forged"),
        )
    assert _reason(keys_container_error) == "trusted_evaluation_score_keys_invalid"

    with pytest.raises(AppProcessError) as key_count_error:
        replace(request, score_keys=request.score_keys[:1])
    assert _reason(key_count_error) == "trusted_evaluation_score_keys_invalid"


@pytest.mark.pit
def test_trusted_request_accepts_visibility_boundary_and_rejects_future_keys() -> None:
    request = _trusted_request()
    boundary_key = replace(
        request.score_keys[0],
        known_at_epoch_us=request.knowledge_cutoff_epoch_us,
        publication_time_epoch_us=request.publication_cutoff_epoch_us,
    )
    boundary_keys = (boundary_key, request.score_keys[1])

    accepted = replace(request, score_keys=boundary_keys)

    assert accepted.score_keys == boundary_keys

    future_knowledge = replace(
        boundary_key,
        known_at_epoch_us=request.knowledge_cutoff_epoch_us + 1,
    )
    with pytest.raises(AppProcessError) as knowledge_error:
        replace(request, score_keys=(future_knowledge, request.score_keys[1]))
    assert _reason(knowledge_error) == "trusted_evaluation_score_keys_invalid"

    future_publication = replace(
        boundary_key,
        publication_time_epoch_us=request.publication_cutoff_epoch_us + 1,
    )
    with pytest.raises(AppProcessError) as publication_error:
        replace(request, score_keys=(future_publication, request.score_keys[1]))
    assert _reason(publication_error) == "trusted_evaluation_score_keys_invalid"


def test_generated_request_rejects_untyped_nodes_and_seed() -> None:
    request = _request()

    with pytest.raises(AppProcessError) as node_error:
        replace(
            request,
            candidate=cast("ResearchCandidateSpec", object()),
        )
    assert _reason(node_error) == "generated_candidate_request_invalid"

    with pytest.raises(AppProcessError) as seed_error:
        replace(request, seed=cast("int", True))
    assert _reason(seed_error) == "sandbox_seed_invalid"


def test_evaluator_rejects_untyped_request_and_sandbox_result() -> None:
    sandbox = _FakeSandbox()
    with pytest.raises(AppProcessError) as request_error:
        GeneratedCandidateEvaluator(
            sandbox=sandbox,
            trusted=_TrustedEvaluator(),
        ).evaluate(cast("GeneratedCandidateEvaluationRequest", object()))
    assert _reason(request_error) == "generated_candidate_request_invalid"
    assert sandbox.fit_requests == []

    class _UntypedResultSandbox(_FakeSandbox):
        def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
            self.fit_requests.append(request)
            return cast("SandboxExecutionResult", object())

    with pytest.raises(AppProcessError) as result_error:
        GeneratedCandidateEvaluator(
            sandbox=_UntypedResultSandbox(),
            trusted=_TrustedEvaluator(),
        ).evaluate(_request())
    assert _reason(result_error) == "sandbox_execution_result_invalid"


@pytest.mark.pit
def test_request_identity_snapshot_schema_and_input_budget_fail_before_sandbox() -> (
    None
):
    request = _request()

    other_code = _code(f"{SOURCE}\n# different candidate identity\n")
    identity_drift = replace(request, candidate=_candidate(other_code))

    snapshot_window = replace(
        request.visible_window,
        snapshot_id=SnapshotId("snapshot-r5-generated-code-drift"),
    )
    snapshot_drift = replace(
        request,
        training_stream=snapshot_window,
        visible_window=snapshot_window,
    )

    schema_artifact = _raw_artifact(
        request.visible_window.artifact.payload,
        serialization=request.visible_window.artifact.serialization,
        schema_hash=ContentHash("e" * 64),
        row_count=request.visible_window.artifact.row_count,
    )
    schema_window = replace(request.visible_window, artifact=schema_artifact)
    schema_drift = replace(
        request,
        training_stream=schema_window,
        visible_window=schema_window,
    )

    input_limit = replace(
        request.resource_limits,
        temporary_storage_bytes=len(request.visible_window.artifact.payload) - 1,
    )
    oversized_input = replace(request, resource_limits=input_limit)

    for drifted, reason in (
        (identity_drift, "generated_code_candidate_identity_mismatch"),
        (snapshot_drift, "sandbox_window_snapshot_mismatch"),
        (schema_drift, "sandbox_input_schema_mismatch"),
        (oversized_input, "sandbox_input_size_exceeded"),
    ):
        sandbox = _FakeSandbox()
        with pytest.raises(AppProcessError) as exc_info:
            GeneratedCandidateEvaluator(
                sandbox=sandbox,
                trusted=_TrustedEvaluator(),
            ).evaluate(drifted)
        assert _reason(exc_info) == reason
        assert sandbox.fit_requests == []


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("root_array", "sandbox_score_schema_invalid"),
        ("unknown_field", "sandbox_score_schema_invalid"),
        ("wrong_schema", "sandbox_score_schema_invalid"),
        ("non_mapping_row", "sandbox_score_schema_invalid"),
        ("untyped_identity", "sandbox_score_schema_invalid"),
        ("untyped_score", "sandbox_score_schema_invalid"),
        ("row_count", "sandbox_output_row_count_mismatch"),
        ("identity", "sandbox_score_identity_mismatch"),
    ],
)
def test_json_score_boundary_rejects_structural_and_value_forgery(
    case: str,
    reason: str,
) -> None:
    payload: object = orjson.loads(orjson.dumps(_score_payload()))
    if case == "root_array":
        payload = []
    else:
        mapping = cast("dict[str, object]", payload)
        rows = cast("list[object]", mapping["rows"])
        if case == "unknown_field":
            mapping["unknown"] = True
        elif case == "wrong_schema":
            mapping["schema_id"] = "candidate-controlled-schema"
        elif case == "non_mapping_row":
            rows[0] = "forged"
        elif case == "untyped_identity":
            cast("dict[str, object]", rows[0])["event_time_epoch_us"] = True
        elif case == "untyped_score":
            cast("dict[str, object]", rows[0])["score"] = True
        elif case == "row_count":
            rows.pop()
        elif case == "identity":
            cast("dict[str, object]", rows[0])["entity_id"] = "forged.SH"

    output = _raw_artifact(
        orjson.dumps(payload),
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    _assert_score_artifact_rejected(output, reason=reason)


def test_corrupt_json_arrow_and_numpy_score_payloads_fail_closed() -> None:
    malformed_json = _raw_artifact(
        b"{",
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    _assert_score_artifact_rejected(
        malformed_json,
        reason="sandbox_score_schema_invalid",
    )

    arrow_sink = BytesIO()
    pl.DataFrame(
        {
            "instrument_id": ["510300.SH", "510500.SH"],
            "event_time_epoch_us": [1_700_000_000_000_000] * 2,
            "score": [0.5, 0.6],
        }
    ).write_ipc(arrow_sink)
    wrong_arrow_schema = _raw_artifact(
        arrow_sink.getvalue(),
        serialization=SandboxArtifactFormat.ARROW_IPC,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    _assert_score_artifact_rejected(
        wrong_arrow_schema,
        reason="sandbox_score_schema_invalid",
    )

    dtype = np.dtype(
        [
            ("entity_id", "U16"),
            ("event_time_epoch_us", "<i8"),
            ("score", "<f8"),
        ]
    )
    version_two_sink = BytesIO()
    np.lib.format.write_array_header_2_0(
        version_two_sink,
        {
            "descr": np.lib.format.dtype_to_descr(dtype),
            "fortran_order": False,
            "shape": (2,),
        },
    )
    truncated_version_two = _raw_artifact(
        version_two_sink.getvalue(),
        serialization=SandboxArtifactFormat.NUMPY_NPY,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    _assert_score_artifact_rejected(
        truncated_version_two,
        reason="sandbox_score_schema_invalid",
    )

    unsupported_version = _raw_artifact(
        np.lib.format.magic(3, 0),
        serialization=SandboxArtifactFormat.NUMPY_NPY,
        schema_hash=OUTPUT_SCHEMA_HASH,
        row_count=2,
    )
    _assert_score_artifact_rejected(
        unsupported_version,
        reason="sandbox_score_schema_invalid",
    )


def test_fit_and_score_output_byte_limits_are_independently_enforced() -> None:
    request = _request()
    fit_limited = replace(
        request,
        resource_limits=replace(request.resource_limits, output_bytes=1),
    )
    with pytest.raises(AppProcessError) as fit_error:
        GeneratedCandidateEvaluator(
            sandbox=_FakeSandbox(),
            trusted=_TrustedEvaluator(),
        ).evaluate(fit_limited)
    assert _reason(fit_error) == "sandbox_output_size_exceeded"

    score_limited = replace(
        request,
        resource_limits=replace(request.resource_limits, output_bytes=100),
    )
    with pytest.raises(AppProcessError) as score_error:
        GeneratedCandidateEvaluator(
            sandbox=_FakeSandbox(),
            trusted=_TrustedEvaluator(),
        ).evaluate(score_limited)
    assert _reason(score_error) == "sandbox_output_size_exceeded"


def test_json_model_state_accepts_sequence_and_rejects_scalar_or_bad_bytes() -> None:
    sequence_state = _artifact(
        [{"mean": 0.0}, {"mean": 0.1}],
        schema_hash=STATE_SCHEMA_HASH,
        row_count=2,
    )
    result = GeneratedCandidateEvaluator(
        sandbox=_RawStateSandbox(sequence_state),
        trusted=_TrustedEvaluator(),
    ).evaluate(_request())
    assert result.constraints_passed is True

    scalar_state = _artifact(1, schema_hash=STATE_SCHEMA_HASH, row_count=1)
    with pytest.raises(AppProcessError) as scalar_error:
        GeneratedCandidateEvaluator(
            sandbox=_RawStateSandbox(scalar_state),
            trusted=_TrustedEvaluator(),
        ).evaluate(_request())
    assert _reason(scalar_error) == "sandbox_model_state_schema_invalid"

    malformed_state = _raw_artifact(
        b"{",
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    with pytest.raises(AppProcessError) as malformed_error:
        GeneratedCandidateEvaluator(
            sandbox=_RawStateSandbox(malformed_state),
            trusted=_TrustedEvaluator(),
        ).evaluate(_request())
    assert _reason(malformed_error) == "sandbox_model_state_schema_invalid"


def test_arrow_model_state_requires_exact_declared_shape() -> None:
    arrow_sink = BytesIO()
    pl.DataFrame({"mean": [0.5]}).write_ipc(arrow_sink)
    payload = arrow_sink.getvalue()
    valid_state = _raw_artifact(
        payload,
        serialization=SandboxArtifactFormat.ARROW_IPC,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )
    result = GeneratedCandidateEvaluator(
        sandbox=_RawStateSandbox(valid_state),
        trusted=_TrustedEvaluator(),
    ).evaluate(_request())
    assert result.constraints_passed is True

    wrong_shape = _raw_artifact(
        payload,
        serialization=SandboxArtifactFormat.ARROW_IPC,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=2,
    )
    with pytest.raises(AppProcessError) as shape_error:
        GeneratedCandidateEvaluator(
            sandbox=_RawStateSandbox(wrong_shape),
            trusted=_TrustedEvaluator(),
        ).evaluate(_request())
    assert _reason(shape_error) == "sandbox_model_state_shape_invalid"


def test_numpy_model_state_round_trips_without_executable_loading() -> None:
    sink = BytesIO()
    np.save(sink, np.array([0.5], dtype="<f8"), allow_pickle=False)
    state = _raw_artifact(
        sink.getvalue(),
        serialization=SandboxArtifactFormat.NUMPY_NPY,
        schema_hash=STATE_SCHEMA_HASH,
        row_count=1,
    )

    result = GeneratedCandidateEvaluator(
        sandbox=_RawStateSandbox(state),
        trusted=_TrustedEvaluator(),
    ).evaluate(_request())

    assert result.constraints_passed is True


def test_post_construction_serialization_forgery_fails_at_public_boundary() -> None:
    state = _artifact({}, schema_hash=STATE_SCHEMA_HASH, row_count=1)
    object.__setattr__(
        state,
        "serialization",
        cast("SandboxArtifactFormat", "application/x-forged"),
    )
    with pytest.raises(AppProcessError) as state_error:
        GeneratedCandidateEvaluator(
            sandbox=_RawStateSandbox(state),
            trusted=_TrustedEvaluator(),
        ).evaluate(_request())
    assert _reason(state_error) == "sandbox_artifact_serialization_invalid"

    output = _artifact(_score_payload(), schema_hash=OUTPUT_SCHEMA_HASH, row_count=2)
    object.__setattr__(
        output,
        "serialization",
        cast("SandboxArtifactFormat", "application/x-forged"),
    )
    _assert_score_artifact_rejected(
        output,
        reason="sandbox_artifact_serialization_invalid",
    )
