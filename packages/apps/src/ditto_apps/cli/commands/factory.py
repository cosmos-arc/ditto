"""
CLI 命令工厂函数.

提供用于创建常见 CLI 命令模式的工厂函数，减少重复代码。
"""

from __future__ import annotations

from collections.abc import Callable

import typer

from ditto_apps.cli.context import create_executor
from ditto_apps.cli.utils.output import (
    print_backfill_summary,
    print_ingestion_result,
)
from ditto_apps.cli.utils.params import CLIIngestOptions, run_instrument_ingest
from ditto_apps.cli.utils.validation import (
    check_instrument_mode,
    validate_date_format,
    validate_instrument_params,
)


def create_instrument_command(
    dataset: str,
    description: str,
    *,
    cli_path: str = "",
) -> Callable[..., None]:
    """
    创建双模式（按日期/按标的）摄取命令的工厂函数.

    生成一个支持两种模式的命令函数:
    1. 按日期批量摄取: ``pixi run <cli_path> 2024-01-15``
    2. 按标的+时间段摄取: ``pixi run <cli_path> --ticker 000001 -s ... -e ...``

    Args:
        dataset: 数据集名称 (如 "stock_daily", "valuation_metrics")
        description: 命令简述.
        cli_path: CLI 示例路径 (如 "ingest market stock")，用于生成帮助文档.

    Returns:
        可直接注册为 Typer 命令的函数.

    """
    daily_impl = create_daily_command(dataset, description)

    def command(  # noqa: PLR0913 — CLI 命令回调，参数由 Typer 注入
        ctx: typer.Context,
        date: str | None = typer.Argument(None, help="交易日期 (YYYY-MM-DD)"),
        ticker: str | None = typer.Option(
            None, "--ticker", "-t", help="裸代码 (如 000001)"
        ),
        standard_ticker: str | None = typer.Option(
            None,
            "--standard-ticker",
            help="标准格式 (如 000001.XSHE)",
        ),
        instrument_id: int | None = typer.Option(
            None, "--instrument-id", "-i", help="内部 ID"
        ),
        start: str | None = typer.Option(
            None, "--start", "-s", help="开始日期 (YYYY-MM-DD)"
        ),
        end: str | None = typer.Option(
            None, "--end", "-e", help="结束日期 (YYYY-MM-DD)"
        ),
        force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
    ) -> None:
        validate_instrument_params(
            date, ticker, standard_ticker, instrument_id, start, end
        )
        if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
            params = CLIIngestOptions(
                ticker=ticker,
                standard_ticker=standard_ticker,
                instrument_id=instrument_id,
                start=start,
                end=end,
                force=force,
            )
            run_instrument_ingest(dataset, params)
        else:
            return daily_impl(ctx, date or "", force)

    if cli_path:
        command.__doc__ = (
            f"{description}.\n\n"
            "支持两种模式:\n\n"
            "1. 按日期批量摄取:\n"
            f"   pixi run {cli_path} 2024-01-15\n\n"
            "2. 按标的+时间段摄取 (标识符三选一):\n"
            f"   pixi run {cli_path} --ticker 000001 "
            "-s 2024-01-01 -e 2024-06-30\n"
            f"   pixi run {cli_path} --standard-ticker 000001.XSHE "
            "-s 2024-01-01 -e 2024-06-30"
        )
    else:
        command.__doc__ = description

    return command


def create_daily_command(dataset: str, description: str) -> Callable[..., None]:
    """
    创建 daily 命令的工厂函数.

    生成一个用于单日数据摄取的命令函数，该命令会:
    1. 验证日期格式
    2. 使用 create_executor 上下文管理器
    3. 调用 executor.ingest_daily()
    4. 打印摄取结果

    Args:
        dataset: 数据集名称 (如 "etf_daily", "stock_daily")
        description: 命令描述文档

    Returns:
        可调用的命令函数

    Examples:
        >>> daily_cmd = create_daily_command("etf_daily", "摄取ETF日行情数据")
        >>> @app.command()
        >>> def daily(ctx: typer.Context, date: str, force: bool):
        ...     return daily_cmd(ctx, date, force)

    """

    def command(ctx: typer.Context, date: str, force: bool) -> None:
        validate_date_format(date)

        with create_executor() as executor:
            result = executor.ingest_daily(dataset, date, force)
            print_ingestion_result(result, ctx.obj["verbose"])

    command.__doc__ = description
    return command


def create_backfill_command(dataset: str, description: str) -> Callable[..., None]:
    """
    创建 backfill 命令的工厂函数.

    生成一个用于历史数据回补的命令函数，该命令会:
    1. 验证开始和结束日期格式
    2. 使用 create_executor 上下文管理器
    3. 调用 executor.backfill_range()
    4. 打印回补摘要

    Args:
        dataset: 数据集名称 (如 "etf_daily", "stock_daily")
        description: 命令描述文档

    Returns:
        可调用的命令函数

    Examples:
        >>> backfill_cmd = create_backfill_command("etf_daily", "回补ETF历史数据")
        >>> @app.command()
        >>> def backfill(ctx: typer.Context, start: str, end: str, parallel: int):
        ...     return backfill_cmd(ctx, start, end, parallel)

    """

    def command(
        ctx: typer.Context,
        start: str,
        end: str,
        parallel: int,
    ) -> None:
        validate_date_format(start)
        validate_date_format(end)

        with create_executor() as executor:
            result = executor.backfill_range(dataset, start, end, parallel)
            print_backfill_summary(result)

    command.__doc__ = description
    return command


def create_basic_command(dataset: str, description: str) -> Callable[..., None]:
    """
    创建 basic 命令的工厂函数.

    生成一个用于基础信息摄取的命令函数，该命令会:
    1. 使用 create_executor 上下文管理器
    2. 调用 executor.ingest_daily() 并传入空字符串作为日期
    3. 打印摄取结果

    Args:
        dataset: 数据集名称 (如 "etf_basic", "stock_basic")
        description: 命令描述文档

    Returns:
        可调用的命令函数

    Examples:
        >>> basic_cmd = create_basic_command("etf_basic", "摄取ETF基础信息")
        >>> @app.command()
        >>> def basic(ctx: typer.Context, force: bool):
        ...     return basic_cmd(ctx, force)

    """

    def command(ctx: typer.Context, force: bool) -> None:
        with create_executor() as executor:
            result = executor.ingest_daily(dataset, "", force)
            print_ingestion_result(result, ctx.obj["verbose"])

    command.__doc__ = description
    return command
