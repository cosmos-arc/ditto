"""Strategy query facade — 封装 StrategyCatalogReader 只读查询."""

from __future__ import annotations

from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.governance.protocols import StrategyVersionStateReader
from ditto_strategy.models import StrategySpecRecord

from ditto_application.contracts import StrategySpecInfo, to_spec_info

__all__ = ["StrategyQueryFacade"]


class StrategyQueryFacade:
    """
    策略只读查询 facade.

    封装 StrategyCatalogReader，对外只暴露 App DTO。``StrategySpecInfo.status``
    由 governance version state 投影（active/draft/review/published/...）；
    无 state reader 注入时过渡回退 ``record.status``（commit #3c-3 移除字段后
    必须注入 reader）。
    """

    def __init__(
        self,
        catalog_service: StrategyCatalogReader,
        version_state_reader: StrategyVersionStateReader | None = None,
    ) -> None:
        self._service = catalog_service
        self._version_state_reader = version_state_reader

    def list_specs(self) -> list[StrategySpecInfo]:
        """列出所有策略（最新版本）."""
        return [self._to_info(r) for r in self._service.list_specs()]

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecInfo | None:
        """获取策略详情，version=None 返回最新版本."""
        record = self._service.get_spec(strategy_id, version)
        return self._to_info(record) if record is not None else None

    def get_active_published(self, strategy_id: str) -> StrategySpecInfo | None:
        """
        获取 governance active pointer 指向的 published payload.

        生产读取（R1/EOD）的唯一入口：无 active pointer 返回 None，
        由调用方走 NO_ACTIVE_STRATEGY fail-closed。
        """
        record = self._service.get_active_published(strategy_id)
        return to_spec_info(record, status="active") if record is not None else None

    def _to_info(self, record: StrategySpecRecord) -> StrategySpecInfo:
        return to_spec_info(record, status=self._resolve_status(record))

    def _resolve_status(self, record: StrategySpecRecord) -> str:
        if self._version_state_reader is None:
            return record.status
        state = self._version_state_reader.get_state(record.strategy_id, record.version)
        if state is None:
            return record.status
        return str(state.state)
