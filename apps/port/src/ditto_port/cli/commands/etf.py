"""ETF 数据摄取命令."""

import typer

from ditto_port.cli.commands.factory import (
    create_backfill_command,
    create_basic_command,
    create_daily_command,
)

app = typer.Typer(help="ETF数据摄取命令")

# 使用工厂函数创建命令实现
_daily_impl = create_daily_command("etf_daily", "摄取ETF日行情数据")
_backfill_impl = create_backfill_command("etf_daily", "回补ETF历史数据")
_basic_impl = create_basic_command("etf_basic", "摄取ETF基础信息")


@app.command()
def daily(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取ETF日行情数据."""
    return _daily_impl(ctx, date, force)


@app.command()
def backfill(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度 (默认 1)"),
) -> None:
    """回补ETF历史数据."""
    return _backfill_impl(ctx, start, end, parallel)


@app.command()
def basic(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取ETF基础信息."""
    return _basic_impl(ctx, force)
