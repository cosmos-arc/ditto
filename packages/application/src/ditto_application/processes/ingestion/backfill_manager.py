"""全量回补管理器 — BackfillManager."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionResult,
)
from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_platform.foundation import logger

from ditto_application.catalog_freshness import completed_covering_snapshot
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.bootstrap_planner import (
    BootstrapChunk,
    BootstrapPlan,
    BootstrapPlanner,
)
from ditto_application.processes.ingestion.result_handler import count_results
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)


class BackfillManager:
    """全量回补管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinatorLike,
        metadata_service: MetadataService,
        bootstrap_planner: BootstrapPlanner | None = None,
        *,
        snapshot_reader: ProviderSnapshotReader | None = None,
        lifecycle_reader: PartitionLifecycleReader | None = None,
    ) -> None:
        """
        初始化 BackfillManager。

        Args:
            coordinator: 摄取协调器端口。
            metadata_service: MetadataService 实例。
            bootstrap_planner: 日程和分块感知的持久回补规划器。
            snapshot_reader: provider snapshot 读端口,与 lifecycle_reader 一起
                构成空洞发现的完成事实。
            lifecycle_reader: 分区生命周期读端口。

        """
        self._coordinator = coordinator
        self._metadata_service = metadata_service
        self._bootstrap_planner = bootstrap_planner or BootstrapPlanner(
            metadata_service=metadata_service
        )
        self._snapshot_reader = snapshot_reader
        self._lifecycle_reader = lifecycle_reader

    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
        source: str = "tushare",
        instrument_ids: tuple[int, ...] = (),
    ) -> BackfillResult:
        """
        全量回补指定日期范围。

        Args:
            dataset: 数据集名称。
            start_date: 开始日期 (YYYY-MM-DD)。
            end_date: 结束日期 (YYYY-MM-DD)。
            parallel: 并行度，默认为 1（串行）。
            source: 数据源标识符（默认: "tushare"）。
            instrument_ids: 可选的显式标的范围；为空时按日期全市场回补。

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

        plan = self._bootstrap_planner.plan(
            dataset_id=dataset,
            source=source,
            start_date=start_date,
            end_date=end_date,
            instrument_ids=instrument_ids,
        )
        if not plan.chunks:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        result = self._execute_plan(
            plan=plan,
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

        first_date = self._metadata_service.calendar.get_first_trading_day()
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

        plan = self._bootstrap_planner.plan(
            dataset_id=dataset,
            source=source,
            start_date=first_date,
            end_date=last_date,
        )
        expected_dates = _planned_dates(plan)
        if not expected_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        evidenced_dates = self._completed_snapshot_dates(
            dataset=dataset,
            source=source,
            expected_dates=expected_dates,
        )
        missing_dates = set(expected_dates) - evidenced_dates
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

    def _completed_snapshot_dates(
        self,
        *,
        dataset: str,
        source: str,
        expected_dates: list[str],
    ) -> set[str]:
        """
        期望日期里已被 completed snapshot 覆盖的日期(#394 完成事实)。

        没有完成事实端口时退化为空集——所有期望日期都视为空洞,
        由下游 skip 决策兜底,避免把未证实的日期静默视为完整。
        """
        if self._snapshot_reader is None or self._lifecycle_reader is None:
            return set()
        return {
            day
            for day in expected_dates
            if completed_covering_snapshot(
                self._snapshot_reader,
                self._lifecycle_reader,
                dataset=dataset,
                source=source,
                trade_date=day,
            )
            is not None
        }

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

    def _execute_plan(
        self,
        *,
        plan: BootstrapPlan,
        parallel: int,
        log_event: str,
    ) -> BackfillResult:
        """Execute planner chunks atomically when the coordinator supports it."""
        requires_instrument_chunks = any(
            chunk.execution_mode == "instrument_range" for chunk in plan.chunks
        )
        supported_chunk_method = (
            getattr(type(self._coordinator), "ingest_planned_instrument_chunk", None)
            if requires_instrument_chunks
            else getattr(type(self._coordinator), "ingest_chunk", None)
        )
        if not callable(supported_chunk_method):
            return self._execute_backfill(
                dataset=plan.dataset_id,
                trade_dates=_planned_dates(plan),
                parallel=parallel,
                log_event=log_event,
            )

        def execute(typed_chunk: BootstrapChunk) -> IngestionResult:
            if typed_chunk.execution_mode == "instrument_range":
                if len(typed_chunk.instrument_ids) != 1:
                    raise AppProcessError(
                        "instrument bootstrap chunk must own exactly one instrument"
                    )
                return self._coordinator.ingest_planned_instrument_chunk(
                    plan.dataset_id,
                    chunk_id=typed_chunk.chunk_id,
                    params=InstrumentIngestParams(
                        instrument_id=typed_chunk.instrument_ids[0],
                        start_date=typed_chunk.request_start,
                        end_date=typed_chunk.request_end,
                    ),
                )
            return self._coordinator.ingest_chunk(
                plan.dataset_id,
                chunk_id=typed_chunk.chunk_id,
                request_start=typed_chunk.request_start,
                request_end=typed_chunk.request_end,
                partition_dates=typed_chunk.partition_dates,
            )

        results: list[IngestionResult] = []
        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = [executor.submit(execute, chunk) for chunk in plan.chunks]
                results.extend(future.result() for future in as_completed(futures))
        else:
            results.extend(execute(chunk) for chunk in plan.chunks)
        counts = count_results(results)
        result = BackfillResult(
            dataset=plan.dataset_id,
            total_dates=plan.expected_partition_count,
            success_count=counts.success,
            skipped_count=counts.skipped,
            failed_count=counts.failed,
            results=tuple(results),
        )
        logger.info(
            "回补完成",
            event=log_event,
            dataset=plan.dataset_id,
            total_dates=result.total_dates,
            chunk_count=len(plan.chunks),
            success_count=result.success_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
        )
        return result


def _planned_dates(plan: BootstrapPlan) -> list[str]:
    """Flatten deterministic planner chunks into unique ordered partitions."""
    return sorted(
        {
            partition_date
            for chunk in plan.chunks
            for partition_date in chunk.partition_dates
        }
    )


__all__ = ["BackfillManager"]
