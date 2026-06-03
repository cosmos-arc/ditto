"""
回测运行管理路由 — trigger / cancel / retry 及其内部辅助函数.

端点:
- POST  /backtests/runs                触发回测
- POST  /backtests/runs/{id}/cancel    取消回测
- POST  /backtests/runs/{id}/retry     重试回测
- POST  /backtests/runs/{id}/resume    从 checkpoint 恢复回测
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from typing import Annotated, Any, cast

import orjson as _orjson
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.backtest import (
    BacktestRunCommand,
    BacktestRunHandler,
    BacktestRunResult,
    CancelRunCommand,
    CancelRunHandler,
    CostConfig,
    ResumeRunCommand,
    ResumeRunHandler,
    RetryRunCommand,
    RetryRunHandler,
)
from ditto_application.exceptions import AppError
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.queries.backtest import BacktestQueryFacade
from ditto_kernel.strategy import RunStatus
from fastapi import APIRouter
from loguru import logger

from ditto_apps.api.errors import (
    APIError,
    raise_business_error,
)
from ditto_apps.jobs.flows.backtest import run_backtest_flow
from ditto_apps.models.backtest import (
    BacktestRunTriggerResponse,
    CancelRunResponse,
    CreateBacktestRunRequest,
    ResumeRunResponse,
    RetryRunResponse,
)
from ditto_apps.models.common import APIResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers (exposed for backward compat via facade re-export)
# ---------------------------------------------------------------------------


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def to_cost_config(body: CreateBacktestRunRequest) -> CostConfig | None:
    """将 API CostConfigRequest 转换为 App 层 CostConfig."""
    cfg = body.cost_config
    if cfg is None:
        return None
    return CostConfig(
        commission_rate=cfg.commission_rate,
        commission_min=cfg.commission_min,
        stamp_duty_rate=cfg.stamp_duty_rate,
        slippage_bps=cfg.slippage_bps,
        impact_model=cfg.impact_model,
    )


def build_flow_params(
    command: BacktestRunCommand,
    result: BacktestRunResult,
) -> dict[str, object]:
    """从 command 和 result 构建 flow 参数（可序列化跨进程边界）."""
    params: dict[str, object] = {
        "run_id": result.run_id,
        "strategy_id": result.strategy_id,
        "start_date": command.start_date,
        "end_date": command.end_date,
        "initial_cash": command.initial_cash,
        "parameter_overrides": command.parameter_overrides,
        "allow_experimental_data": command.allow_experimental_data,
    }
    if result.cost_config is not None:
        params["cost_config"] = dataclasses.asdict(result.cost_config)
    return params


def run_backtest_flow_sync(
    params: dict[str, object],
    on_failure: Callable[[str, str], None] | None = None,
) -> None:
    """进程内执行回测 flow（V1 同步模式，绕过 Prefect engine）。"""
    run_id = str(params.get("run_id", ""))
    try:
        flow_fn = cast(
            Callable[..., Any],
            getattr(run_backtest_flow, "fn", run_backtest_flow),
        )
        flow_fn(**params)
    except Exception as exc:
        logger.exception("Flow execution failed", extra={"run_id": run_id})
        if on_failure is not None:
            on_failure(run_id, f"Flow execution failed: {exc}")


def restore_flow_params_from_config(
    config_json: str,
) -> dict[str, object]:
    """从 config_json 反序列化回测参数."""
    config = _orjson.loads(config_json)
    params: dict[str, object] = {}
    for key in (
        "start_date",
        "end_date",
        "initial_cash",
        "parameter_overrides",
        "allow_experimental_data",
        "resume_from_run_id",
        "resume_checkpoint_trade_date",
        "resume_checkpoint_completed_days",
        "resume_checkpoint_total_days",
        "resume_checkpoint_nav",
        "resume_checkpoint_order_count",
        "resume_checkpoint_fill_count",
        "resume_account_state_json",
        "resume_account_state_hash",
        "resume_settlement_state_json",
        "resume_settlement_state_hash",
        "resume_runtime_state_json",
        "resume_runtime_state_hash",
    ):
        if key in config:
            params[key] = config[key]
    if "cost_config" in config:
        params["cost_config"] = config["cost_config"]
    return params


def make_failure_callback(
    run_service: RunLifecycleService,
) -> Callable[[str, str], None]:
    """创建 flow 失败回调 — 标记 RunRecord 为 failed."""

    def _on_failure(run_id: str, error_message: str) -> None:
        run_service.mark_failed(run_id, error_message)

    return _on_failure


def submit_backtest_flow(
    *,
    flow_params: dict[str, object],
    on_failure: Callable[[str, str], None],
) -> None:
    """Submit a backtest flow without blocking the API response."""
    asyncio.get_running_loop().run_in_executor(
        None,
        run_backtest_flow_sync,
        flow_params,
        on_failure,
    )


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


@router.post(
    "/runs", status_code=202, response_model=APIResponse[BacktestRunTriggerResponse]
)
@inject
async def trigger_backtest(
    body: CreateBacktestRunRequest,
    handler: Annotated[BacktestRunHandler, FromComponent()],
    run_service: Annotated[RunLifecycleService, FromComponent()],
) -> APIResponse[BacktestRunTriggerResponse]:
    """触发回测 — 校验参数 + 创建记录 + 后台提交 flow，返回 202 Accepted."""
    command = BacktestRunCommand(
        strategy_id=body.strategy_id,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_cash=body.initial_cash,
        parameter_overrides=tuple(body.parameter_overrides),
        cost_config=to_cost_config(body),
        allow_experimental_data=body.allow_experimental_data,
    )

    try:
        result = await run_blocking(handler.handle, command)
    except (AppError, ValueError) as exc:
        raise_business_error(exc)

    # 后台提交 flow（不阻塞响应）
    flow_params = build_flow_params(command, result)
    on_failure = make_failure_callback(run_service)
    submit_backtest_flow(flow_params=flow_params, on_failure=on_failure)

    return APIResponse(
        data=BacktestRunTriggerResponse(
            run_id=result.run_id,
            strategy_id=result.strategy_id,
            status=result.status,
        ),
    )


# ---------------------------------------------------------------------------
# Cancel / Retry
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/cancel", response_model=APIResponse[CancelRunResponse])
@inject
async def cancel_run(
    run_id: str,
    handler: Annotated[CancelRunHandler, FromComponent()],
) -> APIResponse[CancelRunResponse]:
    """取消回测运行 — 检查 status in {pending, running}，更新为 cancelled."""
    try:
        await run_blocking(handler.handle, CancelRunCommand(run_id=run_id))
    except (AppError, ValueError) as exc:
        raise_business_error(exc, default_conflict=True)

    return APIResponse(
        data=CancelRunResponse(run_id=run_id, status=RunStatus.CANCELLED)
    )


@router.post(
    "/runs/{run_id}/retry",
    status_code=202,
    response_model=APIResponse[RetryRunResponse],
)
@inject
async def retry_run(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    handler: Annotated[RetryRunHandler, FromComponent()],
    run_service: Annotated[RunLifecycleService, FromComponent()],
) -> APIResponse[RetryRunResponse]:
    """重试回测运行 — 检查 status in {failed, cancelled}，创建新 Run 并提交 flow."""
    try:
        new_run_id = await run_blocking(
            handler.handle,
            RetryRunCommand(run_id=run_id),
        )
    except (AppError, ValueError) as exc:
        raise_business_error(exc, default_conflict=True)

    # 获取 strategy_id + config_json 用于 flow 提交
    record = await run_blocking(facade.get_run, new_run_id)
    if record is None:
        raise APIError(
            f"Retry created run {new_run_id} but record not found",
            status_code=500,
            error_code="INTERNAL_ERROR",
        )

    # 后台提交 flow（不阻塞响应）
    flow_params: dict[str, object] = {
        "run_id": new_run_id,
        "strategy_id": record.strategy_id,
    }
    # 从 config_json 恢复回测参数（start_date, end_date, initial_cash 等）
    if record.config_json:
        flow_params.update(restore_flow_params_from_config(record.config_json))
    on_failure = make_failure_callback(run_service)
    submit_backtest_flow(flow_params=flow_params, on_failure=on_failure)

    return APIResponse(
        data=RetryRunResponse(
            run_id=new_run_id,
            parent_run_id=run_id,
            status=RunStatus.PENDING,
        ),
    )


@router.post(
    "/runs/{run_id}/resume",
    status_code=202,
    response_model=APIResponse[ResumeRunResponse],
)
@inject
async def resume_run(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    handler: Annotated[ResumeRunHandler, FromComponent()],
    run_service: Annotated[RunLifecycleService, FromComponent()],
) -> APIResponse[ResumeRunResponse]:
    """从 latest checkpoint 恢复回测运行，创建 child run 并提交 flow."""
    try:
        new_run_id = await run_blocking(
            handler.handle,
            ResumeRunCommand(run_id=run_id),
        )
    except (AppError, ValueError) as exc:
        raise_business_error(exc, default_conflict=True)

    record = await run_blocking(facade.get_run, new_run_id)
    if record is None:
        raise APIError(
            f"Resume created run {new_run_id} but record not found",
            status_code=500,
            error_code="INTERNAL_ERROR",
        )

    flow_params: dict[str, object] = {
        "run_id": new_run_id,
        "strategy_id": record.strategy_id,
    }
    if record.config_json:
        flow_params.update(restore_flow_params_from_config(record.config_json))
    on_failure = make_failure_callback(run_service)
    submit_backtest_flow(flow_params=flow_params, on_failure=on_failure)

    return APIResponse(
        data=ResumeRunResponse(
            run_id=new_run_id,
            parent_run_id=run_id,
            status=RunStatus.PENDING,
        ),
    )
