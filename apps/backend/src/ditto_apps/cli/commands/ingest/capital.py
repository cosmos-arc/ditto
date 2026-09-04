"""Capital 域摄取命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import (
    create_daily_command,
    create_instrument_command,
)
from ditto_apps.cli.context import create_executor
from ditto_apps.cli.utils.output import print_ingestion_result
from ditto_apps.cli.utils.validation import validate_date_format

app = typer.Typer(help="资本面数据摄取")

# 股权质押
_pledge_impl = create_daily_command("pledge_ratio", "摄取股权质押")

# 双模式命令（按日期/按标的）
app.command("valuation")(
    create_instrument_command(
        "valuation_metrics",
        "摄取估值指标",
        cli_path="ingest capital valuation",
    )
)
app.command("margin")(
    create_instrument_command(
        "margin_trading",
        "摄取融资融券",
        cli_path="ingest capital margin",
    )
)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股权质押."""
    return _pledge_impl(ctx, date, force)


@app.command("index-weight")
def index_weight(
    ctx: typer.Context,
    index_code: str = typer.Argument(..., help="指数代码 (e.g., 000300.SH)"),
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """
    摄取指数成分股权重.

    按指数代码+日期摄取成分股权重:

        pixi run ingest capital index-weight 000300.SH 2024-01-15
    """
    validate_date_format(date)

    with create_executor() as executor:
        result = executor.ingest_daily("index_weight", date, force)
        print_ingestion_result(result, ctx.obj["verbose"])
