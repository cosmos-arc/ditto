"""Tests for MacroQueryFacade — 封装 MacroService，隐藏 MacroQuery 和枚举."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
from ditto_application.query.macro import MacroQueryFacade
from ditto_data.services.macro_service import MacroQuery


class TestMacroQueryFacadeFindIndicators:
    """MacroQueryFacade.find_indicators — 内部构造 MacroQuery 并转换枚举."""

    def test_constructs_macro_query_with_category_and_frequency(self) -> None:
        service = MagicMock(spec=["find_indicators"])
        service.find_indicators.return_value = pl.DataFrame({"value": [3.5]})
        facade = MacroQueryFacade(macro_service=service)

        result = facade.find_indicators(
            indicators=["GDP"],
            start="2024-01-01",
            end="2024-12-31",
            category="economic",
            frequency="quarterly",
        )

        assert len(result) == 1
        query_arg = service.find_indicators.call_args[0][0]
        assert isinstance(query_arg, MacroQuery)
        assert query_arg.indicators == ["GDP"]
        assert query_arg.start == "2024-01-01"
        assert query_arg.end == "2024-12-31"
        assert query_arg.category.value == "economic"
        assert query_arg.frequency.value == "quarterly"

    def test_passes_none_when_no_enum_strings(self) -> None:
        service = MagicMock(spec=["find_indicators"])
        service.find_indicators.return_value = pl.DataFrame()
        facade = MacroQueryFacade(macro_service=service)

        facade.find_indicators(start="2024-01-01", end="2024-12-31")

        query_arg = service.find_indicators.call_args[0][0]
        assert query_arg.indicators is None
        assert query_arg.category is None
        assert query_arg.frequency is None

    def test_passes_indicator_ids(self) -> None:
        service = MagicMock(spec=["find_indicators"])
        service.find_indicators.return_value = pl.DataFrame()
        facade = MacroQueryFacade(macro_service=service)

        facade.find_indicators(indicators=[1, 2, 3])

        query_arg = service.find_indicators.call_args[0][0]
        assert query_arg.indicators == [1, 2, 3]


class TestMacroQueryFacadeListIndicators:
    """MacroQueryFacade.list_indicators — 内部转换 category 字符串."""

    def test_delegates_with_category_conversion(self) -> None:
        service = MagicMock(spec=["list_indicators"])
        service.list_indicators.return_value = pl.DataFrame({"value": [100]})
        facade = MacroQueryFacade(macro_service=service)

        result = facade.list_indicators(
            start="2024-01-01", end="2024-12-31", category="prices"
        )

        assert len(result) == 1
        service.list_indicators.assert_called_once_with(
            start="2024-01-01",
            end="2024-12-31",
            category=service.list_indicators.call_args[1]["category"],
        )
        # Verify category was converted from string
        cat_arg = service.list_indicators.call_args[1]["category"]
        assert cat_arg.value == "prices"

    def test_delegates_without_category(self) -> None:
        service = MagicMock(spec=["list_indicators"])
        service.list_indicators.return_value = pl.DataFrame()
        facade = MacroQueryFacade(macro_service=service)

        facade.list_indicators(start="2024-01-01", end="2024-12-31")

        service.list_indicators.assert_called_once_with(
            start="2024-01-01",
            end="2024-12-31",
            category=None,
        )
