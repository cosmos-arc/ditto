"""Backfill manager for historical data backfill operations."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from ditto_foundation import logger
from pydantic import BaseModel

from ditto_port.services.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionResult,
)

if TYPE_CHECKING:
    from ditto_datahub.stores.calendar_store import CalendarStore
    from ditto_datahub.stores.ingestion_log import IngestionLogStore


class BackfillResult(BaseModel):
    """回补结果统计。"""

    dataset: str
    total_dates: int
    success_count: int
    skipped_count: int
    failed_count: int
    results: list[IngestionResult]


class BackfillManager:
    """全量回补管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        calendar_store: "CalendarStore",
        ingestion_log_store: "IngestionLogStore",
    ) -> None:
        """
        初始化 BackfillManager。

        Args:
            coordinator: IngestionCoordinator 实例。
            calendar_store: CalendarStore 实例。
            ingestion_log_store: IngestionLogStore 实例。

        """
        self._coordinator = coordinator
        self._calendar_store = calendar_store
        self._ingestion_log_store = ingestion_log_store

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

        # 获取日期范围内的所有交易日
        trade_dates = self._calendar_store.get_range(start_date, end_date)

        if not trade_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=[],
            )

        results: list[IngestionResult] = []

        if parallel > 1:
            # 年份级并行，年内串行（避免文件锁冲突）
            dates_by_year = defaultdict(list)
            for trade_date in trade_dates:
                year = trade_date[:4]  # 提取年份
                dates_by_year[year].append(trade_date)

            with ThreadPoolExecutor(
                max_workers=min(parallel, len(dates_by_year))
            ) as executor:
                futures = {}
                for _year, year_dates in dates_by_year.items():
                    # 每个年份串行处理
                    for date in year_dates:
                        future = executor.submit(
                            self._coordinator.ingest_date,
                            dataset,
                            date,
                        )
                        futures[future] = date

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
        else:
            # 串行执行
            for trade_date in trade_dates:
                result = self._coordinator.ingest_date(dataset, trade_date)
                results.append(result)

        # 统计结果
        success_count = sum(1 for r in results if r.status == "success")
        skipped_count = sum(1 for r in results if r.status == "skipped")
        failed_count = sum(1 for r in results if r.status == "failed")

        backfill_result = BackfillResult(
            dataset=dataset,
            total_dates=len(trade_dates),
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            results=results,
        )

        logger.info(
            "回补完成",
            event="backfill_range_complete",
            dataset=dataset,
            total_dates=backfill_result.total_dates,
            success_count=backfill_result.success_count,
            skipped_count=backfill_result.skipped_count,
            failed_count=backfill_result.failed_count,
        )

        return backfill_result

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

        # 获取日历的完整日期范围
        first_date = self._calendar_store.get_first_trading_day()
        last_date = self._calendar_store.get_last_trading_day()

        if not first_date or not last_date:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=[],
            )

        # 获取所有交易日
        all_trade_dates = self._calendar_store.get_range(first_date, last_date)

        if not all_trade_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=[],
            )

        # 获取已摄取的日期
        ingested_dates = self._ingestion_log_store.get_ingested_dates(dataset, source)

        # 计算缺失的日期
        missing_dates = set(all_trade_dates) - set(ingested_dates)

        if not missing_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=[],
            )

        # 按日期排序
        sorted_missing_dates = sorted(missing_dates)

        # 回补缺失的日期
        results: list[IngestionResult] = []

        if parallel > 1:
            # 并行执行
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(
                        self._coordinator.ingest_date, dataset, trade_date
                    ): trade_date
                    for trade_date in sorted_missing_dates
                }

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
        else:
            # 串行执行
            for trade_date in sorted_missing_dates:
                result = self._coordinator.ingest_date(dataset, trade_date)
                results.append(result)

        # 统计结果
        success_count = sum(1 for r in results if r.status == "success")
        skipped_count = sum(1 for r in results if r.status == "skipped")
        failed_count = sum(1 for r in results if r.status == "failed")

        backfill_result = BackfillResult(
            dataset=dataset,
            total_dates=len(sorted_missing_dates),
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            results=results,
        )

        logger.info(
            "缺失数据回补完成",
            event="backfill_missing_complete",
            dataset=dataset,
            total_dates=backfill_result.total_dates,
            success_count=backfill_result.success_count,
            skipped_count=backfill_result.skipped_count,
            failed_count=backfill_result.failed_count,
        )

        return backfill_result
