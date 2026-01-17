"""
CLI 本地执行器.

封装 IngestionCoordinator 和 BackfillManager，为 CLI 命令提供统一执行接口。
"""

from typing import Any

from ditto_datahub.hub import DataHub

from ditto_port.services.ingestion.backfill import BackfillManager
from ditto_port.services.ingestion.coordinator import IngestionCoordinator


class CLIExecutor:
    """CLI 本地执行器，封装 IngestionCoordinator 和 BackfillManager."""

    def __init__(self, app_ctx: Any) -> None:
        """
        初始化 CLIExecutor.

        Args:
            app_ctx: 应用上下文，包含 hub 和 source 属性

        """
        self._app_ctx = app_ctx
        self._hub: DataHub = app_ctx.hub
        self._source = app_ctx.source

        self._coordinator = IngestionCoordinator(
            hub=self._hub,
            source=self._source,
        )

        self._backfill_manager = BackfillManager(
            coordinator=self._coordinator,
            calendar_store=self._hub.calendar_store,
            ingestion_log_store=self._hub.ingestion_log,
        )

    def ingest_daily(
        self, dataset: str, trade_date: str, force: bool = False
    ) -> dict[str, Any]:
        """
        执行单日摄取.

        Args:
            dataset: 数据集名称
            trade_date: 交易日期 (YYYY-MM-DD)
            force: 是否强制重新摄取

        Returns:
            包含摄取结果的字典

        """
        result = self._coordinator.ingest_date(dataset, trade_date, force)
        return {
            "dataset": dataset,
            "trade_date": trade_date,
            "status": result.status,
            "row_count": result.row_count,
            "message": result.message,
            "error": result.error,
        }

    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
    ) -> dict[str, Any]:
        """
        执行日期范围回补.

        Args:
            dataset: 数据集名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            parallel: 并行度

        Returns:
            包含回补结果的字典

        """
        result = self._backfill_manager.backfill_range(
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        )
        return {
            "dataset": dataset,
            "total_dates": result.total_dates,
            "success_count": result.success_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
        }
