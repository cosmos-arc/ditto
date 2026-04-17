"""API 公共查询参数模型."""

from datetime import date

from pydantic import BaseModel, Field


class InstrumentIdentifierQuery(BaseModel):
    """标的标识符查询（三选一）."""

    instrument_id: int | None = Field(None, description="Canonical 标的 ID")
    ticker: str | None = Field(None, description="裸代码, 如 000001")
    standard_ticker: str | None = Field(None, description="标准代码, 如 000001.XSHE")

    model_config = {"extra": "ignore"}


class PITQueryParams(InstrumentIdentifierQuery):
    """PIT（时间点）查询参数 — as_of_date 必填."""

    as_of_date: date = Field(..., description="PIT 查询日期")


class DateRangeQueryParams(InstrumentIdentifierQuery):
    """日期范围查询参数."""

    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    as_of_date: date | None = Field(None, description="PIT 查询日期(可选)")
