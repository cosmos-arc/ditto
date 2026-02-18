"""
黄金数据集配置模型。

Golden Dataset 用于数据质量对账的精选标的子集。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

__all__ = [
    "AssetType",
    "DynamicConfig",
    "GoldenDatasetOptions",
    "GoldenDatasetSpec",
    "TickerSpec",
]


class AssetType(str, Enum):
    """资产类型枚举。"""

    STOCK = "stock"  # A股股票
    ETF = "etf"  # ETF基金
    INDEX_MARKET = "index_market"  # 市场指数
    INDEX_SW = "index_sw"  # 申万行业指数
    INDEX_STYLE = "index_style"  # 风格指数


class TickerSpec(BaseModel):
    """单个标的配置。"""

    ticker: str = Field(..., description="标的代码（裸代码），如 600519")
    name: str = Field(default="", description="标的名称")
    asset_type: AssetType = Field(default=AssetType.STOCK, description="资产类型")
    exchange: str | None = Field(
        default=None, description="交易所代码（内部规范），如 XSHG、XSHE、SW"
    )
    tags: list[str] = Field(default_factory=list, description="标签列表")

    # 内部交易所 -> Tushare 交易所映射
    _EXCHANGE_MAPPING: dict[str, str] = {
        "XSHG": "SH",  # 上海证券交易所
        "XSHE": "SZ",  # 深圳证券交易所
        "SW": "SI",  # 申万指数
    }

    @property
    def source_ticker(self) -> str:
        """获取数据源 ticker（内部 exchange 转换为数据源格式）。"""
        if not self.exchange:
            return self.ticker
        # 转换为数据源交易所格式
        source_exchange = self._EXCHANGE_MAPPING.get(self.exchange, self.exchange)
        return f"{self.ticker}.{source_exchange}"

    @property
    def standard_ticker(self) -> str:
        """获取内部标准格式（ticker.exchange）。"""
        if self.exchange:
            return f"{self.ticker}.{self.exchange}"
        return self.ticker


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
    ticker_specs: list[TickerSpec] = Field(
        default_factory=list, description="完整标的配置列表"
    )
    options: GoldenDatasetOptions = Field(default_factory=GoldenDatasetOptions)

    @field_validator("tickers", mode="before")
    @classmethod
    def validate_tickers(cls, v: Any) -> list[str]:
        """
        验证并处理 tickers 列表。

        支持两种格式：
        - 简单字符串：["600519", "300750"]
        - 完整对象：[{ticker: "600519", name: "贵州茅台", asset_type: "stock"}]

        对于完整对象格式，仅提取 ticker 字段到 tickers 列表。
        完整数据通过 ticker_specs 字段访问。
        """
        if not v:
            return []
        if not isinstance(v, list):
            raise ValueError(f"tickers must be a list, got {type(v).__name__}: {v!r}")

        tickers: set[str] = set()
        items: list[Any] = v  # type: ignore[assignment]

        for item in items:
            if isinstance(item, str):
                # 简单字符串格式
                ticker = item.strip()
                if ticker:
                    tickers.add(ticker)
            elif isinstance(item, Mapping):
                # 完整对象格式
                item_dict: dict[str, Any] = dict(item)  # type: ignore[arg-type]
                ticker_value: Any = item_dict.get("ticker", "")
                if ticker_value and isinstance(ticker_value, str):
                    tickers.add(ticker_value.strip())

        return sorted(tickers)

    @field_validator("ticker_specs", mode="before")
    @classmethod
    def parse_ticker_specs(cls, v: Any) -> list[TickerSpec]:
        """从 tickers 字段解析完整的 TickerSpec 列表。"""
        if not isinstance(v, list):
            return []

        specs: list[TickerSpec] = []
        items: list[Any] = v  # type: ignore[assignment]
        for item in items:
            if isinstance(item, Mapping) and "ticker" in item:
                try:
                    # 转换为 dict 以兼容 Pydantic
                    spec_dict: dict[str, Any] = dict(item)  # type: ignore[assignment]
                    specs.append(TickerSpec(**spec_dict))
                except Exception:
                    logger.debug("忽略无效的 TickerSpec: %s", repr(item))  # type: ignore[reportUnknownArgumentType]

        return specs

    @property
    def is_enabled(self) -> bool:
        """是否启用。"""
        return self.options.enabled and len(self.tickers) > 0

    def get_tickers(self) -> list[str]:
        """获取有效 ticker 列表。"""
        return self.tickers if self.is_enabled else []

    def get_ticker_spec(self, ticker: str) -> TickerSpec | None:
        """获取指定 ticker 的完整配置。"""
        for spec in self.ticker_specs:
            if spec.ticker == ticker:
                return spec
        return None

    def get_tickers_by_asset_type(self, asset_type: AssetType) -> list[str]:
        """按资产类型获取 ticker 列表。"""
        return [
            spec.ticker for spec in self.ticker_specs if spec.asset_type == asset_type
        ]

    def get_source_tickers(self, asset_type: AssetType | None = None) -> list[str]:
        """
        获取数据源 ticker 列表。

        Args:
            asset_type: 可选的资产类型过滤

        Returns:
            数据源 ticker 列表（如 ["000001.SH", "600519.SH"]）

        """
        tickers: list[str] = []
        for spec in self.ticker_specs:
            if asset_type and spec.asset_type != asset_type:
                continue
            tickers.append(spec.source_ticker)
        return tickers
