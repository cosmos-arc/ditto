"""
修补 Flow.

该模块实现数据修补功能：
- 重试失败任务
- 扫描并修补数据空洞
- 每日修补流程
"""

from __future__ import annotations

from typing import cast

from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITReattestationRequest,
)
from ditto_platform.foundation import logger
from prefect import flow

from ditto_apps.registry import create_ingestion_bundle

__all__ = [
    "CONSUMER_CRITICAL_HOLE_DATASETS",
    "LATE_PUBLISHING_REFRESH_DATASETS",
    "LATE_PUBLISHING_REFRESH_WINDOW_DAYS",
    "daily_repair_flow",
    "repair_holes_flow",
    "retry_failed_flow",
    "run_sparse_pit_reattestation",
    "sparse_pit_reattestation_flow",
]

# 空洞扫描的消费者关键数据集（#623：补偿按消费者依赖选择，禁全注册表
# 盲扫）。只有这些核心价格链数据集按日历扫空洞；其余数据集只按真实
# 失败记录进入重试补偿。
CONSUMER_CRITICAL_HOLE_DATASETS: tuple[str, ...] = (
    "etf_daily",
    "stock_daily",
    "adj_factor",
    "fund_adj",
)

# 晚发布数据集（#625）：源侧 T 日数据在当日 21:55 EOD 波尚未发布——
# margin_detail 官方口径为「交易所 T+1 上午 ~8:30 更新上一交易日，深市/
# 北交所周五数据下周一上午更新」（tushare doc_id=59）；fund_share 源侧
# 批量补发（2026-10-26 实测仅 765/1807 行部分发布，10-28~30 当晚全空）。
# 当晚摄取固化为 SUCCESS/0 或 SUCCESS/部分行后，skip 决策与完成事实
# 都判定已覆盖，空洞扫描不可见。修补方式：nightly repair 对这些数据集
# force 重取近 N 个交易日——同业务键幂等合并（SQLite ON CONFLICT /
# Parquet 同 kd upsert），源侧补全后自然收敛；空观察重取经 evidence
# revision 检查点留痕。
LATE_PUBLISHING_REFRESH_DATASETS: tuple[str, ...] = (
    "margin_trading",
    "fund_share",
)
LATE_PUBLISHING_REFRESH_WINDOW_DAYS = 5


def run_sparse_pit_reattestation(
    *,
    dataset: str,
    signal_date: str,
    source: str = "tushare",
) -> dict[str, object]:
    """Run application-owned full-history sparse PIT recovery synchronously."""
    with create_ingestion_bundle(source=source) as bundle:
        result = bundle.sparse_pit_reattestation.run(
            SparsePITReattestationRequest(
                dataset=dataset,
                source=source,
                signal_date=signal_date,
            )
        )
    return result.to_dict()


@flow(
    name="sparse-pit-reattestation",
    description="全量重摄取稀疏 PIT 历史并重建可验证 L1/L2 证据",
)
def sparse_pit_reattestation_flow(
    dataset: str,
    signal_date: str,
    source: str = "tushare",
) -> dict[str, object]:
    """Schedule the same sparse recovery used by the synchronous ops CLI."""
    result = run_sparse_pit_reattestation(
        dataset=dataset,
        signal_date=signal_date,
        source=source,
    )
    if result.get("passed") is not True:
        error = result.get("error")
        error_code = error if isinstance(error, str) else "SPARSE_REATTEST_FAILED"
        raise RuntimeError(error_code)
    return result


