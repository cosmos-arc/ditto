"""
全量回补 Flow。

该模块实现历史数据回补功能：
- 支持日期范围回补
- 支持并行回补
- 支持断点续传
- 失败隔离
- 支持按标的回填
"""

from prefect import flow
from pydantic import BaseModel

from ditto_port.models import InstrumentIngestParams
from ditto_port.registry import create_ingestion_bundle
from ditto_port.services.ingestion.backfill import BackfillManager


class BackfillFlowConfig(BaseModel):
    """回补 Flow 配置。"""

    dataset: str
    start_date: str
    end_date: str
    source: str = "tushare"
    data_root: str = "data"
    parallel: int = 1
    chunk_size: int = 10
    resume_from: str | None = None
    skip_existing: bool = False


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
def backfill_flow(config: BackfillFlowConfig) -> dict[str, object]:
    """
    全量数据回补流程。

    该流程支持：
    1. 指定日期范围回补
    2. 并行回补以提高效率
    3. 断点续传（resume_from）
    4. 跳过已存在数据（skip_existing）

    Args:
        config: 回补配置对象

    Returns:
        回补结果字典

    """
    # 处理 resume_from
    start_date = config.resume_from or config.start_date

    with create_ingestion_bundle(source=config.source) as bundle:
        # 创建回补管理器
        backfill_manager = BackfillManager(
            coordinator=bundle.coordinator,
            metadata_service=bundle.metadata_service,
            ingestion_log_service=bundle.ingestion_log_service,
        )

        # 执行回补
        result = backfill_manager.backfill_range(
            dataset=config.dataset,
            start_date=start_date,
            end_date=config.end_date,
            parallel=config.parallel,
        )

        return {
            "dataset": result.dataset,
            "start_date": start_date,
            "end_date": config.end_date,
            "total_dates": result.total_dates,
            "success_count": result.success_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "message": (f"回补完成: {result.success_count}/{result.total_dates} 成功"),
        }


@flow(name="backfill-missing", description="回补缺失数据")
def backfill_missing_flow(
    dataset: str,
    source: str = "tushare",
    parallel: int = 1,
) -> dict[str, object]:
    """
    回补缺失数据流程。

    该流程自动检测并回补缺失的交易日数据。

    Args:
        dataset: 数据集名称
        source: 数据源名称
        parallel: 并行度

    Returns:
        回补结果字典

    """
    with create_ingestion_bundle(source=source) as bundle:
        # 创建回补管理器
        backfill_manager = BackfillManager(
            coordinator=bundle.coordinator,
            metadata_service=bundle.metadata_service,
            ingestion_log_service=bundle.ingestion_log_service,
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
            "message": (
                f"回补缺失完成: {result.success_count}/{result.total_dates} 成功"
                if result.total_dates > 0
                else "没有缺失数据"
            ),
        }


# ============================================================================
# 按标的回填 Flows
# ============================================================================


class InstrumentBackfillConfig(BaseModel):
    """按标的回填配置。"""

    source_ticker: str
    dataset: str
    start_date: str
    end_date: str
    force: bool = False
    source: str = "tushare"


class InstrumentBackfillResult(BaseModel):
    """按标的回填结果。"""

    dataset: str
    source_ticker: str
    start_date: str
    end_date: str
    status: str
    row_count: int
    message: str


@flow(name="backfill-single-instrument", description="单只标的数据回填")
def backfill_single_instrument_flow(
    source_ticker: str,
    dataset: str,
    start_date: str,
    end_date: str,
    force: bool = False,
    source: str = "tushare",
) -> dict[str, object]:
    """
    单只标的数据回填流程。

    Args:
        source_ticker: 数据源代码 (如 "000001.SZ")
        dataset: 数据集名称 (如 "stock_daily")
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        force: 是否强制覆盖已有数据
        source: 数据源名称

    Returns:
        回填结果字典

    """
    with create_ingestion_bundle(source=source) as bundle:
        # 将 source_ticker 转换为 standard_ticker
        transformer = bundle.exchange_transformers.get(source)
        standard_ticker = transformer.to_standard(source_ticker)

        params = InstrumentIngestParams(
            standard_ticker=standard_ticker,
            start_date=start_date,
            end_date=end_date,
        )
        result = bundle.coordinator.ingest_by_instrument(dataset, params, force)

        return {
            "dataset": result.dataset,
            "source_ticker": source_ticker,
            "start_date": start_date,
            "end_date": end_date,
            "status": result.status,
            "row_count": result.row_count,
            "message": result.message or f"回填完成: {result.status}",
        }


@flow(name="backfill-multiple-instruments", description="批量标的数据回填")
def backfill_multiple_instruments_flow(
    source_tickers: list[str],
    dataset: str,
    start_date: str,
    end_date: str,
    force: bool = False,
    source: str = "tushare",
) -> list[dict[str, object]]:
    """
    批量标的数据回填流程（串行）。

    Args:
        source_tickers: 数据源代码列表
        dataset: 数据集名称
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        force: 是否强制覆盖已有数据
        source: 数据源名称

    Returns:
        回填结果列表

    """
    results: list[dict[str, object]] = []
    for ticker in source_tickers:
        result = backfill_single_instrument_flow(
            source_ticker=ticker,
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            force=force,
            source=source,
        )
        results.append(result)
    return results
