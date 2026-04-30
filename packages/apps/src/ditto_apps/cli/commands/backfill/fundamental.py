"""Fundamental 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import create_backfill_command

app = typer.Typer(help="基本面数据回补")

# 财务报表
_balance_impl = create_backfill_command("balance_sheet", "回补资产负债表")
_income_impl = create_backfill_command("income_statement", "回补利润表")
_cash_flow_impl = create_backfill_command("cash_flow", "回补现金流量表")
_dividend_impl = create_backfill_command("dividend", "回补分红送配")

# 公司行为
_corporate_actions_impl = create_backfill_command("corporate_actions", "回补公司行为")


@app.command("balance")
def balance(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补资产负债表."""
    return _balance_impl(ctx, start, end, parallel)


@app.command("income")
def income(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补利润表."""
    return _income_impl(ctx, start, end, parallel)


@app.command("cash-flow")
def cash_flow(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补现金流量表."""
    return _cash_flow_impl(ctx, start, end, parallel)


@app.command("dividend")
def dividend(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补分红送配."""
    return _dividend_impl(ctx, start, end, parallel)


@app.command("corporate-actions")
def corporate_actions(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补公司行为."""
    return _corporate_actions_impl(ctx, start, end, parallel)
