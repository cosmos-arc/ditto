"""交易策略配置模型."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TradingSettings(BaseModel):
    """交易策略配置。"""

    model_config = ConfigDict(extra="ignore")

    default_universe: str = Field(default="csi300", description="默认标的池")
    max_position_pct: float = Field(default=0.1, description="单只标的最大仓位百分比")
    risk_free_rate: float = Field(default=0.025, description="无风险利率")
    benchmark: str = Field(default="000300.SH", description="基准指数代码")
    cost_bps: float = Field(default=3.0, description="交易成本 (基点)")
    slippage_bps: float = Field(default=1.0, description="滑点成本 (基点)")
    trading_calendar_start: str = Field(
        default="2020-01-01",
        description="交易日历起始日期 (YYYY-MM-DD)",
    )
    trading_calendar_end: str = Field(
        default="2030-12-31",
        description="交易日历结束日期 (YYYY-MM-DD)",
    )

    @field_validator("max_position_pct")
    @classmethod
    def validate_max_position_pct(cls, v: float) -> float:
        """max_position_pct 必须在 (0, 1] 范围内。"""
        if v <= 0 or v > 1:
            raise ValueError("max_position_pct 必须在 (0, 1] 范围内")
        return v


__all__ = ["TradingSettings"]
