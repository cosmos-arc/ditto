"""Capital 域摄取命令."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="资本面数据摄取")

# 估值指标
_valuation_impl = create_daily_command("valuation_metrics", "摄取估值指标")

# 融资融券
_margin_impl = create_daily_command("margin_trading", "摄取融资融券")

# 股权质押
_pledge_impl = create_daily_command("pledge_ratio", "摄取股权质押")

# 期货持仓
_futures_position_impl = create_daily_command("futures_position", "摄取期货持仓")


@app.command("valuation")
def valuation(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取估值指标."""
    return _valuation_impl(ctx, date, force)


@app.command("margin")
def margin(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取融资融券."""
    return _margin_impl(ctx, date, force)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股权质押."""
    return _pledge_impl(ctx, date, force)


@app.command("futures-position")
def futures_position(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取期货持仓."""
    return _futures_position_impl(ctx, date, force)
