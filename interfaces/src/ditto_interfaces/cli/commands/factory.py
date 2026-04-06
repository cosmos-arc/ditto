"""
CLI 命令工厂函数.

提供用于创建常见 CLI 命令模式的工厂函数，减少重复代码。
"""

from __future__ import annotations

from collections.abc import Callable

import typer

from ditto_interfaces.cli.context import create_executor
from ditto_interfaces.cli.utils.output import (
    print_backfill_summary,
    print_ingestion_result,
)
from ditto_interfaces.cli.utils.validation import validate_date_format


def create_daily_command(
    dataset: str, description: str
) -> Callable[[typer.Context, str, bool], None]:
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


def create_backfill_command(
    dataset: str, description: str
) -> Callable[[typer.Context, str, str, int], None]:
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


def create_basic_command(
    dataset: str, description: str
) -> Callable[[typer.Context, bool], None]:
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
