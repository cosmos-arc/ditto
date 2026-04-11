"""回测查询编排 facade — 统一回测结果、成交、审计查询入口."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import polars as pl
from ditto_data.models.strategy import StrategyArtifactRecord
from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_data.services.audit.execution_audit_service import ExecutionAuditService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_app.query.backtest_trade import BacktestTradeQueryFacade, TradeRecord
from ditto_app.query.run import RunReadModel

__all__ = ["BacktestQueryFacade"]

_REPORT_FILENAME = "backtest_report.json"


class BacktestQueryFacade:
    """
    回测查询编排 facade — 统一回测结果、成交、审计查询.

    纯编排层，将查询请求委托给各子 facade / service.
    """

    def __init__(
        self,
        trade_facade: BacktestTradeQueryFacade,
        run_model: RunReadModel,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
    ) -> None:
        self._trade_facade = trade_facade
        self._run_model = run_model
        self._audit_service = audit_service
        self._artifact_service = artifact_service

    # ------------------------------------------------------------------
    # 运行记录查询
    # ------------------------------------------------------------------

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
        """查询运行记录列表."""
        return self._run_model.list_runs(
            strategy_id=strategy_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """获取单个运行记录."""
        return self._run_model.get_run(run_id)

    # ------------------------------------------------------------------
    # 成交查询
    # ------------------------------------------------------------------

    def get_trades(
        self,
        *,
        run_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TradeRecord]:
        """查询回测成交明细."""
        return self._trade_facade.query_trades(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # 审计查询
    # ------------------------------------------------------------------

    def get_audit(
        self,
        run_id: str,
        *,
        record_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询审计记录."""
        return self._audit_service.query(
            run_id,
            record_type=record_type,
            start_date=start_date,
            end_date=end_date,
        )

    # ------------------------------------------------------------------
    # 回测报告
    # ------------------------------------------------------------------

    def get_report(self, run_id: str) -> dict[str, Any] | None:
        """获取回测报告元数据 (从 backtest_report.json)."""
        run = self._run_model.get_run(run_id)
        if run is None:
            return None

        record = self._find_artifact(run_id)
        if record is None:
            return None

        report_path = Path(record.file_path) / _REPORT_FILENAME
        if not report_path.exists():
            return None

        return orjson.loads(report_path.read_bytes())

    # ------------------------------------------------------------------
    # NAV 序列查询
    # ------------------------------------------------------------------

    def get_nav_series(self, run_id: str) -> list[dict[str, object]]:
        """获取回测 NAV 序列 (从 nav.parquet)."""
        record = self._find_artifact(run_id)
        if record is None:
            return []

        nav_path = Path(record.file_path) / "nav.parquet"
        if not nav_path.exists():
            return []

        df = pl.read_parquet(nav_path)
        return df.to_dicts()

    # ------------------------------------------------------------------
    # 基准数据
    # ------------------------------------------------------------------

    def get_benchmark_return(self, run_id: str) -> float | None:
        """从 alpha_stats 中提取基准年化收益率 (CAPM: Rb = (R - alpha) / beta)."""
        report = self.get_report(run_id)
        if report is None:
            return None

        alpha_stats = report.get("alpha_stats")
        if alpha_stats is None:
            return None

        try:
            beta = alpha_stats.get("beta")
            if not isinstance(beta, (int, float)) or beta == 0:
                return None
            ann_return = alpha_stats.get("annualized_return", 0.0)
            alpha_ann = alpha_stats.get("alpha_annualized", 0.0) or 0.0
            return (float(ann_return) - float(alpha_ann)) / float(beta)
        except (AttributeError, TypeError, ValueError):
            return None

    def get_benchmark_nav_series(self, run_id: str) -> list[tuple[str, float]] | None:
        """基准 NAV 序列（当前未持久化，始终返回 None）."""
        return None

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _find_artifact(self, run_id: str) -> StrategyArtifactRecord | None:
        """从产物列表中查找匹配 run_id 的第一条记录."""
        artifacts = self._artifact_service.list_artifacts()
        for record in artifacts:
            if record.run_id == run_id:
                return record
        return None
