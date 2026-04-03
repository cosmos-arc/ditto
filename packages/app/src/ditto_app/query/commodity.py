"""Commodity query facade — 封装 Commodity/VIX 映射和 MarketService.list_bars."""

from __future__ import annotations

import polars as pl
from ditto_data.models.source_codes import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from ditto_data.services.market_service import MarketService

__all__ = ["CommodityQueryFacade"]

# 合并 commodity 和 VIX 映射
_COMBINED_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    **COMMODITY_CODE_TO_INSTRUMENT_ID,
    **VIX_CODE_TO_INSTRUMENT_ID,
}

# 反向映射: instrument_id -> code
_INSTRUMENT_ID_TO_CODE = {v: k for k, v in _COMBINED_CODE_TO_INSTRUMENT_ID.items()}


class CommodityQueryFacade:
    """
    Commodity 域查询 facade.

    封装 Commodity/VIX 代码映射和 MarketService.list_bars，
    隐藏代码映射和资产类别过滤等内部细节。
    """

    def __init__(self, market_service: MarketService) -> None:
        self._service = market_service

    def get_valid_codes(self) -> set[str]:
        """
        获取所有有效的商品/VIX 品种代码.

        Returns:
            品种代码集合（合并 commodity 和 VIX）

        """
        return set(_COMBINED_CODE_TO_INSTRUMENT_ID.keys())

    def get_all_instrument_ids(self) -> list[int]:
        """
        获取所有商品/VIX 品种的 instrument_id.

        Returns:
            instrument_id 列表

        """
        return list(_COMBINED_CODE_TO_INSTRUMENT_ID.values())

    def code_to_instrument_id(self, code: str) -> int:
        """
        将品种代码转换为 instrument_id.

        Args:
            code: 品种代码（如 "COMMOD_WTI"）

        Returns:
            instrument_id

        Raises:
            KeyError: 品种代码不存在

        """
        return _COMBINED_CODE_TO_INSTRUMENT_ID[code]

    def instrument_id_to_code(self, instrument_id: int) -> str | None:
        """
        将 instrument_id 转换为品种代码.

        Args:
            instrument_id: 标的 ID

        Returns:
            品种代码，不存在返回 None

        """
        return _INSTRUMENT_ID_TO_CODE.get(instrument_id)

    def list_bars(
        self,
        *,
        instrument_ids: list[int],
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> pl.DataFrame:
        """
        查询 Commodity K 线数据.

        Args:
            instrument_ids: 标的 ID 列表
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            limit: 返回数量限制

        Returns:
            K 线数据 DataFrame

        """
        return self._service.list_bars(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            asset_class="commodity",
            limit=limit,
        )
