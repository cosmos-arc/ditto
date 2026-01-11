"""ETF 数据摄取命令."""

import typer

from ditto_port.cli.context import ensure_executor
from ditto_port.cli.utils.output import print_backfill_summary, print_ingestion_result
from ditto_port.cli.utils.validation import validate_date_format

app = typer.Typer(help="ETF数据摄取命令")


@app.command()
def daily(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取ETF日行情数据."""
    validate_date_format(date)

    ensure_executor(ctx)
    executor = ctx.obj["executor"]
    result = executor.ingest_daily("etf_daily", date, force)

    print_ingestion_result(result, ctx.obj["verbose"])


@app.command()
def backfill(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度 (默认 1)"),
) -> None:
    """回补ETF历史数据."""
    validate_date_format(start)
    validate_date_format(end)

    ensure_executor(ctx)
    executor = ctx.obj["executor"]
    result = executor.backfill_range("etf_daily", start, end, parallel)

    print_backfill_summary(result)


@app.command()
def basic(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取ETF基础信息."""
    ensure_executor(ctx)
    executor = ctx.obj["executor"]
    result = executor.ingest_daily("etf_basic", "", force)

    print_ingestion_result(result, ctx.obj["verbose"])
