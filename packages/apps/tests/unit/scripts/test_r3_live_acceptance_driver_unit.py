"""Unit contracts for the jobs-aware R3 live acceptance wrapper."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

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

    @contextmanager
    def tick_bundle():
        entered.append(True)
        try:
            yield SimpleNamespace(coordinator=coordinator, worker=worker)
        finally:
            exited.append(True)

    def scheduler_flow(*, runtime: object, occurred_at: datetime):
        runtimes.append(runtime)
        return {"occurred_at": occurred_at.isoformat()}

    expected = object()

    def live_lane(**kwargs: object) -> object:
        scheduler_tick = cast("object", kwargs["scheduler_tick"])
        assert callable(scheduler_tick)
        first = scheduler_tick(occurred_at=datetime(2026, 8, 2, tzinfo=UTC))
        second = scheduler_tick(occurred_at=datetime(2026, 8, 3, tzinfo=UTC))
        assert first != second
        return expected

    monkeypatch.setattr(driver, "create_experiment_tick_bundle", tick_bundle)
    monkeypatch.setattr(driver, "experiment_scheduler_tick_flow", scheduler_flow)
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
