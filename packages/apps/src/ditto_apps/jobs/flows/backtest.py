"""
异步回测 Flow — Prefect 编排.

通过 Prefect Worker 执行回测，委托 BacktestService 管理状态机
PENDING→RUNNING→COMPLETED/FAILED，支持自动重试。
"""

from __future__ import annotations

from ditto_application.commands.backtest import CostConfig
from ditto_application.config import DEFAULT_INITIAL_CASH
from ditto_application.processes.execution.backtest_process import (
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.fee_override import (
    build_fee_model,
    build_slippage_model,
)
from ditto_application.queries.artifact_utils import compute_total_return
from ditto_kernel.strategy import ImpactModel, RunStatus
from prefect import flow

from ditto_apps.registry.contexts.strategy import create_strategy_bundle


def _status_str(status: RunStatus) -> str:
    """RunStatus → str，供 writer.update_status 等接受 str 的接口使用."""
    return status.value


@flow(
    name="run-backtest",
    description="异步回测执行 — BacktestService 状态机管理",
    retries=1,
    retry_delay_seconds=10,
)
def run_backtest_flow(  # noqa: PLR0913 - Prefect flow exposes wire parameters.
    *,
    run_id: str,
    strategy_id: str,
    start_date: str,
    end_date: str,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    parameter_overrides: tuple[str, ...] = (),
    cost_config: dict[str, object] | None = None,
    allow_experimental_data: bool = False,
    parent_run_id: str = "",
    resume_from_run_id: str = "",
    resume_checkpoint_trade_date: str = "",
    resume_checkpoint_completed_days: int = 0,
    resume_checkpoint_total_days: int = 0,
    resume_checkpoint_nav: float = 0.0,
    resume_checkpoint_order_count: int = 0,
    resume_checkpoint_fill_count: int = 0,
    resume_account_state_json: str = "",
    resume_account_state_hash: str = "",
    resume_settlement_state_json: str = "",
    resume_settlement_state_hash: str = "",
    resume_runtime_state_json: str = "",
    resume_runtime_state_hash: str = "",
) -> dict[str, object]:
    """
    异步执行回测.

    BacktestService 内部管理状态机: PENDING → RUNNING → COMPLETED / FAILED.
    run_service 通过 BacktestServiceOptions 传递给 BacktestService。

    Args:
        run_id: 运行唯一标识.
        strategy_id: 策略 ID.
        start_date: 起始日期 (YYYY-MM-DD).
        end_date: 结束日期 (YYYY-MM-DD).
        initial_cash: 初始资金.
        parameter_overrides: 参数覆盖列表.
        cost_config: 成本模型配置（序列化为 dict 传递跨进程边界）.
        allow_experimental_data: 显式允许 experimental 数据集进入研究态回测.
        parent_run_id: 父运行 ID（retry/resume 场景的 lineage 追踪）.
        resume_from_run_id: source run id for checkpoint-backed resume.
        resume_checkpoint_trade_date: source checkpoint completed trade date.
        resume_checkpoint_completed_days: source checkpoint completed day count.
        resume_checkpoint_total_days: source checkpoint total day count.
        resume_checkpoint_nav: source checkpoint NAV.
        resume_checkpoint_order_count: source checkpoint order count.
        resume_checkpoint_fill_count: source checkpoint fill count.
        resume_account_state_json: checkpoint account-state JSON evidence.
        resume_account_state_hash: checkpoint account-state content hash.
        resume_settlement_state_json: checkpoint settlement-state JSON evidence.
        resume_settlement_state_hash: checkpoint settlement-state content hash.
        resume_runtime_state_json: checkpoint runtime-state JSON evidence.
        resume_runtime_state_hash: checkpoint runtime-state content hash.

    Returns:
        包含 run_id, status, total_return 的结果字典.

    """
    cost_cfg = _deserialize_cost_config(cost_config)
    fee_model = build_fee_model(cost_cfg)
    slippage_model = build_slippage_model(cost_cfg)

    config = BacktestServiceConfig(
        strategy_id=strategy_id,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        parameter_overrides=parameter_overrides,
        parent_run_id=parent_run_id,
        resume_from_run_id=resume_from_run_id,
        resume_checkpoint_trade_date=resume_checkpoint_trade_date,
        resume_checkpoint_completed_days=resume_checkpoint_completed_days,
        resume_checkpoint_total_days=resume_checkpoint_total_days,
        resume_checkpoint_nav=resume_checkpoint_nav,
        resume_checkpoint_order_count=resume_checkpoint_order_count,
        resume_checkpoint_fill_count=resume_checkpoint_fill_count,
        resume_account_state_json=resume_account_state_json,
        resume_account_state_hash=resume_account_state_hash,
        resume_settlement_state_json=resume_settlement_state_json,
        resume_settlement_state_hash=resume_settlement_state_hash,
        resume_runtime_state_json=resume_runtime_state_json,
        resume_runtime_state_hash=resume_runtime_state_hash,
    )

    with create_strategy_bundle() as bundle:
        writer = bundle.run_writer

        try:
            options = BacktestServiceOptions(
                run_service=bundle.run_service,
                fee_model=fee_model,
                slippage_model=slippage_model,
                allow_experimental_data=allow_experimental_data,
            )

            report = bundle.strategy_facade.run_backtest_from_catalog(
                config=config,
                options=options,
            )

            total_return = compute_total_return(
                initial_cash=report.initial_cash,
                final_nav=report.final_nav,
            )

            # 从 RunRecord 读取实际状态（service 内部可能已标记 cancelled）
            actual_status: str = RunStatus.COMPLETED
            run_svc = bundle.run_service
            if run_svc is not None:
                record = run_svc.get_run(run_id)
                if record is not None and record.status == RunStatus.CANCELLED:
                    actual_status = RunStatus.CANCELLED
            elif writer is not None:
                writer.update_status(run_id, _status_str(RunStatus.COMPLETED))

            return {
                "run_id": run_id,
                "status": actual_status,
                "total_return": total_return,
            }
        except Exception as exc:
            if writer is not None:
                writer.update_status(
                    run_id,
                    _status_str(RunStatus.FAILED),
                    error_message=str(exc),
                )
            raise


def _deserialize_cost_config(
    raw: dict[str, object] | None,
) -> CostConfig | None:
    """将 dict 反序列化为 CostConfig dataclass."""
    if raw is None:
        return None
    defaults = CostConfig()
    return CostConfig(
        commission_rate=_get_float(raw, "commission_rate", defaults.commission_rate),
        commission_min=_get_float(raw, "commission_min", defaults.commission_min),
        stamp_duty_rate=_get_float(raw, "stamp_duty_rate", defaults.stamp_duty_rate),
        slippage_bps=_get_float(raw, "slippage_bps", defaults.slippage_bps),
        impact_model=_get_impact_model(raw, "impact_model", defaults.impact_model),
    )


def _get_float(data: dict[str, object], key: str, default: float) -> float:
    """从 dict 安全提取 float 值."""
    val = data.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return default


def _get_impact_model(
    data: dict[str, object],
    key: str,
    default: ImpactModel,
) -> ImpactModel:
    """
    从 dict 安全提取 impact_model 值.

    Raises:
        ValueError: 值不为空且不是合法值时抛出.

    """
    val = data.get(key)
    if val is None:
        return default
    if isinstance(val, str):
        try:
            return ImpactModel(val)
        except ValueError:
            msg = (
                f"非法 impact_model 值: {val!r}, "
                f"合法值: {[m.value for m in ImpactModel]}"
            )
            raise ValueError(msg) from None
    return default