@flow(name="retry-failed", description="重试失败任务")
def retry_failed_flow(
    dataset: str,
    max_attempts: int = 3,
    limit: int = 10,
    source: str = "tushare",
) -> dict[str, object]:
    """
    重试失败任务流程。

    Args:
        dataset: 数据集名称（如 "stock_daily"）
        max_attempts: 最大尝试次数筛选条件
        limit: 重试的最大任务数量
        source: 数据源名称

    Returns:
        重试结果字典

    """
    with create_ingestion_bundle(source=source) as bundle:
        # 执行重试
        result = bundle.retry_manager.retry_failed(
            dataset=dataset,
            max_attempts=max_attempts,
            limit=limit,
        )

        return {
            "dataset": result.dataset,
            "total_failed": result.total_failed,
            "retried_count": result.retried_count,
            "success_count": result.success_count,
            "still_failed_count": result.still_failed_count,
            # #623：被失败分类排除出自动重试的失败（永久/源缺失/不支持），
            # 保留原因与补偿范围供人工裁决。
            "excluded_failures": [
                {
                    "trade_date": log.trade_date,
                    "error_code": log.error_code,
                    "error_message": log.error_message,
                    "attempts": log.attempts,
                }
                for log in result.excluded_failures
            ],
            "message": (
                f"重试完成: {result.success_count}/{result.retried_count} 成功"
            ),
        }


@flow(name="repair-holes", description="扫描并修补数据空洞")
def repair_holes_flow(
    dataset: str,
    source: str = "tushare",
    parallel: int = 1,
    refetch_window_days: int = 0,
) -> dict[str, object]:
    """
    扫描并修补数据空洞流程。

    该流程会：
    1. 获取日历中的所有交易日
    2. 对比已摄取日期，找出空洞
    3. 回补空洞日期

    Args:
        dataset: 数据集名称
        source: 数据源名称
        parallel: 并行度
        refetch_window_days: 追加近 N 个交易日 force 重取（#625 晚发布
            数据集；0 表示仅扫空洞）

    Returns:
        修补结果字典

    """
    with create_ingestion_bundle(source=source) as bundle:
        # 回补缺失数据
        result = bundle.backfill_manager.backfill_missing(
            dataset=dataset,
            source=source,
            parallel=parallel,
            force_refresh_days=refetch_window_days,
        )

        return {
            "dataset": result.dataset,
            "holes_count": result.total_dates,
            "repaired_count": result.success_count,
            "failed_count": result.failed_count,
            "message": (
                f"修补完成: {result.success_count} 个空洞已修补"
                if result.total_dates > 0
                else "没有发现空洞"
            ),
        }


