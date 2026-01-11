"""CLI 输出格式化工具."""

from typing import Any

import typer


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
