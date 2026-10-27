"""
每日增量摄取 Flow。

该模块实现 T0 → T1 → T3 的依赖编排：
- T0: 元数据任务（calendar, stock_basic, etf_basic）
- T1: 增量任务（etf_daily, stock_daily, stock_status, adj_factor, fund_adj）
- T3: 数据质量检查（覆盖所有有 DQ 规则的数据集）

Flow 功能：
- 非交易日跳过逻辑
- 汇总所有结果
- 触发 DQC 检查

使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from itertools import chain
from typing import Any, cast
from zoneinfo import ZoneInfo

from ditto_application.config import (
    IngestionScope,
    TaskTier,
    get_datasets_by_tier,
    get_parallel_datasets,
    resolve_ingestion_scope,
)
from ditto_application.processes.ingestion.result_handler import count_results
from ditto_platform.foundation import logger
from prefect import flow, task
from prefect.futures import PrefectFuture

from ditto_apps.jobs.tasks import (
    create_ingest_task_t0,
    create_ingest_task_t1_adj,
    create_ingest_task_t1_bars,
    dq_batch_check,
)
from ditto_apps.jobs.tasks.dq_batch import run_dq_batch_check
from ditto_apps.jobs.tasks.dq_reconcile import (
    dq_reconcile_adj_factor,
    run_dq_reconcile_adj_factor,
)
from ditto_apps.jobs.tasks.fuyao_dump import fuyao_dump_adjustment_factors
from ditto_apps.jobs.tasks.t0_meta import run_ingest_dataset
from ditto_apps.registry import create_ingestion_bundle


def _collect_results(
    futures: list[PrefectFuture[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    """
    从 Prefect futures 收集结果字典。

    Args:
        futures: Prefect Future 对象列表

    Returns:
        以数据集名称为键的结果字典。如果结果中没有 'dataset' 字段，
        则使用 'unknown' 作为键。

    """
    return _index_results(future.result() for future in futures)


def _index_results(
    raw_results: Iterable[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """按 dataset 统一索引同步结果与 Prefect future 结果。"""
    results: dict[str, dict[str, object]] = {}
    for result in raw_results:
        dataset_name = cast(str, result.get("dataset", "unknown"))
        results[dataset_name] = result
    return results


def _dataset_value(dataset: object) -> str:
    value = getattr(dataset, "value", None)
    return value if isinstance(value, str) else ""


def _scheduled_run_date() -> str | None:
    """
    Prefect 定时触发的计划日（Asia/Shanghai 日历日）。

    非 flow 运行上下文（CLI/单测）返回 None。读取异常时告警并返回 None：
    调用方退回执行时墙钟——迟执行补跑会因此归属执行日而非计划日，
    该退化须在运行日志中可见（correctness #613 F2）。
    """
    try:
        from prefect.runtime import flow_run as runtime_flow_run  # noqa: PLC0415
    except Exception:  # pragma: no cover - prefect 缺失仅出现于极端裁剪环境
        return None
    try:
        scheduled = runtime_flow_run.scheduled_start_time
    except Exception as exc:
        logger.warning(
            "scheduled_start_time read failed; late run may fall back to "
            + "execution day",
            error=str(exc),
        )
        return None
    if scheduled is None:
        return None
    return scheduled.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def resolve_trade_date(trade_date: str) -> str:
    """
    空 trade_date 解析为计划运行日的 Asia/Shanghai 日历日。

    Prefect 3.6 部署参数对纯字符串原样透传（`{{ date }}` 不再运行时渲染），
    定时触发必须由 flow 运行时自取日期。优先取 scheduled_start_time：
    迟执行的补跑（worker 宕机恢复后）仍归属计划日；非 Prefect 上下文
    退回墙钟当日。显式传入的日期原样保留。
    """
    if trade_date:
        return trade_date
    scheduled_date = _scheduled_run_date()
    if scheduled_date is not None:
        return scheduled_date
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _daily_ingestion_scope(
    required_datasets: tuple[str, ...] | None,
) -> IngestionScope:
    """Select the full daily registry or one dependency-closed strategy scope."""
    if required_datasets is not None:
        return resolve_ingestion_scope(required_datasets)
    return IngestionScope(
        t0_datasets=tuple(get_datasets_by_tier(TaskTier.T0_META)),
        t1_levels=tuple(
            tuple(level) for level in get_parallel_datasets(TaskTier.T1_INCREMENTAL)
        ),
    )


def run_check_trading_day(trade_date: str) -> bool:
    """执行交易日判断业务，供 Prefect task 与同步 CLI 共用。"""
    with create_ingestion_bundle() as bundle:
        return bundle.metadata_facade.is_trading_day(trade_date)


@task(name="check_trading_day")
def check_trading_day(trade_date: str) -> bool:
    """
    检查指定日期是否为交易日。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)

    Returns:
        是否为交易日

    """
    return run_check_trading_day(trade_date)


def _skipped_ingestion_result(trade_date: str) -> dict[str, object]:
    """构造非交易日稳定结果。"""
    return {
        "trade_date": trade_date,
        "skipped": True,
        "reason": "非交易日",
        "t0_results": {},
        "t1_results": {},
        "dqc_results": {},
        "reconcile_results": {},
        "fuyao_dump": None,
        "summary": {
            "trade_date": trade_date,
            "total_tasks": 0,
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
        },
    }


def _completed_ingestion_result(
    *,
    trade_date: str,
    t0_results: dict[str, dict[str, object]],
    t1_results: dict[str, dict[str, object]],
    dqc_results: dict[str, Any],
    reconcile_results: dict[str, Any],
    fuyao_dump: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    由同一业务结果构造同步与 Prefect 返回契约.

    fuyao dump 刷新仅在 Prefect 例行链执行（sync/CLI 路径不触网）；
    None 表示本路径未运行 dump 任务。
    """
    all_results = {**t0_results, **t1_results}
    counts = count_results(all_results)
    return {
        "trade_date": trade_date,
        "skipped": False,
        "reason": None,
        "t0_results": t0_results,
        "t1_results": t1_results,
        "dqc_results": dqc_results,
        "reconcile_results": reconcile_results,
        "fuyao_dump": fuyao_dump,
        "summary": {
            "trade_date": trade_date,
            "total_tasks": len(all_results),
            "success_count": counts.success,
            "failed_count": counts.failed,
            "skipped_count": counts.skipped,
        },
    }


