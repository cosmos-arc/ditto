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
