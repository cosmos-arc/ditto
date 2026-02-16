"""Macro 域摄取命令."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="宏观数据摄取")

_indicators_impl = create_daily_command("macro_indicators", "摄取宏观指标")


@app.command("indicators")
def indicators(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取宏观指标."""
    return _indicators_impl(ctx, date, force)
