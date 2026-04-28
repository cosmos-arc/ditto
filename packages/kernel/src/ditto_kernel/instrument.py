"""Instrument subdomain — 资产分类、交易所、标的参数。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["AssetClass", "Exchange", "InstrumentIngestParams"]


class AssetClass(StrEnum):
    """资产类型枚举。"""

    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    BOND = "bond"
    FUND = "fund"


class Exchange(StrEnum):
    """统一交易所枚举（ISO 10383 MIC 简化版）。"""

    XSHE = "XSHE"  # 深圳证券交易所
    XSHG = "XSHG"  # 上海证券交易所
    XBSE = "XBSE"  # 北京证券交易所


@dataclass(frozen=True)
class InstrumentIngestParams:
    """
    按标的摄取的参数。

    标识符三选一，优先级: instrument_id > standard_ticker > ticker。
    """

    instrument_id: int | None = None
    standard_ticker: str | None = None
    ticker: str | None = None
    start_date: str = ""
    end_date: str = ""

    @property
    def has_identifier(self) -> bool:
        """是否存在有效标识符。"""
        return (
            self.instrument_id is not None
            or self.standard_ticker is not None
            or self.ticker is not None
        )

    @property
    def primary_identifier(self) -> str | None:
        """按优先级返回主标识符（instrument_id > standard_ticker > ticker）。"""
        if self.instrument_id is not None:
            return str(self.instrument_id)
        return self.standard_ticker or self.ticker
