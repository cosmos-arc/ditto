"""Capital 域摄取命令."""

from typing import Annotated

import typer

from ditto_port.cli.commands.factory import create_daily_command
from ditto_port.cli.context import create_executor
from ditto_port.cli.utils.output import print_ingestion_result
from ditto_port.cli.utils.validation import (
    check_instrument_mode,
    validate_instrument_params,
)

app = typer.Typer(help="资本面数据摄取")

# 估值指标
_valuation_impl = create_daily_command("valuation_metrics", "摄取估值指标")

# 融资融券
_margin_impl = create_daily_command("margin_trading", "摄取融资融券")

# 股权质押
_pledge_impl = create_daily_command("pledge_ratio", "摄取股权质押")


def _run_instrument_ingest(  # noqa: PLR0913
    ctx: typer.Context,
    dataset: str,
    ticker: str | None,
    standard_ticker: str | None,
    instrument_id: int | None,
    start: str | None,
    end: str | None,
    force: bool,
) -> None:
    """执行按标的摄取."""
    with create_executor() as executor:
        result = executor.ingest_by_instrument(
            dataset=dataset,
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            start_date=start or "",
            end_date=end or "",
            force=force,
        )
        print_ingestion_result(result, ctx.obj["verbose"])


@app.command("valuation")
def valuation(  # noqa: PLR0913
    ctx: typer.Context,
    date: Annotated[
        str | None,
        typer.Argument(help="交易日期 (YYYY-MM-DD)"),
    ] = None,
    # 标识符参数（三选一）
    ticker: Annotated[
        str | None,
        typer.Option("--ticker", "-t", help="裸代码 (如 000001)"),
    ] = None,
    standard_ticker: Annotated[
        str | None,
        typer.Option("--standard-ticker", help="Ditto 标准格式 (如 000001.XSHE)"),
    ] = None,
    instrument_id: Annotated[
        int | None,
        typer.Option("--instrument-id", "-i", help="内部 ID"),
    ] = None,
    # 时间范围
    start: Annotated[
        str | None,
        typer.Option("--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    ] = None,
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    r"""
    摄取估值指标.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest capital valuation 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest capital valuation --ticker 000001 \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest capital valuation --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "valuation_metrics",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _valuation_impl(ctx, date or "", force)


@app.command("margin")
def margin(  # noqa: PLR0913
    ctx: typer.Context,
    date: Annotated[
        str | None,
        typer.Argument(help="交易日期 (YYYY-MM-DD)"),
    ] = None,
    # 标识符参数（三选一）
    ticker: Annotated[
        str | None,
        typer.Option("--ticker", "-t", help="裸代码 (如 000001)"),
    ] = None,
    standard_ticker: Annotated[
        str | None,
        typer.Option("--standard-ticker", help="Ditto 标准格式 (如 000001.XSHE)"),
    ] = None,
    instrument_id: Annotated[
        int | None,
        typer.Option("--instrument-id", "-i", help="内部 ID"),
    ] = None,
    # 时间范围
    start: Annotated[
        str | None,
        typer.Option("--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    ] = None,
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    r"""
    摄取融资融券.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest capital margin 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest capital margin --ticker 000001 \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest capital margin --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "margin_trading",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _margin_impl(ctx, date or "", force)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股权质押."""
    return _pledge_impl(ctx, date, force)
