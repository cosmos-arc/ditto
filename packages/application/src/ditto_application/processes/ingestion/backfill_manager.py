"""全量回补管理器 — BackfillManager."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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
from ditto_application.processes.ingestion.dataset_registry import (
    INDEX_WEIGHT_UNIVERSE,
)
from ditto_application.processes.ingestion.result_handler import count_results
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)

# 修补扫描上界时区：A 股数据车道以上海日历日定义"已过去的会话"。
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def repair_scan_horizon(now: datetime | None = None) -> str:
    """
    修补扫描的最新日期：上海昨日（ISO YYYY-MM-DD）。

    ``get_last_trading_day`` 返回的是日历表末端——交易日历提前数年
    发布，未来会话的数据尚未存在、对空洞修补恒为假阳性（#613 部署
    后 nightly repair 曾扫到 2027-12-31，每晚 ~1.1k 请求纯烧配额并
    灌 FAIL 账）。当日数据在 21:55 EOD 波前同样未发布，留给次日扫描。
    """
    current = now or datetime.now(_SHANGHAI)
    if current.tzinfo is None:
        # 朴素时钟在非上海宿主上会被 astimezone 当作宿主本地时间，
        # 得出错误的日界——拒绝而不是猜。
        raise AppProcessError(
            "repair_scan_horizon requires a timezone-aware datetime",
            details={"reason": "REPAIR_HORIZON_NAIVE_DATETIME"},
        )
    return (current.astimezone(_SHANGHAI).date() - timedelta(days=1)).isoformat()


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
        *,
        include_complete: bool = False,
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
            include_complete: 连 COMPLETE 检查点的 chunk 一并重拉（行级
                补数通道，#575：完成度台账是日期级事实，掩盖行级缺口；
                重拉幂等去重，用于缺口修复而非常规回补）。

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
            include_complete=include_complete,
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

    def backfill_index_weight(
        self,
        start_date: str,
        end_date: str,
        parallel: int = 1,
        source: str = "tushare",
    ) -> BackfillResult:
        """
        按权重端点服务宇宙逐指数回补月度权重（#196）.

        index_weight 是月度观察事实，逐日全宇宙回补不可行（trading_days
        规划 × 178 指数/日）；改为把权重服务宇宙（宽基+风格 23 指数）
        解析为 instrument_ids 走 instrument_range 年度 chunk——每指数每年
        一次区间请求，checkpoint 断点续传。
        """
        codes = list(INDEX_WEIGHT_UNIVERSE)
        resolved = self._metadata_service.instrument.resolve_instrument_ids_batch(
            identifiers=codes,
            source=source,
            asof=None,
        )
        unresolved = sorted(set(codes) - resolved.keys())
        if unresolved:
            logger.warning(
                "index_weight 回补宇宙存在未注册指数, 已跳过",
                event="index_weight_universe_unresolved",
                codes=unresolved,
            )
        instrument_ids = tuple(sorted(set(resolved.values())))
        if not instrument_ids:
            # 空 instrument_ids 的契约语义是"按日期全市场回补"——恰好落回
            # 逐日全宇宙的不可行路径，fail fast 而非静默退化。
            raise AppProcessError(
                "index_weight universe resolved to zero instruments",
                field="instrument_ids",
                value=unresolved,
            )
        return self.backfill_range(
            "index_weight",
            start_date,
            end_date,
            parallel=parallel,
            source=source,
            instrument_ids=instrument_ids,
        )

    def backfill_missing(
        self,
        dataset: str,
        source: str = "tushare",
        parallel: int = 1,
        *,
        force_refresh_days: int = 0,
    ) -> BackfillResult:
        """
        回补缺失的交易日。

        Args:
            dataset: 数据集名称。
            source: 数据源标识符（默认: "tushare"）。
            parallel: 并行度，默认为 1（串行）。
            force_refresh_days: 追加近 N 个交易日的 force 重取（#625 晚发布
                数据集）。晚发布源的 T 日数据在当日 EOD 波常为空帧或部分行
                （如 fund_share 2026-10-26 仅 765/1807 行），SUCCESS/部分行
                被 skip 决策固化后空洞扫描不可见——近窗重取以同业务键幂等
                合并，直到源侧补全后自然收敛。0 表示不启用。

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
        # 日历表末端是未来数年——钳到上海昨日，未来会话不进扫描
        # （假空洞会以 EMPTY_DATA_UNEXPECTED 每晚重试烧配额）。
        last_date = min(last_date, repair_scan_horizon())

        plan = self._bootstrap_planner.plan(
            dataset_id=dataset,
            source=source,
            start_date=first_date,
            end_date=last_date,
            include_complete=True,
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
        trailing_dates: set[str] = set()
        if force_refresh_days > 0:
            trailing_dates = self._trailing_trading_days(
                force_refresh_days, horizon=last_date
            )
        if not missing_dates and not trailing_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        # force 只作用于晚发布近窗（#625 correctness W2）：近窗日被 SUCCESS/
        # 空帧或部分行观察固化，必须绕过 skip 决策；普通空洞（无 SUCCESS
        # 日志）不 force 也会正常摄取，历史值不受 KEEP_LAST 覆写。
        plain_dates = sorted(missing_dates - trailing_dates)
        refresh_dates = sorted(trailing_dates)
        results: list[IngestionResult] = []
        if plain_dates:
            results.extend(
                self._execute_backfill(
                    dataset=dataset,
                    trade_dates=plain_dates,
                    parallel=parallel,
                    log_event="backfill_missing_complete",
                ).results
            )
        if refresh_dates:
            results.extend(
                self._execute_backfill(
                    dataset=dataset,
                    trade_dates=refresh_dates,
                    parallel=parallel,
                    log_event="backfill_missing_complete",
                    force=True,
                ).results
            )
        counts = count_results(results)
        return BackfillResult(
            dataset=dataset,
            total_dates=len(plain_dates) + len(refresh_dates),
            success_count=counts.success,
            skipped_count=counts.skipped,
            failed_count=counts.failed,
            results=tuple(results),
        )

    def _trailing_trading_days(self, count: int, *, horizon: str) -> set[str]:
        """
        扫描上界往前的近 N 个交易日（#625 晚发布近窗）.

        horizon 复用调用方已钳制到上海昨日的上界，避免同一次调用内
        双读时钟在午夜跨越时窗口漂移（correctness I3）。
        """
        # 多取 30 个日历日保证覆盖长假后仍 ≥N 个交易日（黄金周 ≤8 天）。
        lookback_start = (date.fromisoformat(horizon) - timedelta(days=30)).isoformat()
        days = self._metadata_service.calendar.list_trading_days(
            lookback_start, horizon
        )
        return set(days[-count:])

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
        *,
        force: bool = False,
    ) -> BackfillResult:
        """
        执行回补：并行/串行摄取 + 结果统计。

        Args:
            dataset: 数据集名称。
            trade_dates: 待回补的交易日期列表。
            parallel: 并行度。
            log_event: 完成日志事件名。
            force: 绕过 skip 决策强制重取（晚发布近窗刷新用）。

        Returns:
            BackfillResult: 回补结果。

        """
        results: list[IngestionResult] = []

        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures: dict[Future[IngestionResult], str] = {
                    executor.submit(self._coordinator.ingest_date, dataset, d, force): d
                    for d in trade_dates
                }
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for trade_date in trade_dates:
                results.append(
                    self._coordinator.ingest_date(dataset, trade_date, force)
                )

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
