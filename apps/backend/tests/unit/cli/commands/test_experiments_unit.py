"""Unit tests for the experiment scheduler tick CLI."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_apps.cli.commands.experiments import _parse_utc_datetime, app, tick
from pytest_mock import MockerFixture
from typer.testing import CliRunner


def test_parse_utc_datetime_defaults_to_now_when_empty() -> None:
    """Empty --at must resolve to the current UTC time (timezone-aware)."""
    before = datetime.now(UTC)
    parsed = _parse_utc_datetime("")
    after = datetime.now(UTC)

    assert parsed.tzinfo is UTC or parsed.utcoffset() == before.utcoffset()
    assert before <= parsed <= after


def test_parse_utc_datetime_accepts_iso_8601_utc() -> None:
    parsed = _parse_utc_datetime("2026-07-26T10:00:00+00:00")

    assert parsed == datetime(2026, 7, 26, 10, 0, 0, tzinfo=UTC)


def test_parse_utc_datetime_normalizes_non_utc_offset() -> None:
    parsed = _parse_utc_datetime("2026-07-26T12:00:00+02:00")

    assert parsed == datetime(2026, 7, 26, 10, 0, 0, tzinfo=UTC)


def test_parse_utc_datetime_rejects_naive_value() -> None:
    import typer

    with pytest.raises(typer.BadParameter, match="UTC offset"):
        _parse_utc_datetime("2026-07-26T10:00:00")


def test_tick_cli_invokes_flow_with_parsed_utc_timestamp(
    mocker: MockerFixture,
) -> None:
    """The CLI must delegate to run_experiment_scheduler_tick and emit JSON."""
    flow = mocker.patch(
        "ditto_apps.cli.commands.experiments.run_experiment_scheduler_tick",
        return_value={"state": "idle", "dispatch_count": 0},
    )

    result = CliRunner().invoke(app, ["tick", "--at", "2026-07-26T10:00:00+00:00"])

    assert result.exit_code == 0, result.stdout
    flow.assert_called_once_with(
        occurred_at=datetime(2026, 7, 26, 10, 0, 0, tzinfo=UTC),
    )
    assert '"state": "idle"' in result.stdout
    assert '"dispatch_count": 0' in result.stdout


def test_tick_cli_defaults_occurred_at_to_now_when_at_omitted(
    mocker: MockerFixture,
) -> None:
    """Omitting --at must use the current UTC time."""
    captured: dict[str, datetime] = {}

    def capture(*, occurred_at: datetime) -> dict[str, object]:
        captured["occurred_at"] = occurred_at
        return {"state": "idle"}

    mocker.patch(
        "ditto_apps.cli.commands.experiments.run_experiment_scheduler_tick",
        side_effect=capture,
    )
    before = datetime.now(UTC)

    result = CliRunner().invoke(app, ["tick"])

    assert result.exit_code == 0, result.stdout
    assert captured["occurred_at"] >= before
    assert captured["occurred_at"].utcoffset() == datetime.now(UTC).utcoffset()


def test_tick_cli_rejects_naive_iso_value(mocker: MockerFixture) -> None:
    mocker.patch(
        "ditto_apps.cli.commands.experiments.run_experiment_scheduler_tick",
        return_value={"state": "idle"},
    )

    result = CliRunner().invoke(app, ["tick", "--at", "2026-07-26T10:00:00"])

    assert result.exit_code != 0
    assert "UTC offset" in (result.stdout + (result.stderr or ""))


def test_tick_function_emits_json_dict(mocker: MockerFixture) -> None:
    """The tick function must route through output_json_dict."""
    mocker.patch(
        "ditto_apps.cli.commands.experiments.run_experiment_scheduler_tick",
        return_value={"state": "idle"},
    )
    output = mocker.patch(
        "ditto_apps.cli.commands.experiments.output_json_dict",
    )

    tick(occurred_at="2026-07-26T10:00:00+00:00")

    output.assert_called_once_with({"state": "idle"})
