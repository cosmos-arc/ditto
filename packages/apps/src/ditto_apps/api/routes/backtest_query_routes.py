"""
回测查询路由 — 列表/详情/成交/审计/报告/血统/重放/NAV/基准.

端点:
- GET    /backtests/runs                     列出运行记录
- GET    /backtests/runs/{id}                获取运行详情
- GET    /backtests/runs/{id}/trades         成交明细
- GET    /backtests/runs/{id}/audit          审计记录
- GET    /backtests/runs/{id}/report         回测报告
- GET    /backtests/runs/{id}/lineage        运行血统
- GET    /backtests/runs/{id}/lineage/data   运行级数据血缘
- GET    /backtests/runs/{id}/lineage/catalog-report 运行级数据血缘 + Catalog 证据
- GET    /backtests/lineage/events           数据血缘事件查询
- GET    /backtests/lineage/graph            数据血缘图查询
- POST   /backtests/runs/{id}/replay         重放验证
- GET    /backtests/runs/{id}/replay/proof   重放 proof 证据
- GET    /backtests/runs/{id}/replay/evidence 恢复/重放证据摘要
- GET    /backtests/runs/{id}/nav            NAV 序列
- GET    /backtests/runs/{id}/benchmark      基准 NAV
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppError
from ditto_application.processes.execution.replay_process import ReplayProcess
from ditto_application.queries.backtest import (
    BacktestQueryFacade,
    ReplayEvidenceSummary,
    RunSummary,
)
from ditto_application.queries.backtest_trade import TradeRecord
from ditto_application.queries.lineage import (
    DataLineageAsset,
    DataLineageCatalogAsset,
    DataLineageCatalogRunReport,
    DataLineageEvent,
    DataLineageGraph,
    DataLineageGraphEdge,
    DataLineageRef,
    DataLineageRunSummary,
    LineageQueryFacade,
)
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
    DataLineageAssetResponse,
    DataLineageCatalogAssetResponse,
    DataLineageCatalogRunReportResponse,
    DataLineageEventResponse,
    DataLineageGraphEdgeResponse,
    DataLineageGraphResponse,
    DataLineageRefResponse,
    DataLineageRunResponse,
    LineageResponse,
    ManifestDiffResponse,
    ReplayEvidenceSummaryResponse,
    ReplayProofResponse,
    ReplayResponse,
)

router = APIRouter()


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


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


def to_data_lineage_asset_response(
    asset: DataLineageAsset,
) -> DataLineageAssetResponse:
    """将 DataLineageAsset 转为 API 响应."""
    return DataLineageAssetResponse(
        dataset_id=asset.dataset_id,
        namespace=asset.namespace,
        partition_keys=list(asset.partition_keys),
    )


def to_data_lineage_ref_response(ref: DataLineageRef) -> DataLineageRefResponse:
    """将 DataLineageRef 转为 API 响应."""
    return DataLineageRefResponse(
        asset=to_data_lineage_asset_response(ref.asset),
        role=ref.role,
    )


def to_data_lineage_event_response(
    event: DataLineageEvent,
) -> DataLineageEventResponse:
    """将 DataLineageEvent 转为 API 响应."""
    return DataLineageEventResponse(
        run_id=event.run_id,
        operation=event.operation,
        timestamp=event.timestamp.isoformat(),
        inputs=[to_data_lineage_ref_response(ref) for ref in event.inputs],
        outputs=[to_data_lineage_ref_response(ref) for ref in event.outputs],
    )


def to_data_lineage_run_response(
    summary: DataLineageRunSummary,
) -> DataLineageRunResponse:
    """将 DataLineageRunSummary 转为 API 响应."""
    return DataLineageRunResponse(
        run_id=summary.run_id,
        events=[to_data_lineage_event_response(event) for event in summary.events],
        input_assets=[
            to_data_lineage_asset_response(asset) for asset in summary.input_assets
        ],
        output_assets=[
            to_data_lineage_asset_response(asset) for asset in summary.output_assets
        ],
    )


def to_data_lineage_catalog_asset_response(
    asset: DataLineageCatalogAsset,
) -> DataLineageCatalogAssetResponse:
    """将 DataLineageCatalogAsset 转为 API 响应."""
    return DataLineageCatalogAssetResponse(
        asset=to_data_lineage_asset_response(asset.asset),
        catalog_status=asset.catalog_status,
        storage_uri=asset.storage_uri,
        source=asset.source,
        schema_hash=asset.schema_hash,
        row_count=asset.row_count,
        schema_created_at=(
            asset.schema_created_at.isoformat()
            if asset.schema_created_at is not None
            else None
        ),
        freshness_at=(
            asset.freshness_at.isoformat() if asset.freshness_at is not None else None
        ),
    )


def to_data_lineage_catalog_run_report_response(
    report: DataLineageCatalogRunReport,
) -> DataLineageCatalogRunReportResponse:
    """将 DataLineageCatalogRunReport 转为 API 响应."""
    return DataLineageCatalogRunReportResponse(
        run_id=report.run_id,
        events=[to_data_lineage_event_response(event) for event in report.events],
        input_assets=[
            to_data_lineage_catalog_asset_response(asset)
            for asset in report.input_assets
        ],
        output_assets=[
            to_data_lineage_catalog_asset_response(asset)
            for asset in report.output_assets
        ],
    )


def to_data_lineage_graph_edge_response(
    edge: DataLineageGraphEdge,
) -> DataLineageGraphEdgeResponse:
    """将 DataLineageGraphEdge 转为 API 响应."""
    return DataLineageGraphEdgeResponse(
        source=to_data_lineage_asset_response(edge.source),
        target=to_data_lineage_asset_response(edge.target),
        event=to_data_lineage_event_response(edge.event),
    )


def to_data_lineage_graph_response(graph: DataLineageGraph) -> DataLineageGraphResponse:
    """将 DataLineageGraph 转为 API 响应."""
    return DataLineageGraphResponse(
        root=to_data_lineage_asset_response(graph.root),
        direction=graph.direction,
        max_depth=graph.max_depth,
        assets=[to_data_lineage_asset_response(asset) for asset in graph.assets],
        events=[to_data_lineage_event_response(event) for event in graph.events],
        edges=[to_data_lineage_graph_edge_response(edge) for edge in graph.edges],
    )


def to_replay_evidence_summary_response(
    summary: ReplayEvidenceSummary,
) -> ReplayEvidenceSummaryResponse:
    """将 App replay evidence summary 转为 API 响应."""
    return ReplayEvidenceSummaryResponse(
        run_id=summary.run_id,
        original_run_id=summary.original_run_id,
        replay_run_id=summary.replay_run_id,
        is_reproducible=summary.is_reproducible,
        input_data_match=summary.input_data_match,
        fill_match=summary.fill_match,
        account_state_match=summary.account_state_match,
        report_resume_provenance=summary.report_resume_provenance,
        proof_resume_provenance=summary.proof_resume_provenance,
        resume_provenance_match=summary.resume_provenance_match,
        missing_sections=list(summary.missing_sections),
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
    summaries = await run_blocking(
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
    summary = await run_blocking(facade.get_run, run_id)
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
    records = await run_blocking(
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
    rows = await run_blocking(
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
    report = await run_blocking(facade.get_report, run_id)
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
    chain = await run_blocking(lineage_facade.get_lineage, run_id)
    if chain is None:
        raise NotFoundError(f"Run not found: {run_id}")
    runs = [to_run_response(s) for s in chain.runs]
    return APIResponse(data=LineageResponse(runs=runs, depth=chain.depth))


@router.get(
    "/lineage/events",
    response_model=APIResponse[list[DataLineageEventResponse]],
)
@inject
async def get_data_lineage_events(
    lineage_facade: Annotated[LineageQueryFacade, FromComponent()],
    namespace: str = Query(..., description="资产命名空间"),
    dataset_id: str = Query(..., description="数据集 ID"),
    partition_keys: list[str] | None = Query(None, description="资产分区键"),
    pagination: PaginationRequest = Depends(pagination_params),
) -> APIResponse[list[DataLineageEventResponse]]:
    """查询某个数据资产关联的 lineage 事件."""
    events = await run_blocking(
        lineage_facade.list_data_events_for_asset,
        namespace=namespace,
        dataset_id=dataset_id,
        partition_keys=tuple(partition_keys or ()),
    )
    return paginate(
        [to_data_lineage_event_response(event) for event in events],
        pagination,
    )


@router.get(
    "/lineage/graph",
    response_model=APIResponse[DataLineageGraphResponse],
)
@inject
async def get_data_lineage_graph(
    lineage_facade: Annotated[LineageQueryFacade, FromComponent()],
    namespace: str = Query(..., description="资产命名空间"),
    dataset_id: str = Query(..., description="数据集 ID"),
    partition_keys: list[str] | None = Query(None, description="资产分区键"),
    direction: str = Query(
        "both",
        description="遍历方向: upstream / downstream / both",
        pattern="^(upstream|downstream|both)$",
    ),
    max_depth: int = Query(3, ge=0, le=20, description="最大遍历深度"),
) -> APIResponse[DataLineageGraphResponse]:
    """查询某个数据资产的 upstream/downstream lineage 图."""
    graph = await run_blocking(
        lineage_facade.get_data_lineage_graph_for_asset,
        namespace=namespace,
        dataset_id=dataset_id,
        partition_keys=tuple(partition_keys or ()),
        direction=direction,
        max_depth=max_depth,
    )
    return APIResponse(data=to_data_lineage_graph_response(graph))


@router.get(
    "/runs/{run_id}/lineage/data",
    response_model=APIResponse[DataLineageRunResponse],
)
@inject
async def get_run_data_lineage(
    run_id: str,
    lineage_facade: Annotated[LineageQueryFacade, FromComponent()],
) -> APIResponse[DataLineageRunResponse]:
    """查询某个运行关联的数据血缘摘要."""
    summary = await run_blocking(lineage_facade.get_data_lineage_for_run, run_id)
    return APIResponse(data=to_data_lineage_run_response(summary))


@router.get(
    "/runs/{run_id}/lineage/catalog-report",
    response_model=APIResponse[DataLineageCatalogRunReportResponse],
)
@inject
async def get_run_data_lineage_catalog_report(
    run_id: str,
    lineage_facade: Annotated[LineageQueryFacade, FromComponent()],
) -> APIResponse[DataLineageCatalogRunReportResponse]:
    """查询某个运行的数据血缘和精确 DataCatalog 证据报告."""
    report = await run_blocking(
        lineage_facade.get_data_lineage_catalog_report_for_run,
        run_id,
    )
    return APIResponse(data=to_data_lineage_catalog_run_report_response(report))


@router.post("/runs/{run_id}/replay", response_model=APIResponse[ReplayResponse])
@inject
async def replay_run(
    run_id: str,
    replay_process: Annotated[ReplayProcess, FromComponent()],
) -> APIResponse[ReplayResponse]:
    """基于原始 manifest 重放回测并验证复现性."""
    try:
        result = await run_blocking(replay_process.replay, run_id)
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


@router.get(
    "/runs/{run_id}/replay/proof",
    response_model=APIResponse[ReplayProofResponse],
)
@inject
async def get_replay_proof(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> APIResponse[ReplayProofResponse]:
    """获取 replay proof 证据 JSON."""
    proof = await run_blocking(facade.get_replay_proof, run_id)
    if proof is None:
        raise NotFoundError(f"Replay proof not found for run: {run_id}")
    return APIResponse(data=ReplayProofResponse.model_validate(proof))


@router.get(
    "/runs/{run_id}/replay/evidence",
    response_model=APIResponse[ReplayEvidenceSummaryResponse],
)
@inject
async def get_replay_evidence_summary(
    run_id: str,
    facade: Annotated[BacktestQueryFacade, FromComponent()],
) -> APIResponse[ReplayEvidenceSummaryResponse]:
    """获取 restored-run report 与 replay proof 的组合证据摘要."""
    summary = await run_blocking(facade.get_replay_evidence_summary, run_id)
    if summary is None:
        raise NotFoundError(f"Replay evidence not found for run: {run_id}")
    return APIResponse(data=to_replay_evidence_summary_response(summary))


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
    nav_series = await run_blocking(facade.get_nav_series, run_id)
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
    nav_series = await run_blocking(facade.get_benchmark_nav_series, run_id)
    benchmark_return = await run_blocking(facade.get_benchmark_return, run_id)

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
