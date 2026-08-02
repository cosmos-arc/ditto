"""Jobs-aware entrypoints for the registry-composed Task 18 live driver."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from ditto_apps.jobs.flows.experiments import (
    ExperimentTickRuntime,
    experiment_scheduler_tick_flow,
)
from ditto_apps.registry.contexts.research_execution import (
    create_experiment_tick_bundle,
)
from ditto_apps.registry.live.r3_live_acceptance_driver import (
    LiveBackupRestoreResult,
    LiveGoldenLaneResult,
    LiveGovernanceLaneResult,
    LiveGovernanceLifecycleResult,
    run_live_backup_restore,
    run_live_governance_lifecycle,
)
from ditto_apps.registry.live.r3_live_acceptance_driver import (
    run_live_golden_lane as _run_live_golden_lane,
)

__all__ = [
    "LiveBackupRestoreResult",
    "LiveGoldenLaneResult",
    "LiveGovernanceLaneResult",
    "LiveGovernanceLifecycleResult",
    "run_live_backup_restore",
    "run_live_golden_lane",
    "run_live_governance_lifecycle",
]


def run_live_golden_lane(
    *,
    lane: Literal["stock", "etf"],
    data_root: Path,
    evidence_root: Path,
    purpose: str,
) -> LiveGoldenLaneResult:
    """Run one live lane with the production jobs scheduler injected explicitly."""
    with create_experiment_tick_bundle() as bundle:
        runtime = ExperimentTickRuntime(
            coordinator=bundle.coordinator,
            worker=bundle.worker,
        )

        def scheduler_tick(*, occurred_at: datetime) -> dict[str, object]:
            return experiment_scheduler_tick_flow(
                runtime=runtime,
                occurred_at=occurred_at,
            )

        return _run_live_golden_lane(
            lane=lane,
            data_root=data_root,
            evidence_root=evidence_root,
            purpose=purpose,
            scheduler_tick=scheduler_tick,
        )
