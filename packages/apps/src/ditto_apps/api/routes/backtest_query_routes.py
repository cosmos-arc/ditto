"""
回测查询路由 — 列表/详情/成交/审计/报告/血统/重放/NAV/基准.

端点:
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
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppError
from ditto_application.processes.execution.replay_process import ReplayProcess
from ditto_application.queries.backtest import BacktestQueryFacade, RunSummary
from ditto_application.queries.backtest_trade import TradeRecord
from ditto_application.queries.lineage import LineageQueryFacade
from fastapi import APIRouter, Depends, Query

from ditto_apps.api.deps import paginate, pagination_params
from ditto_apps.api.errors import NotFoundError, raise_business_error
from ditto_apps.models.backtest import (
    AuditRecordResponse,
    BacktestReportResponse,
    BenchmarkNavResponse,
    NavPointResponse,
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

router = APIRouter()


# ---------------------------------------------------------------------------
# Mappers (App DTO -> API Response)
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
# Lineage / Replay
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
    except (AppError, ValueError) as exc:
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
