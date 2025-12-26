"""日期规范化工具函数，将各种日期类型转换为 YYYY-MM-DD 格式."""

from datetime import date, datetime

# 日期输入类型别名
DateInput = str | date | datetime | None


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
        return value.strftime("%Y-%m-%d")

    if isinstance(value, date):
        # 格式化 date 对象
        return value.strftime("%Y-%m-%d")

    raise TypeError(f"Unsupported date type: {type(value)}")
