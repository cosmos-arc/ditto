"""Fail-closed public-boundary tests for generated-candidate PIT evaluation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, datetime
from typing import cast

import pytest
from ditto_analysis.experiments.persistence import DateWindow, FoldRole
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_sandbox_port import (
    CandidateSandboxPort,
    FrozenSandboxWindow,
)
from ditto_application.processes.experiments.generated_candidate_pit import (
    GeneratedCandidatePitData,
    GeneratedCandidatePitDataFeed,
    GeneratedCandidatePitEvaluationRequest,
    GeneratedCandidatePitEvaluator,
    GeneratedCandidatePitQuery,
    GeneratedCandidatePitRow,
    GeneratedCandidatePitRowReader,
    GeneratedCandidateSandboxContext,
    GeneratedCandidateSandboxFactory,
)
from packages.application.tests.unit.process.experiments import (
    test_generated_candidate_pit as fixtures,
)

pytestmark = pytest.mark.pit


def _assert_rejected(
    action: Callable[[], object],
    reason: str,
    *,
    field: str | None = None,
    phase: str | None = None,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        action()

    assert exc_info.value.details["reason"] == reason
    if field is not None:
        assert exc_info.value.details["field"] == field
    if phase is not None:
        assert exc_info.value.details["phase"] == phase


def _valid_row() -> GeneratedCandidatePitRow:
    return fixtures._row(
        session_day=3,
        event_time=300,
        known_at=700,
        publication_time=600,
        value=3.0,
    )


@pytest.mark.parametrize(
    ("field", "value", "reason", "detail_field"),
    [
        ("entity_id", " ", "pit_row_identity_invalid", "entity_id"),
        ("revision_id", "", "pit_row_identity_invalid", "revision_id"),
        (
            "session_date",
            datetime(2026, 1, 3),
            "pit_session_date_invalid",
            None,
        ),
        (
            "event_time_epoch_us",
            -1,
            "pit_timestamp_invalid",
            "event_time_epoch_us",
        ),
        (
            "source_snapshot_id",
            "latest",
            "pit_source_snapshot_invalid",
            None,
        ),
        (
            "publication_time_epoch_us",
            701,
            "pit_publication_after_knowledge",
            None,
        ),
    ],
)
def test_pit_row_rejects_malformed_provider_identity_and_time(
    field: str,
    value: object,
    reason: str,
    detail_field: str | None,
) -> None:
    _assert_rejected(
        lambda: replace(_valid_row(), **{field: value}),
        reason,
        field=detail_field,
    )


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        (["value"], "pit_features_invalid"),
        ({" value": 1.0}, "pit_feature_name_invalid"),
        ({"value": object()}, "pit_feature_value_invalid"),
        ({"value": float("inf")}, "pit_feature_value_invalid"),
        ({}, "pit_features_invalid"),
    ],
)
def test_pit_row_rejects_noncanonical_feature_payloads(
    features: object,
    reason: str,
) -> None:
    _assert_rejected(
        lambda: replace(_valid_row(), features=features),
        reason,
    )


@pytest.mark.parametrize(
    ("field", "value", "reason", "detail_field"),
    [
        ("snapshot_id", "latest", "pit_source_snapshot_invalid", None),
        ("input_schema_hash", "schema", "pit_input_schema_invalid", None),
        (
            "decision_time_epoch_us",
            -1,
            "pit_timestamp_invalid",
            "decision_time_epoch_us",
        ),
        (
            "knowledge_cutoff_epoch_us",
            True,
            "pit_timestamp_invalid",
            "knowledge_cutoff_epoch_us",
        ),
        (
            "publication_cutoff_epoch_us",
            -1,
            "pit_timestamp_invalid",
            "publication_cutoff_epoch_us",
        ),
    ],
)
def test_pit_query_rejects_untyped_snapshot_schema_and_cutoffs(
    field: str,
    value: object,
    reason: str,
    detail_field: str | None,
) -> None:
    _assert_rejected(
        lambda: replace(fixtures._query(), **{field: value}),
        reason,
        field=detail_field,
    )


def test_pit_query_rejects_cutoff_order_that_can_expose_unknown_data() -> None:
    _assert_rejected(
        lambda: replace(
            fixtures._query(),
            publication_cutoff_epoch_us=1_001,
        ),
        "pit_temporal_order_invalid",
    )


@pytest.mark.parametrize(
    "sessions",
    [
        {date(2026, 1, day) for day in range(1, 10)},
        "2026-01-01",
    ],
)
def test_pit_query_rejects_nonsequence_and_string_calendars(
    sessions: object,
) -> None:
    _assert_rejected(
        lambda: replace(fixtures._query(), trading_sessions=sessions),
        "pit_trading_sessions_invalid",
    )


@pytest.mark.parametrize(
    "sessions",
    [
        (),
        (datetime(2026, 1, 1),),
    ],
)
def test_pit_query_rejects_empty_or_nonexact_date_calendars(
    sessions: object,
) -> None:
    _assert_rejected(
        lambda: replace(fixtures._query(), trading_sessions=sessions),
        "pit_trading_sessions_invalid",
    )


def test_pit_query_rejects_duplicate_or_nonmonotonic_sessions() -> None:
    sessions = tuple(date(2026, 1, day) for day in range(1, 10))

    for invalid in (
        (sessions[0], sessions[0], *sessions[1:]),
        (sessions[1], sessions[0], *sessions[2:]),
    ):
        _assert_rejected(
            lambda invalid=invalid: replace(
                fixtures._query(),
                trading_sessions=invalid,
            ),
            "pit_trading_sessions_invalid",
        )


def test_pit_query_requires_exact_fold_boundaries_in_calendar() -> None:
    sessions_without_train_start = tuple(date(2026, 1, day) for day in range(2, 10))

    _assert_rejected(
        lambda: replace(
            fixtures._query(),
            trading_sessions=sessions_without_train_start,
        ),
        "pit_fold_calendar_boundary_missing",
    )


@pytest.mark.parametrize(
    ("fold", "reason", "detail_field"),
    [
        (object(), "pit_fold_invalid", None),
        (
            replace(fixtures._fold(), train_window=None),
            "pit_fold_not_walk_forward",
            None,
        ),
        (
            replace(fixtures._fold(), role=FoldRole.EXPLORATION),
            "pit_fold_not_walk_forward",
            None,
        ),
        (replace(fixtures._fold(), ordinal=0), "pit_fold_invalid", None),
        (
            replace(fixtures._fold(), test_window=object()),
            "pit_fold_invalid",
            None,
        ),
        (
            replace(fixtures._fold(), purge_sessions=-1),
            "pit_fold_isolation_invalid",
            "purge_sessions",
        ),
        (
            replace(fixtures._fold(), embargo_sessions=True),
            "pit_fold_isolation_invalid",
            "embargo_sessions",
        ),
        (
            replace(
                fixtures._fold(),
                test_window=DateWindow(date(2026, 1, 4), date(2026, 1, 9)),
            ),
            "pit_fold_windows_overlap",
            None,
        ),
    ],
)
def test_pit_query_rejects_non_walk_forward_or_leaky_fold_contracts(
    fold: object,
    reason: str,
    detail_field: str | None,
) -> None:
    _assert_rejected(
        lambda: replace(fixtures._query(), fold=fold),
        reason,
        field=detail_field,
    )


def test_pit_data_rejects_unfrozen_windows() -> None:
    _assert_rejected(
        lambda: GeneratedCandidatePitData(
            training_stream=cast("FrozenSandboxWindow", object()),
            visible_window=cast("FrozenSandboxWindow", object()),
        ),
        "pit_fold_data_invalid",
    )


class _RawReader(GeneratedCandidatePitRowReader):
    def __init__(self, result: object) -> None:
        self.result = result

    def read_rows(
        self,
        query: GeneratedCandidatePitQuery,
    ) -> Sequence[GeneratedCandidatePitRow]:
        del query
        return cast("Sequence[GeneratedCandidatePitRow]", self.result)


@pytest.mark.parametrize("result", [None, "rows", {"row": 1}])
def test_feed_rejects_reader_results_that_are_not_row_sequences(result: object) -> None:
    _assert_rejected(
        lambda: GeneratedCandidatePitDataFeed(_RawReader(result)).load(
            fixtures._query()
        ),
        "pit_reader_result_invalid",
    )


def test_feed_rejects_nonrow_members_from_provider() -> None:
    _assert_rejected(
        lambda: GeneratedCandidatePitDataFeed(_RawReader((object(),))).load(
            fixtures._query()
        ),
        "pit_reader_result_invalid",
    )


def test_feed_rejects_ambiguous_revision_visibility_identity() -> None:
    original = _valid_row()
    ambiguous = replace(
        original,
        revision_id="revision-ambiguous",
        features={"value": 4.0},
    )
    score_row = fixtures._row(
        session_day=6,
        event_time=600,
        known_at=800,
        publication_time=700,
        value=6.0,
    )

    _assert_rejected(
        lambda: GeneratedCandidatePitDataFeed(
            fixtures._Reader((original, ambiguous, score_row))
        ).load(fixtures._query()),
        "pit_revision_visibility_ambiguous",
    )


@pytest.mark.parametrize(
    ("rows", "phase"),
    [
        (
            (
                fixtures._row(
                    session_day=6,
                    event_time=600,
                    known_at=800,
                    publication_time=700,
                    value=6.0,
                ),
            ),
            "fit",
        ),
        ((_valid_row(),), "score"),
    ],
)
def test_feed_fails_closed_when_an_isolated_fold_window_is_empty(
    rows: tuple[GeneratedCandidatePitRow, ...],
    phase: str,
) -> None:
    _assert_rejected(
        lambda: GeneratedCandidatePitDataFeed(fixtures._Reader(rows)).load(
            fixtures._query()
        ),
        "pit_fold_window_empty",
        phase=phase,
    )


def test_feed_rejects_untyped_query_before_calling_provider() -> None:
    reader = fixtures._Reader(())

    _assert_rejected(
        lambda: GeneratedCandidatePitDataFeed(reader).load(
            cast("GeneratedCandidatePitQuery", object())
        ),
        "pit_query_invalid",
    )

    assert reader.queries == []


@pytest.mark.parametrize(
    "field",
    [
        "candidate",
        "experiment_plan",
        "code_artifact",
        "fold",
        "resource_limits",
    ],
)
def test_pit_evaluation_request_rejects_untyped_preregistered_contracts(
    field: str,
) -> None:
    _assert_rejected(
        lambda: replace(fixtures._evaluation_request(), **{field: object()}),
        "pit_evaluation_request_invalid",
    )


@pytest.mark.parametrize("seed", [-1, True])
def test_pit_evaluation_request_requires_exact_nonnegative_seed(seed: object) -> None:
    _assert_rejected(
        lambda: replace(fixtures._evaluation_request(), seed=seed),
        "pit_evaluation_seed_invalid",
    )


def test_pit_evaluation_request_seed_must_match_preregistered_plan() -> None:
    request = fixtures._evaluation_request()

    _assert_rejected(
        lambda: replace(request, seed=request.seed + 1),
        "pit_evaluation_seed_plan_mismatch",
    )


def _sandbox_context() -> GeneratedCandidateSandboxContext:
    request = fixtures._evaluation_request()
    query = request.pit_query
    return GeneratedCandidateSandboxContext(
        candidate_id=request.candidate.candidate.candidate_id,
        candidate_hash=request.candidate.candidate_hash,
        fold_ordinal=request.fold.ordinal,
        snapshot_id=request.experiment_plan.snapshot_id,
        pit_query_hash=query.cache_key,
        code_artifact_hash=request.code_artifact.artifact_hash,
    )


@pytest.mark.parametrize(
    "field",
    [
        "candidate_id",
        "candidate_hash",
        "snapshot_id",
        "pit_query_hash",
        "code_artifact_hash",
    ],
)
def test_sandbox_context_rejects_untyped_pit_identity(field: str) -> None:
    _assert_rejected(
        lambda: replace(_sandbox_context(), **{field: object()}),
        "pit_sandbox_context_invalid",
    )


@pytest.mark.parametrize("ordinal", [0, True])
def test_sandbox_context_requires_positive_exact_fold_ordinal(ordinal: object) -> None:
    _assert_rejected(
        lambda: replace(_sandbox_context(), fold_ordinal=ordinal),
        "pit_sandbox_context_invalid",
    )


def _evaluator(
    factory: GeneratedCandidateSandboxFactory,
) -> tuple[GeneratedCandidatePitEvaluator, fixtures._Trusted]:
    trusted = fixtures._Trusted()
    evaluator = GeneratedCandidatePitEvaluator(
        data_feed=GeneratedCandidatePitDataFeed(
            fixtures._Reader(fixtures._evaluation_rows())
        ),
        sandbox_factory=factory,
        trusted=trusted,
    )
    return evaluator, trusted


def test_evaluator_rejects_untyped_request_before_pit_data_access() -> None:
    factory = fixtures._SandboxFactory()
    evaluator, trusted = _evaluator(factory)

    _assert_rejected(
        lambda: evaluator.evaluate(
            cast("GeneratedCandidatePitEvaluationRequest", object())
        ),
        "pit_evaluation_request_invalid",
    )

    assert factory.contexts == []
    assert trusted.requests == []


class _InvalidSandboxFactory(GeneratedCandidateSandboxFactory):
    def __init__(self) -> None:
        self.contexts: list[GeneratedCandidateSandboxContext] = []

    def create(self, context: GeneratedCandidateSandboxContext) -> CandidateSandboxPort:
        self.contexts.append(context)
        return cast("CandidateSandboxPort", object())


def test_evaluator_rejects_provider_without_sandbox_protocol_before_execution() -> None:
    factory = _InvalidSandboxFactory()
    evaluator, trusted = _evaluator(factory)

    _assert_rejected(
        lambda: evaluator.evaluate(fixtures._evaluation_request()),
        "pit_sandbox_invalid",
    )

    assert len(factory.contexts) == 1
    assert trusted.requests == []
