"""Market 域回补命令 (stock/etf/index/adj/status)."""

from __future__ import annotations

import typer

from ditto_interfaces.cli.commands.factory import create_backfill_command

app = typer.Typer(help="行情数据回补")

# daily (stock/etf/index 日行情)
_stock_daily_impl = create_backfill_command("stock_daily", "回补股票日行情")
_etf_daily_impl = create_backfill_command("etf_daily", "回补ETF日行情")
_index_daily_impl = create_backfill_command("index_daily", "回补指数日行情")

# adj (复权因子)
_adj_factor_impl = create_backfill_command("adj_factor", "回补股票复权因子")
_fund_adj_impl = create_backfill_command("fund_adj", "回补ETF/基金复权因子")

# status (股票状态)
_stock_status_impl = create_backfill_command("stock_status", "回补股票状态")


@app.command("stock")
def stock(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股票日行情."""
    return _stock_daily_impl(ctx, start, end, parallel)


@app.command("etf")
def etf(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补ETF日行情."""
    return _etf_daily_impl(ctx, start, end, parallel)


@app.command("index")
def index(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补指数日行情."""
    return _index_daily_impl(ctx, start, end, parallel)


@app.command("adj")
def adj(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
    fund: bool = typer.Option(False, "--fund", help="回补ETF/基金复权因子"),
) -> None:
    """回补复权因子."""
    if fund:
        return _fund_adj_impl(ctx, start, end, parallel)
    return _adj_factor_impl(ctx, start, end, parallel)


@app.command("status")
def status(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股票状态."""
    return _stock_status_impl(ctx, start, end, parallel)
