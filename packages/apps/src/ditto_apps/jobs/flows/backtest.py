"""
异步回测 Flow — Prefect 编排.

通过 Prefect Worker 执行回测，委托 BacktestService 管理状态机
PENDING→RUNNING→COMPLETED/FAILED，支持自动重试。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

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


@dataclass(frozen=True)
class BacktestFlowRequest:
    """Serializable request for one backend backtest job flow."""

    run_id: str
    strategy_id: str
    start_date: str
    end_date: str
    initial_cash: float = DEFAULT_INITIAL_CASH
    parameter_overrides: tuple[str, ...] = ()
    cost_config: dict[str, object] | None = None
    allow_experimental_data: bool = False
    parent_run_id: str = ""
    resume_from_run_id: str = ""
    resume_checkpoint_trade_date: str = ""
    resume_checkpoint_completed_days: int = 0
    resume_checkpoint_total_days: int = 0
    resume_checkpoint_nav: float = 0.0
    resume_checkpoint_order_count: int = 0
    resume_checkpoint_fill_count: int = 0
    resume_account_state_json: str = ""
    resume_account_state_hash: str = ""
    resume_settlement_state_json: str = ""
    resume_settlement_state_hash: str = ""
    resume_runtime_state_json: str = ""
    resume_runtime_state_hash: str = ""

    @classmethod
    def from_mapping(cls, params: Mapping[str, object]) -> BacktestFlowRequest:
        """Build a request from Prefect/API wire parameters."""
        return cls(
            run_id=_required_str(params, "run_id"),
            strategy_id=_required_str(params, "strategy_id"),
            start_date=_required_str(params, "start_date"),
            end_date=_required_str(params, "end_date"),
            initial_cash=_float_param(params, "initial_cash", DEFAULT_INITIAL_CASH),
            parameter_overrides=_tuple_str_param(params.get("parameter_overrides")),
            cost_config=_cost_config_param(params.get("cost_config")),
            allow_experimental_data=_bool_param(
                params,
                "allow_experimental_data",
                False,
            ),
            parent_run_id=_str_param(params, "parent_run_id"),
            resume_from_run_id=_str_param(params, "resume_from_run_id"),
            resume_checkpoint_trade_date=_str_param(
                params,
                "resume_checkpoint_trade_date",
            ),
            resume_checkpoint_completed_days=_int_param(
                params,
                "resume_checkpoint_completed_days",
            ),
            resume_checkpoint_total_days=_int_param(
                params,
                "resume_checkpoint_total_days",
            ),
            resume_checkpoint_nav=_float_param(
                params,
                "resume_checkpoint_nav",
                0.0,
            ),
            resume_checkpoint_order_count=_int_param(
                params,
                "resume_checkpoint_order_count",
            ),
            resume_checkpoint_fill_count=_int_param(
                params,
                "resume_checkpoint_fill_count",
            ),
            resume_account_state_json=_str_param(params, "resume_account_state_json"),
            resume_account_state_hash=_str_param(params, "resume_account_state_hash"),
            resume_settlement_state_json=_str_param(
                params,
                "resume_settlement_state_json",
            ),
            resume_settlement_state_hash=_str_param(
                params,
                "resume_settlement_state_hash",
            ),
            resume_runtime_state_json=_str_param(params, "resume_runtime_state_json"),
            resume_runtime_state_hash=_str_param(params, "resume_runtime_state_hash"),
        )


BacktestFlowInput = BacktestFlowRequest | Mapping[str, object] | None


def _status_str(status: RunStatus) -> str:
    """RunStatus → str，供 writer.update_status 等接受 str 的接口使用."""
    return status.value


@flow(
    name="run-backtest",
    description="异步回测执行 — BacktestService 状态机管理",
    retries=1,
    retry_delay_seconds=10,
)
def run_backtest_flow(
    request: BacktestFlowInput = None,
    **wire_params: object,
) -> dict[str, object]:
    """
    异步执行回测.

    BacktestService 内部管理状态机: PENDING → RUNNING → COMPLETED / FAILED.
    run_service 通过 BacktestServiceOptions 传递给 BacktestService。

    Args:
        request: typed flow request or mapping of wire parameters.
        wire_params: legacy keyword wire parameters kept for API/backward compatibility.

    Returns:
        包含 run_id, status, total_return 的结果字典.

    """
    flow_request = _normalize_flow_request(request, wire_params)
    cost_cfg = _deserialize_cost_config(flow_request.cost_config)
    fee_model = build_fee_model(cost_cfg)
    slippage_model = build_slippage_model(cost_cfg)

    config = BacktestServiceConfig(
        strategy_id=flow_request.strategy_id,
        run_id=flow_request.run_id,
        start_date=flow_request.start_date,
        end_date=flow_request.end_date,
        initial_cash=flow_request.initial_cash,
        parameter_overrides=flow_request.parameter_overrides,
        parent_run_id=flow_request.parent_run_id,
        resume_from_run_id=flow_request.resume_from_run_id,
        resume_checkpoint_trade_date=flow_request.resume_checkpoint_trade_date,
        resume_checkpoint_completed_days=flow_request.resume_checkpoint_completed_days,
        resume_checkpoint_total_days=flow_request.resume_checkpoint_total_days,
        resume_checkpoint_nav=flow_request.resume_checkpoint_nav,
        resume_checkpoint_order_count=flow_request.resume_checkpoint_order_count,
        resume_checkpoint_fill_count=flow_request.resume_checkpoint_fill_count,
        resume_account_state_json=flow_request.resume_account_state_json,
        resume_account_state_hash=flow_request.resume_account_state_hash,
        resume_settlement_state_json=flow_request.resume_settlement_state_json,
        resume_settlement_state_hash=flow_request.resume_settlement_state_hash,
        resume_runtime_state_json=flow_request.resume_runtime_state_json,
        resume_runtime_state_hash=flow_request.resume_runtime_state_hash,
    )

    with create_strategy_bundle() as bundle:
        writer = bundle.run_writer

        try:
            options = BacktestServiceOptions(
                run_service=bundle.run_service,
                fee_model=fee_model,
                slippage_model=slippage_model,
                allow_experimental_data=flow_request.allow_experimental_data,
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
                record = run_svc.get_run(flow_request.run_id)
                if record is not None and record.status == RunStatus.CANCELLED:
                    actual_status = RunStatus.CANCELLED
            elif writer is not None:
                writer.update_status(
                    flow_request.run_id,
                    _status_str(RunStatus.COMPLETED),
                )

            return {
                "run_id": flow_request.run_id,
                "status": actual_status,
                "total_return": total_return,
            }
        except Exception as exc:
            if writer is not None:
                writer.update_status(
                    flow_request.run_id,
                    _status_str(RunStatus.FAILED),
                    error_message=str(exc),
                )
            raise


def _normalize_flow_request(
    request: BacktestFlowInput,
    wire_params: Mapping[str, object],
) -> BacktestFlowRequest:
    """Normalize typed and legacy Prefect/API inputs into one request."""
    if isinstance(request, BacktestFlowRequest):
        if wire_params:
            msg = "BacktestFlowRequest cannot be combined with keyword wire params"
            raise ValueError(msg)
        return request
    if request is None:
        return BacktestFlowRequest.from_mapping(wire_params)
    merged: dict[str, object] = dict(request)
    merged.update(wire_params)
    return BacktestFlowRequest.from_mapping(merged)


def _required_str(params: Mapping[str, object], key: str) -> str:
    """Read a required string flow parameter."""
    value = params[key]
    if value is None:
        msg = f"Missing required backtest flow parameter: {key}"
        raise ValueError(msg)
    return str(value)


def _str_param(params: Mapping[str, object], key: str, default: str = "") -> str:
    """Read an optional string flow parameter."""
    value = params.get(key)
    if value is None:
        return default
    return str(value)


def _int_param(params: Mapping[str, object], key: str, default: int = 0) -> int:
    """Read an optional integer flow parameter."""
    value = params.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return default


def _float_param(params: Mapping[str, object], key: str, default: float) -> float:
    """Read an optional float flow parameter."""
    value = params.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        return float(value)
    return default


def _bool_param(params: Mapping[str, object], key: str, default: bool) -> bool:
    """Read an optional bool flow parameter."""
    value = params.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return default


def _tuple_str_param(raw: object) -> tuple[str, ...]:
    """Read parameter overrides from wire input."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, tuple):
        tuple_items = cast(tuple[object, ...], raw)
        return tuple(str(item) for item in tuple_items)
    if isinstance(raw, list):
        list_items = cast(list[object], raw)
        return tuple(str(item) for item in list_items)
    return ()


def _cost_config_param(raw: object) -> dict[str, object] | None:
    """Read serialized cost config from wire input."""
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        mapping = cast(Mapping[object, object], raw)
        return {str(key): value for key, value in mapping.items()}
    return None


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
