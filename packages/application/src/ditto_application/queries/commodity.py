"""Commodity query facade — 封装 Commodity/VIX 映射和 MarketService.list_bars."""

from __future__ import annotations

from ditto_data.models.source_codes import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from ditto_data.services.market_service import MarketService

from ditto_application.queries._instrument_code_facade import InstrumentCodeQueryFacade

__all__ = ["CommodityQueryFacade"]

# 合并 commodity 和 VIX 映射
_COMBINED_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    **COMMODITY_CODE_TO_INSTRUMENT_ID,
    **VIX_CODE_TO_INSTRUMENT_ID,
}

# 反向映射: instrument_id -> code
_INSTRUMENT_ID_TO_CODE = {v: k for k, v in _COMBINED_CODE_TO_INSTRUMENT_ID.items()}


class CommodityQueryFacade(InstrumentCodeQueryFacade):
    """
    Commodity 域查询 facade.

    封装 Commodity/VIX 代码映射和 MarketService.list_bars，
    隐藏代码映射和资产类别过滤等内部细节。
    """

    def __init__(self, market_service: MarketService) -> None:
        super().__init__(market_service, asset_class="commodity")

    def get_valid_codes(self) -> set[str]:
        """
        获取所有有效的商品/VIX 品种代码.

        Returns:
            品种代码集合（合并 commodity 和 VIX）

        """
        return set(_COMBINED_CODE_TO_INSTRUMENT_ID.keys())

    @property
    def _code_to_instrument_id(self) -> dict[str, int]:
        return _COMBINED_CODE_TO_INSTRUMENT_ID

    @property
    def _instrument_id_to_code(self) -> dict[int, str]:
        return _INSTRUMENT_ID_TO_CODE
