"""Macro 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import (
    _raise_if_backfill_failed,
    create_backfill_command,
)
from ditto_apps.cli.context import create_executor
from ditto_apps.cli.utils.output import print_backfill_summary
from ditto_apps.cli.utils.validation import validate_date_format

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
    source: str = typer.Option(
        "tushare",
        "--source",
        help="数据源(tushare=中国7类;fred=51 FRED 系列,#658 批次4)",
    ),
) -> None:
    """回补宏观指标(--source fred 驱动 51 FRED 系列落库)."""
    if source == "tushare":
        return _indicators_impl(ctx, start, end, parallel)
    if source != "fred":
        raise typer.BadParameter(f"unsupported --source {source!r}: tushare | fred")
    validate_date_format(start)
    validate_date_format(end)
    # 车道由执行器构造决定(fetcher 在 bundle 装配时选择):
    # source 参数须传 create_executor,backfill_range 的 source 仅是
    # 规划/账本标签(#658 批次4 勘误)。
    with create_executor(source_name="fred") as executor:
        result = executor.backfill_range(
            "macro_indicators", start, end, parallel, source="fred"
        )
        print_backfill_summary(result)
        _raise_if_backfill_failed(result)


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
