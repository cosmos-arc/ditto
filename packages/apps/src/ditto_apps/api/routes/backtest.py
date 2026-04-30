"""
回测 API 路由.

端点:
- POST   /backtests/runs                    触发回测
- POST   /backtests/runs/{id}/cancel         取消回测
- POST   /backtests/runs/{id}/retry          重试回测
- GET    /backtests/runs                     列出运行记录
- GET    /backtests/runs/{id}                获取运行详情
- GET    /backtests/runs/{id}/trades         成交明细
- GET    /backtests/runs/{id}/audit          审计记录
- GET    /backtests/runs/{id}/report         回测报告
- GET    /backtests/runs/{id}/lineage        运行血统
- POST   /backtests/runs/{id}/replay         重放验证
- GET    /backtests/runs/{id}/nav            NAV 序列
- GET    /backtests/runs/{id}/benchmark      基准 NAV
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from typing import Annotated, Any, cast

import orjson as _orjson
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.command.backtest import (
    BacktestRunCommand,
    BacktestRunHandler,
    BacktestRunResult,
    CancelRunCommand,
    CancelRunHandler,
    CostConfig,
    RetryRunCommand,
    RetryRunHandler,
)
from ditto_application.process.execution.replay_process import ReplayProcess
from ditto_application.process.execution.strategy_types import RunLifecycleService
from ditto_application.query.backtest import BacktestQueryFacade, RunSummary
from ditto_application.query.backtest_trade import TradeRecord
from ditto_application.query.lineage import LineageQueryFacade
from ditto_kernel.strategy import RunStatus
from fastapi import APIRouter, Depends, Query
from loguru import logger

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import (
    APIError,
    NotFoundError,
    raise_business_error,
)
from ditto_apps.jobs.flows.backtest import run_backtest_flow
from ditto_apps.models.backtest import (
    AuditRecordResponse,
    BacktestReportResponse,
    BacktestRunTriggerResponse,
    BenchmarkNavResponse,
    CancelRunResponse,
    CreateBacktestRunRequest,
    NavPointResponse,
    RetryRunResponse,
    RunResponse,
    TradeResponse,
    to_audit_record_response,
)
from ditto_apps.models.common import (
    APIResponse,
    PaginationRequest,
)
from ditto_apps.models.lineage import (
    LineageResponse,
    ManifestDiffResponse,
    ReplayResponse,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


# ---------------------------------------------------------------------------
# Mappers (App DTO → API Response)
# ---------------------------------------------------------------------------


def to_run_response(summary: RunSummary) -> RunResponse:
    """将 App RunSummary 转为 API 响应."""
    return RunResponse(
        run_id=summary.run_id,
        strategy_id=summary.strategy_id,
        strategy_version=summary.strategy_version,
        mode=summary.mode,
        status=summary.status,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        error_message=summary.error_message,
        parent_run_id=summary.parent_run_id,
        progress_pct=summary.progress_pct,
        current_step=summary.current_step,
        completed_days=summary.completed_days,
        total_days=summary.total_days,
    )


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


# V1 使用进程内同步执行，远程 Worker 异步提交待后续迭代实现。


def _run_backtest_flow(
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
        cost_config=_to_cost_config(body),
    )

    try:
        result = await asyncio.to_thread(handler.handle, command)
    except ValueError as exc:
        raise_business_error(exc)

    # 后台提交 flow（不阻塞响应）
    flow_params = _build_flow_params(command, result)
    on_failure = _make_failure_callback(run_service)
    asyncio.get_running_loop().run_in_executor(
        None,
        _run_backtest_flow,
        flow_params,
        on_failure,
    )

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
        await asyncio.to_thread(handler.handle, CancelRunCommand(run_id=run_id))
    except ValueError as exc:
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
        new_run_id = await asyncio.to_thread(
            handler.handle,
            RetryRunCommand(run_id=run_id),
        )
    except ValueError as exc:
        raise_business_error(exc, default_conflict=True)

    # 获取 strategy_id + config_json 用于 flow 提交
    record = await asyncio.to_thread(facade.get_run, new_run_id)
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
        flow_params.update(_restore_flow_params_from_config(record.config_json))
    on_failure = _make_failure_callback(run_service)
    asyncio.get_running_loop().run_in_executor(
        None,
        _run_backtest_flow,
        flow_params,
        on_failure,
    )

    return APIResponse(
        data=RetryRunResponse(
            run_id=new_run_id,
            parent_run_id=run_id,
            status=RunStatus.PENDING,
        ),
    )


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=APIResponse[list[RunResponse]])
@inject
async def list_runs(
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    strategy_id: str | None = Query(None, description="策略 ID"),
    status: str | None = Query(None, description="运行状态筛选"),
    start_date: str | None = Query(None, description="起始日期(含)"),
    end_date: str | None = Query(None, description="结束日期(含)"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[RunResponse]]:
    """列出回测运行记录."""
    summaries = await asyncio.to_thread(
        facade.list_runs,
        strategy_id=strategy_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return paginate([to_run_response(s) for s in summaries], pagination)


@router.get("/runs/{run_id}", response_model=APIResponse[RunResponse])
@inject
async def get_run(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> APIResponse[RunResponse]:
    """获取回测运行详情."""
    summary = await asyncio.to_thread(facade.get_run, run_id)
    if summary is None:
        raise NotFoundError(f"Run not found: {run_id}")
    return APIResponse(data=to_run_response(summary))


@router.get("/runs/{run_id}/trades", response_model=APIResponse[list[TradeResponse]])
@inject
async def get_trades(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    start_date: str | None = Query(None, description="起始日期(含)"),
    end_date: str | None = Query(None, description="结束日期(含)"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[TradeResponse]]:
    """获取回测成交明细."""
    records = await asyncio.to_thread(
        facade.get_trades,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
    )
    return paginate([to_trade_response(r) for r in records], pagination)


@router.get(
    "/runs/{run_id}/audit",
    response_model=APIResponse[list[AuditRecordResponse]],
)
@inject
async def get_audit(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
    record_type: str | None = Query(None, description="审计记录类型筛选"),
    start_date: str | None = Query(None, description="起始日期(含)"),
    end_date: str | None = Query(None, description="结束日期(含)"),
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


@router.get(
    "/runs/{run_id}/report",
    response_model=APIResponse[BacktestReportResponse],
)
@inject
async def get_report(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> APIResponse[BacktestReportResponse]:
    """获取回测报告 (backtest_report.json 元数据)."""
    report = await asyncio.to_thread(facade.get_report, run_id)
    if report is None:
        raise NotFoundError(f"Report not found for run: {run_id}")
    return APIResponse(data=BacktestReportResponse.model_validate(report))


# ---------------------------------------------------------------------------
# Phase 3: Lineage / Replay
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/lineage", response_model=APIResponse[LineageResponse])
@inject
async def get_lineage(
    run_id: str,
    lineage_facade: Annotated[LineageQueryFacade, FromComponent()],
) -> APIResponse[LineageResponse]:
    """查询运行血统链 — 从当前运行追溯到原始运行."""
    chain = await asyncio.to_thread(lineage_facade.get_lineage, run_id)
    if chain is None:
        raise NotFoundError(f"Run not found: {run_id}")
    runs = [to_run_response(s) for s in chain.runs]
    return APIResponse(data=LineageResponse(runs=runs, depth=chain.depth))


@router.post("/runs/{run_id}/replay", response_model=APIResponse[ReplayResponse])
@inject
async def replay_run(
    run_id: str,
    replay_process: Annotated[ReplayProcess, FromComponent()],
) -> APIResponse[ReplayResponse]:
    """基于原始 manifest 重放回测并验证复现性."""
    try:
        result = await asyncio.to_thread(replay_process.replay, run_id)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise_business_error(exc)

    validation = result.validation
    return APIResponse(
        data=ReplayResponse(
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
        ),
    )


# ---------------------------------------------------------------------------
# NAV
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/nav", response_model=APIResponse[list[NavPointResponse]])
@inject
async def get_nav_series(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> APIResponse[list[NavPointResponse]]:
    """获取回测 NAV 序列."""
    nav_series = await asyncio.to_thread(facade.get_nav_series, run_id)
    return APIResponse(
        data=[NavPointResponse.model_validate(item) for item in nav_series]
    )


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
        raise NotFoundError(f"No benchmark data for run: {run_id}")

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
