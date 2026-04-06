"""
黄金数据集配置模型。

Golden Dataset 用于数据质量对账的精选标的子集。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

__all__ = [
    "AssetType",
    "DynamicConfig",
    "GoldenDatasetOptions",
    "GoldenDatasetSpec",
    "TickerSpec",
]


class AssetType(StrEnum):
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

    @staticmethod
    def _parse_tickers_list(
        items: list[Any],
    ) -> tuple[set[str], list[TickerSpec]]:
        """解析 tickers 列表，返回 (ticker_set, specs)。"""
        tickers_set: set[str] = set()
        specs: list[TickerSpec] = []

        for item in items:
            if isinstance(item, str):
                ticker = item.strip()
                if ticker:
                    tickers_set.add(ticker)
            elif isinstance(item, Mapping):
                item_dict: dict[str, Any] = cast(dict[str, Any], item)
                ticker_val: Any = item_dict.get("ticker", "")
                if ticker_val and isinstance(ticker_val, str):
                    tickers_set.add(ticker_val.strip())
                    try:
                        specs.append(TickerSpec(**item_dict))
                    except (TypeError, ValueError):
                        msg = repr(cast(object, item))
                        logger.debug("忽略无效的 TickerSpec: %s", msg)

        return tickers_set, specs

    @model_validator(mode="before")
    @classmethod
    def parse_tickers_data(cls, data: Any) -> Any:
        """
        从 tickers 字段同时解析 ticker 字符串和 TickerSpec 对象。

        支持两种格式：
        - 简单字符串：["600519", "300750"]
        - 完整对象：[{ticker: "600519", name: "贵州茅台", asset_type: "stock"}]
        """
        if not isinstance(data, dict):
            return data

        data_dict: dict[str, Any] = cast(dict[str, Any], data)
        tickers_raw: Any = data_dict.get("tickers", [])

        # 处理 None：转换为空列表
        if tickers_raw is None:
            data_dict["tickers"] = []
            return data_dict

        # 处理非列表类型
        if not isinstance(tickers_raw, list):
            return data_dict

        # 解析 tickers 列表
        items_list: list[Any] = cast(list[Any], tickers_raw)
        tickers_set, specs = cls._parse_tickers_list(items_list)

        # 更新数据
        data_dict["tickers"] = sorted(tickers_set)
        # 如果没有已存在的 specs，则使用解析出的 specs
        if specs and not data_dict.get("ticker_specs"):
            data_dict["ticker_specs"] = specs

        return data_dict

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
