"""CLI 输出格式化工具."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import orjson
import typer
from pydantic import BaseModel

#: 表格显示记录数上限
TABLE_DISPLAY_LIMIT = 20


def output_json(items: Sequence[BaseModel]) -> None:
    """
    输出 Pydantic 模型列表的 JSON 格式.

    Args:
        items: 包含 model_dump() 方法的对象列表

    """
    data = [item.model_dump() for item in items]
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def output_json_single(item: BaseModel) -> None:
    """
    输出单个 Pydantic 模型对象的 JSON 格式.

    Args:
        item: 包含 model_dump() 方法的对象

    """
    typer.echo(orjson.dumps(item.model_dump(), option=orjson.OPT_INDENT_2).decode())


def output_json_dicts(data: list[dict[str, Any]]) -> None:
    """
    输出字典列表的 JSON 格式.

    Args:
        data: 字典列表

    """
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def print_truncated_hint(total: int) -> None:
    """
    打印分页提示.

    Args:
        total: 总记录数

    """
    typer.echo(f"\n共 {total} 条记录, 仅显示前 {TABLE_DISPLAY_LIMIT} 条")


def print_ingestion_result(result: dict[str, Any], verbose: bool = False) -> None:
    """
    打印摄取结果.

    Args:
        result: 摄取结果字典
        verbose: 是否显示详细信息

    """
    status = result["status"]
    status_color = {
        "success": typer.colors.GREEN,
        "skipped": typer.colors.YELLOW,
        "failed": typer.colors.RED,
    }.get(status, typer.colors.WHITE)

    typer.secho(f"状态: {status}", fg=status_color, bold=True)
    typer.echo(f"数据集: {result['dataset']}")

    if result.get("trade_date"):
        typer.echo(f"交易日期: {result['trade_date']}")

    if result.get("row_count"):
        typer.echo(f"行数: {result['row_count']}")

    if verbose and result.get("message"):
        typer.echo(f"消息: {result['message']}")

    if result.get("error"):
        typer.secho(f"错误: {result['error']}", fg=typer.colors.RED)


def print_backfill_summary(result: dict[str, Any]) -> None:
    """
    打印回补摘要.

    Args:
        result: 回补结果字典

    """
    typer.secho("回补完成", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"数据集: {result['dataset']}")
    typer.echo(f"总日期数: {result['total_dates']}")
    typer.echo(f"成功: {result['success_count']}")
    typer.echo(f"跳过: {result['skipped_count']}")

    if result["failed_count"] > 0:
        typer.secho(f"失败: {result['failed_count']}", fg=typer.colors.RED)
    else:
        typer.echo(f"失败: {result['failed_count']}")
