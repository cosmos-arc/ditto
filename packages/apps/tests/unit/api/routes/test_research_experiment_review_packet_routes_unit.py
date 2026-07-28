"""Unit tests for GET /research/experiments/{id}/review-packet route."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.experiments import (
    ExperimentQueryFacade,
    ExperimentReviewPacketReadModel,
    ReviewGateOutcome,
    ReviewSelectionTraceRef,
)
from ditto_apps.api.errors import NotFoundError
from ditto_apps.api.routes.research_experiment_routes import (
    get_research_experiment_review_packet,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    ExperimentReviewPacketResponse,
    ReviewGateOutcomeResponse,
    ReviewSelectionTraceRefResponse,
)

pytestmark = pytest.mark.asyncio

_Route = Callable[..., Awaitable[APIResponse[ExperimentReviewPacketResponse]]]


@pytest.fixture(autouse=True)
def _inline_review_packet_route_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.research_experiment_routes.run_blocking", run_inline
    )


def _read_model() -> ExperimentReviewPacketReadModel:
    return ExperimentReviewPacketReadModel(
        experiment_id="exp-1",
        candidate_id="candidate-1",
        bundle_hash="a" * 64,
        hard_review_blocked=False,
        gate_outcomes=(
            ReviewGateOutcome(
                rule_id="certified_snapshot", layer="hard", outcome="pass"
            ),
        ),
        schema_version=2,
        fold_ids=("fold-1",),
        attempt_ids=("attempt-1",),
        spec_hash="a" * 64,
        resolved_spec_hash="b" * 64,
        parameter_hash="c" * 64,
        snapshot_hash="d" * 64,
        registry_hash="e" * 64,
        objective_payload_hash="f" * 64,
        comparison_payload_hash="9" * 64,
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id="claim-1",
        candidate_rationale="Captures durable net return after costs.",
        selection_trace_artifact_refs=(
            ReviewSelectionTraceRef(
                artifact_kind="fold_selection_trace_candidate_universe_v1",
                artifact_id="trace-0",
                content_hash="1" * 64,
            ),
        ),
    )


def _unwrap(route: Callable[..., object]) -> Callable[..., object]:
    return cast(Callable[..., object], getattr(route, "__dishka_orig_func__", route))


async def test_get_review_packet_returns_response() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get_review_packet.return_value = _read_model()
    route = cast(_Route, _unwrap(get_research_experiment_review_packet))

    result = await route(experiment_id="exp-1", facade=facade)

    assert result.data == ExperimentReviewPacketResponse(
        experiment_id="exp-1",
        candidate_id="candidate-1",
        bundle_hash="a" * 64,
        hard_review_blocked=False,
        gate_outcomes=[
            ReviewGateOutcomeResponse(
                rule_id="certified_snapshot", layer="hard", outcome="pass"
            )
        ],
        schema_version=2,
        fold_ids=["fold-1"],
        attempt_ids=["attempt-1"],
        spec_hash="a" * 64,
        resolved_spec_hash="b" * 64,
        parameter_hash="c" * 64,
        snapshot_hash="d" * 64,
        registry_hash="e" * 64,
        objective_payload_hash="f" * 64,
        comparison_payload_hash="9" * 64,
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id="claim-1",
        candidate_rationale="Captures durable net return after costs.",
        selection_trace_artifact_refs=[
            ReviewSelectionTraceRefResponse(
                artifact_kind="fold_selection_trace_candidate_universe_v1",
                artifact_id="trace-0",
                content_hash="1" * 64,
            )
        ],
    )
    facade.get_review_packet.assert_called_once_with("exp-1")


async def test_get_review_packet_raises_not_found_when_absent() -> None:
    facade = MagicMock(spec=ExperimentQueryFacade)
    facade.get_review_packet.return_value = None
    route = cast(_Route, _unwrap(get_research_experiment_review_packet))

    with pytest.raises(NotFoundError):
        await route(experiment_id="exp-1", facade=facade)
