"""Unit tests for research experiment routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.candidate_selection import (
    CandidateSelectionHandler,
    CandidateSelectionReceipt,
)
from ditto_application.commands.experiments import (
    ClaimHoldoutCandidateHandler,
    LaunchExperimentCommand,
    LaunchExperimentHandler,
    PauseExperimentHandler,
    RetryExperimentFoldHandler,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments.comparison_reader import (
    CandidateComparisonView,
    ExperimentComparisonReader,
)
from ditto_application.processes.experiments.holdout import HoldoutClaimReceipt
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
    PreflightOutcome,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPlanningProcess,
    ExperimentPreflightReport,
    ExperimentPreflightStatus,
)
from ditto_application.processes.experiments.selection_evidence_reader import (
    ExperimentSelectionEvidenceReader,
    SelectionEvidenceView,
)
from ditto_application.queries.experiments import (
    ExperimentArtifactReadModel,
    ExperimentCandidateReadModel,
    ExperimentDetailReadModel,
    ExperimentFoldReadModel,
    ExperimentGateReadModel,
    ExperimentQueryFacade,
)
from ditto_apps.api.errors import (
    APIError,
    ConflictError,
    NotFoundError,
    UnprocessableEntityError,
)
from ditto_apps.api.routes import research_experiment_routes
from ditto_apps.api.routes.research_experiment_routes import (
    get_experiment,
    get_experiment_comparison,
    get_experiment_selection_evidence,
    launch_experiment,
    list_experiment_artifacts,
    pause_experiment,
    preflight_experiment,
    retry_fold_experiment,
    to_artifact_response,
    to_comparison_response,
    to_experiment_response,
    to_gate_response,
    to_selection_evidence_response,
)
from ditto_apps.api.routes.research_selection_routes import (
    claim_experiment_holdout,
    select_experiment_candidate,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    CandidateSelectionReceiptResponse,
    CandidateSelectionRequest,
    ExperimentArtifactResponse,
    ExperimentCandidateResponse,
    ExperimentComparisonResponse,
    ExperimentControlReceiptResponse,
    ExperimentControlRequest,
    ExperimentDetailResponse,
    ExperimentLaunchRequest,
    ExperimentLaunchResponse,
    ExperimentPlanningRequest,
    ExperimentPreflightResponse,
    ExperimentRetryFoldRequest,
    ExperimentSelectionEvidenceResponse,
    HoldoutEvaluationReceiptResponse,
    HoldoutEvaluationRequest,
    HoldoutSelectionReasonRequest,
)

pytestmark = pytest.mark.asyncio

_GetRoute = Callable[..., Awaitable[APIResponse[ExperimentDetailResponse]]]
_CandidateRoute = Callable[
    ..., Awaitable[APIResponse[list[ExperimentCandidateResponse]]]
]
_ArtifactRoute = Callable[..., Awaitable[APIResponse[list[ExperimentArtifactResponse]]]]
_SelectionEvidenceRoute = Callable[
    ..., Awaitable[APIResponse[ExperimentSelectionEvidenceResponse]]
]
_ComparisonRoute = Callable[..., Awaitable[APIResponse[ExperimentComparisonResponse]]]
_ControlRoute = Callable[..., Awaitable[APIResponse[ExperimentControlReceiptResponse]]]
_PreflightRoute = Callable[..., Awaitable[APIResponse[ExperimentPreflightResponse]]]
_LaunchRoute = Callable[..., Awaitable[APIResponse[ExperimentLaunchResponse]]]
_CandidateSelectionRoute = Callable[
    ..., Awaitable[APIResponse[CandidateSelectionReceiptResponse]]
]
_HoldoutRoute = Callable[..., Awaitable[APIResponse[HoldoutEvaluationReceiptResponse]]]


@pytest.fixture(autouse=True)
def _inline_experiment_route_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.research_experiment_routes.run_blocking",
        run_inline,
    )
    monkeypatch.setattr(
        "ditto_apps.api.routes.research_selection_routes.run_blocking",
        run_inline,
    )


def _candidate() -> ExperimentCandidateReadModel:
    return ExperimentCandidateReadModel(
        candidate_id="candidate-1",
        ordinal=3,
        is_baseline=False,
        parameters=MappingProxyType(
            {
                "lookback": 20,
                "weights": (0.25, 0.75),
                "meta": MappingProxyType({"family": "momentum"}),
            }
        ),
    )


def _planning_payload() -> dict[str, object]:
    return {
        "experiment_id": "exp-1",
        "research_cycle_id": "cycle-1",
        "research_cycle_hash": "a" * 64,
        "strategy": {
            "strategy_id": "strategy-1",
            "version": 2,
            "spec_hash": "b" * 64,
            "spec_json": {"name": "Strategy"},
        },
        "snapshot": {
            "snapshot_id": "snapshot-1",
            "manifest_hash": "c" * 64,
        },
        "validation": {"trading_sessions": ["2026-07-30"]},
        "matrix": {
            "baseline": {
                "descriptor_type": "active-strategy",
                "payload": {"strategy_id": "strategy-1"},
                "schema_version": 1,
            },
            "axes": [
                {
                    "name": "selector.top_k",
                    "values": [{"type": "int", "value": 10}],
                }
            ],
            "candidate_limit": 4,
        },
        "promotion_objective": {
            "schema_id": "r3-promotion-objective",
            "schema_version": 1,
        },
        "dataset_requirements": [
            {
                "dataset_id": "etf_daily",
                "expected_snapshot_ids": ["provider-snapshot-1"],
                "requires_pit_universe": True,
                "certified_from": "2016-01-01",
            }
        ],
        "cost_model": {
            "bytes_per_run": 100,
            "bytes_per_trading_session": 2,
        },
        "budget": {
            "candidate_limit": 4,
            "fold_run_limit": 100,
            "trading_session_limit": 10_000,
            "disk_byte_limit": 1_000_000,
        },
        "seed": 42,
        "worker_count": 2,
        "failure_policy": "fail_fast",
        "created_at": "2026-07-30T00:00:00Z",
    }


def _preflight_report() -> ExperimentPreflightReport:
    return ExperimentPreflightReport(
        status=ExperimentPreflightStatus.READY,
        plan_hash="d" * 64,
        checks=(
            ExperimentPreflightCheck(
                rule_id="history",
                outcome=PreflightOutcome.PASS,
                code=None,
                reason=None,
                remediation=None,
                observed=MappingProxyType({"eligible_month_count": 96}),
                policy=MappingProxyType({"promotion_minimum": 96}),
            ),
        ),
        candidate_count=2,
        planned_fold_count=8,
        budget_run_count=7,
        estimated_trading_sessions=1234,
        estimated_disk_bytes=5678,
        eligible_month_count=96,
        isolation_width_sessions=5,
        validation_plan=None,
        work_plan=None,
    )


def _fold() -> ExperimentFoldReadModel:
    return ExperimentFoldReadModel(
        candidate_id="candidate-1",
        fold_id="fold-1",
        ordinal=4,
        role="walk_forward",
        status="completed",
        train_start=date(2018, 1, 1),
        train_end=date(2023, 12, 31),
        test_start=date(2024, 1, 1),
        test_end=date(2024, 12, 31),
        purge_sessions=5,
        embargo_sessions=2,
        claim_owner_token="worker-1",
        revision=8,
        updated_at=datetime(2026, 7, 23, 1, 2, 3, tzinfo=UTC),
    )


def _detail() -> ExperimentDetailReadModel:
    return ExperimentDetailReadModel(
        experiment_id="exp-1",
        research_cycle_id="cycle-1",
        research_cycle_hash="cycle-hash",
        strategy_version="v1",
        strategy_spec_hash="spec-hash",
        snapshot_id="snap-1",
        status="completed",
        desired_state="running",
        stage="completed",
        failure_code="candidate_failure",
        queue_ordinal=7,
        revision=9,
        created_at=datetime(2026, 7, 23, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 23, 1, 0, 0, tzinfo=UTC),
        seed=42,
        worker_count=2,
        failure_policy="continue",
        candidate_limit=128,
        fold_run_limit=24,
        fold_protocol_id="fold-proto",
        fold_protocol_version=1,
        fold_protocol_hash="fold-hash",
        candidates=(_candidate(),),
        folds=(_fold(),),
    )


async def _call_get(
    experiment_id: str,
    facade: MagicMock,
) -> APIResponse[ExperimentDetailResponse]:
    route = cast(
        _GetRoute,
        getattr(get_experiment, "__dishka_orig_func__", get_experiment),
    )
    return await route(experiment_id=experiment_id, facade=facade)


def test_to_experiment_response_maps_every_application_field_without_loss() -> None:
    response = to_experiment_response(_detail())

    assert response.model_dump(mode="json") == {
        "experiment_id": "exp-1",
        "research_cycle_id": "cycle-1",
        "research_cycle_hash": "cycle-hash",
        "strategy_version": "v1",
        "strategy_spec_hash": "spec-hash",
        "snapshot_id": "snap-1",
        "status": "completed",
        "desired_state": "running",
        "stage": "completed",
        "failure_code": "candidate_failure",
        "queue_ordinal": 7,
        "revision": 9,
        "created_at": "2026-07-23T00:00:00Z",
        "updated_at": "2026-07-23T01:00:00Z",
        "seed": 42,
        "worker_count": 2,
        "failure_policy": "continue",
        "candidate_limit": 128,
        "fold_run_limit": 24,
        "fold_protocol_id": "fold-proto",
        "fold_protocol_version": 1,
        "fold_protocol_hash": "fold-hash",
        "candidate_count": 1,
        "fold_count": 1,
        "candidates": [
            {
                "candidate_id": "candidate-1",
                "ordinal": 3,
                "is_baseline": False,
                "parameters": {
                    "lookback": 20,
                    "weights": [0.25, 0.75],
                    "meta": {"family": "momentum"},
                },
            }
        ],
        "folds": [
            {
                "candidate_id": "candidate-1",
                "fold_id": "fold-1",
                "ordinal": 4,
                "role": "walk_forward",
                "status": "completed",
                "train_start": "2018-01-01",
                "train_end": "2023-12-31",
                "test_start": "2024-01-01",
                "test_end": "2024-12-31",
                "purge_sessions": 5,
                "embargo_sessions": 2,
                "claim_owner_token": "worker-1",
                "revision": 8,
                "updated_at": "2026-07-23T01:02:03Z",
            }
        ],
    }


def test_to_gate_response_preserves_lineage_policy_and_payload_hash() -> None:
    gate = ExperimentGateReadModel(
        evaluation_id="gate-1",
        experiment_id="exp-1",
        candidate_id="candidate-1",
        fold_id="fold-1",
        attempt_id="attempt-1",
        rule_id="history",
        policy_version="r3-v1",
        layer="hard",
        outcome="pass",
        observed=MappingProxyType({"months": 96, "warnings": ("none",)}),
        policy=MappingProxyType({"minimum_months": 96}),
        artifact_id="artifact-1",
        payload_hash="a" * 64,
        evaluated_at=datetime(2026, 7, 23, 2, 0, 0, tzinfo=UTC),
    )

    response = to_gate_response(gate)

    assert response.model_dump(mode="json") == {
        "evaluation_id": "gate-1",
        "experiment_id": "exp-1",
        "candidate_id": "candidate-1",
        "fold_id": "fold-1",
        "attempt_id": "attempt-1",
        "rule_id": "history",
        "policy_version": "r3-v1",
        "layer": "hard",
        "outcome": "pass",
        "observed": {"months": 96, "warnings": ["none"]},
        "policy": {"minimum_months": 96},
        "artifact_id": "artifact-1",
        "payload_hash": "a" * 64,
        "evaluated_at": "2026-07-23T02:00:00Z",
    }


def test_candidate_mapping_rejects_non_string_keys_without_coercion() -> None:
    candidate = ExperimentCandidateReadModel(
        candidate_id="candidate-drift",
        ordinal=1,
        is_baseline=False,
        parameters=cast(
            Any,
            MappingProxyType(
                {"nested": MappingProxyType({1: "invalid"})},
            ),
        ),
    )

    with pytest.raises(TypeError, match="mapping key must be str"):
        research_experiment_routes.to_candidate_response(candidate)


async def test_get_experiment_returns_detail() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.return_value = _detail()

    response = await _call_get("exp-1", facade)

    facade.get.assert_called_once_with("exp-1")
    assert response.data.experiment_id == "exp-1"


async def test_get_experiment_raises_not_found() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.return_value = None

    with pytest.raises(NotFoundError):
        await _call_get("missing", facade)


async def _call_preflight(
    request: ExperimentPlanningRequest,
    process: MagicMock,
) -> APIResponse[ExperimentPreflightResponse]:
    route = cast(
        _PreflightRoute,
        getattr(preflight_experiment, "__dishka_orig_func__", preflight_experiment),
    )
    return await route(experiment_id="exp-1", request=request, process=process)


async def test_preflight_builds_canonical_request_and_maps_every_typed_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExperimentPlanningRequest.model_validate(_planning_payload())
    application_request = MagicMock()
    builder = MagicMock(return_value=application_request)
    monkeypatch.setattr(
        research_experiment_routes,
        "build_experiment_planning_request",
        builder,
    )
    process = MagicMock(spec=ExperimentPlanningProcess)
    process.preflight.return_value = _preflight_report()

    response = await _call_preflight(request, process)

    builder.assert_called_once_with(request.model_dump(mode="python"))
    process.preflight.assert_called_once_with(application_request)
    assert response.data.model_dump(mode="json") == {
        "status": "ready",
        "plan_hash": "d" * 64,
        "checks": [
            {
                "rule_id": "history",
                "outcome": "pass",
                "code": None,
                "reason": None,
                "remediation": None,
                "observed": {"eligible_month_count": 96},
                "policy": {"promotion_minimum": 96},
            }
        ],
        "candidate_count": 2,
        "planned_fold_count": 8,
        "budget_run_count": 7,
        "estimated_trading_sessions": 1234,
        "estimated_disk_bytes": 5678,
        "eligible_month_count": 96,
        "isolation_width_sessions": 5,
    }


async def test_preflight_rejects_path_body_experiment_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExperimentPlanningRequest.model_validate(_planning_payload())
    builder = MagicMock()
    monkeypatch.setattr(
        research_experiment_routes,
        "build_experiment_planning_request",
        builder,
    )
    process = MagicMock(spec=ExperimentPlanningProcess)
    route = getattr(preflight_experiment, "__dishka_orig_func__", preflight_experiment)

    with pytest.raises(UnprocessableEntityError) as caught:
        await route(experiment_id="different", request=request, process=process)

    assert caught.value.error_code == "SPEC_INVALID"
    builder.assert_not_called()
    process.preflight.assert_not_called()


async def test_preflight_maps_typed_builder_failure_to_unprocessable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExperimentPlanningRequest.model_validate(_planning_payload())
    monkeypatch.setattr(
        research_experiment_routes,
        "build_experiment_planning_request",
        MagicMock(
            side_effect=AppProcessError(
                "canonical planning document is invalid",
                details={"code": "SPEC_INVALID", "reason": "strategy_hash_mismatch"},
            )
        ),
    )
    process = MagicMock(spec=ExperimentPlanningProcess)

    with pytest.raises(UnprocessableEntityError) as caught:
        await _call_preflight(request, process)

    assert caught.value.error_code == "SPEC_INVALID"
    process.preflight.assert_not_called()


async def _call_launch(
    request: ExperimentLaunchRequest,
    handler: MagicMock,
) -> APIResponse[ExperimentLaunchResponse]:
    route = cast(
        _LaunchRoute,
        getattr(launch_experiment, "__dishka_orig_func__", launch_experiment),
    )
    return await route(
        request=request,
        idempotency_key="unit.launch-001",
        handler=handler,
    )


async def test_launch_rebuilds_same_document_and_returns_exact_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {**_planning_payload(), "confirmed_plan_hash": "d" * 64}
    request = ExperimentLaunchRequest.model_validate(payload)
    application_request = MagicMock()
    builder = MagicMock(return_value=application_request)
    monkeypatch.setattr(
        research_experiment_routes,
        "build_experiment_planning_request",
        builder,
    )
    handler = MagicMock(spec=LaunchExperimentHandler)
    handler.handle.return_value = ExperimentLaunchReceipt(
        experiment_id="exp-1",
        status="queued",
        queue_ordinal=3,
        revision=1,
        candidate_count=2,
        fold_count=8,
        plan_hash="d" * 64,
    )

    response = await _call_launch(request, handler)

    expected_document = _planning_payload()
    builder.assert_called_once_with(expected_document)
    command = handler.handle.call_args.args[0]
    assert type(command) is LaunchExperimentCommand
    assert command.request is application_request
    assert command.confirmed_plan_hash == "d" * 64
    assert response.data.model_dump(mode="json") == {
        "experiment_id": "exp-1",
        "status": "queued",
        "queue_ordinal": 3,
        "revision": 1,
        "candidate_count": 2,
        "fold_count": 8,
        "plan_hash": "d" * 64,
    }


@pytest.mark.parametrize(
    ("code", "expected_error"),
    [
        ("PLAN_HASH_MISMATCH", ConflictError),
        ("EXPERIMENT_ALREADY_EXISTS", ConflictError),
        ("HARD_GATE_FAILED", UnprocessableEntityError),
        ("SPEC_INVALID", UnprocessableEntityError),
        ("MATRIX_TOO_LARGE", UnprocessableEntityError),
        ("BUDGET_EXCEEDED", UnprocessableEntityError),
        ("SNAPSHOT_NOT_CERTIFIED", UnprocessableEntityError),
        ("INSUFFICIENT_HISTORY", UnprocessableEntityError),
        ("WINDOW_LEAKAGE", UnprocessableEntityError),
        ("EXECUTOR_UNAVAILABLE", UnprocessableEntityError),
    ],
)
async def test_launch_maps_only_typed_planning_error_codes(
    code: str,
    expected_error: type[ConflictError] | type[UnprocessableEntityError],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {**_planning_payload(), "confirmed_plan_hash": "d" * 64}
    request = ExperimentLaunchRequest.model_validate(payload)
    monkeypatch.setattr(
        research_experiment_routes,
        "build_experiment_planning_request",
        MagicMock(return_value=MagicMock()),
    )
    handler = MagicMock(spec=LaunchExperimentHandler)
    handler.handle.side_effect = AppCommandError(
        "launch rejected",
        details={"code": code, "reason": "typed_failure"},
    )

    with pytest.raises(expected_error) as caught:
        await _call_launch(request, handler)

    assert caught.value.error_code == code


@pytest.mark.parametrize(
    "code",
    [
        "EXPERIMENT_PERSISTENCE_FAILED",
        "FUTURE_TYPED_PLANNING_FAILURE",
    ],
)
async def test_launch_maps_unrecognized_typed_errors_to_stable_internal_error(
    code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {**_planning_payload(), "confirmed_plan_hash": "d" * 64}
    request = ExperimentLaunchRequest.model_validate(payload)
    monkeypatch.setattr(
        research_experiment_routes,
        "build_experiment_planning_request",
        MagicMock(return_value=MagicMock()),
    )
    handler = MagicMock(spec=LaunchExperimentHandler)
    handler.handle.side_effect = AppCommandError(
        "launch failed internally",
        details={"code": code, "reason": "typed_internal_failure"},
    )

    with pytest.raises(APIError) as caught:
        await _call_launch(request, handler)

    assert caught.value.status_code == 500
    assert caught.value.error_code == code


async def _call_candidates(
    experiment_id: str,
    facade: MagicMock,
) -> APIResponse[list[ExperimentCandidateResponse]]:
    endpoint = getattr(
        research_experiment_routes,
        "list_experiment_candidates",
        None,
    )
    assert callable(endpoint), "GET /{experiment_id}/candidates is not implemented"
    route = cast(
        _CandidateRoute,
        getattr(endpoint, "__dishka_orig_func__", endpoint),
    )
    return await route(experiment_id=experiment_id, facade=facade)


async def test_list_experiment_candidates_uses_same_detail_lineage() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.return_value = _detail()

    response = await _call_candidates("exp-1", facade)

    facade.get.assert_called_once_with("exp-1")
    assert [candidate.model_dump(mode="json") for candidate in response.data] == [
        {
            "candidate_id": "candidate-1",
            "ordinal": 3,
            "is_baseline": False,
            "parameters": {
                "lookback": 20,
                "weights": [0.25, 0.75],
                "meta": {"family": "momentum"},
            },
        }
    ]


async def test_list_experiment_candidates_raises_not_found_for_missing_parent() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.return_value = None

    with pytest.raises(NotFoundError):
        await _call_candidates("missing", facade)

    facade.get.assert_called_once_with("missing")


def _artifact_read_model() -> ExperimentArtifactReadModel:
    return ExperimentArtifactReadModel(
        artifact_id="artifact-1",
        experiment_id="exp-1",
        candidate_id="candidate-1",
        fold_id="fold-1",
        attempt_id="attempt-1",
        artifact_kind="comparison-ledger",
        relative_path="experiments/exp-1/comparison.parquet",
        content_hash="a" * 64,
        schema_hash="b" * 64,
        row_count=2,
        byte_size=128,
        reproduction_fingerprint="d" * 64,
        manifest=MappingProxyType({"format": "parquet"}),
        is_pinned=False,
        pinned_at=None,
        created_at=datetime(2026, 7, 23, 0, 0, 0, tzinfo=UTC),
        revision=0,
    )


def test_to_artifact_response_maps_every_application_field_without_loss() -> None:
    response = to_artifact_response(_artifact_read_model())

    assert response.model_dump(mode="json") == {
        "artifact_id": "artifact-1",
        "experiment_id": "exp-1",
        "candidate_id": "candidate-1",
        "fold_id": "fold-1",
        "attempt_id": "attempt-1",
        "artifact_kind": "comparison-ledger",
        "relative_path": "experiments/exp-1/comparison.parquet",
        "content_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "row_count": 2,
        "byte_size": 128,
        "reproduction_fingerprint": "d" * 64,
        "manifest": {"format": "parquet"},
        "is_pinned": False,
        "pinned_at": None,
        "created_at": "2026-07-23T00:00:00Z",
        "revision": 0,
    }


async def _call_artifacts(
    experiment_id: str,
    facade: MagicMock,
) -> APIResponse[list[ExperimentArtifactResponse]]:
    route = cast(
        "_ArtifactRoute",
        getattr(
            list_experiment_artifacts, "__dishka_orig_func__", list_experiment_artifacts
        ),
    )
    return await route(experiment_id=experiment_id, facade=facade)


async def test_list_experiment_artifacts_returns_lineage_in_storage_order() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.return_value = _detail()
    facade.list_artifacts.return_value = (_artifact_read_model(),)

    response = await _call_artifacts("exp-1", facade)

    facade.get.assert_called_once_with("exp-1")
    facade.list_artifacts.assert_called_once_with("exp-1")
    assert [artifact.model_dump(mode="json") for artifact in response.data] == [
        to_artifact_response(_artifact_read_model()).model_dump(mode="json")
    ]


async def test_list_experiment_artifacts_raises_not_found_for_missing_parent() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get.return_value = None

    with pytest.raises(NotFoundError):
        await _call_artifacts("missing", facade)

    facade.get.assert_called_once_with("missing")
    facade.list_artifacts.assert_not_called()


def _selection_view() -> SelectionEvidenceView:
    return SelectionEvidenceView(
        artifact_id="selection-evidence-" + "a" * 64,
        experiment_id="exp-1",
        content_hash="a" * 64,
        byte_size=128,
        is_pinned=True,
        created_at=datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC),
        payload=MappingProxyType({"selected": ("candidate-1",)}),
    )


def test_to_selection_evidence_response_maps_payload_and_metadata() -> None:
    response = to_selection_evidence_response(_selection_view())

    assert response.model_dump(mode="json") == {
        "artifact_id": "selection-evidence-" + "a" * 64,
        "experiment_id": "exp-1",
        "content_hash": "a" * 64,
        "byte_size": 128,
        "is_pinned": True,
        "created_at": "2026-07-30T00:00:00Z",
        "payload": {"selected": ["candidate-1"]},
    }


async def _call_selection_evidence(
    experiment_id: str,
    reader: MagicMock,
) -> APIResponse[ExperimentSelectionEvidenceResponse]:
    route = cast(
        "_SelectionEvidenceRoute",
        getattr(
            get_experiment_selection_evidence,
            "__dishka_orig_func__",
            get_experiment_selection_evidence,
        ),
    )
    return await route(experiment_id=experiment_id, reader=reader)


async def test_get_experiment_selection_evidence_returns_view() -> None:
    reader = MagicMock(spec=ExperimentSelectionEvidenceReader)
    reader.load_view.return_value = _selection_view()

    response = await _call_selection_evidence("exp-1", reader)

    reader.load_view.assert_called_once_with("exp-1")
    assert response.data.content_hash == "a" * 64
    assert response.data.payload == {"selected": ["candidate-1"]}


async def test_get_experiment_selection_evidence_raises_not_found_when_absent() -> None:
    reader = MagicMock(spec=ExperimentSelectionEvidenceReader)
    reader.load_view.return_value = None

    with pytest.raises(NotFoundError):
        await _call_selection_evidence("exp-1", reader)


def _comparison_view() -> CandidateComparisonView:
    return CandidateComparisonView(
        experiment_id="exp-1",
        payload_hash="a" * 64,
        revision=7,
        payload=MappingProxyType(
            {"baseline": MappingProxyType({"candidate_id": "candidate-1"}), "folds": ()}
        ),
    )


def test_to_comparison_response_maps_payload() -> None:
    response = to_comparison_response(_comparison_view())

    assert response.model_dump(mode="json") == {
        "experiment_id": "exp-1",
        "payload_hash": "a" * 64,
        "revision": 7,
        "payload": {"baseline": {"candidate_id": "candidate-1"}, "folds": []},
    }


async def _call_comparison(
    experiment_id: str,
    reader: MagicMock,
) -> APIResponse[ExperimentComparisonResponse]:
    route = cast(
        "_ComparisonRoute",
        getattr(
            get_experiment_comparison,
            "__dishka_orig_func__",
            get_experiment_comparison,
        ),
    )
    return await route(experiment_id=experiment_id, reader=reader)


async def test_get_experiment_comparison_returns_view() -> None:
    reader = MagicMock(spec=ExperimentComparisonReader)
    reader.load_comparison.return_value = _comparison_view()

    response = await _call_comparison("exp-1", reader)

    reader.load_comparison.assert_called_once_with("exp-1")
    assert response.data.experiment_id == "exp-1"
    assert response.data.payload == {
        "baseline": {"candidate_id": "candidate-1"},
        "folds": [],
    }


async def test_get_experiment_comparison_raises_not_found_when_absent() -> None:
    reader = MagicMock(spec=ExperimentComparisonReader)
    reader.load_comparison.return_value = None

    with pytest.raises(NotFoundError):
        await _call_comparison("exp-1", reader)


def _receipt() -> ExperimentControlReceipt:
    return ExperimentControlReceipt(
        experiment_id="exp-1",
        status="pause_requested",
        desired_state="pause",
        revision=2,
        occurred_at=datetime(2026, 7, 25, 0, 0, 0, tzinfo=UTC),
        live_run_ids=("run-1", "run-2"),
    )


def _control_error(reason: str, *, code: str = "SPEC_INVALID") -> AppCommandError:
    return AppCommandError("control failed", details={"code": code, "reason": reason})


async def _call_pause(
    request: ExperimentControlRequest,
    handler: MagicMock,
) -> APIResponse[ExperimentControlReceiptResponse]:
    route = cast(
        _ControlRoute,
        getattr(pause_experiment, "__dishka_orig_func__", pause_experiment),
    )
    return await route(
        experiment_id="exp-1",
        request=request,
        idempotency_key="unit.pause-001",
        handler=handler,
    )


async def test_pause_experiment_returns_receipt() -> None:
    handler = MagicMock(spec=PauseExperimentHandler)
    handler.handle.return_value = _receipt()

    response = await _call_pause(ExperimentControlRequest(expected_revision=1), handler)

    assert response.data.status == "pause_requested"
    assert response.data.live_run_ids == ["run-1", "run-2"]
    command = handler.handle.call_args.args[0]
    assert command.experiment_id == "exp-1"
    assert command.expected_revision == 1


async def test_pause_experiment_maps_stale_revision_to_conflict() -> None:
    handler = MagicMock(spec=PauseExperimentHandler)
    handler.handle.side_effect = _control_error("stale_projection_revision")

    with pytest.raises(ConflictError):
        await _call_pause(ExperimentControlRequest(expected_revision=1), handler)


async def test_pause_experiment_maps_not_found_reason_to_not_found() -> None:
    handler = MagicMock(spec=PauseExperimentHandler)
    handler.handle.side_effect = _control_error(
        "experiment_not_found", code="EXPERIMENT_INTEGRITY_FAILED"
    )

    with pytest.raises(NotFoundError):
        await _call_pause(ExperimentControlRequest(expected_revision=1), handler)


async def test_pause_experiment_maps_invalid_receipt_to_stable_internal_error() -> None:
    handler = MagicMock(spec=PauseExperimentHandler)
    handler.handle.side_effect = _control_error(
        "idempotency_receipt_invalid",
        code="IDEMPOTENCY_RECEIPT_INVALID",
    )

    with pytest.raises(APIError) as caught:
        await _call_pause(ExperimentControlRequest(expected_revision=1), handler)

    assert caught.value.status_code == 500
    assert caught.value.error_code == "IDEMPOTENCY_RECEIPT_INVALID"


async def test_retry_fold_experiment_passes_fold_fields() -> None:
    handler = MagicMock(spec=RetryExperimentFoldHandler)
    handler.handle.return_value = _receipt()

    route = getattr(
        retry_fold_experiment, "__dishka_orig_func__", retry_fold_experiment
    )
    response = await route(
        experiment_id="exp-1",
        request=ExperimentRetryFoldRequest(
            candidate_id="cand-1", fold_id="fold-1", expected_revision=3
        ),
        idempotency_key="unit.retry-001",
        handler=handler,
    )

    assert response.data.revision == 2
    command = handler.handle.call_args.args[0]
    assert command.candidate_id == "cand-1"
    assert command.fold_id == "fold-1"
    assert command.expected_revision == 3


async def test_candidate_selection_route_builds_idempotent_command_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    occurred_at = datetime(2026, 8, 1, 1, 2, 3, tzinfo=UTC)
    monkeypatch.setattr(
        research_experiment_routes,
        "mutation_occurred_at",
        lambda: occurred_at,
    )
    handler = MagicMock(spec=CandidateSelectionHandler)
    handler.handle.return_value = CandidateSelectionReceipt(
        selection_id="candidate-selection:one",
        experiment_id="exp-1",
        candidate_id="candidate-1",
        comparison_payload_hash="a" * 64,
        candidate_evidence_artifact_id="candidate-evidence-1",
        candidate_evidence_content_hash="b" * 64,
        selection_evidence_content_hash="c" * 64,
        experiment_revision=8,
        event_id="status:selection",
        occurred_at=occurred_at,
    )
    route = cast(
        _CandidateSelectionRoute,
        getattr(
            select_experiment_candidate,
            "__dishka_orig_func__",
            select_experiment_candidate,
        ),
    )

    response = await route(
        experiment_id="exp-1",
        request=CandidateSelectionRequest(
            candidate_id="candidate-1",
            rationale="selected after objective review",
            comparison_payload_hash="a" * 64,
            expected_revision=7,
        ),
        handler=handler,
        idempotency_key="selection-key-1",
    )

    command = handler.handle.call_args.args[0]
    assert command.request.experiment_id == "exp-1"
    assert command.request.expected_revision == 7
    assert command.request.idempotency.operation_id == (
        "design_research_candidate_selection"
    )
    assert response.data.selection_id == "candidate-selection:one"
    assert response.data.revision == 8


async def test_holdout_route_binds_persisted_selection_and_evidence_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    occurred_at = datetime(2026, 8, 1, 1, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(
        research_experiment_routes,
        "mutation_occurred_at",
        lambda: occurred_at,
    )
    handler = MagicMock(spec=ClaimHoldoutCandidateHandler)
    handler.handle.return_value = HoldoutClaimReceipt(
        claim_id="holdout-claim-1",
        experiment_id="exp-1",
        candidate_id="candidate-1",
        fold_id="holdout-candidate-1",
        logical_run_id="holdout-run-1",
        reproduction_fingerprint="d" * 64,
        claim_payload_hash="e" * 64,
        selection_evidence_hash="c" * 64,
        experiment_revision=9,
        event_id="status:holdout",
        occurred_at=occurred_at,
        selection_id="candidate-selection:one",
        candidate_evidence_content_hash="b" * 64,
    )
    route = cast(
        _HoldoutRoute,
        getattr(
            claim_experiment_holdout,
            "__dishka_orig_func__",
            claim_experiment_holdout,
        ),
    )

    response = await route(
        experiment_id="exp-1",
        request=HoldoutEvaluationRequest(
            candidate_id="candidate-1",
            selection_id="candidate-selection:one",
            expected_selection_evidence_hash="c" * 64,
            expected_candidate_evidence_content_hash="b" * 64,
            expected_revision=8,
            operator_confirmation="operator reviewed immutable evidence",
            selection_reason=HoldoutSelectionReasonRequest(
                code="objective_review",
                summary="candidate won the registered objective",
            ),
        ),
        handler=handler,
        idempotency_key="holdout-key-1",
    )

    command = handler.handle.call_args.args[0]
    assert command.request.selection_id == "candidate-selection:one"
    assert command.request.expected_candidate_evidence_content_hash == "b" * 64
    assert command.request.idempotency.operation_id == (
        "design_research_holdout_evaluations"
    )
    assert response.data.claim_id == "holdout-claim-1"
    assert response.data.state == "claimed"
