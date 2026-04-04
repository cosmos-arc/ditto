"""Fundamental 域摄取命令."""

from typing import Annotated

import typer

from ditto_interfaces.cli.commands.factory import create_daily_command
from ditto_interfaces.cli.context import create_executor
from ditto_interfaces.cli.utils.output import print_ingestion_result
from ditto_interfaces.cli.utils.validation import (
    check_instrument_mode,
    validate_instrument_params,
)

app = typer.Typer(help="基本面数据摄取")

# 财务报表
_balance_impl = create_daily_command("balance_sheet", "摄取资产负债表")
_income_impl = create_daily_command("income_statement", "摄取利润表")
_cash_flow_impl = create_daily_command("cash_flow", "摄取现金流量表")
_dividend_impl = create_daily_command("dividend", "摄取分红送配")

# 公司行为
_corporate_actions_impl = create_daily_command("corporate_actions", "摄取公司行为")


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


@app.command("balance")
def balance(  # noqa: PLR0913
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
    摄取资产负债表.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest fundamental balance 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest fundamental balance --ticker 000001 \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest fundamental balance --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "balance_sheet",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _balance_impl(ctx, date or "", force)


@app.command("income")
def income(  # noqa: PLR0913
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
    摄取利润表.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest fundamental income 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest fundamental income --ticker 000001 \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest fundamental income --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "income_statement",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _income_impl(ctx, date or "", force)


@app.command("cash-flow")
def cash_flow(  # noqa: PLR0913
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
    摄取现金流量表.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest fundamental cash-flow 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest fundamental cash-flow --ticker 000001 \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest fundamental cash-flow --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "cash_flow",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _cash_flow_impl(ctx, date or "", force)


@app.command("dividend")
def dividend(  # noqa: PLR0913
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
    摄取分红送配.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest fundamental dividend 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest fundamental dividend --ticker 000001 \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest fundamental dividend --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "dividend",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _dividend_impl(ctx, date or "", force)


@app.command("corporate-actions")
def corporate_actions(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取公司行为."""
    return _corporate_actions_impl(ctx, date, force)
