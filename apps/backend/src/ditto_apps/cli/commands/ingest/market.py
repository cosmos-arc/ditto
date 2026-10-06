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

# nav (ETF 单位净值) — 双模式（按日期滚动窗/按标的）
app.command("nav")(
    create_instrument_command(
        "etf_nav",
        "摄取ETF单位净值",
        cli_path="ingest market nav",
    )
)

# status (股票状态)
_stock_status_impl = create_daily_command("stock_status", "摄取股票状态")

# limit (涨跌停价格, #517)
_stock_limit_impl = create_daily_command("stock_limit", "摄取股票涨跌停价格")

# limit-list (涨跌停/炸板名单, #519) 与 fund-share (基金份额, #522)
_limit_list_impl = create_instrument_command(
    "limit_list",
    "摄取涨跌停与炸板名单",
    cli_path="ingest market limit-list",
)
_fund_share_impl = create_instrument_command(
    "fund_share",
    "摄取基金份额",
    cli_path="ingest market fund-share",
)

# fx (汇率)
_fx_daily_impl = create_daily_command("fx_daily", "摄取汇率日线数据")

# commodity (商品)
_commodity_daily_impl = create_daily_command("commodity_daily", "摄取商品价格数据")

# #434 期货（按日期全市场/按合约）与指数估值
_futures_daily_impl = create_instrument_command(
    "futures_daily",
    "摄取国内期货合约日线",
    cli_path="ingest market futures",
)
_futures_basic_impl = create_daily_command("futures_basic", "摄取期货合约信息")
_index_valuation_impl = create_daily_command("index_valuation", "摄取指数每日估值")


@app.command("adj")
def adj(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    r"""
    摄取股票复权因子.

    按日期批量摄取股票复权因子:

        uv run --no-sync ingest market adj 2024-01-15

    ETF/基金复权因子请使用 adj-fund 命令:

        uv run --no-sync ingest market adj-fund 2024-01-15
        uv run --no-sync ingest market adj-fund --ticker 510300 \\
            -s 2024-01-01 -e 2024-01-31
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


@app.command("limit")
def limit(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票涨跌停价格 (#517)."""
    return _stock_limit_impl(ctx, date, force)


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


@app.command("futures")
def futures(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取国内期货合约日线（按日期全市场）."""
    return _futures_daily_impl(ctx, date, force)


@app.command("futures-basic")
def futures_basic(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="采集日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取期货合约信息快照（按交易所分片）."""
    return _futures_basic_impl(ctx, date, force)


@app.command("index-valuation")
def index_valuation(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取指数每日估值（市值元/股本股）."""
    return _index_valuation_impl(ctx, date, force)


@app.command("limit-list")
def limit_list(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取涨跌停与炸板名单 (#519)."""
    return _limit_list_impl(ctx, date, force)


@app.command("fund-share")
def fund_share(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取基金份额 (#522)."""
    return _fund_share_impl(ctx, date, force)
