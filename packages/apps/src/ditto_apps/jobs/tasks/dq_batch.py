"""L3 统计异常检测的 DQ 批量检查任务."""

from __future__ import annotations

from typing import Any, Literal

from ditto_application.config import get_all_datasets
from ditto_application.processes.quality import QualityPatrolService
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_kernel.quality import DQIssue
from ditto_platform.foundation import Metrics, logger
from ditto_platform.services.notification import AlertManager, alert_dq_failure
from prefect import task

from ditto_apps.jobs.context import create_prefect_host

_DEFAULT_DATASETS = [
    "etf_daily",
    "index_daily",
    "stock_daily",
    "adj_factor",
    "index_weight",
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "dividend",
    "corporate_actions",
    "valuation_metrics",
    "margin_trading",
    "pledge_ratio",
    "macro_indicators",
    "fx_daily",
    "commodity_daily",
]

type _AssetClass = Literal["stock", "etf", "index"]


def _asset_class_or_none(dataset: str) -> _AssetClass | None:
    for registered_dataset in get_all_datasets():
        if registered_dataset.value != dataset:
            continue

        asset_class = registered_dataset.get_asset_class(dataset)
        if asset_class == "other":
            return None
        return asset_class
    return None


_ASSET_CLASS_BY_DATASET: dict[str, _AssetClass | None] = {
    dataset.value: _asset_class_or_none(dataset.value) for dataset in get_all_datasets()
}


@task(
    name="dq-batch-check",
    description="批量数据质量检查(L3 统计异常)",
    tags=["dq", "batch", "l3"],
)
async def dq_batch_check(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
    market_wide: bool = False,
) -> dict[str, Any]:
    """
    执行 L3 批量检查任务.

    Args:
        trade_date: 交易日期(YYYY-MM-DD)，默认为最后一个交易日
        datasets: 要检查的数据集列表，默认为常用数据集
        market_wide: 是否使用全市场查询模式

    Returns:
        检查结果摘要

    """
    logger.info(
        "Starting DQ batch check",
        event="dq_batch_start",
        trade_date=trade_date,
        datasets=datasets,
        market_wide=market_wide,
    )

    with create_prefect_host() as container:
        l3_service = container.get(QualityPatrolService)
        metadata_service = container.get(MetadataQueryFacade)
        resolved_date = _resolve_trade_date(trade_date, metadata_service)
        resolved_datasets = datasets or list(_DEFAULT_DATASETS)

        all_issues, results_by_dataset = _execute_all_checks(
            l3_service, resolved_datasets, resolved_date, market_wide
        )

        summary = _build_batch_summary(
            resolved_date, resolved_datasets, all_issues, results_by_dataset
        )

        return summary


def _resolve_trade_date(
    trade_date: str | None,
    metadata_service: MetadataQueryFacade,
) -> str:
    """
    解析 trade_date: 使用显式传入值或获取最后一个交易日.

    Args:
        trade_date: 显式交易日期，或 None 自动解析.
        metadata_service: 元数据服务，用于获取最后一个交易日.

    Returns:
        解析后的交易日期字符串.

    Raises:
        ValueError: 无法解析交易日期时.

    """
    if trade_date is not None:
        return trade_date

    trade_date = metadata_service.get_last_trading_day()
    logger.info(
        "Using last trading day",
        event="dq_batch_date_resolved",
        trade_date=trade_date,
    )
    if trade_date is None:
        raise ValueError("Failed to resolve trade_date")
    return trade_date


def _execute_all_checks(
    l3_service: QualityPatrolService,
    datasets: list[str],
    trade_date: str,
    market_wide: bool,
) -> tuple[list[DQIssue], dict[str, dict[str, Any]]]:
    """
    对所有数据集执行 L3 检查并汇总结果.

    Args:
        l3_service: L3 批量检查服务实例.
        datasets: 待检查的数据集名称列表.
        trade_date: 交易日期字符串.
        market_wide: 是否使用全市场查询模式.

    Returns:
        元组 (所有问题列表, 按数据集分组的结果).

    """
    all_issues: list[DQIssue] = []
    results_by_dataset: dict[str, dict[str, Any]] = {}

    for dataset in datasets:
        dataset_result, dataset_issues = _execute_single_check(
            l3_service, dataset, trade_date, market_wide
        )
        results_by_dataset[dataset] = dataset_result
        all_issues.extend(dataset_issues)

    return all_issues, results_by_dataset


