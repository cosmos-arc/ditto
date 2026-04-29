"""回测运行统一查询 — 跨策略列表查询与过滤."""

from __future__ import annotations

from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_data.services.strategy.strategy_run_service import StrategyRunLifecycleStore

__all__ = ["RunReadModel"]


class RunReadModel:
    """回测运行读模型 — 跨策略列表查询与过滤."""

    def __init__(self, run_service: StrategyRunLifecycleStore) -> None:
        self._service = run_service

    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StrategyRunRecord]:
        """查询运行记录，支持多维度过滤."""
        return self._service.list_runs(
            strategy_id=strategy_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """获取单个运行记录."""
        return self._service.get_run(run_id)
