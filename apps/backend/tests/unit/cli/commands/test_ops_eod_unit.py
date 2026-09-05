"""ops run-eod CLI。"""

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent

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


def test_run_eod_never_enters_prefect_engine_in_real_import_process() -> None:
    """真实 Prefect import 下，CLI 也只调用未装饰 pipeline runner。"""
    script = dedent(
        """
        from unittest.mock import patch

        from prefect.flows import Flow
        from prefect.tasks import Task
        from typer.testing import CliRunner
        from ditto_application.processes.execution.eod_coordinator import (
            EodStrategyRequest,
        )

        from ditto_apps.cli.commands.ops import app
        import ditto_apps.jobs.flows.eod as eod_module

        strategy_outcomes = [
            {"strategy_id": "s1", "status": "completed"},
        ]
        with (
            patch.object(
                Flow,
                "__call__",
                side_effect=AssertionError("Prefect engine invoked"),
            ) as prefect_engine,
            patch.object(
                Task,
                "__call__",
                side_effect=AssertionError("Prefect task engine invoked"),
            ) as prefect_task_engine,
            patch.object(eod_module, "run_check_trading_day", return_value=True),
            patch.object(
                eod_module,
                "_resolve_published_eod_request",
                return_value=EodStrategyRequest(
                    strategy_id="s1",
                    strategy_version="1",
                    required_datasets=("etf_daily",),
                ),
            ),
            patch.object(
                eod_module,
                "run_daily_ingestion",
                return_value={
                    "trade_date": "2026-07-16",
                    "skipped": False,
                    "t0_results": {},
                    "t1_results": {},
                    "dqc_results": {},
                    "summary": {"failed_count": 0},
                },
            ),
            patch.object(
                eod_module,
                "run_daily_materialization",
                return_value={
                    "trade_date": "2026-07-16",
                    "results": [],
                    "summary": {"materialized_count": 0},
                },
            ),
            patch.object(
                eod_module,
                "_run_strategies",
                return_value=(strategy_outcomes, True),
            ),
        ):
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
            assert result.exit_code == 0, result.exception
            prefect_engine.assert_not_called()
            prefect_task_engine.assert_not_called()
        """
    )

    # 固定为当前解释器、静态参数且 shell=False；子进程用于隔离真实 Prefect import。
    # 全量 coverage 会同时启动八个解释器，超时只约束测试基础设施，不参与
    # “不得进入 Prefect engine”的行为断言，因此为冷导入保留调度余量。
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Starting temporary server" not in result.stderr
