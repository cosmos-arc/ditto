"""
API 模型公共日期/格式化辅助工具.

供 market / commodity / fx / macro 等模型模块复用，
文件名以 _ 开头表示内部模块，不对外暴露。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Protocol

from pydantic import BeforeValidator


def parse_date(v: str | date | None) -> date | None:
    """解析日期值，支持字符串和 date 对象."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(v)


def format_float(value: float | None, decimals: int = 2) -> float | None:
    """格式化浮点数到指定小数位."""
    if value is None:
        return None
    return round(value, decimals)


def format_date(value: date | str | None) -> str | None:
    """将日期转换为字符串格式 (YYYY-MM-DD)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


# 支持从 JSON 字符串解析日期的类型
DateField = Annotated[date | None, BeforeValidator(parse_date)]


class _DateRangeModel(Protocol):
    """validate_date_range 所需的最小接口."""

    @property
    def start_date(self) -> date | None: ...

    @property
    def end_date(self) -> date | None: ...


def validate_date_range(
    self: _DateRangeModel,
) -> _DateRangeModel:
    """
    验证日期范围: start_date <= end_date.

    如果只提供了一个日期，则跳过校验。

    Raises:
        ValueError: 如果 start_date > end_date

    """
    if (
        self.start_date is not None
        and self.end_date is not None
        and self.start_date > self.end_date
    ):
        msg = (
            f"start_date ({self.start_date}) cannot be greater than "
            f"end_date ({self.end_date})"
        )
        raise ValueError(msg)
    return self
