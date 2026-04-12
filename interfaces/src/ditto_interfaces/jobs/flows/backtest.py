"""
异步回测 Flow — Prefect 编排.

通过 Prefect Worker 执行回测，委托 BacktestService 管理状态机
PENDING→RUNNING→COMPLETED/FAILED，支持自动重试。
"""

from __future__ import annotations

from ditto_app.command.backtest import CostConfig
from ditto_app.process.execution.backtest_process import (
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_app.process.execution.fee_override import build_fee_model
from ditto_engine.backtest.statistics import BacktestReport
from ditto_engine.execution.reality.constants import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_MIN_COMMISSION,
)
from prefect import flow

from ditto_interfaces.registry.contexts.strategy import create_strategy_bundle


@flow(
    name="run-backtest",
    description="异步回测执行 — BacktestService 状态机管理",
    retries=1,
    retry_delay_seconds=10,
)
def run_backtest_flow(
    *,
    run_id: str,
    strategy_id: str,
    start_date: str,
    end_date: str,
    initial_cash: float = 1_000_000.0,
    parameter_overrides: tuple[str, ...] = (),
    cost_config: dict[str, object] | None = None,
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

    Returns:
        包含 run_id, status, total_return 的结果字典.

    """
    cost_cfg = _deserialize_cost_config(cost_config)
    fee_model = build_fee_model(cost_cfg)

    config = BacktestServiceConfig(
        strategy_id=strategy_id,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        parameter_overrides=parameter_overrides,
    )

    with create_strategy_bundle() as bundle:
        writer = bundle.run_writer
        if writer is not None:
            writer.update_status(run_id, "running")

        try:
            options = BacktestServiceOptions(
                run_service=bundle.run_service,
                fee_model=fee_model,
            )

            report: BacktestReport = bundle.strategy_facade.run_backtest_from_catalog(
                config=config,
                options=options,
            )

            total_return = _compute_total_return(report)

            if writer is not None:
                writer.update_status(run_id, "completed")

            return {
                "run_id": run_id,
                "status": "completed",
                "total_return": total_return,
            }
        except Exception as exc:
            if writer is not None:
                writer.update_status(run_id, "failed", error_message=str(exc))
            raise


def _deserialize_cost_config(
    raw: dict[str, object] | None,
) -> CostConfig | None:
    """将 dict 反序列化为 CostConfig dataclass."""
    if raw is None:
        return None
    return CostConfig(
        commission_rate=_get_float(raw, "commission_rate", DEFAULT_COMMISSION_RATE),
        commission_min=_get_float(raw, "commission_min", DEFAULT_MIN_COMMISSION),
        stamp_duty_rate=_get_float(raw, "stamp_duty_rate", 0.001),
        slippage_bps=_get_float(raw, "slippage_bps", 1.0),
        impact_model=_get_str(raw, "impact_model", "none"),
    )


def _get_float(data: dict[str, object], key: str, default: float) -> float:
    """从 dict 安全提取 float 值."""
    val = data.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return default


def _get_str(data: dict[str, object], key: str, default: str) -> str:
    """从 dict 安全提取 str 值."""
    val = data.get(key)
    if isinstance(val, str):
        return val
    return default


def _compute_total_return(report: BacktestReport) -> float:
    """从 BacktestReport 计算总收益率."""
    if report.initial_cash > 0:
        return report.final_nav / report.initial_cash - 1
    return 0.0