def _execute_single_check(
    l3_service: QualityPatrolService,
    dataset: str,
    trade_date: str,
    market_wide: bool,
) -> tuple[dict[str, Any], list[DQIssue]]:
    """
    对单个数据集执行 L3 检查（含错误处理）.

    Args:
        l3_service: L3 批量检查服务实例.
        dataset: 待检查的数据集名称.
        trade_date: 交易日期字符串.
        market_wide: 是否使用全市场查询模式.

    Returns:
        元组 (结果字典, 收集的问题列表).

    """
    try:
        asset_class = _ASSET_CLASS_BY_DATASET.get(dataset)
        if asset_class is None:
            raise ValueError(f"Unknown dataset: {dataset}")

        result = l3_service.check_dataset(
            dataset=dataset,
            trade_date=trade_date,
            asset_class=asset_class,
            market_wide=market_wide,
        )

        dataset_result: dict[str, Any] = {
            "passed": result.passed,
            "issue_count": result.issue_count,
            "alert_count": result.alert_count,
        }

        issues: list[DQIssue] = list(result.issues)

        if result.alert_count > 0:
            logger.warning(
                "L3 DQ issues found",
                event="dq_batch_issues",
                dataset=dataset,
                count=result.issue_count,
            )

        return dataset_result, issues

    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning(
            "dq_batch_known_error",
            event="dq_batch_error",
            dataset=dataset,
            error_type=type(e).__name__,
            error=str(e),
        )
        return {
            "passed": False,
            "issue_count": 0,
            "alert_count": 0,
            "error": f"{type(e).__name__}: {e}",
        }, []

    except Exception as e:
        logger.exception(
            "dq_batch_unknown_error",
            event="dq_batch_error",
            dataset=dataset,
            error_type=type(e).__name__,
        )
        return {
            "passed": False,
            "issue_count": 0,
            "alert_count": 0,
            "error": f"{type(e).__name__}: {e}",
        }, []


def _build_batch_summary(
    trade_date: str,
    datasets: list[str],
    all_issues: list[DQIssue],
    results_by_dataset: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    构建批量检查摘要，发送告警并记录指标.

    Args:
        trade_date: 交易日期字符串.
        datasets: 已检查的数据集名称列表.
        all_issues: 跨数据集收集的所有问题.
        results_by_dataset: 按数据集分组的结果.

    Returns:
        摘要字典.

    """
    alert_count = sum(1 for i in all_issues if i.severity.value == "alert")

    summary = {
        "trade_date": trade_date,
        "datasets_checked": datasets,
        "total_issues": len(all_issues),
        "alert_count": alert_count,
        "results_by_dataset": results_by_dataset,
    }

    logger.info(
        "DQ batch check complete",
        event="dq_batch_complete",
        **summary,
    )

    if alert_count > 0:
        _send_dq_alert(trade_date, all_issues)

    Metrics.dq_batch_checks.add(1.0, {"trade_date": trade_date})
    Metrics.dq_batch_issues.add(float(len(all_issues)), {"trade_date": trade_date})
    Metrics.dq_batch_alerts.add(float(alert_count), {"trade_date": trade_date})

    return summary


def _send_dq_alert(trade_date: str, issues: list[Any]) -> None:
    """
    发送 DQ 告警通知.

    通过 AlertManager 发送多渠道告警；获取失败时退化为日志记录。

    Args:
        trade_date: 交易日期
        issues: 问题列表

    """
    logger.warning(
        "DQ alert notification",
        event="dq_alert",
        trade_date=trade_date,
        issue_count=len(issues),
    )
    try:
        with create_prefect_host() as container:
            manager = container.get(AlertManager)
            failed_rules = [i.rule_name for i in issues]
            alert_dq_failure(
                manager=manager,
                dataset="batch",
                trade_date=trade_date,
                failed_rules=failed_rules,
                error_count=len(issues),
            )
    except Exception as exc:
        logger.exception(
            "Failed to send DQ alert via AlertManager",
            event="dq_alert_failed",
            error=str(exc),
        )


@task(
    name="dq-completeness-check",
    description="数据完整性检查",
    tags=["dq", "completeness"],
)
def dq_completeness_check(
    trade_date: str,
    dataset: str,
    expected_sids: list[int] | None = None,
    market_wide: bool = False,
) -> dict[str, Any]:
    """
    检查数据完整性。

    Args:
        trade_date: 交易日期
        dataset: 数据集名称
        expected_sids: 预期的 Instrument ID 列表
        market_wide: 是否使用全市场查询模式

    Returns:
        完整性检查结果

    """
    with create_prefect_host() as container:
        market_service: MarketQueryFacade = container.get(MarketQueryFacade)
        # 读取实际数据（market_service 是 MarketQueryFacade）
        df = market_service.find_bars(
            start=trade_date,
            end=trade_date,
            market_wide=market_wide,
        )

        actual_sids = (
            df["instrument_id"].unique().to_list() if not df.is_empty() else []
        )

        # 计算缺失
        missing_sids: set[int]
        extra_sids: set[int]
        if expected_sids:
            missing_sids = set(expected_sids) - set(actual_sids)
            extra_sids = set(actual_sids) - set(expected_sids)
        else:
            missing_sids = set()
            extra_sids = set()

        result = {
            "trade_date": trade_date,
            "dataset": dataset,
            "expected_count": len(expected_sids) if expected_sids else None,
            "actual_count": len(actual_sids),
            "missing_count": len(missing_sids),
            "missing_sids": sorted(missing_sids),
            "extra_count": len(extra_sids),
            "extra_sids": sorted(extra_sids),
            "is_complete": len(missing_sids) == 0,
        }

        logger.info(
            "Completeness check complete",
            event="dq_completeness_complete",
            **result,
        )

        return result
