"""OPS-01 workstation schedule contract tests."""

from ditto_apps.jobs.flows.deploy import SCHEDULE_EOD
from ditto_apps.jobs.workstation_schedule import WORKSTATION_SCHEDULE


def test_workstation_schedule_has_one_fail_closed_daily_chain() -> None:
    """Data, Selection, Paper and closeout must form one exact daily chain."""
    assert tuple(item.stage for item in WORKSTATION_SCHEDULE) == (
        "data",
        "selection",
        "paper",
        "eod",
    )
    assert tuple(item.depends_on for item in WORKSTATION_SCHEDULE) == (
        (),
        ("data",),
        ("selection",),
        ("data", "selection", "paper"),
    )
    assert all(item.fail_closed for item in WORKSTATION_SCHEDULE)


def test_workstation_schedule_uses_the_deployed_shanghai_trigger() -> None:
    """The operations table and Prefect deployment share the same trigger."""
    data_stage = WORKSTATION_SCHEDULE[0]

    assert data_stage.trigger == "cron"
    assert data_stage.cron == SCHEDULE_EOD.cron == "45 19 * * 1-5"
    assert data_stage.timezone == SCHEDULE_EOD.timezone == "Asia/Shanghai"
    assert all(item.timezone == "Asia/Shanghai" for item in WORKSTATION_SCHEDULE)


def test_downstream_stages_are_event_driven_not_independently_scheduled() -> None:
    """No downstream phase may race ahead of its certified predecessor."""
    assert tuple(item.trigger for item in WORKSTATION_SCHEDULE) == (
        "cron",
        "after_success",
        "after_success",
        "after_success",
    )
    assert all(item.cron is None for item in WORKSTATION_SCHEDULE[1:])
