"""Macro query facade — 封装 MacroService，隐藏 MacroQuery 和枚举类型."""

from __future__ import annotations

import polars as pl
from ditto_data.services.macro_service import MacroQuery, MacroService
from ditto_kernel.market import MacroCategory, MacroFrequency

__all__ = ["MacroQueryFacade"]


class MacroQueryFacade:
    """
    Macro 域查询 facade.

    封装 MacroService，隐藏 MacroQuery / MacroCategory / MacroFrequency 等内部类型，
    对外只暴露字符串参数和 pl.DataFrame 返回值。
    """

    def __init__(self, macro_service: MacroService) -> None:
        self._service = macro_service

    def find_indicators(
        self,
        *,
        indicators: list[int] | list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        category: str | None = None,
        frequency: str | None = None,
    ) -> pl.DataFrame:
        """
        查询宏观指标数据.

        Args:
            indicators: 指标 ID 或代码列表，None 表示全部
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            category: 类别字符串，内部转换为 MacroCategory
            frequency: 频率字符串，内部转换为 MacroFrequency

        Returns:
            宏观指标 DataFrame

        """
        query = MacroQuery(
            indicators=indicators,
            start=start,
            end=end,
            category=MacroCategory(category) if category is not None else None,
            frequency=MacroFrequency(frequency) if frequency is not None else None,
        )
        return self._service.find_indicators(query)

    def list_indicators(
        self,
        start: str,
        end: str,
        category: str | None = None,
    ) -> pl.DataFrame:
        """
        按日期范围列出宏观指标.

        Args:
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            category: 类别字符串，内部转换为 MacroCategory

        Returns:
            宏观指标 DataFrame

        """
        return self._service.list_indicators(
            start=start,
            end=end,
            category=MacroCategory(category) if category is not None else None,
        )
