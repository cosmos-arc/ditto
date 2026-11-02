"""
Fundamental 域 API 模型.

包含:
- FinancialType: 财务报表类型枚举
- FinancialQuery: 财务报表查询参数模型
- Financial: 财务报表响应模型
- DividendQuery: 分红查询参数模型
- Dividend: 分红响应模型
- CorporateActionsQuery: 公司行动查询参数模型
- CorporateAction: 公司行动响应模型
- 转换函数
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Self

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FinancialType(StrEnum):
    """
    财务报表类型枚举.

    Attributes:
        BALANCE_SHEET: 资产负债表
        INCOME_STATEMENT: 利润表
        CASH_FLOW: 现金流量表

    """

    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"


class FinancialQuery(BaseModel):
    """
    财务报表查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: PIT 查询日期

    """

    instrument_id: int = Field(description="标的 ID")
    as_of_date: date = Field(description="PIT 查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Financial(BaseModel):
    """
    财务报表响应模型（pit_asof：as_of 可见版本，多版本收敛到最新披露）.

    Attributes:
        instrument_id: 标的 ID
        report_date: 报告期
        report_type: 报表类型
        data: 财务数据字典（读取器业务列）
        knowledge_date: 公告锚（as_of 可见的披露日）
        effective_from: 版本生效起点（=公告锚）
        effective_to: 版本关闭日（空=当前版本开放）

    """

    instrument_id: int = Field(description="标的 ID")
    report_date: str = Field(description="报告期")
    report_type: str = Field(description="报表类型")
    data: dict[str, Any] = Field(description="财务数据字典")
    knowledge_date: str | None = Field(
        default=None, description="公告锚（as_of 可见的披露日）"
    )
    effective_from: str | None = Field(default=None, description="版本生效起点")
    effective_to: str | None = Field(
        default=None, description="版本关闭日（空=当前版本开放）"
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class DividendQuery(BaseModel):
    """
    分红查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: PIT 查询日期

    """

    instrument_id: int = Field(description="标的 ID")
    as_of_date: date = Field(description="PIT 查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Dividend(BaseModel):
    """
    分红响应模型（pit_asof：as_of 可见版本）.

    存储列：ex_dividend_date（事实日）、div_proc、dividend_per_share（元/股）、
    dividend_yield；公告锚即 knowledge_date（#628 起按真实列映射，
    旧 amount 恒 0.0 的伪映射废弃）.

    Attributes:
        instrument_id: 标的 ID
        ex_dividend_date: 除息日（事实日，可能为空=未定除息日）
        div_proc: 分红流程阶段（预案/股东大会/实施等）
        dividend_per_share: 每股分红（元；空=未披露数值）
        dividend_yield: 股息率
        knowledge_date: 公告锚（as_of 可见的披露日）
        effective_from: 版本生效起点
        effective_to: 版本关闭日（空=当前版本开放）

    """

    instrument_id: int = Field(description="标的 ID")
    ex_dividend_date: str | None = Field(description="除息日（事实日）")
    div_proc: str | None = Field(description="分红流程阶段")
    dividend_per_share: float | None = Field(description="每股分红（元）")
    dividend_yield: float | None = Field(description="股息率")
    knowledge_date: str | None = Field(
        default=None, description="公告锚（as_of 可见的披露日）"
    )
    effective_from: str | None = Field(default=None, description="版本生效起点")
    effective_to: str | None = Field(
        default=None, description="版本关闭日（空=当前版本开放）"
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class CorporateActionsQuery(BaseModel):
    """
    公司行动查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        start_date: 开始日期
        end_date: 结束日期

    """

    instrument_id: int = Field(description="标的 ID")
    start_date: date = Field(description="开始日期")
    end_date: date = Field(description="结束日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """
        验证日期范围: start_date <= end_date.

        Raises:
            ValueError: 如果 start_date > end_date

        """
        if self.start_date > self.end_date:
            msg = (
                f"start_date ({self.start_date}) cannot be greater than "
                f"end_date ({self.end_date})"
            )
            raise ValueError(msg)
        return self


class CorporateAction(BaseModel):
    """
    公司行动响应模型.

    as_of_date 给定时为 pit_asof 语义（同事实键多版本收敛到最新可见披露）；
    缺省时为 latest_available 语义（版本历史原样返回，多版本行可见）.

    Attributes:
        instrument_id: 标的 ID
        action_date: 行动日期
        action_type: 行动类型
        description: 行动描述
        knowledge_date: 公告锚
        effective_from: 版本生效起点
        effective_to: 版本关闭日（空=当前版本开放）

    """

    instrument_id: int = Field(description="标的 ID")
    action_date: str = Field(description="行动日期")
    action_type: str = Field(description="行动类型")
    description: str = Field(description="行动描述")
    knowledge_date: str | None = Field(default=None, description="公告锚")
    effective_from: str | None = Field(default=None, description="版本生效起点")
    effective_to: str | None = Field(
        default=None, description="版本关闭日（空=当前版本开放）"
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


# 行内非业务列：身份、事实日与 PIT 版本轴不进入 data 字典
_NON_BUSINESS_COLUMNS = frozenset(
    {
        "instrument_id",
        "report_date",
        "report_type",
        "data",
        "knowledge_date",
        "effective_from",
        "effective_to",
    }
)


def _optional_str(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return None if value is None else str(value)


def _optional_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    return None if value is None else float(value)


def to_financial(row: dict[str, Any], report_type: FinancialType) -> Financial:
    """
    将数据库行转换为 Financial 模型.

    读取器行是平铺业务列；data 字典由业务列聚合，公告锚与版本区间
    作为独立字段透出（#628：事实/公告/版本分开）.

    Args:
        row: 数据库行字典
        report_type: 财务报表类型

    Returns:
        Financial 模型实例

    """
    data = {
        key: value for key, value in row.items() if key not in _NON_BUSINESS_COLUMNS
    }
    return Financial(
        instrument_id=int(row["instrument_id"]),
        report_date=str(row.get("report_date", "")),
        report_type=report_type.value,
        data=data or dict(row.get("data") or {}),
        knowledge_date=_optional_str(row, "knowledge_date"),
        effective_from=_optional_str(row, "effective_from"),
        effective_to=_optional_str(row, "effective_to"),
    )


def to_financial_list(df: pl.DataFrame, report_type: FinancialType) -> list[Financial]:
    """
    将 DataFrame 转换为 Financial 列表.

    Args:
        df: 包含财务数据的 DataFrame
        report_type: 财务报表类型

    Returns:
        Financial 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Financial] = []
    for row in df.to_dicts():
        result.append(to_financial(row, report_type))

    return result


