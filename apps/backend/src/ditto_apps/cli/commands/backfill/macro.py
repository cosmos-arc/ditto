"""Macro 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import create_backfill_command

app = typer.Typer(help="宏观数据回补")

_indicators_impl = create_backfill_command("macro_indicators", "回补宏观指标")
# #629 P5 支撑源：fx/commodity 历史回补（月块 range 请求）
_fx_impl = create_backfill_command("fx_daily", "回补汇率日线")
_commodity_impl = create_backfill_command("commodity_daily", "回补大宗商品日线")


@app.command("indicators")
def indicators(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补宏观指标."""
    return _indicators_impl(ctx, start, end, parallel)


@app.command("fx")
def fx(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补汇率日线（FXCM 六对，GMT 日 K）."""
    return _fx_impl(ctx, start, end, parallel)


@app.command("commodity")
def commodity(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补大宗商品日线（FRED 油/VIX + FXCM 金属 + 新浪外盘参考）."""
    return _commodity_impl(ctx, start, end, parallel)
