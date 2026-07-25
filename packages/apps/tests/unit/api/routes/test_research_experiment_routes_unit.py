"""Unit tests for research experiment routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.experiments import (
    PauseExperimentHandler,
    RetryExperimentFoldHandler,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.queries.experiments import (
    ExperimentDetailReadModel,
    ExperimentQueryFacade,
)
from ditto_apps.api.errors import ConflictError, NotFoundError
from ditto_apps.api.routes.research_experiment_routes import (
    get_experiment,
    pause_experiment,
    retry_fold_experiment,
    to_experiment_response,
)
from ditto_apps.models.research import (
    ExperimentControlRequest,
    ExperimentRetryFoldRequest,
)

pytestmark = pytest.mark.asyncio


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
        failure_code=None,
        queue_ordinal=None,
        revision=1,
        created_at=datetime(2026, 7, 23, 0, 0, 0),
        updated_at=datetime(2026, 7, 23, 0, 0, 0),
        seed=42,
        worker_count=2,
        failure_policy="continue",
        candidate_limit=128,
        fold_run_limit=24,
        fold_protocol_id="fold-proto",
        fold_protocol_version=1,
        fold_protocol_hash="fold-hash",
        candidates=(),
        folds=(),
    )


async def _call_get(experiment_id: str, facade: MagicMock) -> object:
    route = getattr(get_experiment, "__dishka_orig_func__", get_experiment)
    return await route(experiment_id=experiment_id, facade=facade)


def test_to_experiment_response_maps_fields() -> None:
    response = to_experiment_response(_detail())

    assert response.experiment_id == "exp-1"
    assert response.status == "completed"
    assert response.candidate_count == 0
    assert response.fold_count == 0


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


async def _call_pause(request: ExperimentControlRequest, handler: MagicMock) -> object:
    route = getattr(pause_experiment, "__dishka_orig_func__", pause_experiment)
    return await route(experiment_id="exp-1", request=request, handler=handler)


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
        handler=handler,
    )

    assert response.data.revision == 2
    command = handler.handle.call_args.args[0]
    assert command.candidate_id == "cand-1"
    assert command.fold_id == "fold-1"
    assert command.expected_revision == 3