def run_daily_ingestion(
    trade_date: str = "",
    source: str = "tushare",
    force: bool = False,
    required_datasets: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """
    顺序执行每日摄取业务，可限制为策略依赖闭包。

    trade_date 为空时取 Asia/Shanghai 当日（定时触发路径）。

    仅同步执行 T0/T1/T3 业务函数与 adj_factor 对账；fuyao dump 例行刷新
    只在 Prefect 部署链运行（不触网，保持 CLI/测试确定性，#617）。
    """
    trade_date = resolve_trade_date(trade_date)
    if not run_check_trading_day(trade_date):
        return _skipped_ingestion_result(trade_date)

    scope = _daily_ingestion_scope(required_datasets)
    t0_results = _index_results(
        run_ingest_dataset(
            dataset=dataset,
            trade_date=trade_date,
            source=source,
            force=force,
        )
        for dataset in scope.t0_datasets
    )

    t1_results = _index_results(
        run_ingest_dataset(
            dataset=dataset,
            trade_date=trade_date,
            source=source,
            force=force,
        )
        for level in scope.t1_levels
        for dataset in level
    )
    ingestion_results = {**t0_results, **t1_results}
    dqc_results = run_dq_batch_check(
        trade_date=trade_date,
        datasets=list(ingestion_results),
        market_wide=True,
        ingestion_results=ingestion_results,
    )
    reconcile_results = run_dq_reconcile_adj_factor(trade_date)
    return _completed_ingestion_result(
        trade_date=trade_date,
        t0_results=t0_results,
        t1_results=t1_results,
        dqc_results=dqc_results,
        reconcile_results=reconcile_results,
    )


@flow(name="daily-ingestion", description="每日增量数据摄取流程")
def daily_ingestion_flow(
    trade_date: str = "",
    source: str = "tushare",
    force: bool = False,
    required_datasets: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """
    每日增量数据摄取流程。

    该流程实现 T0 → T1 → T3 的依赖编排：
    1. 验证交易日
    2. 提交例行 fuyao dump 刷新（与 T0/T1 并行，#617）
    3. 执行 T0 元数据任务（并行）
    4. 执行 T1 增量任务（并行，依赖 T0）
    5. 触发 T3 数据质量检查（覆盖所有有 DQ 规则的数据集）
    6. 例行 adj_factor 跨源对账（等待 DQC 与 fuyao dump，#515 A3）

    使用 Prefect 原生依赖机制（@task + wait_for）实现声明式编排。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)；为空时取 Asia/Shanghai 当日
            （定时部署触发路径，Prefect 3.6 参数模板不渲染 `{{ date }}`）
        source: 数据源名称
        force: 是否强制重新摄取
        required_datasets: 显式策略依赖；提供时仅执行其依赖闭包。

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
    # 0. 定时触发未携带日期时自取当日
    trade_date = resolve_trade_date(trade_date)

    # 1. 检查交易日
    is_trading = check_trading_day(trade_date=trade_date)

    # 如果非交易日，直接返回
    if not is_trading:
        return _skipped_ingestion_result(trade_date)

    scope = _daily_ingestion_scope(required_datasets)

    # 1.5 例行 fuyao adjustment-factors dump 刷新（#617）：纯源下载，与
    # T0/T1 并行；为链尾 adj_factor 对账提供当日 dump（陈旧守卫要求 dump
    # 日期 ≥ 目标交易日）。任务内自兜失败，status 字段显式报告。
    dump_future = fuyao_dump_adjustment_factors.submit()

    # 2. 提交 T0 任务（并行执行）
    t0_futures: list[PrefectFuture[dict[str, object]]] = []
    for dataset in scope.t0_datasets:
        t0_task = create_ingest_task_t0(dataset)
        future = t0_task.submit(
            trade_date=trade_date,
            source=source,
            force=force,
        )
        t0_futures.append(future)

    # 3. 提交 T1 任务（按依赖层级并行执行）
    # T1 数据集按依赖关系分层：
    # - Level 0: etf_daily, stock_daily (只依赖 T0)
    # - Level 1: stock_status/adj_factor/fund_adj (依赖日行情数据)
    t1_futures: list[PrefectFuture[dict[str, object]]] = []
    level_futures: list[list[PrefectFuture[dict[str, object]]]] = []

    for level_idx, level in enumerate(scope.t1_levels):
        # 确定等待的任务：第一层等待 T0，后续层等待前面所有层
        if level_idx == 0:
            wait_for_futures = t0_futures
        else:
            # 收集前面所有层的 futures
            wait_for_futures = list(chain.from_iterable(level_futures))

        current_level_futures: list[PrefectFuture[dict[str, object]]] = []
        for dataset in level:
            # 根据数据集类型选择对应的 task 创建函数
            if _dataset_value(dataset) in {"adj_factor", "fund_adj"}:
                task = create_ingest_task_t1_adj(dataset)
            else:
                task = create_ingest_task_t1_bars(dataset)

            future = task.submit(
                trade_date=trade_date,
                source=source,
                force=force,
                wait_for=wait_for_futures,
            )
            current_level_futures.append(future)
            t1_futures.append(future)

        # 记录本层的 futures，供后续层依赖
        level_futures.append(current_level_futures)

    # 4. 收集结果
    t0_results = _collect_results(t0_futures)
    t1_results = _collect_results(t1_futures)
    ingestion_results = {**t0_results, **t1_results}

    # 5. 触发 DQC（等待 T1 任务完成）
    dqc_future: PrefectFuture[dict[str, Any]] = dq_batch_check.submit(  # pyright: ignore[reportCallIssue]
        trade_date=trade_date,
        datasets=list(ingestion_results),
        market_wide=True,
        ingestion_results=ingestion_results,
        wait_for=t1_futures,
    )
    dqc_results = cast(
        dict[str, Any],
        dqc_future.result(),
    )

    # 5.5 例行 adj_factor 跨源对账（#515 A3）：排在 DQC 之后，失败显式
    # skip 不拖垮摄取链（结果在 reconcile_results 键下报告）；同时等待
    # 当日 fuyao dump（#617），对账辅源才能通过陈旧守卫读到当日事件
    reconcile_future: PrefectFuture[dict[str, Any]] = dq_reconcile_adj_factor.submit(  # pyright: ignore[reportCallIssue]
        trade_date=trade_date,
        wait_for=[dqc_future, dump_future],
    )
    reconcile_results = cast(dict[str, Any], reconcile_future.result())
    fuyao_dump_result = cast(dict[str, object], dump_future.result())

    # 6. 汇总统计
    return _completed_ingestion_result(
        trade_date=trade_date,
        t0_results=t0_results,
        t1_results=t1_results,
        dqc_results=dqc_results,
        reconcile_results=reconcile_results,
        fuyao_dump=fuyao_dump_result,
    )
