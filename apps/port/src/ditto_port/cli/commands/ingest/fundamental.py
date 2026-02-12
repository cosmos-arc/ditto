"""Fundamental 域摄取命令."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="基本面数据摄取")

# 财务报表
_balance_impl = create_daily_command("balance_sheet", "摄取资产负债表")
_income_impl = create_daily_command("income_statement", "摄取利润表")
_cash_flow_impl = create_daily_command("cash_flow", "摄取现金流量表")
_dividend_impl = create_daily_command("dividend", "摄取分红送配")

# 公司行为
_corporate_actions_impl = create_daily_command("corporate_actions", "摄取公司行为")


@app.command("balance")
def balance(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取资产负债表."""
    return _balance_impl(ctx, date, force)


@app.command("income")
def income(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取利润表."""
    return _income_impl(ctx, date, force)


@app.command("cash-flow")
def cash_flow(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取现金流量表."""
    return _cash_flow_impl(ctx, date, force)


@app.command("dividend")
def dividend(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取分红送配."""
    return _dividend_impl(ctx, date, force)


@app.command("corporate-actions")
def corporate_actions(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取公司行为."""
    return _corporate_actions_impl(ctx, date, force)
