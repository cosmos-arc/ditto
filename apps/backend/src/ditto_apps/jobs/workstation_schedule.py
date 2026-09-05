"""Machine-readable schedule for the personal workstation daily close."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ditto_apps.jobs.flows.deploy import SCHEDULE_EOD

type WorkstationStage = Literal["data", "selection", "paper", "eod"]
type WorkstationTrigger = Literal["cron", "after_success"]


@dataclass(frozen=True, slots=True)
class WorkstationScheduleEntry:
    """One fail-closed stage in the single daily workstation chain."""

    stage: WorkstationStage
    owner: str
    trigger: WorkstationTrigger
    depends_on: tuple[WorkstationStage, ...]
    timezone: str = "Asia/Shanghai"
    cron: str | None = None
    fail_closed: bool = True


WORKSTATION_SCHEDULE: tuple[WorkstationScheduleEntry, ...] = (
    WorkstationScheduleEntry(
        stage="data",
        owner="ditto_apps.jobs.flows.eod",
        trigger="cron",
        depends_on=(),
        cron=SCHEDULE_EOD.cron,
        timezone=SCHEDULE_EOD.timezone or "Asia/Shanghai",
    ),
    WorkstationScheduleEntry(
        stage="selection",
        owner="ditto_apps.jobs.flows.eod",
        trigger="after_success",
        depends_on=("data",),
    ),
    WorkstationScheduleEntry(
        stage="paper",
        owner="ditto_apps.jobs.paper_eod",
        trigger="after_success",
        depends_on=("selection",),
    ),
    WorkstationScheduleEntry(
        stage="eod",
        owner="ditto_apps.jobs.eod_evidence",
        trigger="after_success",
        depends_on=("data", "selection", "paper"),
    ),
)

__all__ = ["WORKSTATION_SCHEDULE", "WorkstationScheduleEntry"]