def to_dividend(row: dict[str, Any]) -> Dividend:
    """
    将数据库行转换为 Dividend 模型.

    存储列为 ex_dividend_date/div_proc/dividend_per_share/dividend_yield
    （+PIT 版本轴）；未披露数值以 null 透出，不再零填充（#628）.

    Args:
        row: 数据库行字典

    Returns:
        Dividend 模型实例

    """
    return Dividend(
        instrument_id=int(row["instrument_id"]),
        ex_dividend_date=_optional_str(row, "ex_dividend_date"),
        div_proc=_optional_str(row, "div_proc"),
        dividend_per_share=_optional_float(row, "dividend_per_share"),
        dividend_yield=_optional_float(row, "dividend_yield"),
        knowledge_date=_optional_str(row, "knowledge_date"),
        effective_from=_optional_str(row, "effective_from"),
        effective_to=_optional_str(row, "effective_to"),
    )


def to_dividend_list(df: pl.DataFrame) -> list[Dividend]:
    """
    将 DataFrame 转换为 Dividend 列表.

    Args:
        df: 包含分红数据的 DataFrame

    Returns:
        Dividend 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Dividend] = []
    for row in df.to_dicts():
        result.append(to_dividend(row))

    return result


def to_corporate_action(row: dict[str, Any]) -> CorporateAction:
    """
    将数据库行转换为 CorporateAction 模型.

    Args:
        row: 数据库行字典

    Returns:
        CorporateAction 模型实例

    """
    return CorporateAction(
        instrument_id=int(row["instrument_id"]),
        action_date=str(row.get("action_date", "")),
        action_type=str(row.get("action_type", "")),
        description=str(row.get("description", "")),
        knowledge_date=_optional_str(row, "knowledge_date"),
        effective_from=_optional_str(row, "effective_from"),
        effective_to=_optional_str(row, "effective_to"),
    )


def to_corporate_action_list(df: pl.DataFrame) -> list[CorporateAction]:
    """
    将 DataFrame 转换为 CorporateAction 列表.

    Args:
        df: 包含公司行动数据的 DataFrame

    Returns:
        CorporateAction 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[CorporateAction] = []
    for row in df.to_dicts():
        result.append(to_corporate_action(row))

    return result


__all__ = [
    "CorporateAction",
    "CorporateActionsQuery",
    "Dividend",
    "DividendQuery",
    "Financial",
    "FinancialQuery",
    "FinancialType",
    "to_corporate_action",
    "to_corporate_action_list",
    "to_dividend",
    "to_dividend_list",
    "to_financial",
    "to_financial_list",
]
