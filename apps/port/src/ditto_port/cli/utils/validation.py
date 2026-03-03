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


def validate_instrument_params(
    date: str | None,
    ticker: str | None,
    standard_ticker: str | None,
    instrument_id: int | None,
    start: str | None,
    end: str | None,
) -> None:
    """
    验证标识符参数和时间范围参数的互斥关系.

    Args:
        date: 日期参数
        ticker: 裸代码
        standard_ticker: Ditto 标准格式
        instrument_id: 内部 ID
        start: 开始日期
        end: 结束日期

    Raises:
        typer.BadParameter: 参数组合无效时抛出

    """
    identifiers = [ticker, standard_ticker, instrument_id]
    has_identifier = any(identifiers)

    # 不能同时指定日期和标识符
    if date and has_identifier:
        msg = "不能同时指定日期和标识符参数, 请选择按日期批量或按标的摄取模式"
        raise typer.BadParameter(msg)

    # 按标的模式必须同时指定 start 和 end
    if has_identifier and (not start or not end):
        raise typer.BadParameter("按标的摄取需要同时指定 --start 和 --end 参数")

    # 按日期模式
    if date and not has_identifier:
        return

    # 按标的模式验证日期格式
    if has_identifier:
        if start:
            validate_date_format(start)
        if end:
            validate_date_format(end)
        # 验证日期范围
        if start and end and start > end:
            raise typer.BadParameter(f"start ({start}) 不能晚于 end ({end})")


def check_instrument_mode(
    date: str | None,
    ticker: str | None,
    standard_ticker: str | None,
    instrument_id: int | None,
) -> bool:
    """
    检查是否为按标的模式.

    Args:
        date: 日期参数
        ticker: 裸代码
        standard_ticker: Ditto 标准格式
        instrument_id: 内部 ID

    Returns:
        如果指定了标识符且没有指定日期，返回 True

    Raises:
        typer.BadParameter: 如果既没有指定日期也没有指定标识符

    """
    identifiers = [ticker, standard_ticker, instrument_id]
    has_identifier = any(identifiers)

    if has_identifier and not date:
        return True
    if date and not has_identifier:
        return False

    raise typer.BadParameter(
        "请指定以下模式之一: 按日期批量(date)或按标的摄取(标识符+时间范围)"
    )
