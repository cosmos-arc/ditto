"""全量回补管理器 — BackfillManager."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from ditto_data.models.ingestion import BackfillResult, IngestionResult
from ditto_data.services.metadata_service import MetadataService
from ditto_platform.foundation import logger

from ditto_application.process.ingestion.coordinator import IngestionCoordinator
from ditto_application.process.ingestion.result_handler import count_results


class BackfillManager:
    """全量回补管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        metadata_service: MetadataService,
        ingestion_log_service: IngestionLogService,
    ) -> None:
        """
        初始化 BackfillManager。

        Args:
            coordinator: IngestionCoordinator 实例。
            metadata_service: MetadataService 实例。
            ingestion_log_service: IngestionLogService 实例。

        """
        self._coordinator = coordinator
        self._metadata_service = metadata_service
        self._ingestion_log_service = ingestion_log_service

    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
    ) -> BackfillResult:
        """
        全量回补指定日期范围。

        Args:
            dataset: 数据集名称。
            start_date: 开始日期 (YYYY-MM-DD)。
            end_date: 结束日期 (YYYY-MM-DD)。
            parallel: 并行度，默认为 1（串行）。

        Returns:
            BackfillResult: 回补结果。

        """
        logger.info(
            "开始回补数据",
            event="backfill_range_start",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        )

        trade_dates = self._metadata_service.list_trading_days(start_date, end_date)
        if not trade_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        # 按年份分组，并发度上限为 min(parallel, 年份数)
        # 注意：同一年内的日期仍会并行执行，依赖 FileLockManager 避免冲突
        dates_by_year: defaultdict[str, list[str]] = defaultdict(list)
        for trade_date in trade_dates:
            dates_by_year[trade_date[:4]].append(trade_date)

        result = self._execute_backfill(
            dataset=dataset,
            trade_dates=trade_dates,
            parallel=parallel,
            log_event="backfill_range_complete",
        )
        return result

    def backfill_missing(
        self,
        dataset: str,
        source: str = "tushare",
        parallel: int = 1,
    ) -> BackfillResult:
        """
        回补缺失的交易日。

        Args:
            dataset: 数据集名称。
            source: 数据源标识符（默认: "tushare"）。
            parallel: 并行度，默认为 1（串行）。

        Returns:
            BackfillResult: 回补结果。

        """
        logger.info(
            "开始回补缺失数据",
            event="backfill_missing_start",
            dataset=dataset,
            parallel=parallel,
        )

        first_date = self._metadata_service.get_first_trading_day()
        last_date = self._metadata_service.get_last_trading_day()
        if not first_date or not last_date:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        all_trade_dates = self._metadata_service.list_trading_days(
            first_date,
            last_date,
        )
        if not all_trade_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        ingested_dates = self._ingestion_log_service.list_ingested_dates(
            dataset,
            source,
        )
        missing_dates = set(all_trade_dates) - set(ingested_dates)
        if not missing_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        sorted_missing_dates = sorted(missing_dates)

        return self._execute_backfill(
            dataset=dataset,
            trade_dates=sorted_missing_dates,
            parallel=parallel,
            log_event="backfill_missing_complete",
        )

    def _execute_backfill(
        self,
        dataset: str,
        trade_dates: list[str],
        parallel: int,
        log_event: str,
    ) -> BackfillResult:
        """
        执行回补：并行/串行摄取 + 结果统计。

        Args:
            dataset: 数据集名称。
            trade_dates: 待回补的交易日期列表。
            parallel: 并行度。
            log_event: 完成日志事件名。

        Returns:
            BackfillResult: 回补结果。

        """
        results: list[IngestionResult] = []

        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures: dict[Future[IngestionResult], str] = {
                    executor.submit(self._coordinator.ingest_date, dataset, d): d
                    for d in trade_dates
                }
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for trade_date in trade_dates:
                results.append(self._coordinator.ingest_date(dataset, trade_date))

        counts = count_results(results)
        backfill_result = BackfillResult(
            dataset=dataset,
            total_dates=len(trade_dates),
            success_count=counts.success,
            skipped_count=counts.skipped,
            failed_count=counts.failed,
            results=tuple(results),
        )

        logger.info(
            "回补完成",
            event=log_event,
            dataset=dataset,
            total_dates=backfill_result.total_dates,
            success_count=backfill_result.success_count,
            skipped_count=backfill_result.skipped_count,
            failed_count=backfill_result.failed_count,
        )

        return backfill_result


__all__ = ["BackfillManager"]
