"""Market 域摄取命令 (stock/etf/index/adj/status/fx/commodity)."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import (
    create_daily_command,
    create_instrument_command,
)

app = typer.Typer(help="行情数据摄取")

# 双模式命令（按日期/按标的）
app.command("stock")(
    create_instrument_command(
        "stock_daily",
        "摄取股票日行情",
        cli_path="ingest market stock",
    )
)
app.command("etf")(
    create_instrument_command(
        "etf_daily",
        "摄取ETF日行情",
        cli_path="ingest market etf",
    )
)
app.command("index")(
    create_instrument_command(
        "index_daily",
        "摄取指数日行情",
        cli_path="ingest market index",
    )
)

# adj (复权因子)
_adj_factor_impl = create_daily_command("adj_factor", "摄取股票复权因子")

# adj-fund (ETF/基金复权因子) — 双模式（按日期/按标的）
app.command("adj-fund")(
    create_instrument_command(
        "fund_adj",
        "摄取ETF/基金复权因子",
        cli_path="ingest market adj-fund",
    )
)

# status (股票状态)
_stock_status_impl = create_daily_command("stock_status", "摄取股票状态")

# fx (汇率)
_fx_daily_impl = create_daily_command("fx_daily", "摄取汇率日线数据")

# commodity (商品)
_commodity_daily_impl = create_daily_command("commodity_daily", "摄取商品价格数据")


@app.command("adj")
def adj(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """
    摄取股票复权因子.

    按日期批量摄取股票复权因子:

        pixi run ingest market adj 2024-01-15

    ETF/基金复权因子请使用 adj-fund 命令:

        pixi run ingest market adj-fund 2024-01-15
        pixi run ingest market adj-fund --ticker 510300 -s 2024-01-01 -e 2024-01-31
    """
    return _adj_factor_impl(ctx, date, force)


@app.command("status")
def status(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票状态."""
    return _stock_status_impl(ctx, date, force)


@app.command("fx")
def fx(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取汇率日线数据."""
    return _fx_daily_impl(ctx, date, force)


@app.command("commodity")
def commodity(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取商品价格数据."""
    return _commodity_daily_impl(ctx, date, force)
