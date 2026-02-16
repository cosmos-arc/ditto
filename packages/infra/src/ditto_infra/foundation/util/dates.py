"""日期规范化工具函数，将各种日期类型转换为 YYYY-MM-DD 格式."""

from datetime import date, datetime
from typing import TypeGuard

# 日期输入类型别名
DateInput = str | date | datetime | None


def _is_pure_date(value: object) -> TypeGuard[date]:
    """
    检查是否是纯 date 类型（不是 datetime）.

    Args:
        value: 待检查的日期/日期时间对象

    Returns:
        如果是纯 date 类型返回 True，否则返回 False

    """
    return isinstance(value, date) and not isinstance(value, datetime)


def normalize_date(value: DateInput) -> str | None:
    """
    Normalize various date input types to YYYY-MM-DD string format.

    Args:
        value: Date input (str, date, datetime or None).

    Returns:
        Normalized date string in YYYY-MM-DD format, or None if input is None.

    Raises:
        ValueError: If string is not in valid YYYY-MM-DD format.

    """
    if value is None:
        return None

    if isinstance(value, str):
        # 通过尝试解析来验证字符串格式
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError as e:
            raise ValueError(f"Invalid date format: {value}") from e

    if isinstance(value, datetime):
        # 将 datetime 转换为日期字符串
        # 使用 f-string 确保4位年份（strftime %Y 对1-999年不补零）
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"

    # 类型收窄：使用 TypeGuard 确保这是纯 date 类型（不是 datetime）
    if _is_pure_date(value):
        # 使用 f-string 确保4位年份（strftime %Y 对1-999年不补零）
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"

    raise TypeError(f"Unsupported date type: {type(value).__name__}")
