"""
CLI 本地执行器.

封装 IngestionCoordinator 和 BackfillManager，为 CLI 命令提供统一执行接口。

使用工厂模式创建依赖，支持运行时参数（如 source_name）。
"""

from contextlib import contextmanager
from typing import Any

from ditto_datahub import DataHub
from ditto_datahub.models import Source

from ditto_port.services.ingestion import create_coordinator
from ditto_port.services.ingestion.backfill import BackfillManager
from ditto_port.services.ingestion.coordinator import IngestionCoordinator


class CLIExecutor:
    """CLI 本地执行器，封装 IngestionCoordinator 和 BackfillManager."""

    def __init__(
        self,
        hub: DataHub,
        source_name: str | Source = Source.TUSHARE,
    ) -> None:
        """
        初始化 CLIExecutor.

        Args:
            hub: DataHub 实例
            source_name: 数据源名称，默认为 tushare

        """
        self._hub = hub
        self._source_name = (
            source_name if isinstance(source_name, Source) else Source(source_name)
        )
        # 使用延迟初始化 - coordinator 和 backfill_manager 在需要时创建
        self._coordinator: IngestionCoordinator | None = None
        self._backfill_manager: BackfillManager | None = None

    @property
    def coordinator(self):
        """获取 coordinator（延迟初始化）."""
        if self._coordinator is None:
            raise RuntimeError(
                "Coordinator not initialized. "
                "Use with CLIExecutor.create() context manager."
            )
        return self._coordinator

    @property
    def backfill_manager(self):
        """获取 backfill_manager（延迟初始化）."""
        if self._backfill_manager is None:
            raise RuntimeError(
                "BackfillManager not initialized. "
                "Use with CLIExecutor.create() context manager."
            )
        return self._backfill_manager

    @classmethod
    @contextmanager
    def create(cls, hub: DataHub, source_name: str | Source = Source.TUSHARE):
        """
        创建 CLIExecutor 实例并初始化依赖.

        Args:
            hub: DataHub 实例
            source_name: 数据源名称

        Yields:
            CLIExecutor: 已初始化的执行器实例

        """
        executor = cls(hub=hub, source_name=source_name)
        with create_coordinator(hub=hub, source_name=source_name) as coordinator:
            executor._coordinator = coordinator
            backfill_manager = BackfillManager(
                coordinator=coordinator,
                hub=hub,
            )
            executor._backfill_manager = backfill_manager
            yield executor

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
        result = self.coordinator.ingest_date(dataset, trade_date, force)
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
        result = self.backfill_manager.backfill_range(
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
