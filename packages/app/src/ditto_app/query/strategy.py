"""Strategy query facade — 封装 StrategyCatalogService 只读查询."""

from __future__ import annotations

from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.services.strategy.strategy_catalog_service import StrategyCatalogService

__all__ = ["StrategyQueryFacade"]


class StrategyQueryFacade:
    """
    策略只读查询 facade.

    封装 StrategyCatalogService，对外只暴露原始参数和记录返回值。
    """

    def __init__(self, catalog_service: StrategyCatalogService) -> None:
        self._service = catalog_service

    def list_specs(self) -> list[StrategySpecRecord]:
        """列出所有策略（最新版本）."""
        return self._service.list_specs()

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """获取策略详情，version=None 返回最新版本."""
        return self._service.get_spec(strategy_id, version)
