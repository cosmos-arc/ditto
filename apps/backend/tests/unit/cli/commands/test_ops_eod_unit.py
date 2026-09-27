"""ops run-eod CLI。"""

from __future__ import annotations

from ditto_apps.cli.commands.ops import app
from typer.testing import CliRunner


def test_run_eod_outputs_structured_result(mocker) -> None:
    pipeline = mocker.patch(
        "ditto_apps.cli.commands.ops.run_eod_pipeline",
        create=True,
        return_value={"strategies": [{"strategy_id": "s1", "status": "completed"}]},
    )
    prefect_flow = mocker.patch(
        "ditto_apps.cli.commands.ops.eod_flow",
        create=True,
        side_effect=AssertionError("CLI must not invoke the Prefect flow"),
    )

    result = CliRunner().invoke(
        app,
        [
            "run-eod",
            "--signal-date",
            "2026-07-16",
            "--strategy-id",
            "s1",
            "--account-id",
            "paper",
        ],
    )

    assert result.exit_code == 0
    assert '"strategy_id": "s1"' in result.stdout
    pipeline.assert_called_once_with(
        trade_date="2026-07-16",
        strategy_id="s1",
        account_id="paper",
        allow_experimental_data=False,
    )
    prefect_flow.assert_not_called()


def test_run_eod_requires_explicit_flag_for_experimental_dataset_access(mocker) -> None:
    pipeline = mocker.patch(
        "ditto_apps.cli.commands.ops.run_eod_pipeline",
        return_value={"strategies": [{"strategy_id": "s1", "status": "completed"}]},
    )

    result = CliRunner().invoke(
        app,
        [
            "run-eod",
            "--signal-date",
            "2026-07-16",
            "--strategy-id",
            "s1",
            "--account-id",
            "paper",
            "--allow-experimental-data",
        ],
    )

    assert result.exit_code == 0
    pipeline.assert_called_once_with(
        trade_date="2026-07-16",
        strategy_id="s1",
        account_id="paper",
        allow_experimental_data=True,
    )


def test_run_eod_returns_nonzero_for_blocked_strategy(mocker) -> None:
    mocker.patch(
        "ditto_apps.cli.commands.ops.run_eod_pipeline",
        create=True,
        return_value={"strategies": [{"strategy_id": "s1", "status": "blocked"}]},
    )

    result = CliRunner().invoke(
        app,
        [
            "run-eod",
            "--signal-date",
            "2026-07-16",
            "--strategy-id",
            "s1",
            "--account-id",
            "paper",
        ],
    )

    assert result.exit_code == 1


def test_run_eod_requires_explicit_strategy_and_account() -> None:
    result = CliRunner().invoke(
        app,
        ["run-eod", "--signal-date", "2026-07-16"],
    )

    assert result.exit_code == 2
    assert "--strategy-id" in result.output
