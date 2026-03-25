"""Tests for Fundamental domain models.

FinancialType, FinancialQuery, Financial, DividendQuery, Dividend,
CorporateActionsQuery, CorporateAction, to_financial, to_financial_list,
to_dividend, to_dividend_list, to_corporate_action, to_corporate_action_list.
"""

from datetime import date
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestFinancialType:
    """测试 FinancialType 枚举."""

    def test_financial_type_values(self) -> None:
        """验证 FinancialType 包含 balance_sheet, income_statement, cash_flow."""
        from ditto_port.models.fundamental import FinancialType

        assert FinancialType.BALANCE_SHEET.value == "balance_sheet"
        assert FinancialType.INCOME_STATEMENT.value == "income_statement"
        assert FinancialType.CASH_FLOW.value == "cash_flow"

    def test_financial_type_from_string(self) -> None:
        """验证可以从字符串创建 FinancialType."""
        from ditto_port.models.fundamental import FinancialType

        assert FinancialType("balance_sheet") == FinancialType.BALANCE_SHEET
        assert FinancialType("income_statement") == FinancialType.INCOME_STATEMENT
        assert FinancialType("cash_flow") == FinancialType.CASH_FLOW

    def test_financial_type_invalid_value(self) -> None:
        """验证无效值会抛出异常."""
        from ditto_port.models.fundamental import FinancialType

        with pytest.raises(ValueError):
            FinancialType("invalid")


@pytest.mark.unit
class TestFinancialQuery:
    """测试 FinancialQuery 查询参数模型."""

    def test_default_values(self) -> None:
        """验证必须字段: instrument_id, as_of_date."""
        from ditto_port.models.fundamental import FinancialQuery

        query = FinancialQuery(instrument_id=1, as_of_date=date(2024, 1, 1))
        assert query.instrument_id == 1
        assert query.as_of_date == date(2024, 1, 1)

    def test_custom_values(self) -> None:
        """验证自定义查询参数."""
        from ditto_port.models.fundamental import FinancialQuery

        query = FinancialQuery(
            instrument_id=600000,
            as_of_date=date(2024, 3, 31),
        )
        assert query.instrument_id == 600000
        assert query.as_of_date == date(2024, 3, 31)

    def test_instrument_id_required(self) -> None:
        """验证 instrument_id 是必须字段."""
        from ditto_port.models.fundamental import FinancialQuery

        with pytest.raises(ValidationError) as exc_info:
            FinancialQuery(as_of_date=date(2024, 1, 1))  # type: ignore[call-arg]
        assert "instrument_id" in str(exc_info.value)

    def test_as_of_date_required(self) -> None:
        """验证 as_of_date 是必须字段."""
        from ditto_port.models.fundamental import FinancialQuery

        with pytest.raises(ValidationError) as exc_info:
            FinancialQuery(instrument_id="1")  # type: ignore[call-arg]
        assert "as_of_date" in str(exc_info.value)


@pytest.mark.unit
class TestFinancial:
    """测试 Financial 响应模型."""

    def test_basic_financial(self) -> None:
        """验证基本 Financial 创建."""
        from ditto_port.models.fundamental import Financial

        financial = Financial(
            instrument_id=1,
            report_date="2024-03-31",
            report_type="balance_sheet",
            data={"total_assets": 1000000.0, "total_liabilities": 500000.0},
        )

        assert financial.instrument_id == 1
        assert financial.report_date == "2024-03-31"
        assert financial.report_type == "balance_sheet"
        assert financial.data["total_assets"] == 1000000.0

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_port.models.fundamental import Financial

        financial = Financial(
            instrument_id=1,
            report_date="2024-03-31",
            report_type="balance_sheet",
            data={"total_assets": 1000000.0},
        )

        data = financial.model_dump()
        assert data["instrument_id"] == 1
        assert data["report_date"] == "2024-03-31"
        assert data["report_type"] == "balance_sheet"
        assert data["data"]["total_assets"] == 1000000.0


@pytest.mark.unit
class TestToFinancial:
    """测试 to_financial 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_port.models.fundamental import FinancialType, to_financial

        row: dict[str, Any] = {
            "instrument_id": 1,
            "report_date": "2024-03-31",
            "report_type": "balance_sheet",
            "data": {"total_assets": 1000000.0, "total_liabilities": 500000.0},
        }

        financial = to_financial(row, FinancialType.BALANCE_SHEET)

        assert financial.instrument_id == 1
        assert financial.report_date == "2024-03-31"
        assert financial.report_type == "balance_sheet"
        assert financial.data["total_assets"] == 1000000.0


@pytest.mark.unit
class TestToFinancialList:
    """测试 to_financial_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_port.models.fundamental import FinancialType, to_financial_list

        df = pl.DataFrame()
        result = to_financial_list(df, FinancialType.BALANCE_SHEET)
        assert result == []

    def test_convert_single_row_dataframe(self) -> None:
        """验证单行 DataFrame 转换."""
        from ditto_port.models.fundamental import FinancialType, to_financial_list

        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "report_date": ["2024-03-31"],
                "data": [{"total_assets": 1000000.0}],
            }
        )

        result = to_financial_list(df, FinancialType.BALANCE_SHEET)

        assert len(result) == 1
        assert result[0].instrument_id == 1
        assert result[0].report_date == "2024-03-31"


