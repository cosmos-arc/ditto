"""回测 API 路由."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from collections.abc import Callable
from typing import Annotated

import orjson as _orjson
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.command.backtest import (
    BacktestRunCommand,
    BacktestRunHandler,
    BacktestRunResult,
    CancelRunHandler,
    CostConfig,
    RetryRunHandler,
)
from ditto_app.process.execution.replay_process import ReplayProcess
from ditto_app.process.execution.strategy_types import RunLifecycleService
from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.backtest_trade import TradeRecord
from ditto_app.query.lineage import LineageQueryFacade
from ditto_kernel.enums import RunStatus
from fastapi import APIRouter, HTTPException, Query

from ditto_interfaces.jobs.flows.backtest import run_backtest_flow
from ditto_interfaces.models.backtest import (
    AuditRecordResponse,
    BacktestRunTriggerResponse,
    BenchmarkNavResponse,
    CancelRunResponse,
    CreateBacktestRunRequest,
    RetryRunResponse,
    RunResponse,
    TradeResponse,
    to_audit_record_response,
    to_run_response,
)
from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.lineage import (
    LineageResponse,
    ManifestDiffResponse,
    ReplayResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtests"])


def to_trade_response(record: TradeRecord) -> TradeResponse:
    """将 TradeRecord 转为 API 响应."""
    return TradeResponse(
        trade_date=record.trade_date,
        instrument_id=record.instrument_id,
        direction=record.direction,
        entry_date=record.entry_date,
        exit_date=record.exit_date,
        entry_price=record.entry_price,
        exit_price=record.exit_price,
        quantity=record.quantity,
        pnl=record.pnl,
    )


def _to_cost_config(body: CreateBacktestRunRequest) -> CostConfig | None:
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


def _build_flow_params(
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
    }
    if result.cost_config is not None:
        params["cost_config"] = dataclasses.asdict(result.cost_config)
    return params


def _submit_flow(
    params: dict[str, object],
    on_failure: Callable[[str, str], None] | None = None,
) -> None:
    """
    同步提交 Prefect flow（在 executor 线程中运行）.

    R3 骨架: 当 PREFECT_API_URL 已设置时，通过 Prefect Client 异步提交；
    否则回退到进程内执行（开发模式）。

    Args:
        params: flow 参数.
        on_failure: 异常回调 (run_id, error_message)，用于标记 RunRecord 为 failed.

    """
    run_id = str(params.get("run_id", ""))
    prefect_api_url = os.getenv("PREFECT_API_URL")

    if prefect_api_url:
        # R3: 通过 Prefect Client 提交到远程 Worker（待完整实现）
        logger.info(
            "Prefect Server available, submitting flow to worker",
            extra={"run_id": run_id, "prefect_api_url": prefect_api_url},
        )
        # TODO(R3): async with get_client() as client:
        #     await client.create_flow_run_from_deployment(
        #         deployment_name="run-backtest/backtest-prod",
        #         parameters=params,
        #     )
        # 当前仍回退到进程内执行
        _run_in_process(params, on_failure)
    else:
        # 开发模式: 进程内同步执行
        _run_in_process(params, on_failure)


def _run_in_process(
    params: dict[str, object],
    on_failure: Callable[[str, str], None] | None = None,
) -> None:
    """进程内执行 Prefect flow（开发模式 fallback）。"""
    run_id = str(params.get("run_id", ""))
    try:
        _prefect_fn = getattr(run_backtest_flow, "func", run_backtest_flow)
        _prefect_fn(**params)  # type: ignore[reportCallIssue]
    except Exception:
        logger.exception("Flow execution failed", extra={"run_id": run_id})
        if on_failure is not None:
            on_failure(run_id, "Flow execution failed")


def _restore_flow_params_from_config(
    config_json: str,
) -> dict[str, object]:
    """从 config_json 反序列化回测参数."""
    config = _orjson.loads(config_json)
    params: dict[str, object] = {}
    for key in ("start_date", "end_date", "initial_cash", "parameter_overrides"):
        if key in config:
            params[key] = config[key]
    if "cost_config" in config:
        params["cost_config"] = config["cost_config"]
    return params


def _make_failure_callback(
    run_service: RunLifecycleService,
) -> Callable[[str, str], None]:
    """创建 flow 失败回调 — 标记 RunRecord 为 failed."""

    def _on_failure(run_id: str, error_message: str) -> None:
        run_service.mark_failed(run_id, error_message)

    return _on_failure


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


@router.post("/runs", status_code=202, response_model=BacktestRunTriggerResponse)
@inject
async def trigger_backtest(
    body: CreateBacktestRunRequest,
    handler: Annotated[BacktestRunHandler, FromComponent()],
    run_service: Annotated[RunLifecycleService, FromComponent()],
) -> BacktestRunTriggerResponse:
    """触发回测 — 校验参数 + 创建记录 + 后台提交 flow，返回 202 Accepted."""
    command = BacktestRunCommand(
        strategy_id=body.strategy_id,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_cash=body.initial_cash,
        parameter_overrides=tuple(body.parameter_overrides),
        cost_config=_to_cost_config(body),
    )

    try:
        result = await asyncio.to_thread(handler.handle, command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 后台提交 flow（不阻塞响应）
    flow_params = _build_flow_params(command, result)
    on_failure = _make_failure_callback(run_service)
    asyncio.get_running_loop().run_in_executor(
        None,
        _submit_flow,
        flow_params,
        on_failure,
    )

    return BacktestRunTriggerResponse(
        run_id=result.run_id,
        strategy_id=result.strategy_id,
        status=result.status,
    )


# ---------------------------------------------------------------------------
# Cancel / Retry
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/cancel", response_model=CancelRunResponse)
@inject
async def cancel_run(
    run_id: str,
    handler: Annotated[CancelRunHandler, FromComponent()],
) -> CancelRunResponse:
    """取消回测运行 — 检查 status in {pending, running}，更新为 cancelled."""
    try:
        await asyncio.to_thread(handler.handle, run_id)
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return CancelRunResponse(run_id=run_id, status=RunStatus.CANCELLED)


@router.post("/runs/{run_id}/retry", status_code=202, response_model=RetryRunResponse)
@inject
async def retry_run(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    handler: Annotated[RetryRunHandler, FromComponent()],
    run_service: Annotated[RunLifecycleService, FromComponent()],
) -> RetryRunResponse:
    """重试回测运行 — 检查 status in {failed, cancelled}，创建新 Run 并提交 flow."""
    try:
        new_run_id = await asyncio.to_thread(handler.handle, run_id)
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # 获取 strategy_id + config_json 用于 flow 提交
    record = await asyncio.to_thread(facade.get_run, new_run_id)

    # 后台提交 flow（不阻塞响应）
    flow_params: dict[str, object] = {
        "run_id": new_run_id,
        "strategy_id": record.strategy_id if record else "",
    }
    # 从 config_json 恢复回测参数（start_date, end_date, initial_cash 等）
    if record is not None and record.config_json:
        flow_params.update(_restore_flow_params_from_config(record.config_json))
    on_failure = _make_failure_callback(run_service)
    asyncio.get_running_loop().run_in_executor(
        None,
        _submit_flow,
        flow_params,
        on_failure,
    )

    return RetryRunResponse(
        run_id=new_run_id,
        parent_run_id=run_id,
        status=RunStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=APIResponse[list[RunResponse]])
@inject
async def list_runs(
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    strategy_id: str | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> APIResponse[list[RunResponse]]:
    """列出回测运行记录."""
    records = await asyncio.to_thread(
        facade.list_runs,
        strategy_id=strategy_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    runs = [to_run_response(r) for r in records]
    return APIResponse(data=runs)


@router.get("/runs/{run_id}", response_model=RunResponse)
@inject
async def get_run(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> RunResponse:
    """获取回测运行详情."""
    record = await asyncio.to_thread(facade.get_run, run_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run not found: {run_id}",
        )
    return to_run_response(record)


@router.get("/runs/{run_id}/trades", response_model=APIResponse[list[TradeResponse]])
@inject
async def get_trades(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> APIResponse[list[TradeResponse]]:
    """获取回测成交明细."""
    records = await asyncio.to_thread(
        facade.get_trades,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    if not records:
        return APIResponse(data=[])
    trades = [to_trade_response(r) for r in records]
    return APIResponse(data=trades)


@router.get(
    "/runs/{run_id}/audit",
    response_model=APIResponse[list[AuditRecordResponse]],
)
@inject
async def get_audit(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    record_type: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> APIResponse[list[AuditRecordResponse]]:
    """获取回测审计记录."""
    rows = await asyncio.to_thread(
        facade.get_audit,
        run_id,
        record_type=record_type,
        start_date=start_date,
        end_date=end_date,
    )
    records = [to_audit_record_response(row) for row in rows]
    return APIResponse(data=records)


# ---------------------------------------------------------------------------
# Phase 3: Lineage / Replay
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/lineage", response_model=LineageResponse)
@inject
async def get_lineage(
    run_id: str,
    lineage_facade: Annotated[LineageQueryFacade, FromComponent()],
) -> LineageResponse:
    """查询运行血统链 — 从当前运行追溯到原始运行."""
    chain = await asyncio.to_thread(lineage_facade.get_lineage, run_id)
    if chain is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run not found: {run_id}",
        )
    runs = [to_run_response(r) for r in chain.runs]
    return LineageResponse(runs=runs, depth=chain.depth)


@router.post("/runs/{run_id}/replay", response_model=ReplayResponse)
@inject
async def replay_run(
    run_id: str,
    replay_process: Annotated[ReplayProcess, FromComponent()],
) -> ReplayResponse:
    """基于原始 manifest 重放回测并验证复现性."""
    try:
        result = await asyncio.to_thread(replay_process.replay, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    validation = result.validation
    return ReplayResponse(
        new_run_id=result.new_run_id,
        is_reproducible=validation.is_reproducible,
        nav_correlation=validation.nav_correlation,
        max_nav_diff_bps=validation.max_nav_diff_bps,
        manifest_diff=ManifestDiffResponse(
            config_diffs=list(validation.manifest_diff.config_diffs),
            data_diffs=list(validation.manifest_diff.data_diffs),
            version_diffs=list(validation.manifest_diff.version_diffs),
            seed_diffs=list(validation.manifest_diff.seed_diffs),
            has_diff=validation.manifest_diff.has_diff,
        ),
        input_data_match=validation.input_data_match,
    )


# ---------------------------------------------------------------------------
# NAV
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/nav", response_model=APIResponse[list[dict[str, object]]])
@inject
async def get_nav_series(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> APIResponse[list[dict[str, object]]]:
    """获取回测 NAV 序列."""
    nav_series = await asyncio.to_thread(facade.get_nav_series, run_id)
    return APIResponse(data=nav_series)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


_RESP_BENCHMARK = APIResponse[BenchmarkNavResponse]


@router.get("/runs/{run_id}/benchmark", response_model=_RESP_BENCHMARK)
@inject
async def get_benchmark(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> _RESP_BENCHMARK:
    """获取回测基准 NAV 序列与基准收益率."""
    nav_series = await asyncio.to_thread(facade.get_benchmark_nav_series, run_id)
    benchmark_return = await asyncio.to_thread(facade.get_benchmark_return, run_id)

    if nav_series is None and benchmark_return is None:
        raise HTTPException(
            status_code=404,
            detail=f"No benchmark data for run: {run_id}",
        )

    dates: list[str] = []
    navs: list[float] = []
    if nav_series is not None:
        dates = [d for d, _ in nav_series]
        navs = [v for _, v in nav_series]

    return APIResponse(
        data=BenchmarkNavResponse(
            run_id=run_id,
            dates=dates,
            navs=navs,
            benchmark_return=benchmark_return,
        ),
    )
