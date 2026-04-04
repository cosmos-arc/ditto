"""Capital 域回补命令."""

import typer

from ditto_interfaces.cli.commands.factory import create_backfill_command

app = typer.Typer(help="资本面数据回补")

# 估值指标
_valuation_impl = create_backfill_command("valuation_metrics", "回补估值指标")

# 融资融券
_margin_impl = create_backfill_command("margin_trading", "回补融资融券")

# 股权质押
_pledge_impl = create_backfill_command("pledge_ratio", "回补股权质押")


@app.command("valuation")
def valuation(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补估值指标."""
    return _valuation_impl(ctx, start, end, parallel)


@app.command("margin")
def margin(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补融资融券."""
    return _margin_impl(ctx, start, end, parallel)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股权质押."""
    return _pledge_impl(ctx, start, end, parallel)
