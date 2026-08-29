"""Trusted host validation and evaluation for generated research candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol, cast

import numpy as np
import orjson
import polars as pl
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.campaign import (
    EvaluationResult,
    ExperimentPlan,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExitStatus,
    SandboxResourceLimits,
    validate_research_code_contract,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash, SnapshotId
from ditto_analysis.experiments.persistence import canonical_payload

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    FrozenSandboxArtifact,
    FrozenSandboxWindow,
    SandboxArtifactFormat,
    SandboxExecutionResult,
    SandboxFitRequest,
    SandboxScoreKey,
    SandboxScoreRequest,
    sandbox_manifest_attestation_hash,
)

__all__ = [
    "CandidateScoreRow",
    "GeneratedCandidateEvaluationRequest",
    "GeneratedCandidateEvaluator",
    "TrustedCandidateEvaluationPort",
    "TrustedCandidateEvaluationRequest",
]

_SCORE_FIELDS = frozenset({"entity_id", "event_time_epoch_us", "score"})


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "generated candidate evaluation failed closed",
        details={"code": "GENERATED_CANDIDATE_INVALID", "reason": reason, **details},
    )


def _freeze_runtime_sequence(value: object, *, reason: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(reason)
    return tuple(cast("Sequence[object]", value))


@dataclass(frozen=True, slots=True)
class CandidateScoreRow:
    """Only untrusted identity/time/score values admitted to trusted evaluation."""

    entity_id: str
    event_time_epoch_us: int
    score: float

    def __post_init__(self) -> None:
        """Reject ambiguous identities, timestamps, and non-finite scores."""
        if (
            type(self.entity_id) is not str
            or not self.entity_id
            or self.entity_id != self.entity_id.strip()
        ):
            raise _error("sandbox_score_identity_invalid")
        if type(self.event_time_epoch_us) is not int or self.event_time_epoch_us < 0:
            raise _error("sandbox_score_time_invalid")
        if type(self.score) is not float or not math.isfinite(self.score):
            raise _error("sandbox_score_value_invalid")


@dataclass(frozen=True, slots=True)
class TrustedCandidateEvaluationRequest:
    """Typed handoff to existing host-owned backtest/statistical evaluation."""

    candidate_id: CandidateId
    candidate_hash: ContentHash
    validation_protocol_hash: ContentHash
    snapshot_id: SnapshotId
    decision_time_epoch_us: int
    knowledge_cutoff_epoch_us: int
    publication_cutoff_epoch_us: int
    code_artifact_hash: ContentHash
    score_artifact_hash: ContentHash
    scores: Sequence[CandidateScoreRow]
    score_keys: Sequence[SandboxScoreKey]

    def __post_init__(self) -> None:
        """Freeze one exact typed handoff to trusted numerical evaluation."""
        typed = (
            (self.candidate_id, CandidateId),
            (self.candidate_hash, ContentHash),
            (self.validation_protocol_hash, ContentHash),
            (self.snapshot_id, SnapshotId),
            (self.code_artifact_hash, ContentHash),
            (self.score_artifact_hash, ContentHash),
        )
        if any(type(value) is not expected for value, expected in typed):
            raise _error("trusted_evaluation_request_identity_invalid")
        for field_name in (
            "decision_time_epoch_us",
            "knowledge_cutoff_epoch_us",
            "publication_cutoff_epoch_us",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise _error("trusted_evaluation_request_cutoff_invalid")
        if not (
            self.publication_cutoff_epoch_us
            <= self.knowledge_cutoff_epoch_us
            <= self.decision_time_epoch_us
        ):
            raise _error("trusted_evaluation_request_cutoff_invalid")
        rows = _freeze_runtime_sequence(
            cast("object", self.scores), reason="trusted_evaluation_scores_invalid"
        )
        if not rows or any(type(row) is not CandidateScoreRow for row in rows):
            raise _error("trusted_evaluation_scores_invalid")
        typed_rows = cast("tuple[CandidateScoreRow, ...]", rows)
        keys = _freeze_runtime_sequence(
            cast("object", self.score_keys),
            reason="trusted_evaluation_score_keys_invalid",
        )
        if len(keys) != len(typed_rows) or any(
            type(key) is not SandboxScoreKey for key in keys
        ):
            raise _error("trusted_evaluation_score_keys_invalid")
        typed_keys = cast("tuple[SandboxScoreKey, ...]", keys)
        if tuple(
            (row.entity_id, row.event_time_epoch_us) for row in typed_rows
        ) != tuple(
            (key.entity_id, key.event_time_epoch_us) for key in typed_keys
        ) or any(
            key.known_at_epoch_us > self.knowledge_cutoff_epoch_us
            or key.publication_time_epoch_us > self.publication_cutoff_epoch_us
            for key in typed_keys
        ):
            raise _error("trusted_evaluation_score_keys_invalid")
        object.__setattr__(self, "scores", typed_rows)
        object.__setattr__(self, "score_keys", typed_keys)

    @property
    def evaluation_input_hash(self) -> ContentHash:
        """Bind every trusted evaluation input, including PIT row provenance."""
        return canonical_payload(
            {
                "candidate_id": str(self.candidate_id),
                "candidate_hash": str(self.candidate_hash),
                "validation_protocol_hash": str(self.validation_protocol_hash),
                "snapshot_id": str(self.snapshot_id),
                "decision_time_epoch_us": self.decision_time_epoch_us,
                "knowledge_cutoff_epoch_us": self.knowledge_cutoff_epoch_us,
                "publication_cutoff_epoch_us": self.publication_cutoff_epoch_us,
                "code_artifact_hash": str(self.code_artifact_hash),
                "score_artifact_hash": str(self.score_artifact_hash),
                "scores": [
                    {
                        "entity_id": row.entity_id,
                        "event_time_epoch_us": row.event_time_epoch_us,
                        "score": row.score,
                    }
                    for row in self.scores
                ],
                "score_keys": [
                    {
                        "entity_id": key.entity_id,
                        "event_time_epoch_us": key.event_time_epoch_us,
                        "known_at_epoch_us": key.known_at_epoch_us,
                        "publication_time_epoch_us": key.publication_time_epoch_us,
                        "execution_eligible_at_epoch_us": (
                            key.execution_eligible_at_epoch_us
                        ),
                    }
                    for key in self.score_keys
                ],
            }
        ).content_hash


class TrustedCandidateEvaluationPort(Protocol):
    """Existing host-owned experiment/backtest/evaluation numerical authority."""

    def evaluate(self, request: TrustedCandidateEvaluationRequest) -> EvaluationResult:
        """Compute formal metrics, constraints, significance, and evidence."""
        ...


@dataclass(frozen=True, slots=True)
class GeneratedCandidateEvaluationRequest:
    """One exact generated candidate, protocol, PIT window, and sandbox budget."""

    candidate: ResearchCandidateSpec
    experiment_plan: ExperimentPlan
    code_artifact: ResearchCodeArtifact
    training_stream: FrozenSandboxWindow
    visible_window: FrozenSandboxWindow
    resource_limits: SandboxResourceLimits
    seed: int

    def __post_init__(self) -> None:
        """Require complete typed candidate, PIT, code, and budget inputs."""
        typed = (
            (self.candidate, ResearchCandidateSpec),
            (self.experiment_plan, ExperimentPlan),
            (self.code_artifact, ResearchCodeArtifact),
            (self.training_stream, FrozenSandboxWindow),
            (self.visible_window, FrozenSandboxWindow),
            (self.resource_limits, SandboxResourceLimits),
        )
        if any(type(value) is not expected for value, expected in typed):
            raise _error("generated_candidate_request_invalid")
        if type(self.seed) is not int or self.seed < 0:
            raise _error("sandbox_seed_invalid")


def _decode_json_score_rows(payload: bytes) -> tuple[Mapping[str, object], ...]:
    decoded: object = orjson.loads(payload)
    if not isinstance(decoded, Mapping):
        raise _error("sandbox_score_schema_invalid")
    mapping = cast("Mapping[str, object]", decoded)
    if set(mapping) != {
        "schema_id",
        "schema_version",
        "rows",
    }:
        raise _error("sandbox_score_schema_invalid")
    rows = mapping["rows"]
    if (
        mapping["schema_id"] != "r5-candidate-score-frame"
        or mapping["schema_version"] != 1
        or not isinstance(rows, Sequence)
        or isinstance(rows, (str, bytes, bytearray))
    ):
        raise _error("sandbox_score_schema_invalid")
    values = tuple(cast("Sequence[object]", rows))
    if any(not isinstance(item, Mapping) for item in values):
        raise _error("sandbox_score_schema_invalid")
    return cast("tuple[Mapping[str, object], ...]", values)


def _decode_arrow_score_rows(
    payload: bytes,
    *,
    expected_row_count: int,
) -> tuple[Mapping[str, object], ...]:
    frame = pl.read_ipc(BytesIO(payload), n_rows=expected_row_count + 1)
    if frame.columns != ["entity_id", "event_time_epoch_us", "score"]:
        raise _error("sandbox_score_schema_invalid")
    return tuple(cast("Mapping[str, object]", row) for row in frame.to_dicts())


def _numpy_header(payload: bytes) -> tuple[tuple[int, ...], np.dtype[np.generic]]:
    stream = BytesIO(payload)
    version = np.lib.format.read_magic(stream)
    if version == (1, 0):
        shape, _fortran_order, dtype = np.lib.format.read_array_header_1_0(stream)
    elif version == (2, 0):
        shape, _fortran_order, dtype = np.lib.format.read_array_header_2_0(stream)
    else:
        raise _error("sandbox_score_schema_invalid")
    return shape, cast("np.dtype[np.generic]", dtype)


def _decode_numpy_score_rows(
    payload: bytes,
    *,
    expected_row_count: int,
) -> tuple[Mapping[str, object], ...]:
    shape, dtype = _numpy_header(payload)
    expected_dtype = np.dtype(
        [
            ("entity_id", "U16"),
            ("event_time_epoch_us", "<i8"),
            ("score", "<f8"),
        ]
    )
    if shape != (expected_row_count,):
        raise _error("sandbox_output_shape_mismatch")
    if dtype.hasobject or dtype != expected_dtype:
        raise _error("sandbox_score_schema_invalid")
    raw_values: object = np.load(BytesIO(payload), allow_pickle=False)
    if not isinstance(raw_values, np.ndarray):
        raise _error("sandbox_score_schema_invalid")
    values = cast("np.ndarray[tuple[int, ...], np.dtype[np.generic]]", raw_values)
    if values.shape != shape:
        raise _error("sandbox_score_schema_invalid")
    return tuple(
        {
            "entity_id": str(row["entity_id"]),
            "event_time_epoch_us": int(row["event_time_epoch_us"]),
            "score": float(row["score"]),
        }
        for row in values
    )


def _validate_numpy_model_state(
    state: FrozenSandboxArtifact,
    *,
    output_limit: int,
) -> None:
    shape, dtype = _numpy_header(state.payload)
    decoded_size = math.prod(shape) * dtype.itemsize
    first_dimension = shape[0] if shape else 1
    if (
        dtype.hasobject
        or first_dimension != state.row_count
        or decoded_size > output_limit
    ):
        raise _error("sandbox_model_state_shape_invalid")
    raw_loaded: object = np.load(BytesIO(state.payload), allow_pickle=False)
    if not isinstance(raw_loaded, np.ndarray):
        raise _error("sandbox_model_state_schema_invalid")
    loaded = cast("np.ndarray[tuple[int, ...], np.dtype[np.generic]]", raw_loaded)
    if loaded.shape != shape:
        raise _error("sandbox_model_state_schema_invalid")


def _validate_json_model_state(state: FrozenSandboxArtifact) -> None:
    decoded: object = orjson.loads(state.payload)
    if isinstance(decoded, Mapping):
        actual_row_count = 1
    elif isinstance(decoded, Sequence) and not isinstance(
        decoded, (str, bytes, bytearray)
    ):
        actual_row_count = len(cast("Sequence[object]", decoded))
    else:
        raise _error("sandbox_model_state_schema_invalid")
    if actual_row_count != state.row_count:
        raise _error("sandbox_model_state_shape_invalid")


class GeneratedCandidateEvaluator:
    """Keep untrusted code outside numerical, financial, and execution authority."""

    def __init__(
        self,
        *,
        sandbox: CandidateSandboxPort,
        trusted: TrustedCandidateEvaluationPort,
    ) -> None:
        self._sandbox = sandbox
        self._trusted = trusted

    def evaluate(
        self, request: GeneratedCandidateEvaluationRequest
    ) -> EvaluationResult:
        """Fit, double-score, validate, then delegate formal evaluation."""
        if type(request) is not GeneratedCandidateEvaluationRequest:
            raise _error("generated_candidate_request_invalid")
        self._validate_request(request)
        fit_request = SandboxFitRequest(
            code_artifact=request.code_artifact,
            training_stream=request.training_stream,
            resource_limits=request.resource_limits,
            seed=request.seed,
        )
        fitted = self._sandbox.fit(fit_request)
        state = self._validate_execution(fit_request, fitted)
        self._validate_model_state(state, request.resource_limits)
        score_request = SandboxScoreRequest(
            code_artifact=request.code_artifact,
            visible_window=request.visible_window,
            immutable_model_state=state,
            resource_limits=request.resource_limits,
            seed=request.seed,
        )
        first = self._sandbox.score(score_request)
        second = self._sandbox.score(score_request)
        first_output = self._validate_execution(score_request, first)
        second_output = self._validate_execution(score_request, second)
        if first_output != second_output:
            raise _error("sandbox_nondeterministic_output")
        rows = self._decode_scores(
            first_output,
            expected_schema_hash=request.code_artifact.output_schema_hash,
            expected_keys=tuple(request.visible_window.score_keys),
            output_limit=request.resource_limits.output_bytes,
        )
        trusted_request = TrustedCandidateEvaluationRequest(
            candidate_id=request.candidate.candidate.candidate_id,
            candidate_hash=request.candidate.candidate_hash,
            validation_protocol_hash=request.experiment_plan.validation_protocol_hash,
            snapshot_id=request.visible_window.snapshot_id,
            decision_time_epoch_us=request.visible_window.decision_time_epoch_us,
            knowledge_cutoff_epoch_us=(
                request.visible_window.knowledge_cutoff_epoch_us
            ),
            publication_cutoff_epoch_us=(
                request.visible_window.publication_cutoff_epoch_us
            ),
            code_artifact_hash=request.code_artifact.artifact_hash,
            score_artifact_hash=first_output.content_hash,
            scores=rows,
            score_keys=request.visible_window.score_keys,
        )
        result = self._trusted.evaluate(trusted_request)
        self._validate_trusted_result(result, trusted_request)
        return result

    @staticmethod
    def _validate_request(request: GeneratedCandidateEvaluationRequest) -> None:
        try:
            validate_research_code_contract(request.code_artifact)
        except ExperimentSpecError as exc:
            raise _error(
                "generated_code_contract_invalid",
                contract_reason=exc.details.get("reason_code"),
            ) from exc
        expected_code_hash = {
            SearchAxis.FACTOR_CODE: request.candidate.factor_code_hash,
            SearchAxis.MODEL_CODE: request.candidate.model_code_hash,
            SearchAxis.PARAMETERS: None,
        }[request.candidate.search_axis]
        if expected_code_hash != request.code_artifact.artifact_hash:
            raise _error("generated_code_candidate_identity_mismatch")
        if request.seed != request.experiment_plan.seed:
            raise _error("generated_candidate_seed_mismatch")
        temporal_contexts = {
            (
                window.decision_time_epoch_us,
                window.knowledge_cutoff_epoch_us,
                window.publication_cutoff_epoch_us,
            )
            for window in (request.training_stream, request.visible_window)
        }
        if len(temporal_contexts) != 1:
            raise _error("sandbox_window_temporal_context_mismatch")
        for window in (request.training_stream, request.visible_window):
            if window.snapshot_id != request.experiment_plan.snapshot_id:
                raise _error("sandbox_window_snapshot_mismatch")
            if window.artifact.schema_hash != request.code_artifact.input_schema_hash:
                raise _error("sandbox_input_schema_mismatch")
            if (
                len(window.artifact.payload)
                > request.resource_limits.temporary_storage_bytes
            ):
                raise _error("sandbox_input_size_exceeded")

    @staticmethod
    def _validate_execution(
        request: SandboxFitRequest | SandboxScoreRequest,
        result: SandboxExecutionResult,
    ) -> FrozenSandboxArtifact:
        if type(result) is not SandboxExecutionResult:
            raise _error("sandbox_execution_result_invalid")
        manifest = result.manifest
        if (
            manifest.code_artifact_hash != request.code_artifact.artifact_hash
            or manifest.runtime_digest != request.code_artifact.image_digest
            or manifest.resource_limits != request.resource_limits
            or manifest.input_hash != request.input_hash
            or manifest.output_hash != result.output.content_hash
            or manifest.seed != request.seed
            or manifest.exit_status is not SandboxExitStatus.SUCCEEDED
            or manifest.exit_code != 0
            or manifest.attestation_hash != sandbox_manifest_attestation_hash(manifest)
        ):
            raise _error("sandbox_execution_attestation_mismatch")
        return result.output

    @staticmethod
    def _validate_model_state(
        state: FrozenSandboxArtifact,
        limits: SandboxResourceLimits,
    ) -> None:
        if len(state.payload) > limits.output_bytes:
            raise _error("sandbox_output_size_exceeded")
        try:
            if state.serialization is SandboxArtifactFormat.JSON:
                _validate_json_model_state(state)
            elif state.serialization is SandboxArtifactFormat.ARROW_IPC:
                frame = pl.read_ipc(
                    BytesIO(state.payload),
                    n_rows=state.row_count + 1,
                )
                if (
                    frame.height != state.row_count
                    or frame.estimated_size() > limits.output_bytes
                ):
                    raise _error("sandbox_model_state_shape_invalid")
            elif state.serialization is SandboxArtifactFormat.NUMPY_NPY:
                _validate_numpy_model_state(
                    state,
                    output_limit=limits.output_bytes,
                )
            else:
                raise _error("sandbox_artifact_serialization_invalid")
        except AppProcessError:
            raise
        except (ValueError, TypeError, OSError, pl.exceptions.PolarsError) as exc:
            raise _error(
                "sandbox_model_state_schema_invalid",
                decoder_error=type(exc).__name__,
            ) from exc

    @staticmethod
    def _decode_scores(
        artifact: FrozenSandboxArtifact,
        *,
        expected_schema_hash: ContentHash,
        expected_keys: tuple[SandboxScoreKey, ...],
        output_limit: int,
    ) -> tuple[CandidateScoreRow, ...]:
        if artifact.schema_hash != expected_schema_hash:
            raise _error("sandbox_output_schema_mismatch")
        if len(artifact.payload) > output_limit:
            raise _error("sandbox_output_size_exceeded")
        if artifact.row_count != len(expected_keys):
            raise _error("sandbox_output_row_count_mismatch")
        raw_rows = GeneratedCandidateEvaluator._decode_score_rows(
            artifact,
            expected_row_count=len(expected_keys),
        )
        if len(raw_rows) != artifact.row_count:
            raise _error("sandbox_output_row_count_mismatch")
        rows = tuple(GeneratedCandidateEvaluator._score_row(item) for item in raw_rows)
        observed_keys = tuple((row.entity_id, row.event_time_epoch_us) for row in rows)
        expected_identity = tuple(
            (key.entity_id, key.event_time_epoch_us) for key in expected_keys
        )
        if observed_keys != expected_identity:
            raise _error("sandbox_score_identity_mismatch")
        return rows

    @staticmethod
    def _decode_score_rows(
        artifact: FrozenSandboxArtifact,
        *,
        expected_row_count: int,
    ) -> tuple[Mapping[str, object], ...]:
        try:
            if artifact.serialization is SandboxArtifactFormat.JSON:
                return _decode_json_score_rows(artifact.payload)
            if artifact.serialization is SandboxArtifactFormat.ARROW_IPC:
                return _decode_arrow_score_rows(
                    artifact.payload,
                    expected_row_count=expected_row_count,
                )
            if artifact.serialization is SandboxArtifactFormat.NUMPY_NPY:
                return _decode_numpy_score_rows(
                    artifact.payload,
                    expected_row_count=expected_row_count,
                )
        except AppProcessError:
            raise
        except (ValueError, TypeError, OSError, pl.exceptions.PolarsError) as exc:
            raise _error(
                "sandbox_score_schema_invalid",
                decoder_error=type(exc).__name__,
            ) from exc
        raise _error("sandbox_artifact_serialization_invalid")

    @staticmethod
    def _score_row(raw: Mapping[str, object]) -> CandidateScoreRow:
        if frozenset(raw) != _SCORE_FIELDS:
            raise _error("sandbox_score_schema_invalid")
        entity_id = raw["entity_id"]
        event_time = raw["event_time_epoch_us"]
        score = raw["score"]
        if type(entity_id) is not str or type(event_time) is not int:
            raise _error("sandbox_score_schema_invalid")
        if type(score) not in (int, float) or type(score) is bool:
            raise _error("sandbox_score_schema_invalid")
        typed_score = cast("int | float", score)
        return CandidateScoreRow(
            entity_id=entity_id,
            event_time_epoch_us=event_time,
            score=float(typed_score),
        )

    @staticmethod
    def _validate_trusted_result(
        result: EvaluationResult,
        request: TrustedCandidateEvaluationRequest,
    ) -> None:
        if (
            type(result) is not EvaluationResult
            or result.candidate_id != request.candidate_id
            or result.candidate_hash != request.candidate_hash
            or result.validation_protocol_hash != request.validation_protocol_hash
            or result.evaluation_input_hash != request.evaluation_input_hash
            or request.score_artifact_hash not in result.evidence_refs
        ):
            raise _error("trusted_evaluation_identity_mismatch")
