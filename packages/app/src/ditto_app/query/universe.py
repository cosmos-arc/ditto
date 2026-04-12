"""Universe query facade — 封装 MetadataService universe 只读查询."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_data.services.metadata_service import MetadataService

__all__ = ["UniverseQueryFacade"]


class UniverseQueryFacade:
    """Universe 只读查询 facade."""

    def __init__(self, metadata_service: MetadataService) -> None:
        self._service = metadata_service

    def list_universes(self, universe_type: str | None = None) -> list[dict[str, Any]]:
        """列出所有 universe（可选按类型过滤）."""
        df: pl.DataFrame = self._service._universe_reader.list_universes(  # pyright: ignore[reportPrivateUsage]
            universe_type,
        )
        if df.is_empty():
            return []
        return df.to_dicts()

    def get_universe_detail(self, universe_id: str) -> dict[str, Any] | None:
        """获取 universe 详情."""
        return self._service._universe_reader.get_universe(universe_id)  # pyright: ignore[reportPrivateUsage]

    def get_members(self, universe_id: str, asof: str | None = None) -> list[int]:
        """获取 universe 成分股 instrument_id 列表（PIT 安全）."""
        return self._service.get_universe(universe_id, asof)
