"""Metadata 域摄取命令 (calendar + basic)."""

import typer

from ditto_interfaces.cli.commands.factory import (
    create_basic_command,
    create_daily_command,
)

app = typer.Typer(help="元数据摄取")

# calendar
_calendar_impl = create_daily_command("calendar", "摄取交易日历")

# basic (stock/etf/index 基础信息)
_stock_basic_impl = create_basic_command("stock_basic", "摄取股票基础信息")
_etf_basic_impl = create_basic_command("etf_basic", "摄取ETF基础信息")
_index_basic_impl = create_basic_command("index_basic", "摄取指数基础信息")


@app.command("calendar")
def calendar(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取交易日历."""
    return _calendar_impl(ctx, date, force)


@app.command("basic")
def basic(
    ctx: typer.Context,
    asset: str = typer.Argument(..., help="资产类型 (stock/etf/index)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取基础信息 (stock/etf/index)."""
    asset = asset.lower()
    if asset == "stock":
        return _stock_basic_impl(ctx, force)
    elif asset == "etf":
        return _etf_basic_impl(ctx, force)
    elif asset == "index":
        return _index_basic_impl(ctx, force)
    else:
        typer.echo(f"未知资产类型: {asset}, 支持: stock/etf/index", err=True)
        raise typer.Exit(1)
