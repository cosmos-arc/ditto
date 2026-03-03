"""Market 域摄取命令 (stock/etf/index/adj/status/fx/commodity)."""

from typing import Annotated

import typer

from ditto_port.cli.commands.factory import create_daily_command
from ditto_port.cli.context import create_executor
from ditto_port.cli.utils.output import print_ingestion_result
from ditto_port.cli.utils.validation import (
    check_instrument_mode,
    validate_instrument_params,
)

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

# fx (汇率)
_fx_daily_impl = create_daily_command("fx_daily", "摄取汇率日线数据")

# commodity (商品)
_commodity_daily_impl = create_daily_command("commodity_daily", "摄取商品价格数据")


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


@app.command("stock")
def stock(  # noqa: PLR0913
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
    摄取股票日行情.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest market stock 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest market stock --ticker 000001 -s 2024-01-01 -e 2024-01-31
       pixi run ingest market stock --standard-ticker 000001.XSHE \
           -s 2024-01-01 -e 2024-06-30
       pixi run ingest market stock --instrument-id 1000001 \
           -s 2024-01-01 -e 2024-01-31

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "stock_daily",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        # 此时 date 必定不为 None（由 check_instrument_mode 保证）
        return _stock_daily_impl(ctx, date or "", force)


@app.command("etf")
def etf(  # noqa: PLR0913
    ctx: typer.Context,
    date: Annotated[
        str | None,
        typer.Argument(help="交易日期 (YYYY-MM-DD)"),
    ] = None,
    # 标识符参数（三选一）
    ticker: Annotated[
        str | None,
        typer.Option("--ticker", "-t", help="裸代码 (如 510300)"),
    ] = None,
    standard_ticker: Annotated[
        str | None,
        typer.Option("--standard-ticker", help="Ditto 标准格式 (如 510300.XSHG)"),
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
    摄取ETF日行情.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest market etf 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest market etf --ticker 510300 -s 2024-01-01 -e 2024-01-31
       pixi run ingest market etf --standard-ticker 510300.XSHG \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "etf_daily",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _etf_daily_impl(ctx, date or "", force)


@app.command("index")
def index(  # noqa: PLR0913
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
        typer.Option("--standard-ticker", help="Ditto 标准格式 (如 000001.XSHG)"),
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
    摄取指数日行情.

    支持两种模式：

    1. 按日期批量摄取：
       pixi run ingest market index 2024-01-15

    2. 按标的+时间段摄取（标识符三选一）：
       pixi run ingest market index --ticker 000001 -s 2024-01-01 -e 2024-01-31
       pixi run ingest market index --standard-ticker 000001.XSHG \
           -s 2024-01-01 -e 2024-06-30

    """
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(
            ctx,
            "index_daily",
            ticker,
            standard_ticker,
            instrument_id,
            start,
            end,
            force,
        )
    else:
        return _index_daily_impl(ctx, date or "", force)


@app.command("adj")
def adj(  # noqa: PLR0913
    ctx: typer.Context,
    date: Annotated[
        str | None,
        typer.Argument(help="交易日期 (YYYY-MM-DD)"),
    ] = None,
    # 标识符参数（三选一，仅 --fund 模式支持）
    ticker: Annotated[
        str | None,
        typer.Option("--ticker", "-t", help="裸代码 (如 510300)"),
    ] = None,
    standard_ticker: Annotated[
        str | None,
        typer.Option("--standard-ticker", help="Ditto 标准格式 (如 510300.XSHG)"),
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
    fund: bool = typer.Option(False, "--fund", help="摄取ETF/基金复权因子"),
) -> None:
    r"""
    摄取复权因子.

    支持两种模式：

    1. 股票复权因子（按日期批量）：
       pixi run ingest market adj 2024-01-15

    2. ETF/基金复权因子（按日期或按标的）：
       pixi run ingest market adj --fund 2024-01-15
       pixi run ingest market adj --fund --ticker 510300 -s 2024-01-01 -e 2024-01-31

    """
    if fund:
        validate_instrument_params(
            date, ticker, standard_ticker, instrument_id, start, end
        )
        if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
            _run_instrument_ingest(
                ctx,
                "fund_adj",
                ticker,
                standard_ticker,
                instrument_id,
                start,
                end,
                force,
            )
        else:
            return _fund_adj_impl(ctx, date or "", force)
    else:
        # 股票复权因子必须指定日期
        if date is None:
            raise typer.BadParameter("股票复权因子必须指定交易日期")
        return _adj_factor_impl(ctx, date, force)


@app.command("status")
def status(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票状态."""
    return _stock_status_impl(ctx, date, force)


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
