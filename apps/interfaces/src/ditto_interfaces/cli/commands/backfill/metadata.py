"""Metadata 域回补命令 (calendar + basic)."""

import typer

from ditto_interfaces.cli.commands.factory import create_backfill_command

app = typer.Typer(help="元数据回补")

# calendar
_calendar_impl = create_backfill_command("calendar", "回补交易日历")

# basic (stock/etf/index 基础信息)
_stock_basic_impl = create_backfill_command("stock_basic", "回补股票基础信息")
_etf_basic_impl = create_backfill_command("etf_basic", "回补ETF基础信息")
_index_basic_impl = create_backfill_command("index_basic", "回补指数基础信息")


@app.command("calendar")
def calendar(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补交易日历."""
    return _calendar_impl(ctx, start, end, parallel)


@app.command("basic")
def basic(
    ctx: typer.Context,
    asset: str = typer.Argument(..., help="资产类型 (stock/etf/index)"),
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补基础信息 (stock/etf/index)."""
    asset = asset.lower()
    if asset == "stock":
        return _stock_basic_impl(ctx, start, end, parallel)
    elif asset == "etf":
        return _etf_basic_impl(ctx, start, end, parallel)
    elif asset == "index":
        return _index_basic_impl(ctx, start, end, parallel)
    else:
        typer.echo(f"未知资产类型: {asset}, 支持: stock/etf/index", err=True)
        raise typer.Exit(1)
