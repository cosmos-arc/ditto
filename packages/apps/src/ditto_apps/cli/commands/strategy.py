"""CLI strategy 命令组."""

from __future__ import annotations

import typer
from ditto_application.config import DEFAULT_INITIAL_CASH
from ditto_application.processes.execution.backtest_process import (
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.strategy_run_process import (
    StrategyRunMode,
    StrategyRunServiceConfig,
)
from ditto_application.processes.strategy.seed_bootstrap import (
    SeedBootstrapResult,
    SeedBootstrapStatus,
)

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.registry.contexts import create_strategy_bundle

app = typer.Typer(help="运行策略与回测")


def _seed_bootstrap_payload(
    results: tuple[SeedBootstrapResult, ...],
) -> dict[str, object]:
    return {
        "summary": {
            "created": sum(result.created for result in results),
            "published": sum(result.published for result in results),
            "unchanged": sum(
                result.status == SeedBootstrapStatus.UNCHANGED for result in results
            ),
            "conflict": sum(
                result.status == SeedBootstrapStatus.CONFLICT for result in results
            ),
        },
        "results": [
            {
                "strategy_id": result.strategy_id,
                "status": result.status.value,
                "version": result.version,
                "created": result.created,
                "published": result.published,
                "differences": list(result.differences),
            }
            for result in results
        ],
    }


@app.command("bootstrap-seeds")
def bootstrap_seeds() -> None:
    """幂等创建并发布内置 seed 策略。"""
    with create_strategy_bundle() as bundle:
        if bundle.seed_bootstrap is None:
            raise typer.BadParameter("SeedStrategyBootstrap 未配置")
        results = bundle.seed_bootstrap.run()
    output_json_dict(_seed_bootstrap_payload(results))
    if any(result.status == SeedBootstrapStatus.CONFLICT for result in results):
        raise typer.Exit(code=1)


def _build_run_config(
    strategy_id: str,
    mode: StrategyRunMode,
) -> StrategyRunServiceConfig:
    return StrategyRunServiceConfig(strategy_id=strategy_id, mode=mode)


def _print_strategy_result(
    run_id: str,
    strategy_id: str,
    trade_date: str,
    mode: str,
) -> None:
    typer.echo(
        f"run_id={run_id} strategy_id={strategy_id} trade_date={trade_date} mode={mode}"
    )


def _print_backtest_result(
    run_id: str,
    period: tuple[str, str],
    final_nav: float,
) -> None:
    typer.echo(f"run_id={run_id} period={period[0]}:{period[1]} final_nav={final_nav}")


@app.command()
def research(
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    trade_date: str = typer.Argument(..., help="交易日期 YYYY-MM-DD"),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
    allow_experimental_data: bool = typer.Option(
        False,
        "--allow-experimental-data",
        help="显式允许 experimental 数据集进入研究态运行",
    ),
) -> None:
    """执行 research 模式策略运行。"""
    config = _build_run_config(strategy_id, StrategyRunMode.RESEARCH)
    with create_strategy_bundle() as bundle:
        result = bundle.strategy_facade.run_strategy_for_date_from_catalog(
            config=config,
            trade_date=trade_date,
            version=version,
            source=source,
            allow_experimental_data=allow_experimental_data,
        )
    _print_strategy_result(result.run_id, strategy_id, trade_date, "research")


@app.command()
def recommend(
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    trade_date: str = typer.Argument(..., help="交易日期 YYYY-MM-DD"),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
    allow_experimental_data: bool = typer.Option(
        False,
        "--allow-experimental-data",
        help="显式允许 experimental 数据集进入推荐态运行",
    ),
) -> None:
    """执行 recommendation 模式策略运行。"""
    config = _build_run_config(strategy_id, StrategyRunMode.RECOMMENDATION)
    with create_strategy_bundle() as bundle:
        result = bundle.strategy_facade.run_strategy_for_date_from_catalog(
            config=config,
            trade_date=trade_date,
            version=version,
            source=source,
            allow_experimental_data=allow_experimental_data,
        )
    _print_strategy_result(result.run_id, strategy_id, trade_date, "recommendation")


@app.command("publish-signals")
def publish_signals(  # noqa: PLR0913 — CLI 命令回调，参数由 Typer 注入
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    trade_date: str = typer.Argument(..., help="交易日期 YYYY-MM-DD"),
    account_id: str | None = typer.Option(
        None,
        "--account-id",
        help="人工账户 ID, 停用命令仅用于生成迁移指引",
    ),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
    dataset_snapshot: list[str] | None = typer.Option(
        None,
        "--dataset-snapshot",
        help="数据快照校验, 格式 DATASET=CHECKSUM, 可重复",
    ),
    factor: list[str] | None = typer.Option(
        None,
        "--factor",
        help="信号解释中的因子 ID, 可重复",
    ),
    threshold: float = typer.Option(0.01, "--threshold", help="最小调仓权重"),
    allow_experimental_data: bool = typer.Option(
        False,
        "--allow-experimental-data",
        help="显式允许 experimental 数据集进入推荐态运行",
    ),
) -> None:
    """已停用；人工交易信号只能由 EOD 数据质量门禁发布。"""
    del version, source, dataset_snapshot, factor, threshold, allow_experimental_data
    migrated_account_id = account_id or "ACCOUNT_ID"
    command = (
        f"ditto ops run-eod --signal-date {trade_date} "
        f"--strategy-id {strategy_id} --account-id {migrated_account_id}"
    )
    message = (
        "已停用: strategy publish-signals 会绕过 EOD 数据新鲜度与 DQ 门禁; "
        + "未写入信号包。请改用: "
        + command
    )
    typer.echo(
        message,
        err=True,
    )
    raise typer.Exit(code=2)


@app.command()
def backtest(
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    start_date: str = typer.Argument(..., help="开始日期 YYYY-MM-DD"),
    end_date: str = typer.Argument(..., help="结束日期 YYYY-MM-DD"),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
    initial_cash: float = typer.Option(
        DEFAULT_INITIAL_CASH,
        "--initial-cash",
        help="初始资金",
    ),
    allow_experimental_data: bool = typer.Option(
        False,
        "--allow-experimental-data",
        help="显式允许 experimental 数据集进入研究态回测",
    ),
) -> None:
    """执行完整回测。"""
    config = BacktestServiceConfig(
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
    )
    with create_strategy_bundle() as bundle:
        options = (
            BacktestServiceOptions(allow_experimental_data=True)
            if allow_experimental_data
            else None
        )
        result = bundle.strategy_facade.run_backtest_from_catalog(
            config=config,
            version=version,
            source=source,
            options=options,
        )
    _print_backtest_result(result.run_id, result.period, result.final_nav)
