"""CLI 参数验证工具."""

import re
from datetime import datetime

import typer

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date_format(date_str: str) -> None:
    """
    验证日期格式 (YYYY-MM-DD).

    Args:
        date_str: 日期字符串

    Raises:
        typer.Exit: 如果日期格式无效

    """
    if not DATE_PATTERN.match(date_str):
        typer.echo(f"错误: 日期格式应为 YYYY-MM-DD, 收到: {date_str}")
        raise typer.Exit(1)

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        typer.echo(f"错误: 无效日期: {date_str}")
        raise typer.Exit(1) from None
