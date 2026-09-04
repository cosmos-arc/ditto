"""
Market 域 API 模型.

包含:
- Adjustment: 复权类型枚举
- BarsQuery: K 线查询参数模型
- Bar: K 线响应模型
- to_bar: 转换函数
- to_bar_list: 批量转换函数
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

import polars as pl
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from ditto_apps.models._date_helpers import DateField, format_date, format_float


class Adjustment(StrEnum):
    """
    复权类型枚举.

    Attributes:
        NONE: 不复权
        QFQ: 前复权
        HFQ: 后复权

    """

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


def _parse_adjustment(v: str | Adjustment) -> Adjustment:
    """解析复权类型，支持字符串和 Adjustment 对象."""
    if isinstance(v, Adjustment):
        return v
    return Adjustment(v)


# 支持从 JSON 字符串解析复权类型
AdjustmentField = Annotated[Adjustment, BeforeValidator(_parse_adjustment)]


class BarsQuery(BaseModel):
    """
    K 线查询参数模型.

    Attributes:
        instrument_ids: 标的 ID 列表 (可选)
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)
        adjustment: 复权类型, 默认 none
        asset_class: 资产类别过滤 (可选)
        allow_experimental_data: 显式允许 experimental 数据集进入研究态查询
        limit: 返回数量限制, 默认 1000, 范围 1-10000

    """

    instrument_ids: list[int] | None = Field(default=None, description="标的 ID 列表")
    start_date: DateField = Field(default=None, description="开始日期")
    end_date: DateField = Field(default=None, description="结束日期")
    adjustment: AdjustmentField = Field(default=Adjustment.NONE, description="复权类型")
    asset_class: str | None = Field(default=None, description="资产类别过滤")
    allow_experimental_data: bool = Field(
        default=False,
        description="显式允许 experimental 数据集进入研究态查询",
    )
    limit: int = Field(default=1000, ge=1, le=10000, description="返回数量限制")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
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


class Bar(BaseModel):
    """
    K 线响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期 (YYYY-MM-DD)
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量 (保留2位小数)
        amount: 成交额
        turnover_rate: 换手率 (可选)

    """

    instrument_id: int = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    open: float = Field(description="开盘价")
    high: float = Field(description="最高价")
    low: float = Field(description="最低价")
    close: float = Field(description="收盘价")
    volume: float = Field(description="成交量")
    amount: float = Field(description="成交额")
    turnover_rate: float | None = Field(default=None, description="换手率")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class RegimeIndicatorResponse(BaseModel):
    """One normalized input used by the frozen regime model."""

    model_config = ConfigDict(strict=True, frozen=True)

    name: str
    normalized_score: float


class RegimeObservationResponse(BaseModel):
    """One EOD regime observation whose close is visible before cutoff."""

    model_config = ConfigDict(strict=True, frozen=True)

    observed_at: date
    score: float
    label: Literal["bull", "bear", "neutral"]
    position_ratio: float
    indicators: list[RegimeIndicatorResponse]


class RegimeTransitionResponse(BaseModel):
    """One label transition between consecutive eligible observations."""

    model_config = ConfigDict(strict=True, frozen=True)

    observed_at: date
    from_label: Literal["bull", "bear", "neutral"]
    to_label: Literal["bull", "bear", "neutral"]


class RegimeDiagnosticsResponse(BaseModel):
    """PIT-safe regime diagnostics and their complete immutable evidence identity."""

    model_config = ConfigDict(strict=True, frozen=True)

    snapshot_id: str
    snapshot_manifest_hash: str
    dataset_id: str
    source_snapshot_ids: list[str]
    builder_version: str
    known_at_policy: str
    benchmark_instrument_id: int
    start_date: date
    end_date: date
    knowledge_cutoff: date
    model_id: str
    lookback_observations: int
    bear_threshold: float
    bull_threshold: float
    bars_input_id: str
    bars_content_hash: str
    bars_schema_hash: str
    current: RegimeObservationResponse
    observations: list[RegimeObservationResponse]
    transitions: list[RegimeTransitionResponse]


class MarketContextDriverResponse(BaseModel):
    """One ordered contribution to the current market regime."""

    model_config = ConfigDict(strict=True, frozen=True)

    name: str
    category: str
    contribution: float
    direction: Literal["supportive", "pressuring", "neutral"]


class MarketContextMetricResponse(BaseModel):
    """One observed market fact with direct immutable evidence lineage."""

    model_config = ConfigDict(strict=True, frozen=True)

    name: str
    category: Literal["a_share", "style", "global", "rates", "fx", "commodity", "macro"]
    value: float
    unit: str
    trend: Literal["rising", "falling", "flat", "mixed", "unknown"]
    freshness: Literal["fresh", "stale", "missing"]
    evidence_ref: str


class MarketContextImpactResponse(BaseModel):
    """One deterministic implication for a downstream decision domain."""

    model_config = ConfigDict(strict=True, frozen=True)

    target_domain: Literal["industry", "selection", "portfolio", "risk"]
    target: str
    direction: Literal["supportive", "pressuring", "neutral"]
    rationale_driver: str


class MarketContextResponse(BaseModel):
    """Exact PIT market context shared by Markets, Today, and Agent."""

    model_config = ConfigDict(strict=True, frozen=True)

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: list[str]
    source_snapshot_set_id: str
    status: Literal["ready", "degraded", "blocked"]
    feature_set_id: str
    feature_version: str
    regime_label: Literal["risk_on", "balanced", "risk_off"] | None
    regime_score: float | None
    drivers: list[MarketContextDriverResponse]
    metrics: list[MarketContextMetricResponse]
    impacts: list[MarketContextImpactResponse]
    missing_inputs: list[str]
    data_conflicts: list[str]
    uncertainties: list[str]
    evidence_refs: list[str]


def to_bar(row: dict[str, Any]) -> Bar:
    """
    将数据库行转换为 Bar 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, open, high, low,
             close, volume, amount, turnover_rate 等字段

    Returns:
        Bar 模型实例

    """
    return Bar(
        instrument_id=row["instrument_id"],
        trade_date=format_date(row["trade_date"]) or "",
        open=format_float(row["open"]) or 0.0,
        high=format_float(row["high"]) or 0.0,
        low=format_float(row["low"]) or 0.0,
        close=format_float(row["close"]) or 0.0,
        volume=format_float(row["volume"]) or 0.0,
        amount=format_float(row["amount"]) or 0.0,
        turnover_rate=format_float(row.get("turnover_rate")),
    )


def to_bar_list(df: pl.DataFrame) -> list[Bar]:
    """
    将 DataFrame 转换为 Bar 列表.

    Args:
        df: 包含 K 线数据的 DataFrame

    Returns:
        Bar 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Bar] = []
    for row in df.to_dicts():
        result.append(to_bar(row))

    return result


__all__ = [
    "Adjustment",
    "Bar",
    "BarsQuery",
    "MarketContextDriverResponse",
    "MarketContextImpactResponse",
    "MarketContextMetricResponse",
    "MarketContextResponse",
    "RegimeDiagnosticsResponse",
    "RegimeIndicatorResponse",
    "RegimeObservationResponse",
    "RegimeTransitionResponse",
    "to_bar",
    "to_bar_list",
]
