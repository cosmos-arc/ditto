"""复权因子命令."""

import typer

from ditto_port.cli.context import ensure_executor
from ditto_port.cli.utils.output import print_ingestion_result
from ditto_port.cli.utils.validation import validate_date_format

app = typer.Typer(help="复权因子命令")


@app.command("adj-factor")
def adj_factor(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票复权因子数据."""
    validate_date_format(date)

    ensure_executor(ctx)
    executor = ctx.obj["executor"]
    result = executor.ingest_daily("adj_factor", date, force)

    print_ingestion_result(result, ctx.obj["verbose"])


@app.command("fund-adj")
def fund_adj(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取基金复权因子数据."""
    validate_date_format(date)

    ensure_executor(ctx)
    executor = ctx.obj["executor"]
    result = executor.ingest_daily("fund_adj", date, force)

    print_ingestion_result(result, ctx.obj["verbose"])
