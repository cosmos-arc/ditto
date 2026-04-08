"""FX query facade — 封装 FX 映射和 MarketService.list_bars."""

from __future__ import annotations

from ditto_data.models.source_codes import FX_CODE_TO_INSTRUMENT_ID
from ditto_data.services.market_service import MarketService

from ditto_app.query._instrument_code_facade import InstrumentCodeQueryFacade

__all__ = ["FXQueryFacade"]

# 反向映射: instrument_id -> pair
_INSTRUMENT_ID_TO_PAIR = {v: k for k, v in FX_CODE_TO_INSTRUMENT_ID.items()}


class FXQueryFacade(InstrumentCodeQueryFacade):
    """
    FX 域查询 facade.

    封装 FX_CODE_TO_INSTRUMENT_ID 映射和 MarketService.list_bars，
    隐藏代码映射和资产类别过滤等内部细节。
    """

    def __init__(self, market_service: MarketService) -> None:
        super().__init__(market_service, asset_class="fx")

    def get_valid_pairs(self) -> set[str]:
        """
        获取所有有效的汇率品种代码.

        Returns:
            品种代码集合

        """
        return set(FX_CODE_TO_INSTRUMENT_ID.keys())

    def pair_to_instrument_id(self, pair: str) -> int:
        """
        将汇率品种代码转换为 instrument_id.

        Args:
            pair: 品种代码（如 "USDCNH.FXCM"）

        Returns:
            instrument_id

        Raises:
            KeyError: 品种代码不存在

        """
        return FX_CODE_TO_INSTRUMENT_ID[pair]

    def instrument_id_to_pair(self, instrument_id: int) -> str | None:
        """
        将 instrument_id 转换为汇率品种代码.

        Args:
            instrument_id: 标的 ID

        Returns:
            品种代码，不存在返回 None

        """
        return _INSTRUMENT_ID_TO_PAIR.get(instrument_id)

    @property
    def _code_to_instrument_id(self) -> dict[str, int]:
        return FX_CODE_TO_INSTRUMENT_ID

    @property
    def _instrument_id_to_code(self) -> dict[int, str]:
        return _INSTRUMENT_ID_TO_PAIR
