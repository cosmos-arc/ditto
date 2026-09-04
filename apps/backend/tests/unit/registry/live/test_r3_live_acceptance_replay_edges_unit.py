"""Replay and fail-closed completion edges for the R3 live acceptance driver."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.experiments.planning_process import (
    ExperimentPreflightStatus,
)
from ditto_apps.registry.live import r3_live_acceptance_driver as driver


@contextmanager
def _research_bundle(bundle: SimpleNamespace) -> Iterator[SimpleNamespace]:
    yield bundle


class _SequenceHandler:
    def __init__(self, responses: tuple[object | BaseException, ...]) -> None:
        self._responses = iter(responses)
        self.commands: list[object] = []

    def handle(self, command: object) -> object:
        self.commands.append(command)
        response = next(self._responses)
        if isinstance(response, BaseException):
            raise response
        return response


def _selection_receipt() -> SimpleNamespace:
    return SimpleNamespace(
        candidate_evidence_content_hash="b" * 64,
        experiment_revision=8,
        selection_id="selection-live",
        selection_evidence_content_hash="c" * 64,
    )


def _holdout_receipt() -> SimpleNamespace:
    return SimpleNamespace(claim_id="claim-live")


def _candidate_selection_bundle(
    *,
    selection_responses: tuple[object | BaseException, ...],
    holdout_responses: tuple[object | BaseException, ...],
) -> SimpleNamespace:
    detail = SimpleNamespace(
        stage="candidate_selection",
        revision=7,
        candidates=(
            SimpleNamespace(is_baseline=True, candidate_id="baseline"),
            SimpleNamespace(is_baseline=False, candidate_id="candidate-live"),
        ),
    )
    return SimpleNamespace(
        experiment_query=SimpleNamespace(get=lambda _experiment_id: detail),
        candidate_evidence_reader=SimpleNamespace(
            load_current_bundle=lambda _experiment_id, _candidate_id: (
                object(),
                SimpleNamespace(
                    manifest={"comparison_payload_hash": "a" * 64},
                ),
            ),
        ),
        candidate_selection_handler=_SequenceHandler(selection_responses),
        holdout_claim_handler=_SequenceHandler(holdout_responses),
    )


def test_launch_accepts_an_idempotent_ready_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = SimpleNamespace(experiment_id="experiment-live")
    receipt = object()
    launch_handler = _SequenceHandler((receipt, receipt))
    bundle = SimpleNamespace(
        planning_process=SimpleNamespace(
            preflight=lambda _request: SimpleNamespace(
                status=ExperimentPreflightStatus.READY,
                plan_hash="a" * 64,
            ),
        ),
        launch_handler=launch_handler,
    )
    artifact = cast(
        "driver.LivePlanningArtifact",
        SimpleNamespace(
            planning_document={"experiment_id": "experiment-live"},
            plan_hash="a" * 64,
            lane="stock",
            purpose="unit",
        ),
    )
    monkeypatch.setattr(
        driver,
        "build_experiment_planning_request",
        lambda _document: request,
    )
    monkeypatch.setattr(
        driver,
        "create_research_bundle",
        lambda: _research_bundle(bundle),
    )

    driver._launch(artifact)

    assert len(launch_handler.commands) == 2


def test_detail_returns_a_nonterminal_experiment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = SimpleNamespace(status="running", stage="candidate_selection")
    bundle = SimpleNamespace(
        experiment_query=SimpleNamespace(get=lambda _experiment_id: detail),
    )
    monkeypatch.setattr(
        driver,
        "create_research_bundle",
        lambda: _research_bundle(bundle),
    )

    assert driver._detail("experiment-live") is detail


def test_tick_until_fails_closed_after_the_real_maximum_tick_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = SimpleNamespace(stage="worker", status="running")
    ticks: list[datetime] = []
    monkeypatch.setattr(driver, "_detail", lambda _experiment_id: detail)

    def scheduler_tick(*, occurred_at: datetime) -> dict[str, object]:
        ticks.append(occurred_at)
        return {"dispatch_count": 0}

    with pytest.raises(ValueError, match="did not reach completed"):
        driver._tick_until(
            "experiment-live",
            target="completed",
            scheduler_tick=scheduler_tick,
        )

    assert len(ticks) == 6000


def test_candidate_selection_and_holdout_replays_complete_once() -> None:
    selection = _selection_receipt()
    holdout = _holdout_receipt()
    duplicate = AppCommandError(
        "holdout already claimed",
        details={"code": "HOLDOUT_ALREADY_CLAIMED"},
    )
    bundle = _candidate_selection_bundle(
        selection_responses=(selection, selection),
        holdout_responses=(holdout, holdout, duplicate),
    )

    result = driver.select_and_claim_with_bundle(
        cast("driver.ResearchBundle", bundle),
        "experiment-live",
    )

    assert result == ("candidate-live", "claim-live", "c" * 64, True)
    assert len(bundle.candidate_selection_handler.commands) == 2
    assert len(bundle.holdout_claim_handler.commands) == 3


@pytest.mark.parametrize(
    ("selection_responses", "holdout_responses", "message"),
    [
        pytest.param(
            (object(), object()),
            (),
            "candidate selection idempotency replay drifted",
            id="selection-replay",
        ),
        pytest.param(
            (_selection_receipt(),) * 2,
            (object(), object()),
            "holdout claim idempotency replay drifted",
            id="holdout-replay",
        ),
        pytest.param(
            (_selection_receipt(),) * 2,
            (_holdout_receipt(),) * 3,
            "second live holdout claim was not blocked",
            id="duplicate-not-blocked",
        ),
    ],
)
def test_candidate_selection_rejects_replay_and_duplicate_drift(
    selection_responses: tuple[object | BaseException, ...],
    holdout_responses: tuple[object | BaseException, ...],
    message: str,
) -> None:
    bundle = _candidate_selection_bundle(
        selection_responses=selection_responses,
        holdout_responses=holdout_responses,
    )

    with pytest.raises(ValueError, match=message):
        driver.select_and_claim_with_bundle(
            cast("driver.ResearchBundle", bundle),
            "experiment-live",
        )
