"""Instrument code query facade 基类。"""

from __future__ import annotations

import polars as pl
from ditto_data.services.market_service import MarketService


class InstrumentCodeQueryFacade:
    """
    通过 code 映射查询行情数据的基类。

    子类通过 ``_code_to_instrument_id`` 和 ``_instrument_id_to_code``
    属性提供具体的映射表。
    """

    def __init__(self, market_service: MarketService, *, asset_class: str) -> None:
        self._service = market_service
        self._asset_class = asset_class

    def get_all_instrument_ids(self) -> list[int]:
        """获取所有品种的 instrument_id 列表。"""
        return list(self._code_to_instrument_id.values())

    def code_to_instrument_id(self, code: str) -> int:
        """将品种代码转换为 instrument_id。"""
        return self._code_to_instrument_id[code]

    def instrument_id_to_code(self, instrument_id: int) -> str | None:
        """将 instrument_id 转换为品种代码，不存在返回 None。"""
        return self._instrument_id_to_code.get(instrument_id)

    def list_bars(
        self,
        *,
        instrument_ids: list[int],
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> pl.DataFrame:
        """查询 K 线数据。"""
        return self._service.list_bars(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            asset_class=self._asset_class,
            limit=limit,
        )

    @property
    def _code_to_instrument_id(self) -> dict[str, int]:
        raise NotImplementedError

    @property
    def _instrument_id_to_code(self) -> dict[int, str]:
        raise NotImplementedError
