"""
EOD (End-of-Day) 编排 Flow。

将每日数据摄取 -> 因子物化 -> 策略运行串联为完整的运营 pipeline。

执行流程:
    eod_flow (Cron: 45 19 * * 1-5)
    |
    +-- check_trading_day(date)
    |   +-- 非交易日 -> return {skipped: true}
    |
    +-- daily_ingestion_flow(date)
    |   +-- 返回 summary: {success_count, failed_count}
    |
    +-- 检查摄取结果
    |   +-- skipped=True -> 整体跳过
    |   +-- failed_count > 0 -> 记录告警，跳过物化和策略
    |   +-- 全部成功 -> 继续
    |
    +-- daily_materialization_flow(date)
    |   +-- 返回 results + summary
    |
    +-- 策略运行（配置驱动）
    |   +-- 通过 DI 获取 StrategyCatalogService，列出已发布策略
    |   +-- 通过 StrategyFacade 逐一运行
    |   +-- 每个策略独立 try/except，单个失败不影响其他
    |
    +-- 返回汇总 {date, ingestion, materialization, strategies, overall_status}
"""

from datetime import UTC, datetime
from typing import Any, cast

from ditto_app.process.execution.strategy_run_process import (
    StrategyRunMode,
    StrategyRunServiceConfig,
)
from ditto_infra.foundation import logger
from ditto_infra.services.notification.manager import AlertManager
from ditto_infra.services.notification.message import NotificationLevel
from prefect import flow

from ditto_interfaces.jobs.flows.daily import check_trading_day, daily_ingestion_flow
from ditto_interfaces.jobs.flows.materialization import daily_materialization_flow
from ditto_interfaces.registry.container import make_app_container
from ditto_interfaces.registry.contexts.strategy import create_strategy_bundle


def _send_alert_safely(
    alert_manager: AlertManager,
    template: str,
    context: dict[str, Any],
    level: NotificationLevel,
) -> None:
    """
    安全发送告警通知，失败不阻断主流程。

    Args:
        alert_manager: 告警管理器
        template: 模板名称
        context: 模板上下文
        level: 通知级别

    """
    try:
        alert_manager.send_alert(
            template=template,
            context=context,
            level=level,
            timestamp=datetime.now(UTC),
        )
    except Exception:
        logger.exception("发送告警失败", template=template)


def _run_strategies(
    trade_date: str,
) -> tuple[list[dict[str, Any]], bool]:
    """
    运行所有已发布策略。

    Args:
        trade_date: 交易日期

    Returns:
        (策略结果列表, 是否全部成功)

    """
    with create_strategy_bundle() as bundle:
        catalog = bundle.catalog_service
        facade = bundle.strategy_facade

        if catalog is None:
            return [], True

        published_specs = [
            spec for spec in catalog.list_specs() if spec.status == "published"
        ]

        if not published_specs:
            return [], True

        results: list[dict[str, Any]] = []
        all_success = True

        for spec in published_specs:
            try:
                run_result = facade.run_strategy_for_date_from_catalog(
                    config=StrategyRunServiceConfig(
                        strategy_id=spec.strategy_id,
                        strategy_version=str(spec.version),
                        mode=StrategyRunMode.RESEARCH,
                    ),
                    trade_date=trade_date,
                    version=spec.version,
                )
                results.append(
                    {
                        "strategy_id": spec.strategy_id,
                        "run_id": run_result.run_id,
                        "status": "success",
                    }
                )
            except Exception as exc:
                logger.exception(
                    "策略运行失败",
                    strategy_id=spec.strategy_id,
                    trade_date=trade_date,
                )
                results.append(
                    {
                        "strategy_id": spec.strategy_id,
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                all_success = False

        return results, all_success


@flow(
    name="eod-pipeline",
    description="EOD 编排: 摄取 -> 物化 -> 策略运行",
)
def eod_flow(trade_date: str, source: str = "tushare") -> dict[str, object]:
    """
    EOD 编排 Flow。

    将每日数据摄取、因子物化、策略运行串联为完整运营 pipeline。
    非交易日自动跳过，摄取失败跳过物化和策略，物化失败不阻断策略运行。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        source: 数据源名称

    Returns:
        EOD 运行结果字典，包含:
        - date: 交易日期
        - skipped: 是否跳过
        - overall_status: 整体状态 (skipped / success / partial)
        - ingestion: 摄取结果
        - materialization: 物化结果
        - strategies: 策略运行结果列表

    """
    # 1. 检查交易日
    is_trading = check_trading_day(trade_date=trade_date)

    if not is_trading:
        return {
            "date": trade_date,
            "skipped": True,
            "overall_status": "skipped",
            "ingestion": None,
            "materialization": None,
            "strategies": [],
        }

    # 2. 执行摄取
    ingestion_result = daily_ingestion_flow(trade_date=trade_date, source=source)

    # 摄取内部跳过（理论上不会，因为已检查交易日，但防御性处理）
    if ingestion_result.get("skipped", False):
        return {
            "date": trade_date,
            "skipped": True,
            "overall_status": "skipped",
            "ingestion": ingestion_result,
            "materialization": None,
            "strategies": [],
        }

    # 3. 检查摄取结果
    summary: dict[str, Any] = cast(dict[str, Any], ingestion_result.get("summary", {}))
    failed_count: int = cast(int, summary.get("failed_count", 0))

    if failed_count > 0:
        # 摄取有失败: 发送告警，跳过物化和策略
        container = make_app_container()
        try:
            alert_manager = container.get(AlertManager)
            _send_alert_safely(
                alert_manager=alert_manager,
                template="eod_ingestion_failure",
                context={
                    "trade_date": trade_date,
                    "success_count": cast(int, summary.get("success_count", 0)),
                    "failed_count": failed_count,
                },
                level=NotificationLevel.WARNING,
            )
        finally:
            container.close()

        return {
            "date": trade_date,
            "skipped": False,
            "overall_status": "partial",
            "ingestion": ingestion_result,
            "materialization": None,
            "strategies": [],
        }

    # 4. 执行物化
    mat_success = True
    mat_result: dict[str, object] | None = None

    try:
        mat_result = daily_materialization_flow(trade_date=trade_date)
    except Exception as exc:
        logger.exception("物化流程执行失败", trade_date=trade_date)
        mat_success = False
        mat_result = {
            "trade_date": trade_date,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }

        # 发送物化失败告警
        container = make_app_container()
        try:
            alert_manager = container.get(AlertManager)
            _send_alert_safely(
                alert_manager=alert_manager,
                template="eod_materialization_failure",
                context={
                    "trade_date": trade_date,
                    "error": str(exc),
                },
                level=NotificationLevel.ERROR,
            )
        finally:
            container.close()

    # 5. 运行策略（策略依赖摄取数据，不依赖物化结果）
    strategy_results, strategy_all_success = _run_strategies(trade_date)

    # 6. 计算整体状态
    overall_status = "success" if mat_success and strategy_all_success else "partial"

    return {
        "date": trade_date,
        "skipped": False,
        "overall_status": overall_status,
        "ingestion": ingestion_result,
        "materialization": mat_result,
        "strategies": strategy_results,
    }
