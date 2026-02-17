"""
黄金数据集配置模型。

Golden Dataset 用于数据质量对账的精选标的子集。
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, Field, field_validator

__all__ = ["GoldenDatasetOptions", "GoldenDatasetSpec"]


class GoldenDatasetOptions(BaseModel):
    """黄金数据集选项。"""

    enabled: bool = Field(default=True, description="是否启用黄金数据集过滤")
    dynamic: DynamicConfig | None = Field(default=None, description="动态标的配置")


class DynamicConfig(BaseModel):
    """动态标的配置（未来扩展）。"""

    include_new_stocks: bool = Field(default=False, description="纳入次新股")
    new_stock_days: int = Field(default=60, ge=1, le=365, description="新股天数")
    include_st: bool = Field(default=True, description="纳入 ST 股")
    include_suspended: bool = Field(default=False, description="纳入停牌股")


class GoldenDatasetSpec(BaseModel):
    """黄金数据集配置规范。"""

    description: str = Field(default="", description="配置描述")
    tickers: list[str] = Field(default_factory=list, description="ticker 列表")
    options: GoldenDatasetOptions = Field(default_factory=GoldenDatasetOptions)

    @field_validator("tickers", mode="before")
    @classmethod
    def validate_tickers(cls, v: Any) -> list[str]:
        """
        验证并处理 tickers 列表。

        - 拒绝非列表类型（常见 YAML 误写如 tickers: "600519"）
        - 去重并排序
        """
        if not v:
            return []
        if not isinstance(v, list):
            raise ValueError(f"tickers must be a list, got {type(v).__name__}: {v!r}")
        items = cast(list[Any], v)
        return sorted({str(t).strip() for t in items if t and str(t).strip()})

    @property
    def is_enabled(self) -> bool:
        """是否启用。"""
        return self.options.enabled and len(self.tickers) > 0

    def get_tickers(self) -> list[str]:
        """获取有效 ticker 列表。"""
        return self.tickers if self.is_enabled else []
