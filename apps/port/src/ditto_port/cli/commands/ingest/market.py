"""Market 域摄取命令 (stock/etf/index/adj/status)."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="行情数据摄取")

# daily (stock/etf/index 日行情)
_stock_daily_impl = create_daily_command("stock_daily", "摄取股票日行情")
_etf_daily_impl = create_daily_command("etf_daily", "摄取ETF日行情")
_index_daily_impl = create_daily_command("index_daily", "摄取指数日行情")

# adj (复权因子)
_adj_factor_impl = create_daily_command("adj_factor", "摄取股票复权因子")
_fund_adj_impl = create_daily_command("fund_adj", "摄取ETF/基金复权因子")

# status (股票状态)
_stock_status_impl = create_daily_command("stock_status", "摄取股票状态")


@app.command("stock")
def stock(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票日行情."""
    return _stock_daily_impl(ctx, date, force)


@app.command("etf")
def etf(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取ETF日行情."""
    return _etf_daily_impl(ctx, date, force)


@app.command("index")
def index(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取指数日行情."""
    return _index_daily_impl(ctx, date, force)


@app.command("adj")
def adj(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
    fund: bool = typer.Option(False, "--fund", help="摄取ETF/基金复权因子"),
) -> None:
    """摄取复权因子."""
    if fund:
        return _fund_adj_impl(ctx, date, force)
    return _adj_factor_impl(ctx, date, force)


@app.command("status")
def status(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票状态."""
    return _stock_status_impl(ctx, date, force)
