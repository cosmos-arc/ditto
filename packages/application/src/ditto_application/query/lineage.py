"""运行血统查询 — 提供 lineage chain 查询能力."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.services.strategy.strategy_run_service import StrategyRunLifecycleStore

from ditto_application.query.backtest import RunSummary, to_run_summary

__all__ = ["LineageChain", "LineageQueryFacade"]


@dataclass(frozen=True)
class LineageChain:
    """
    运行血统链.

    Attributes:
        runs: 血统链（原始运行 → ... → 当前运行，按时间正序）
        depth: 当前运行的重放深度（0 = 原始运行）

    """

    runs: tuple[RunSummary, ...]
    depth: int


class LineageQueryFacade:
    """运行血统查询 facade — 提供血统链查询."""

    def __init__(self, run_service: StrategyRunLifecycleStore) -> None:
        self._service = run_service

    def get_lineage(self, run_id: str) -> LineageChain | None:
        """获取运行血统链."""
        chain = self._service.list_lineage(run_id)
        if not chain:
            return None
        return LineageChain(
            runs=tuple(to_run_summary(r) for r in chain),
            depth=len(chain) - 1,
        )

    def list_replays(self, run_id: str) -> list[RunSummary]:
        """列出指定运行的所有直接重放记录."""
        return [to_run_summary(r) for r in self._service.list_replays(run_id)]
