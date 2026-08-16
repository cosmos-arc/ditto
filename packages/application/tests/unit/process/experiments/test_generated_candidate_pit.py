"""PIT feed and fold-boundary tests for generated research candidates."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date

import orjson
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
from ditto_analysis.experiments.models import CandidateId, ContentHash, SnapshotId
from ditto_analysis.experiments.persistence import DateWindow, FoldRole
from ditto_analysis.experiments.specs import CandidateSpec, FoldProtocolSpec
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    SandboxArtifactFormat,
    SandboxExecutionResult,
    SandboxFitRequest,
    SandboxScoreRequest,
    build_successful_sandbox_result,
    freeze_sandbox_artifact,
)
from ditto_application.processes.experiments.generated_candidate_evaluator import (
    TrustedCandidateEvaluationPort,
    TrustedCandidateEvaluationRequest,
)
from ditto_application.processes.experiments.generated_candidate_pit import (
    GeneratedCandidatePitDataFeed,
    GeneratedCandidatePitEvaluationRequest,
    GeneratedCandidatePitEvaluator,
    GeneratedCandidatePitQuery,
    GeneratedCandidatePitRow,
    GeneratedCandidatePitRowReader,
    GeneratedCandidateSandboxContext,
    GeneratedCandidateSandboxFactory,
)
from ditto_application.research_validation_windows import ValidationFoldPlan

INPUT_SCHEMA_HASH = ContentHash("1" * 64)
SNAPSHOT_A = SnapshotId("snapshot-generated-pit-a")
SNAPSHOT_B = SnapshotId("snapshot-generated-pit-b")
OUTPUT_SCHEMA_HASH = ContentHash("2" * 64)
STATE_SCHEMA_HASH = ContentHash("3" * 64)
SEED = 41
SOURCE = (
    "def fit(training_stream):\n"
    "    return {'mean': 0.0}\n"
    "def score(visible_window, immutable_model_state):\n"
    "    return []\n"
)


def _fold() -> ValidationFoldPlan:
    return ValidationFoldPlan(
        ordinal=2,
        role=FoldRole.WALK_FORWARD,
        train_window=DateWindow(date(2026, 1, 1), date(2026, 1, 4)),
        test_window=DateWindow(date(2026, 1, 5), date(2026, 1, 9)),
        purge_sessions=1,
        embargo_sessions=1,
    )


def _query(snapshot_id: SnapshotId = SNAPSHOT_A) -> GeneratedCandidatePitQuery:
    return GeneratedCandidatePitQuery(
        fold=_fold(),
        snapshot_id=snapshot_id,
        input_schema_hash=INPUT_SCHEMA_HASH,
        decision_time_epoch_us=1_200,
        knowledge_cutoff_epoch_us=1_000,
        publication_cutoff_epoch_us=900,
        trading_sessions=tuple(date(2026, 1, day) for day in range(1, 10)),
    )


def _row(
    *,
    session_day: int,
    event_time: int,
    known_at: int,
    publication_time: int,
    value: float,
    snapshot_id: SnapshotId = SNAPSHOT_A,
    revision_id: str = "revision-1",
) -> GeneratedCandidatePitRow:
    return GeneratedCandidatePitRow(
        entity_id="510300.SH",
        session_date=date(2026, 1, session_day),
        event_time_epoch_us=event_time,
        known_at_epoch_us=known_at,
        publication_time_epoch_us=publication_time,
        execution_eligible_at_epoch_us=event_time + 1,
        source_snapshot_id=snapshot_id,
        revision_id=revision_id,
        features={"value": value},
    )


class _Reader(GeneratedCandidatePitRowReader):
    def __init__(self, rows: tuple[GeneratedCandidatePitRow, ...]) -> None:
        self.rows = rows
        self.queries: list[GeneratedCandidatePitQuery] = []

    def read_rows(
        self, query: GeneratedCandidatePitQuery
    ) -> tuple[GeneratedCandidatePitRow, ...]:
        self.queries.append(query)
        return self.rows


def _decoded_values(payload: bytes) -> list[float]:
    decoded = orjson.loads(payload)
    return [float(row["features"]["value"]) for row in decoded["rows"]]


def test_future_sentinel_late_revision_and_fold_gaps_do_not_change_visible_data() -> (
    None
):
    reader = _Reader(
        (
            _row(
                session_day=3,
                event_time=300,
                known_at=700,
                publication_time=600,
                value=3.0,
            ),
            # The final training session is removed by the dynamic purge width.
            _row(
                session_day=4,
                event_time=400,
                known_at=700,
                publication_time=600,
                value=4_000_000.0,
            ),
            # The first test session is removed by the dynamic embargo width.
            _row(
                session_day=5,
                event_time=500,
                known_at=700,
                publication_time=600,
                value=5_000_000.0,
            ),
            _row(
                session_day=6,
                event_time=600,
                known_at=800,
                publication_time=700,
                value=6.0,
                revision_id="revision-visible",
            ),
            # A late revision and extreme value must be invisible at the cutoff.
            _row(
                session_day=6,
                event_time=600,
                known_at=1_001,
                publication_time=899,
                value=999_999_999.0,
                revision_id="revision-late",
            ),
            # Exact cutoff boundaries remain visible.
            _row(
                session_day=9,
                event_time=900,
                known_at=1_000,
                publication_time=900,
                value=9.0,
            ),
        )
    )

    data = GeneratedCandidatePitDataFeed(reader).load(_query())

    assert _decoded_values(data.training_stream.artifact.payload) == [3.0]
    assert _decoded_values(data.visible_window.artifact.payload) == [6.0, 9.0]
    assert [key.known_at_epoch_us for key in data.visible_window.score_keys] == [
        800,
        1_000,
    ]
    assert data.visible_window.snapshot_id == SNAPSHOT_A
    assert len(reader.queries) == 1


def test_future_event_is_invisible_even_when_revision_metadata_looks_old() -> None:
    reader = _Reader(
        (
            _row(
                session_day=3,
                event_time=300,
                known_at=700,
                publication_time=600,
                value=3.0,
            ),
            _row(
                session_day=6,
                event_time=600,
                known_at=800,
                publication_time=700,
                value=6.0,
            ),
            _row(
                session_day=7,
                event_time=1_201,
                known_at=800,
                publication_time=700,
                value=999_999_999.0,
            ),
        )
    )

    data = GeneratedCandidatePitDataFeed(reader).load(_query())

    assert _decoded_values(data.visible_window.artifact.payload) == [6.0]


def test_snapshot_is_part_of_cache_and_artifact_identity() -> None:
    class _SnapshotReader(GeneratedCandidatePitRowReader):
        def __init__(self) -> None:
            self.queries: list[GeneratedCandidatePitQuery] = []

        def read_rows(
            self, query: GeneratedCandidatePitQuery
        ) -> tuple[GeneratedCandidatePitRow, ...]:
            self.queries.append(query)
            return (
                _row(
                    session_day=3,
                    event_time=300,
                    known_at=700,
                    publication_time=600,
                    value=3.0,
                    snapshot_id=query.snapshot_id,
                ),
                _row(
                    session_day=6,
                    event_time=600,
                    known_at=800,
                    publication_time=700,
                    value=6.0,
                    snapshot_id=query.snapshot_id,
                ),
            )

    reader = _SnapshotReader()
    feed = GeneratedCandidatePitDataFeed(reader)
    first = feed.load(_query(SNAPSHOT_A))
    second = feed.load(_query(SNAPSHOT_B))

    assert _query(SNAPSHOT_A).cache_key != _query(SNAPSHOT_B).cache_key
    assert first.visible_window.identity_hash != second.visible_window.identity_hash
    assert [query.snapshot_id for query in reader.queries] == [SNAPSHOT_A, SNAPSHOT_B]


def test_source_snapshot_mismatch_never_falls_back_to_available_rows() -> None:
    reader = _Reader(
        (
            _row(
                session_day=3,
                event_time=300,
                known_at=700,
                publication_time=600,
                value=3.0,
                snapshot_id=SNAPSHOT_B,
            ),
        )
    )

    with pytest.raises(AppProcessError) as exc_info:
        GeneratedCandidatePitDataFeed(reader).load(_query(SNAPSHOT_A))

    assert exc_info.value.details["reason"] == "pit_source_snapshot_mismatch"


def test_same_close_execution_eligibility_is_rejected() -> None:
    row = _row(
        session_day=6,
        event_time=600,
        known_at=800,
        publication_time=700,
        value=6.0,
    )

    with pytest.raises(AppProcessError) as exc_info:
        replace(row, execution_eligible_at_epoch_us=row.event_time_epoch_us)

    assert exc_info.value.details["reason"] == "same_close_execution_forbidden"


def test_fold_isolation_cannot_exhaust_train_or_test_sessions() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        replace(_query(), fold=replace(_fold(), purge_sessions=4))
    assert exc_info.value.details["reason"] == "pit_purge_exhausts_training_window"

    with pytest.raises(AppProcessError) as exc_info:
        replace(_query(), fold=replace(_fold(), embargo_sessions=5))
    assert exc_info.value.details["reason"] == "pit_embargo_exhausts_test_window"


def _hash(value: bytes | str) -> ContentHash:
    raw = value.encode() if isinstance(value, str) else value
    return ContentHash(hashlib.sha256(raw).hexdigest())


def _code() -> ResearchCodeArtifact:
    return ResearchCodeArtifact(
        source_code=SOURCE,
        source_hash=_hash(SOURCE),
        canonical_ast_hash=canonical_research_ast_hash(SOURCE),
        dependency_lock_hash=ContentHash("4" * 64),
        dependencies=("numpy==2.3.2", "polars==1.32.2"),
        image_digest=ContentHash("5" * 64),
        input_schema_hash=INPUT_SCHEMA_HASH,
        output_schema_hash=OUTPUT_SCHEMA_HASH,
    )


def _candidate(code: ResearchCodeArtifact) -> ResearchCandidateSpec:
    return ResearchCandidateSpec(
        candidate=CandidateSpec(
            candidate_id=CandidateId("candidate-generated-pit"),
            ordinal=2,
            is_baseline=False,
            parameters={"lookback": 20},
        ),
        search_axis=SearchAxis.FACTOR_CODE,
        parent_candidate_id=CandidateId("candidate-baseline"),
        factor_code_hash=code.artifact_hash,
        model_code_hash=None,
        data_requirement_hashes=(ContentHash("6" * 64),),
    )


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        fold_protocol=FoldProtocolSpec(
            protocol_id="walk-forward-generated-pit",
            protocol_version=1,
            protocol_hash=ContentHash("7" * 64),
        ),
        snapshot_id=SNAPSHOT_A,
        validation_objective_hash=ContentHash("8" * 64),
        cost_model_hash=ContentHash("9" * 64),
        seed=SEED,
        purge_sessions=1,
        embargo_sessions=1,
    )


def _evaluation_request() -> GeneratedCandidatePitEvaluationRequest:
    code = _code()
    return GeneratedCandidatePitEvaluationRequest(
        candidate=_candidate(code),
        experiment_plan=_plan(),
        code_artifact=code,
        fold=_fold(),
        trading_sessions=tuple(date(2026, 1, day) for day in range(1, 10)),
        decision_time_epoch_us=1_200,
        knowledge_cutoff_epoch_us=1_000,
        publication_cutoff_epoch_us=900,
        resource_limits=SandboxResourceLimits(output_bytes=64 * 1024),
        seed=SEED,
    )


class _Sandbox(CandidateSandboxPort):
    def __init__(self) -> None:
        self.fit_requests: list[SandboxFitRequest] = []
        self.score_requests: list[SandboxScoreRequest] = []

    def fit(self, request: SandboxFitRequest) -> SandboxExecutionResult:
        self.fit_requests.append(request)
        state = freeze_sandbox_artifact(
            orjson.dumps({"schema_id": "r5-model-state", "mean": 0.0}),
            serialization=SandboxArtifactFormat.JSON,
            schema_hash=STATE_SCHEMA_HASH,
            row_count=1,
        )
        return build_successful_sandbox_result(request, state)

    def score(self, request: SandboxScoreRequest) -> SandboxExecutionResult:
        self.score_requests.append(request)
        output = freeze_sandbox_artifact(
            orjson.dumps(
                {
                    "schema_id": "r5-candidate-score-frame",
                    "schema_version": 1,
                    "rows": [
                        {
                            "entity_id": key.entity_id,
                            "event_time_epoch_us": key.event_time_epoch_us,
                            "score": 0.5,
                        }
                        for key in request.visible_window.score_keys
                    ],
                },
                option=orjson.OPT_SORT_KEYS,
            ),
            serialization=SandboxArtifactFormat.JSON,
            schema_hash=OUTPUT_SCHEMA_HASH,
            row_count=len(request.visible_window.score_keys),
        )
        return build_successful_sandbox_result(request, output)


class _SandboxFactory(GeneratedCandidateSandboxFactory):
    def __init__(self, *, reuse: bool = False) -> None:
        self.reuse = reuse
        self.contexts: list[GeneratedCandidateSandboxContext] = []
        self.sandboxes: list[_Sandbox] = []

    def create(self, context: GeneratedCandidateSandboxContext) -> CandidateSandboxPort:
        self.contexts.append(context)
        if self.reuse and self.sandboxes:
            return self.sandboxes[0]
        sandbox = _Sandbox()
        self.sandboxes.append(sandbox)
        return sandbox


class _Trusted(TrustedCandidateEvaluationPort):
    def __init__(self) -> None:
        self.requests: list[TrustedCandidateEvaluationRequest] = []

    def evaluate(self, request: TrustedCandidateEvaluationRequest) -> EvaluationResult:
        self.requests.append(request)
        return EvaluationResult(
            candidate_id=request.candidate_id,
            candidate_hash=request.candidate_hash,
            validation_protocol_hash=request.validation_protocol_hash,
            metrics_artifact_hash=ContentHash("a" * 64),
            constraints_passed=True,
            significance_evidence_hash=ContentHash("b" * 64),
            failure_classification=None,
            evidence_refs=(request.score_artifact_hash,),
        )


def _evaluation_rows() -> tuple[GeneratedCandidatePitRow, ...]:
    return (
        _row(
            session_day=3,
            event_time=300,
            known_at=700,
            publication_time=600,
            value=3.0,
        ),
        _row(
            session_day=6,
            event_time=600,
            known_at=800,
            publication_time=700,
            value=6.0,
        ),
    )


def test_each_evaluation_gets_fresh_fold_sandbox_and_full_temporal_handoff() -> None:
    reader = _Reader(_evaluation_rows())
    factory = _SandboxFactory()
    trusted = _Trusted()
    evaluator = GeneratedCandidatePitEvaluator(
        data_feed=GeneratedCandidatePitDataFeed(reader),
        sandbox_factory=factory,
        trusted=trusted,
    )

    first = evaluator.evaluate(_evaluation_request())
    second = evaluator.evaluate(_evaluation_request())

    assert first == second
    assert len(factory.sandboxes) == 2
    assert factory.sandboxes[0] is not factory.sandboxes[1]
    assert [len(item.fit_requests) for item in factory.sandboxes] == [1, 1]
    assert [len(item.score_requests) for item in factory.sandboxes] == [2, 2]
    assert len(reader.queries) == 1  # exact-snapshot PIT artifact is cacheable
    assert len(trusted.requests) == 2
    handoff = trusted.requests[0]
    assert handoff.decision_time_epoch_us == 1_200
    assert handoff.knowledge_cutoff_epoch_us == 1_000
    assert handoff.publication_cutoff_epoch_us == 900
    assert handoff.snapshot_id == SNAPSHOT_A
    assert handoff.score_keys[0].publication_time_epoch_us == 700
    assert handoff.score_keys[0].execution_eligible_at_epoch_us == 601


def test_trusted_handoff_rejects_score_key_beyond_host_cutoff() -> None:
    trusted = _Trusted()
    evaluator = GeneratedCandidatePitEvaluator(
        data_feed=GeneratedCandidatePitDataFeed(_Reader(_evaluation_rows())),
        sandbox_factory=_SandboxFactory(),
        trusted=trusted,
    )
    evaluator.evaluate(_evaluation_request())
    handoff = trusted.requests[0]
    forged_key = replace(
        handoff.score_keys[0],
        known_at_epoch_us=handoff.knowledge_cutoff_epoch_us + 1,
    )

    with pytest.raises(AppProcessError) as exc_info:
        replace(handoff, score_keys=(forged_key,))

    assert exc_info.value.details["reason"] == "trusted_evaluation_score_keys_invalid"


def test_reused_fold_sandbox_is_rejected_before_second_fit() -> None:
    factory = _SandboxFactory(reuse=True)
    evaluator = GeneratedCandidatePitEvaluator(
        data_feed=GeneratedCandidatePitDataFeed(_Reader(_evaluation_rows())),
        sandbox_factory=factory,
        trusted=_Trusted(),
    )
    evaluator.evaluate(_evaluation_request())

    with pytest.raises(AppProcessError) as exc_info:
        evaluator.evaluate(_evaluation_request())

    assert exc_info.value.details["reason"] == "pit_sandbox_reused"
    assert len(factory.sandboxes[0].fit_requests) == 1


def test_fold_isolation_must_match_preregistered_experiment_plan() -> None:
    request = _evaluation_request()

    with pytest.raises(AppProcessError) as exc_info:
        replace(
            request,
            experiment_plan=replace(request.experiment_plan, purge_sessions=2),
        )

    assert exc_info.value.details["reason"] == "pit_fold_isolation_plan_mismatch"