@flow(name="daily-repair", description="每日修补流程")
def daily_repair_flow(
    datasets: list[str] | None = None,
    max_attempts: int = 3,
    retry_limit: int = 10,
    source: str = "tushare",
    parallel: int = 1,
) -> dict[str, object]:
    """
    每日修补流程。

    该流程运行三个步骤：
    1. 重试失败的任务（仅瞬态失败，#623 失败分类）
    2. 扫描并修补数据空洞（仅消费者关键数据集）
    3. 晚发布数据集近窗 force 重取（#625：margin_trading/fund_share 的
       SUCCESS/空帧或部分行观察被固化，须 force 重取直至源侧补全）

    补偿目标按真实失败记录选择（datasets=None 时自动发现有瞬态失败的
    数据集），不做全注册表每日回补；被分类排除的失败（永久/源缺失/
    不支持）在 summary.excluded_failure_groups 留痕待人工裁决。

    适合每日凌晨运行。

    Args:
        datasets: 显式修补的数据集列表；None 时按失败记录自动发现
            （重试=瞬态 FAIL 数据集，空洞=消费者关键数据集，近窗刷新=
            晚发布数据集）
        max_attempts: 重试的最大尝试次数
        retry_limit: 重试的最大任务数
        source: 数据源名称
        parallel: 并行度

    Returns:
        修补结果汇总

    """
    excluded_groups: list[dict[str, object]] = []
    refresh_datasets: list[str] = []
    if datasets is None:
        # #623 补偿选择：重试目标=瞬态失败数据集（事件驱动、天然有界），
        # 空洞扫描=消费者关键数据集白名单（低频源不按日盲目回补）。
        # #625 晚发布数据集额外追加近窗 force 重取（补偿选择之外）。
        with create_ingestion_bundle(source=source) as bundle:
            retry_datasets, excluded_groups = (
                bundle.retry_manager.compensation_selection(
                    max_attempts=max_attempts,
                )
            )
        holes_datasets = list(CONSUMER_CRITICAL_HOLE_DATASETS)
        refresh_datasets = list(LATE_PUBLISHING_REFRESH_DATASETS)
        if excluded_groups:
            logger.warning(
                "非瞬态失败不自动补偿, 待人工裁决",
                event="repair_excluded_failure_groups",
                groups=excluded_groups,
            )
    else:
        retry_datasets = list(datasets)
        holes_datasets = list(datasets)

    retry_results: dict[str, dict[str, object]] = {}
    holes_results: dict[str, dict[str, object]] = {}

    for dataset in retry_datasets:
        # 逐数据集隔离（#623 correctness F2）：补偿发现来自 ingestion_log，
        # 可能含已改名/移除/权限被撤的数据集名——单个数据集的编排异常
        # 不得拖垮整晚修补（消费者关键数据集的空洞扫描仍须执行）。
        try:
            retry_result = retry_failed_flow(
                dataset=dataset,
                max_attempts=max_attempts,
                limit=retry_limit,
                source=source,
            )
        except Exception as exc:
            logger.exception(
                "重试数据集编排失败",
                event="repair_retry_dataset_failed",
                dataset=dataset,
                error_type=type(exc).__name__,
            )
            retry_result: dict[str, object] = {
                "dataset": dataset,
                "error": f"{type(exc).__name__}: {exc}",
            }
        retry_results[dataset] = retry_result

    for dataset in holes_datasets:
        try:
            holes_result = repair_holes_flow(
                dataset=dataset,
                source=source,
                parallel=parallel,
            )
        except Exception as exc:
            logger.exception(
                "空洞扫描数据集编排失败",
                event="repair_holes_dataset_failed",
                dataset=dataset,
                error_type=type(exc).__name__,
            )
            holes_result: dict[str, object] = {
                "dataset": dataset,
                "error": f"{type(exc).__name__}: {exc}",
            }
        holes_results[dataset] = holes_result

    # #625 晚发布近窗刷新：对晚发布数据集 force 重取近 N 个交易日，
    # 治愈被 SUCCESS 固化的空帧/部分行观察。逐数据集隔离同上。
    refresh_results: dict[str, dict[str, object]] = {}
    for dataset in refresh_datasets:
        try:
            refresh_result = repair_holes_flow(
                dataset=dataset,
                source=source,
                parallel=parallel,
                refetch_window_days=LATE_PUBLISHING_REFRESH_WINDOW_DAYS,
            )
        except Exception as exc:
            logger.exception(
                "晚发布数据集近窗刷新编排失败",
                event="repair_late_publishing_refresh_failed",
                dataset=dataset,
                error_type=type(exc).__name__,
            )
            refresh_result: dict[str, object] = {
                "dataset": dataset,
                "error": f"{type(exc).__name__}: {exc}",
            }
        refresh_results[dataset] = refresh_result

    # 汇总结果
    total_retried = sum(
        cast(int, r.get("retried_count", 0)) for r in retry_results.values()
    )
    total_repaired = sum(
        cast(int, r.get("repaired_count", 0)) for r in holes_results.values()
    )
    total_refreshed = sum(
        cast(int, r.get("repaired_count", 0)) for r in refresh_results.values()
    )

    return {
        "retry_result": retry_results,
        "holes_result": holes_results,
        "refresh_result": refresh_results,
        "summary": {
            "retry_datasets": retry_datasets,
            "holes_datasets": holes_datasets,
            "refresh_datasets": refresh_datasets,
            "total_retried": total_retried,
            "total_repaired": total_repaired,
            "total_refreshed": total_refreshed,
            "excluded_failure_groups": excluded_groups,
            "message": (
                f"修补完成: 重试 {total_retried} 个任务, 修补 {total_repaired} 个空洞, "
                f"近窗刷新 {total_refreshed} 个会话"
            ),
        },
    }