@pytest.mark.unit
class TestDividendQuery:
    """测试 DividendQuery 查询参数模型."""

    def test_required_fields(self) -> None:
        """验证必须字段: instrument_id, as_of_date."""
        from ditto_port.models.fundamental import DividendQuery

        query = DividendQuery(instrument_id=1, as_of_date=date(2024, 1, 1))
        assert query.instrument_id == 1
        assert query.as_of_date == date(2024, 1, 1)

    def test_instrument_id_required(self) -> None:
        """验证 instrument_id 是必须字段."""
        from ditto_port.models.fundamental import DividendQuery

        with pytest.raises(ValidationError) as exc_info:
            DividendQuery(as_of_date=date(2024, 1, 1))  # type: ignore[call-arg]
        assert "instrument_id" in str(exc_info.value)


@pytest.mark.unit
class TestDividend:
    """测试 Dividend 响应模型."""

    def test_basic_dividend(self) -> None:
        """验证基本 Dividend 创建."""
        from ditto_port.models.fundamental import Dividend

        dividend = Dividend(
            instrument_id=1,
            announce_date="2024-03-31",
            dividend_type="cash",
            amount=0.5,
        )

        assert dividend.instrument_id == 1
        assert dividend.announce_date == "2024-03-31"
        assert dividend.dividend_type == "cash"
        assert dividend.amount == 0.5


@pytest.mark.unit
class TestToDividend:
    """测试 to_dividend 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_port.models.fundamental import to_dividend

        row: dict[str, Any] = {
            "instrument_id": 1,
            "announce_date": "2024-03-31",
            "dividend_type": "cash",
            "amount": 0.5,
        }

        dividend = to_dividend(row)

        assert dividend.instrument_id == 1
        assert dividend.announce_date == "2024-03-31"
        assert dividend.dividend_type == "cash"
        assert dividend.amount == 0.5


@pytest.mark.unit
class TestToDividendList:
    """测试 to_dividend_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_port.models.fundamental import to_dividend_list

        df = pl.DataFrame()
        result = to_dividend_list(df)
        assert result == []


@pytest.mark.unit
class TestCorporateActionsQuery:
    """测试 CorporateActionsQuery 查询参数模型."""

    def test_required_fields(self) -> None:
        """验证必须字段: instrument_id, start_date, end_date."""
        from ditto_port.models.fundamental import CorporateActionsQuery

        query = CorporateActionsQuery(
            instrument_id=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
        )
        assert query.instrument_id == 1
        assert query.start_date == date(2024, 1, 1)
        assert query.end_date == date(2024, 3, 31)

    def test_date_range_validation_success(self) -> None:
        """验证日期范围校验成功: start_date <= end_date."""
        from ditto_port.models.fundamental import CorporateActionsQuery

        # start_date == end_date 应该有效
        query = CorporateActionsQuery(
            instrument_id=1,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )
        assert query.start_date == date(2024, 1, 15)
        assert query.end_date == date(2024, 1, 15)

    def test_date_range_validation_failure(self) -> None:
        """验证日期范围校验失败: start_date > end_date."""
        from ditto_port.models.fundamental import CorporateActionsQuery

        with pytest.raises(ValidationError) as exc_info:
            CorporateActionsQuery(
                instrument_id=1,
                start_date=date(2024, 3, 31),
                end_date=date(2024, 1, 1),
            )
        assert "start_date" in str(exc_info.value).lower()
        assert "end_date" in str(exc_info.value).lower()

    def test_instrument_id_required(self) -> None:
        """验证 instrument_id 是必须字段."""
        from ditto_port.models.fundamental import CorporateActionsQuery

        with pytest.raises(ValidationError) as exc_info:
            CorporateActionsQuery(  # type: ignore[call-arg]
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31),
            )
        assert "instrument_id" in str(exc_info.value)


@pytest.mark.unit
class TestCorporateAction:
    """测试 CorporateAction 响应模型."""

    def test_basic_corporate_action(self) -> None:
        """验证基本 CorporateAction 创建."""
        from ditto_port.models.fundamental import CorporateAction

        action = CorporateAction(
            instrument_id=1,
            action_date="2024-03-31",
            action_type="split",
            description="1:2 股票拆分",
        )

        assert action.instrument_id == 1
        assert action.action_date == "2024-03-31"
        assert action.action_type == "split"
        assert action.description == "1:2 股票拆分"


@pytest.mark.unit
class TestToCorporateAction:
    """测试 to_corporate_action 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_port.models.fundamental import to_corporate_action

        row: dict[str, Any] = {
            "instrument_id": 1,
            "action_date": "2024-03-31",
            "action_type": "split",
            "description": "1:2 股票拆分",
        }

        action = to_corporate_action(row)

        assert action.instrument_id == 1
        assert action.action_date == "2024-03-31"
        assert action.action_type == "split"
        assert action.description == "1:2 股票拆分"


@pytest.mark.unit
class TestToCorporateActionList:
    """测试 to_corporate_action_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_port.models.fundamental import to_corporate_action_list

        df = pl.DataFrame()
        result = to_corporate_action_list(df)
        assert result == []

    def test_convert_multiple_rows_dataframe(self) -> None:
        """验证多行 DataFrame 转换."""
        from ditto_port.models.fundamental import to_corporate_action_list

        df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "action_date": ["2024-01-15", "2024-03-31"],
                "action_type": ["dividend", "split"],
                "description": ["现金分红", "1:2 股票拆分"],
            }
        )

        result = to_corporate_action_list(df)

        assert len(result) == 2
        assert result[0].action_type == "dividend"
        assert result[1].action_type == "split"
