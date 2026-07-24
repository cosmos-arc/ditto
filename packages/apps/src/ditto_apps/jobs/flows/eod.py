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
    |   +-- failed_count > 0 -> 记录告警，跳过物化，持久化逐策略 blocked outcome
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

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, cast

from ditto_application.config import resolve_ingestion_scope
from ditto_application.eod_request import (
    eod_request_from_strategy_spec as _eod_request,
)
from ditto_application.exceptions import AppConfigurationError
from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodStrategyOutcome,
    EodStrategyRequest,
    R2PreflightPolicy,
)
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContextBuilder,
)
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
)
from ditto_application.processes.execution.signal_package_models import (
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.strategy_run_process import (
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunServiceConfig,
)
from ditto_platform.foundation import logger
from ditto_platform.services import AlertManager, NotificationLevel
from prefect import flow

from ditto_apps.jobs.eod_evidence import (
    dataset_states_from_ingestion as _dataset_states_from_ingestion,
)
from ditto_apps.jobs.flows.daily import (
    check_trading_day,
    daily_ingestion_flow,
    run_check_trading_day,
    run_daily_ingestion,
)
from ditto_apps.jobs.flows.materialization import (
    daily_materialization_flow,
    run_daily_materialization,
)
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.strategy import create_strategy_bundle


@dataclass(frozen=True)
class EodPipelineDependencies:
    """Execution adapters selected by the EOD host boundary."""

    check_trading_day: Callable[..., bool]
    daily_ingestion: Callable[..., dict[str, object]]
    daily_materialization: Callable[..., dict[str, object]]


@dataclass(frozen=True)
class EodSignalPublishRequest:
    """Strategy output and evidence needed to stage one EOD package."""

    result: StrategyRunResult
    account_id: str
    strategy: EodStrategyRequest
    trade_date: str
    dataset_states: Mapping[str, DatasetReadiness]
    snapshots: Mapping[str, str]
    allow_experimental_data: bool


@dataclass(frozen=True)
class EodSignalPublishDependencies:
    """Services used to size, date, and persist one EOD package."""

    publisher: SignalPackagePublisher | None
    sizing_builder: ManualSizingContextBuilder | None
    date_resolver: AShareTradeDateResolver | None


def _default_eod_pipeline_dependencies() -> EodPipelineDependencies:
    """Resolve synchronous adapters at call time so composition remains patchable."""
    return EodPipelineDependencies(
        check_trading_day=run_check_trading_day,
        daily_ingestion=run_daily_ingestion,
        daily_materialization=run_daily_materialization,
    )


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
    except Exception as exc:
        logger.error(
            "发送告警失败",
            event="eod_alert_send_failed",
            error_code="EOD_ALERT_SEND_FAILED",
            error_type=type(exc).__name__,
            template=template,
        )


def _publish_eod_signals(
    request: EodSignalPublishRequest,
    dependencies: EodSignalPublishDependencies,
) -> SignalPackage:
    """Build and stage one package from the production EOD dependencies."""
    publisher = dependencies.publisher
    if publisher is None:
        msg = "SignalPackagePublisher 未配置, 无法持久化 EOD package"
        raise RuntimeError(msg)
    sizing_builder = dependencies.sizing_builder
    if sizing_builder is None:
        msg = "ManualSizingContextBuilder 未配置, 无法生成人工建议数量"
        raise RuntimeError(msg)
    date_resolver = dependencies.date_resolver
    if date_resolver is None:
        msg = "AShareTradeDateResolver 未配置, 无法解析 D+1"
        raise RuntimeError(msg)
    result = request.result
    strategy = request.strategy
    target = result.target
    instrument_ids = tuple(sorted(int(item) for item in target.positions))
    sizing = sizing_builder.build(
        account_id=request.account_id,
        strategy_id=strategy.strategy_id,
        signal_date=request.trade_date,
        instrument_ids=instrument_ids,
        allow_experimental_data=request.allow_experimental_data,
        risk_locked_instruments=result.risk_locked_instruments,
    )
    trade_dates = date_resolver.resolve(
        signal_date=request.trade_date,
        decision_date=request.trade_date,
    )
    return publisher.publish(
        SignalPackagePublishRequest(
            target=target,
            strategy_version=strategy.strategy_version,
            account_id=sizing.account_id,
            sleeve_id=sizing.sleeve_id,
            sizing_contexts=sizing.contexts,
            decision_date=trade_dates.decision_date,
            intended_trade_date=trade_dates.intended_trade_date,
            required_datasets=strategy.required_datasets,
            required_dataset_states=tuple(
                asdict(
                    request.dataset_states.get(
                        dataset,
                        DatasetReadiness(dataset=dataset, status="unknown"),
                    )
                )
                for dataset in strategy.required_datasets
            ),
            dataset_snapshot_ids=dict(request.snapshots),
            factor_ids=result.factor_ids,
            factor_values=result.factor_values,
            risk_flags=result.risk_flags,
            threshold=0.01,
        )
    )


def _finalize_eod_signals(
    publisher: SignalPackagePublisher | None,
    package: SignalPackage,
) -> SignalPackage:
    if publisher is None:
        msg = "SignalPackagePublisher 未配置, 无法激活 EOD package"
        raise RuntimeError(msg)
    return publisher.finalize(package)


def _find_staged_eod_signals(
    publisher: SignalPackagePublisher | None,
    request: EodStrategyRequest,
    signal_date: str,
    batch_key: str,
) -> SignalPackage | None:
    if publisher is None:
        msg = "SignalPackagePublisher 未配置, 无法恢复 EOD package"
        raise RuntimeError(msg)
    return publisher.find_staged(
        strategy_id=request.strategy_id,
        run_id=batch_key,
        signal_date=signal_date,
    )


def _resolve_published_eod_request(strategy_id: str) -> EodStrategyRequest | None:
    """Snapshot the selected published strategy before any ingestion starts."""
    with create_strategy_bundle() as bundle:
        catalog = bundle.catalog_service
        if catalog is None:
            return None
        spec = catalog.get_active_published(strategy_id)
        return _eod_request(spec) if spec is not None else None


def _run_strategies(
    trade_date: str,
    *,
    dataset_states: dict[str, DatasetReadiness],
    strategy: EodStrategyRequest,
    account_id: str,
    source: str,
    allow_experimental_data: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """
    运行显式选择的单个已发布策略。

    Args:
        trade_date: 交易日期
        dataset_states: 摄取与 DQ 产出的逐数据集就绪证据。
        strategy: 摄取前锁定的 published 策略版本与数据依赖。
        account_id: 人工交易账户 ID。
        source: 与摄取一致的数据源名称。
        allow_experimental_data: 是否显式允许实验级数据集进入策略输入。

    Returns:
        (策略结果列表, 是否全部成功)

    """
    with create_strategy_bundle() as bundle:
        facade = bundle.strategy_facade
        run_service = bundle.run_service
        publisher = bundle.signal_package_publisher
        sizing_builder = bundle.sizing_context_builder
        date_resolver = bundle.trade_date_resolver
        publish_dependencies = EodSignalPublishDependencies(
            publisher=publisher,
            sizing_builder=sizing_builder,
            date_resolver=date_resolver,
        )

        if run_service is None:
            return [
                _failed_strategy_outcome(
                    trade_date,
                    strategy.strategy_id,
                    reason="RUN_LIFECYCLE_SERVICE_UNAVAILABLE",
                )
            ], False
        request = strategy

        def run_strategy(
            request: EodStrategyRequest,
            signal_date: str,
            batch_key: str,
        ) -> object:
            return facade.run_strategy_for_date_from_catalog(
                config=StrategyRunServiceConfig(
                    strategy_id=request.strategy_id,
                    strategy_version=request.strategy_version,
                    run_id=batch_key,
                    mode=StrategyRunMode.RECOMMENDATION,
                    manage_run_lifecycle=False,
                ),
                trade_date=signal_date,
                version=int(request.strategy_version),
                source=source,
                allow_experimental_data=allow_experimental_data,
            )

        def publish_signals(
            run_result: object,
            snapshots: Mapping[str, str],
        ) -> SignalPackage:
            result = cast(StrategyRunResult, run_result)
            return _publish_eod_signals(
                EodSignalPublishRequest(
                    result=result,
                    account_id=account_id,
                    strategy=request,
                    trade_date=trade_date,
                    dataset_states=dataset_states,
                    snapshots=snapshots,
                    allow_experimental_data=allow_experimental_data,
                ),
                publish_dependencies,
            )

        def finalize_signals(package: SignalPackage) -> SignalPackage:
            return _finalize_eod_signals(publisher, package)

        def find_staged_signals(
            request: EodStrategyRequest,
            signal_date: str,
            batch_key: str,
        ) -> SignalPackage | None:
            return _find_staged_eod_signals(
                publisher,
                request,
                signal_date,
                batch_key,
            )

        outcomes = EodCoordinator(
            run_strategy=run_strategy,
            publish_signals=publish_signals,
            finalize_signals=finalize_signals,
            find_staged_signals=find_staged_signals,
            run_service=run_service,
            data_readiness_query=bundle.data_readiness_query,
            r2_preflight_policy=R2PreflightPolicy(mode="shadow"),
        ).run(
            signal_date=trade_date,
            strategies=(request,),
            dataset_states=dataset_states,
        )
        results = [_outcome_dict(outcome) for outcome in outcomes]
        all_success = all(
            outcome.status in {"completed", "no_rebalance"} for outcome in outcomes
        )
        return results, all_success


def _missing_strategy_outcome(trade_date: str, strategy_id: str) -> dict[str, Any]:
    """对显式选中但没有 published 版本的策略结构化 fail closed。"""
    batch_key = f"eod-{trade_date}-{strategy_id}-unpublished"
    return {
        "strategy_id": strategy_id,
        "strategy_version": "",
        "batch_key": batch_key,
        "status": "blocked",
        "required_dataset_states": [],
        "artifact_id": None,
        "checksum": None,
        "reason": "NO_ACTIVE_STRATEGY",
        "run_id": batch_key,
    }


def _failed_strategy_outcome(
    trade_date: str,
    strategy_id: str,
    *,
    reason: str,
) -> dict[str, Any]:
    """在控制面服务不可用时返回稳定、不可误判为成功的 outcome。"""
    batch_key = f"eod-{trade_date}-{strategy_id}-unknown"
    return {
        "strategy_id": strategy_id,
        "strategy_version": "",
        "batch_key": batch_key,
        "status": "failed",
        "required_dataset_states": [],
        "artifact_id": None,
        "checksum": None,
        "reason": reason,
        "error": reason,
        "run_id": batch_key,
    }


def _outcome_dict(outcome: EodStrategyOutcome) -> dict[str, Any]:
    payload = asdict(outcome)
    if outcome.r2_preflight_status == "not_run":
        payload.pop("r2_preflight_status")
    payload["required_dataset_states"] = [
        asdict(state) for state in outcome.required_dataset_states
    ]
    payload["run_id"] = outcome.batch_key
    if outcome.status == "failed":
        payload["error"] = outcome.reason
    return payload


def run_eod_pipeline(
    trade_date: str,
    source: str = "tushare",
    strategy_id: str | None = None,
    account_id: str | None = None,
    allow_experimental_data: bool = False,
    *,
    dependencies: EodPipelineDependencies | None = None,
) -> dict[str, object]:
    """
    执行 EOD 业务 pipeline，不依赖 Prefect engine。

    将每日数据摄取、因子物化、策略运行串联为完整运营 pipeline。
    非交易日自动跳过；摄取失败跳过物化但仍持久化逐策略 outcome；
    物化失败不阻断策略运行。

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        source: 数据源名称
        strategy_id: 显式选择的活动执行策略。
        account_id: 显式选择的人工交易账户。
        allow_experimental_data: 是否显式允许实验级数据集进入策略输入。
        dependencies: 宿主选择的执行 adapters；默认使用同步业务函数。

    Returns:
        EOD 运行结果字典，包含:
        - date: 交易日期
        - skipped: 是否跳过
        - overall_status: 整体状态 (skipped / success / partial)
        - ingestion: 摄取结果
        - materialization: 物化结果
        - strategies: 策略运行结果列表

    """
    runners = dependencies or _default_eod_pipeline_dependencies()

    # 执行 sleeve 必须显式选择；缺失时在任何摄取/写入前 fail closed。
    if not strategy_id or not account_id:
        reason = (
            "STRATEGY_SELECTION_REQUIRED"
            if not strategy_id
            else "ACCOUNT_SELECTION_REQUIRED"
        )
        return _selection_blocked_result(
            trade_date=trade_date,
            strategy_id=strategy_id or "",
            reason=reason,
        )

    # 1. 检查交易日
    is_trading = runners.check_trading_day(trade_date=trade_date)

    if not is_trading:
        return {
            "date": trade_date,
            "skipped": True,
            "overall_status": "skipped",
            "ingestion": None,
            "materialization": None,
            "strategies": [],
        }

    # 2. 锁定 published 版本并解析其数据依赖；无效 scope 不得调用 provider。
    strategy = _resolve_published_eod_request(strategy_id)
    if strategy is None:
        return _pre_ingestion_blocked_result(
            trade_date=trade_date,
            strategies=[_missing_strategy_outcome(trade_date, strategy_id)],
        )
    try:
        resolve_ingestion_scope(strategy.required_datasets)
    except AppConfigurationError:
        strategy_results, _ = _run_strategies(
            trade_date,
            dataset_states={},
            strategy=strategy,
            account_id=account_id,
            source=source,
            allow_experimental_data=allow_experimental_data,
        )
        return _pre_ingestion_blocked_result(
            trade_date=trade_date,
            strategies=strategy_results,
        )

    # 3. 仅执行已发布策略所需数据集的依赖闭包。
    ingestion_result = runners.daily_ingestion(
        trade_date=trade_date,
        source=source,
        required_datasets=strategy.required_datasets,
    )

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

    # 4. 检查摄取结果
    summary: dict[str, Any] = cast(dict[str, Any], ingestion_result.get("summary", {}))
    failed_count: int = cast(int, summary.get("failed_count", 0))
    dataset_states = _dataset_states_from_ingestion(
        ingestion_result,
        signal_date=trade_date,
    )

    if failed_count > 0:
        # 摄取有失败: 发送告警，并始终由 coordinator 持久化逐策略 outcome。
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

    # 5. 执行物化
    mat_success = failed_count == 0
    mat_result: dict[str, object] | None = None

    if failed_count == 0:
        try:
            mat_result = runners.daily_materialization(trade_date=trade_date)
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

    # 6. 运行策略（策略依赖摄取数据，不依赖物化结果）
    strategy_results, strategy_all_success = _run_strategies(
        trade_date,
        dataset_states=dataset_states,
        strategy=strategy,
        account_id=account_id,
        source=source,
        allow_experimental_data=allow_experimental_data,
    )

    # 7. 计算整体状态
    overall_status = "success" if mat_success and strategy_all_success else "partial"

    return {
        "date": trade_date,
        "skipped": False,
        "overall_status": overall_status,
        "ingestion": ingestion_result,
        "materialization": mat_result,
        "strategies": strategy_results,
    }


@flow(
    name="eod-pipeline",
    description="EOD 编排: 摄取 -> 物化 -> 策略运行",
)
def eod_flow(
    trade_date: str,
    source: str = "tushare",
    strategy_id: str | None = None,
    account_id: str | None = None,
    allow_experimental_data: bool = False,
) -> dict[str, object]:
    """用 Prefect adapters 调用共享 EOD pipeline。"""
    return run_eod_pipeline(
        trade_date=trade_date,
        source=source,
        strategy_id=strategy_id,
        account_id=account_id,
        allow_experimental_data=allow_experimental_data,
        dependencies=EodPipelineDependencies(
            check_trading_day=check_trading_day,
            daily_ingestion=daily_ingestion_flow,
            daily_materialization=daily_materialization_flow,
        ),
    )


def _selection_blocked_result(
    *,
    trade_date: str,
    strategy_id: str,
    reason: str,
) -> dict[str, object]:
    """将缺失执行选择表示为稳定 outcome，不触发任何外部副作用。"""
    return {
        "date": trade_date,
        "skipped": False,
        "overall_status": "partial",
        "ingestion": None,
        "materialization": None,
        "strategies": [
            {
                "strategy_id": strategy_id,
                "strategy_version": "",
                "batch_key": "",
                "status": "blocked",
                "required_dataset_states": [],
                "artifact_id": None,
                "checksum": None,
                "reason": reason,
                "run_id": "",
            }
        ],
    }


def _pre_ingestion_blocked_result(
    *,
    trade_date: str,
    strategies: list[dict[str, Any]],
) -> dict[str, object]:
    """Return a stable fail-closed EOD result without ingestion side effects."""
    return {
        "date": trade_date,
        "skipped": False,
        "overall_status": "partial",
        "ingestion": None,
        "materialization": None,
        "strategies": strategies,
    }
