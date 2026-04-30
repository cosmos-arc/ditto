"""回测查询编排 facade — 统一回测结果、成交、审计查询入口."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_data.services.audit.execution_audit_service import ExecutionAuditService
from ditto_data.services.strategy.backtest_artifact_reader import (
    BacktestArtifactReaderProtocol,
)
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.query.artifact_utils import find_artifact
from ditto_application.query.backtest_trade import BacktestTradeQueryFacade, TradeRecord
from ditto_application.query.run import RunReadModel

__all__ = ["BacktestQueryFacade", "RunSummary", "to_run_summary"]


@dataclass(frozen=True)
class RunSummary:
    """App 层运行摘要 DTO — 切断 interfaces -> data 直接依赖."""

    run_id: str
    strategy_id: str
    strategy_version: str = ""
    mode: str = "backtest"
    status: str = ""
    started_at: str = ""
    completed_at: str = ""
    error_message: str = ""
    parent_run_id: str = ""
    progress_pct: float = 0.0
    current_step: str = ""
    completed_days: int = 0
    total_days: int = 0
    config_json: str = ""


def to_run_summary(record: StrategyRunRecord) -> RunSummary:
    """将 Data Record 转换为 App DTO."""
    return RunSummary(
        run_id=record.run_id,
        strategy_id=record.strategy_id,
        strategy_version=record.strategy_version,
        mode=record.mode,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error_message=record.error_message,
        parent_run_id=record.parent_run_id,
        progress_pct=record.progress_pct,
        current_step=record.current_step,
        completed_days=record.completed_days,
        total_days=record.total_days,
        config_json=record.config_json,
    )


_REPORT_FILENAME = "backtest_report.json"


def _build_path(base: str, filename: str) -> str:
    """拼接产物目录与文件名，返回字符串路径."""
    return str(Path(base) / filename)


class BacktestQueryFacade:
    """
    回测查询编排 facade -- 统一回测结果、成交、审计查询.

    纯编排层，将查询请求委托给各子 facade / service.
    """

    def __init__(
        self,
        trade_facade: BacktestTradeQueryFacade,
        run_model: RunReadModel,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        artifact_reader: BacktestArtifactReaderProtocol,
    ) -> None:
        self._trade_facade = trade_facade
        self._run_model = run_model
        self._audit_service = audit_service
        self._artifact_service = artifact_service
        self._artifact_reader = artifact_reader

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
    ) -> list[RunSummary]:
        """查询运行记录列表."""
        records = self._run_model.list_runs(
            strategy_id=strategy_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return [to_run_summary(r) for r in records]

    def get_run(self, run_id: str) -> RunSummary | None:
        """获取单个运行记录."""
        record = self._run_model.get_run(run_id)
        return to_run_summary(record) if record is not None else None

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

        record = find_artifact(self._artifact_service, run_id)
        if record is None:
            return None

        report_path = _build_path(record.file_path, _REPORT_FILENAME)
        return self._artifact_reader.read_json(report_path)

    # ------------------------------------------------------------------
    # NAV 序列查询
    # ------------------------------------------------------------------

    def get_nav_series(self, run_id: str) -> list[dict[str, object]]:
        """获取回测 NAV 序列 (从 nav.parquet)."""
        record = find_artifact(self._artifact_service, run_id)
        if record is None:
            return []

        nav_path = _build_path(record.file_path, "nav.parquet")
        df = self._artifact_reader.read_parquet(nav_path)
        return df.to_dicts() if df is not None else []

    # ------------------------------------------------------------------
    # 基准数据
    # ------------------------------------------------------------------

    def get_benchmark_return(self, run_id: str) -> float | None:
        """从 alpha_stats 提取基准年化收益率 (CAPM: Rb = (R - alpha) / beta)."""
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
        """基准 NAV 序列 (当前未持久化，始终返回 None)."""
        return None
