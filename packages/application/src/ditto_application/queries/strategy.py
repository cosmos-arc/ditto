"""Strategy query facade — 封装 StrategyCatalogReader 只读查询."""

from __future__ import annotations

from ditto_strategy.contracts import StrategyCatalogReader

from ditto_application.contracts import StrategySpecInfo, to_spec_info

__all__ = ["StrategyQueryFacade"]


class StrategyQueryFacade:
    """
    策略只读查询 facade.

    封装 StrategyCatalogReader，对外只暴露 App DTO。
    """

    def __init__(self, catalog_service: StrategyCatalogReader) -> None:
        self._service = catalog_service

    def list_specs(self) -> list[StrategySpecInfo]:
        """列出所有策略（最新版本）."""
        return [to_spec_info(r) for r in self._service.list_specs()]

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecInfo | None:
        """获取策略详情，version=None 返回最新版本."""
        record = self._service.get_spec(strategy_id, version)
        return to_spec_info(record) if record is not None else None

    def get_active_published(self, strategy_id: str) -> StrategySpecInfo | None:
        """
        获取 governance active pointer 指向的 published payload.

        生产读取（R1/EOD）的唯一入口：无 active pointer 返回 None，
        由调用方走 NO_ACTIVE_STRATEGY fail-closed。
        """
        record = self._service.get_active_published(strategy_id)
        return to_spec_info(record, status="active") if record is not None else None

    def get_latest_published(self, strategy_id: str) -> StrategySpecInfo | None:
        """
        获取活动 published 版本，忽略更新的草稿.

        .. deprecated:: R3
            生产读取应改用 :meth:`get_active_published`。
        """
        record = self._service.get_latest_published(strategy_id)
        return to_spec_info(record) if record is not None else None

    def list_latest_published(self) -> list[StrategySpecInfo]:
        """列出每个策略的活动 published 版本."""
        return [to_spec_info(r) for r in self._service.list_latest_published()]
