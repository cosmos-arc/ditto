"""复权因子命令."""

from collections.abc import Callable

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="复权因子命令")

_adj_factor_impl: Callable[[typer.Context, str, bool], None] = create_daily_command(
    "adj_factor", "摄取股票复权因子数据"
)
_fund_adj_impl: Callable[[typer.Context, str, bool], None] = create_daily_command(
    "fund_adj", "摄取基金复权因子数据"
)


@app.command("adj-factor")
def adj_factor(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票复权因子数据."""
    return _adj_factor_impl(ctx, date, force)


@app.command("fund-adj")
def fund_adj(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取基金复权因子数据."""
    return _fund_adj_impl(ctx, date, force)
