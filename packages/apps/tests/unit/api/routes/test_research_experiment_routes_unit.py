"""Unit tests for research experiment routes."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.experiments import (
    ExperimentDetailReadModel,
    ExperimentQueryFacade,
)
from ditto_apps.api.errors import NotFoundError
from ditto_apps.api.routes.research_experiment_routes import (
    get_experiment,
    to_experiment_response,
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
