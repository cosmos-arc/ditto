"""回测 API 路由."""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_app.process.execution.replay_process import ReplayProcess
from ditto_app.query.backtest import BacktestQueryFacade
from ditto_app.query.lineage import LineageQueryFacade
from fastapi import APIRouter, HTTPException, Query

from ditto_interfaces.models.backtest import (
    AuditRecordResponse,
    BenchmarkNavResponse,
    RunResponse,
    TradeResponse,
    to_audit_record_response,
    to_run_response,
    to_trade_response,
)
from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.lineage import (
    LineageResponse,
    ManifestDiffResponse,
    ReplayResponse,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


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
