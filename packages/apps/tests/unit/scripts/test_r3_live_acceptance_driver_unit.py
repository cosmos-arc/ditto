"""Unit contracts for the jobs-aware R3 live acceptance wrapper."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from ditto_apps.registry.live import r3_live_acceptance_driver as registry_driver
from ditto_apps.scripts import r3_live_acceptance_driver as driver


def test_live_lane_reuses_one_scheduler_runtime_for_every_tick(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """One lane must retain its lease authority across every scheduler tick."""
    coordinator = object()
    worker = object()
    entered: list[bool] = []
    exited: list[bool] = []
    runtimes: list[object] = []
    research = cast("object", SimpleNamespace())
    selections: list[tuple[object, str]] = []

    @contextmanager
    def tick_bundle():
        entered.append(True)
        try:
            yield SimpleNamespace(
                coordinator=coordinator,
                worker=worker,
                research=research,
            )
        finally:
            exited.append(True)

    def scheduler_flow(*, runtime: object, occurred_at: datetime):
        runtimes.append(runtime)
        return {"occurred_at": occurred_at.isoformat()}

    expected = object()

    def live_lane(**kwargs: object) -> object:
        scheduler_tick = cast("object", kwargs["scheduler_tick"])
        select_and_claim = cast("object", kwargs["select_and_claim"])
        assert callable(scheduler_tick)
        assert callable(select_and_claim)
        first = scheduler_tick(occurred_at=datetime(2026, 8, 2, tzinfo=UTC))
        second = scheduler_tick(occurred_at=datetime(2026, 8, 3, tzinfo=UTC))
        assert select_and_claim("experiment-live") == (
            "candidate",
            "claim",
            "evidence",
            True,
        )
        assert first != second
        return expected

    def select_with_bundle(bundle: object, experiment_id: str):
        selections.append((bundle, experiment_id))
        return "candidate", "claim", "evidence", True

    monkeypatch.setattr(driver, "create_live_research_acceptance_bundle", tick_bundle)
    monkeypatch.setattr(driver, "experiment_scheduler_tick_flow", scheduler_flow)
    monkeypatch.setattr(driver, "select_and_claim_with_bundle", select_with_bundle)
    monkeypatch.setattr(driver, "_run_live_golden_lane", live_lane)

    result = driver.run_live_golden_lane(
        lane="stock",
        data_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        purpose="unit",
    )

    assert result is expected
    assert entered == [True]
    assert exited == [True]
    assert len(runtimes) == 2
    assert runtimes[0] is runtimes[1]
    runtime = cast("object", runtimes[0])
    assert runtime.coordinator is coordinator  # type: ignore[attr-defined]
    assert runtime.worker is worker  # type: ignore[attr-defined]
    assert selections == [(research, "experiment-live")]


def test_candidate_selection_tick_replays_missing_evidence(
    monkeypatch,
) -> None:
    """A persisted stage must replay its idempotent evidence publication."""
    detail = SimpleNamespace(stage="candidate_selection", status="running")
    ticks: list[datetime] = []
    monkeypatch.setattr(registry_driver, "_detail", lambda _experiment_id: detail)

    result = registry_driver._tick_until(
        "experiment-live",
        target="candidate_selection",
        scheduler_tick=lambda *, occurred_at: ticks.append(occurred_at),
    )

    assert result is detail
    assert len(ticks) == 1


def test_select_and_claim_recovers_persisted_holdout_claim() -> None:
    """An interrupted acceptance run resumes without repeating mutations."""
    claim = SimpleNamespace(
        candidate_id="candidate-live",
        claim_id="holdout-live",
        selection_evidence_hash="e" * 64,
    )
    scheduler_store = SimpleNamespace(
        load_snapshot=lambda _experiment_id: SimpleNamespace(holdout_claim=claim)
    )
    bundle = cast(
        "object",
        SimpleNamespace(
            experiment_query=SimpleNamespace(
                get=lambda _experiment_id: SimpleNamespace(stage="holdout")
            ),
            candidate_evidence_reader=SimpleNamespace(
                scheduler_store=scheduler_store,
            ),
        ),
    )

    result = registry_driver.select_and_claim_with_bundle(
        bundle,  # type: ignore[arg-type]
        "experiment-live",
    )

    assert result == (
        "candidate-live",
        "holdout-live",
        "e" * 64,
        True,
    )
