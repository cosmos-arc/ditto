"""ops run-eod CLI。"""

from ditto_apps.cli.commands.ops import app
from typer.testing import CliRunner


def test_run_eod_outputs_structured_result(mocker) -> None:
    mocker.patch(
        "ditto_apps.cli.commands.ops.eod_flow",
        return_value={"strategies": [{"strategy_id": "s1", "status": "completed"}]},
    )

    result = CliRunner().invoke(
        app,
        ["run-eod", "--signal-date", "2026-07-16", "--strategy-id", "s1"],
    )

    assert result.exit_code == 0
    assert '"strategy_id": "s1"' in result.stdout


def test_run_eod_returns_nonzero_for_blocked_strategy(mocker) -> None:
    mocker.patch(
        "ditto_apps.cli.commands.ops.eod_flow",
        return_value={"strategies": [{"strategy_id": "s1", "status": "blocked"}]},
    )

    result = CliRunner().invoke(
        app,
        ["run-eod", "--signal-date", "2026-07-16"],
    )

    assert result.exit_code == 1
