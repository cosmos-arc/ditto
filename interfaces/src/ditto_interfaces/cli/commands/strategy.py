"""CLI strategy 命令组."""

from __future__ import annotations

import typer
from ditto_app.process.strategy import (
    BacktestServiceConfig,
    StrategyRunMode,
    StrategyRunServiceConfig,
)

from ditto_interfaces.registry.contexts import create_strategy_bundle

app = typer.Typer(help="运行策略与回测")


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
) -> None:
    """执行 research 模式策略运行。"""
    config = _build_run_config(strategy_id, StrategyRunMode.RESEARCH)
    with create_strategy_bundle() as bundle:
        result = bundle.strategy_facade.run_strategy_for_date_from_catalog(
            config=config,
            trade_date=trade_date,
            version=version,
            source=source,
        )
    _print_strategy_result(result.run_id, strategy_id, trade_date, "research")


@app.command()
def recommend(
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    trade_date: str = typer.Argument(..., help="交易日期 YYYY-MM-DD"),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
) -> None:
    """执行 recommendation 模式策略运行。"""
    config = _build_run_config(strategy_id, StrategyRunMode.RECOMMENDATION)
    with create_strategy_bundle() as bundle:
        result = bundle.strategy_facade.run_strategy_for_date_from_catalog(
            config=config,
            trade_date=trade_date,
            version=version,
            source=source,
        )
    _print_strategy_result(result.run_id, strategy_id, trade_date, "recommendation")


@app.command()
def backtest(
    strategy_id: str = typer.Argument(..., help="策略 ID"),
    start_date: str = typer.Argument(..., help="开始日期 YYYY-MM-DD"),
    end_date: str = typer.Argument(..., help="结束日期 YYYY-MM-DD"),
    version: int | None = typer.Option(None, "--version", help="策略版本"),
    source: str = typer.Option("tushare", "--source", help="数据源名称"),
    initial_cash: float = typer.Option(1_000_000.0, "--initial-cash", help="初始资金"),
) -> None:
    """执行完整回测。"""
    config = BacktestServiceConfig(
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
    )
    with create_strategy_bundle() as bundle:
        result = bundle.strategy_facade.run_backtest_from_catalog(
            config=config,
            version=version,
            source=source,
        )
    _print_backtest_result(result.run_id, result.period, result.final_nav)
