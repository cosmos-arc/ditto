"""
每日增量摄取 Flow。

该模块实现 T0 → T1 → T3 的依赖编排：
- T0: 元数据任务（calendar, stock_basic, etf_basic）
- T1: 增量任务（etf_daily, stock_daily, adj_factor, fund_adj）
- T3: 数据质量检查

Flow 功能：
- 非交易日跳过逻辑
- 汇总所有结果
- 触发 DQC 检查

使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefect import flow, task

from ditto_port.ingestion.config.datasets import (
    Dataset,
    TaskTier,
    get_datasets_by_tier,
    get_parallel_datasets,
)
from ditto_port.ingestion.tasks import (
    create_ingest_task_t0,
    create_ingest_task_t1_adj,
    create_ingest_task_t1_bars,
)

if TYPE_CHECKING:
    pass


@task(name="check_trading_day")
def check_trading_day(trade_date: str, data_root: str) -> bool:
    """
    检查指定日期是否为交易日。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        data_root: DataHub 根目录

    Returns:
        是否为交易日

    """
    from ditto_datahub import DataHub  # noqa: PLC0415

    hub = DataHub(data_root=data_root)
    try:
        return hub.calendar.is_trading_day(trade_date)
    finally:
        hub.close()


@flow(name="daily-ingestion", description="每日增量数据摄取流程")
def daily_ingestion_flow(
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
    force: bool = False,
) -> dict[str, object]:
    """
    每日增量数据摄取流程。

    该流程实现 T0 → T1 → T3 的依赖编排：
    1. 验证交易日
    2. 执行 T0 元数据任务（并行）
    3. 执行 T1 增量任务（并行，依赖 T0）
    4. 触发 T3 数据质量检查

    使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        source: 数据源名称
        data_root: DataHub 根目录
        force: 是否强制重新摄取

    Returns:
        摄取结果字典，包含：
        - trade_date: 交易日期
        - skipped: 是否跳过（非交易日）
        - reason: 跳过原因
        - t0_results: T0 任务结果
        - t1_results: T1 任务结果
        - dqc_results: DQC 检查结果
        - summary: 汇总统计

    """
    # 1. 检查交易日
    is_trading = check_trading_day(trade_date=trade_date, data_root=data_root)

    # 如果非交易日，直接返回
    if not is_trading:
        return {
            "trade_date": trade_date,
            "skipped": True,
            "reason": "非交易日",
            "t0_results": {},
            "t1_results": {},
            "dqc_results": {},
            "summary": {
                "trade_date": trade_date,
                "total_tasks": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
            },
        }

    # 2. 提交 T0 任务（并行执行）
    t0_datasets = get_datasets_by_tier(TaskTier.T0_META)
    t0_futures: list[Any] = []
    for dataset in t0_datasets:
        t0_task = create_ingest_task_t0(dataset)
        future = t0_task.submit(
            trade_date=trade_date,
            source=source,
            data_root=data_root,
            force=force,
        )
        t0_futures.append(future)

    # 3. 提交 T1 任务（按依赖层级并行执行）
    # T1 数据集按依赖关系分层：
    # - Level 0: etf_daily, stock_daily (只依赖 T0)
    # - Level 1: adj_factor (依赖 stock_daily), fund_adj (依赖 etf_daily)
    t1_levels = get_parallel_datasets(TaskTier.T1_INCREMENTAL)
    t1_futures: list[Any] = []
    level_futures: list[list[Any]] = []

    for level_idx, level in enumerate(t1_levels):
        # 确定等待的任务：第一层等待 T0，后续层等待前面所有层
        if level_idx == 0:
            wait_for_futures = t0_futures
        else:
            # 收集前面所有层的 futures
            wait_for_futures_inner: list[Any] = []
            for prev_level in level_futures:
                wait_for_futures_inner.extend(prev_level)
            wait_for_futures = wait_for_futures_inner

        current_level_futures: list[Any] = []
        for dataset in level:
            # 根据数据集类型选择对应的 task 创建函数
            if dataset in [Dataset.ADJ_FACTOR, Dataset.FUND_ADJ]:
                task = create_ingest_task_t1_adj(dataset)
            else:
                task = create_ingest_task_t1_bars(dataset)

            future = task.submit(
                trade_date=trade_date,
                source=source,
                data_root=data_root,
                force=force,
                wait_for=wait_for_futures,
            )
            current_level_futures.append(future)
            t1_futures.append(future)

        # 记录本层的 futures，供后续层依赖
        level_futures.append(current_level_futures)

    # 4. 收集结果
    t0_results = {}
    for future in t0_futures:
        result = future.result()
        dataset_name = result.get("dataset", "unknown")
        t0_results[dataset_name] = result

    t1_results = {}
    for future in t1_futures:
        result = future.result()
        dataset_name = result.get("dataset", "unknown")
        t1_results[dataset_name] = result

    # 5. 触发 DQC（TODO: 待实现）
    dqc_results = {
        "trade_date": trade_date,
        "status": "skipped",
        "message": "DQC 检查待实现",
    }

    # 6. 汇总统计
    all_results = {**t0_results, **t1_results}
    success_count = sum(1 for r in all_results.values() if r.get("status") == "success")
    failed_count = sum(1 for r in all_results.values() if r.get("status") == "failed")
    skipped_count = sum(1 for r in all_results.values() if r.get("status") == "skipped")

    summary = {
        "trade_date": trade_date,
        "total_tasks": len(all_results),
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
    }

    return {
        "trade_date": trade_date,
        "skipped": False,
        "reason": None,
        "t0_results": t0_results,
        "t1_results": t1_results,
        "dqc_results": dqc_results,
        "summary": summary,
    }
