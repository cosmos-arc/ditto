"""
全量回补 Flow。

该模块实现历史数据回补功能：
- 支持日期范围回补
- 支持并行回补
- 支持断点续传
- 失败隔离
"""

from typing import TYPE_CHECKING

from prefect import flow
from pydantic import BaseModel

from ditto_port.jobs.flows.helpers import create_ingestion_context
from ditto_port.services.ingestion.backfill import BackfillManager

if TYPE_CHECKING:
    pass


class BackfillFlowResult(BaseModel):
    """回补 Flow 结果。"""

    dataset: str
    start_date: str
    end_date: str
    total_dates: int
    success_count: int
    skipped_count: int
    failed_count: int
    message: str = ""


@flow(name="backfill", description="全量数据回补流程")
def backfill_flow(  # noqa: PLR0913
    dataset: str,
    start_date: str,
    end_date: str,
    source: str = "tushare",
    data_root: str = "data",
    parallel: int = 1,
    chunk_size: int = 10,
    resume_from: str | None = None,
    skip_existing: bool = False,
) -> dict[str, object]:
    """
    全量数据回补流程。

    该流程支持：
    1. 指定日期范围回补
    2. 并行回补以提高效率
    3. 断点续传（resume_from）
    4. 跳过已存在数据（skip_existing）

    Args:
        dataset: 数据集名称（如 "stock_daily"）
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        source: 数据源名称
        data_root: DataHub 根目录
        parallel: 并行度，默认为 1（串行）
        chunk_size: 分块大小，用于进度追踪
        resume_from: 从指定日期恢复回补
        skip_existing: 是否跳过已存在的数据

    Returns:
        回补结果字典

    """
    with create_ingestion_context(data_root=data_root, source=source) as (
        hub,
        coordinator,
    ):
        # 创建回补管理器
        backfill_manager = BackfillManager(
            coordinator=coordinator,
            calendar_store=hub.calendar_store,
            ingestion_log_store=hub.ingestion_log,
        )

        # 处理 resume_from
        if resume_from:
            start_date = resume_from

        # 执行回补
        result = backfill_manager.backfill_range(
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        )

        return {
            "dataset": result.dataset,
            "start_date": start_date,
            "end_date": end_date,
            "total_dates": result.total_dates,
            "success_count": result.success_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "message": f"回补完成: {result.success_count}/{result.total_dates} 成功",
        }


@flow(name="backfill-missing", description="回补缺失数据")
def backfill_missing_flow(
    dataset: str,
    source: str = "tushare",
    data_root: str = "data",
    parallel: int = 1,
) -> dict[str, object]:
    """
    回补缺失数据流程。

    该流程自动检测并回补缺失的交易日数据。

    Args:
        dataset: 数据集名称
        source: 数据源名称
        data_root: DataHub 根目录
        parallel: 并行度

    Returns:
        回补结果字典

    """
    with create_ingestion_context(data_root=data_root, source=source) as (
        hub,
        coordinator,
    ):
        # 创建回补管理器
        backfill_manager = BackfillManager(
            coordinator=coordinator,
            calendar_store=hub.calendar_store,
            ingestion_log_store=hub.ingestion_log,
        )

        # 执行回补
        result = backfill_manager.backfill_missing(
            dataset=dataset,
            parallel=parallel,
        )

        return {
            "dataset": result.dataset,
            "total_dates": result.total_dates,
            "success_count": result.success_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "message": f"回补缺失完成: {result.success_count}/{result.total_dates} 成功"
            if result.total_dates > 0
            else "没有缺失数据",
        }
