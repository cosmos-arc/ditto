"""Macro 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import create_backfill_command

app = typer.Typer(help="宏观数据回补")

_indicators_impl = create_backfill_command("macro_indicators", "回补宏观指标")


@app.command("indicators")
def indicators(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补宏观指标."""
    return _indicators_impl(ctx, start, end, parallel)
