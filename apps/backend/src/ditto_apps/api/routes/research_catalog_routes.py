"""
Research catalog REST routes — static node + factor registry surface.

Maturity: experimental — R3 research control-plane surface exposing the
immutable strategy node registry and the governed core-factor catalog via the
application-owned :class:`ResearchCatalogQueryFacade`; no capability imports
and no mutation authority live here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.factor_diagnostics_reader import (
    FactorDiagnosticsReader,
    FactorDiagnosticsScope,
)
from ditto_application.queries.evaluation import (
    EvaluationOptions,
    FactorEvaluationFacade,
)
from ditto_application.queries.research_catalog import (
    FactorDescriptorInfo,
    NodeDescriptorInfo,
    ResearchCatalogQueryFacade,
)
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.api.errors import APIError, UnprocessableEntityError
from ditto_apps.api.json_values import to_json_mapping
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    FactorDescriptorResponse,
    FactorDiagnosticsResponse,
    FactorEvaluationSeriesResponse,
    MonthlyIcCell,
    NodeDescriptorResponse,
    QuantileNavColumn,
)

router = APIRouter(prefix="/research", tags=["research"])


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def _to_node_response(info: NodeDescriptorInfo) -> NodeDescriptorResponse:
    """将 application read model 转 API 响应."""
    return NodeDescriptorResponse(
        node_type=info.node_type,
        version=info.version,
        category=info.category,
        display_name=info.display_name,
        implementation_key=info.implementation_key,
        config_schema=dict(info.config_schema),
        default_config=to_json_mapping(info.default_config),
        required_datasets=list(info.required_datasets),
        capability_tags=list(info.capability_tags),
        deterministic=info.deterministic,
    )


def _to_factor_response(info: FactorDescriptorInfo) -> FactorDescriptorResponse:
    """将 application read model 转 API 响应."""
    return FactorDescriptorResponse(
        factor_id=info.factor_id,
        resolved_payload=to_json_mapping(info.resolved_payload),
    )


@router.get(
    "/node-descriptors",
    response_model=APIResponse[list[NodeDescriptorResponse]],
    operation_id="research_list_research_node_descriptors",
)
@inject
async def list_research_node_descriptors(
    facade: Annotated[ResearchCatalogQueryFacade, FromComponent()],
) -> APIResponse[list[NodeDescriptorResponse]]:
    """列出 R3 内置策略节点 descriptor(pipeline studio 事实源)."""
    descriptors = await run_blocking(facade.list_node_descriptors)
    return APIResponse(data=[_to_node_response(d) for d in descriptors])


@router.get(
    "/factors",
    response_model=APIResponse[list[FactorDescriptorResponse]],
    operation_id="research_list_research_factors",
)
@inject
async def list_research_factors(
    facade: Annotated[ResearchCatalogQueryFacade, FromComponent()],
) -> APIResponse[list[FactorDescriptorResponse]]:
    """列出 R3 受控核心因子目录(governed catalog order)."""
    factors = await run_blocking(facade.list_factors)
    return APIResponse(data=[_to_factor_response(factor) for factor in factors])


@router.get(
    "/factors/{factor_id}/diagnostics",
    response_model=APIResponse[FactorDiagnosticsResponse],
    operation_id="design_research_factor_diagnostics",
)
@inject
async def get_research_factor_diagnostics(
    factor_id: str,
    reader: Annotated[FactorDiagnosticsReader, FromComponent()],
    snapshot_id: Annotated[str, Query(min_length=1)],
    start_date: date,
    end_date: date,
    registry_hash: Annotated[str, Query(min_length=64, max_length=64)],
) -> APIResponse[FactorDiagnosticsResponse]:
    """Read one provenance-bound factor diagnostic artifact by exact scope."""
    try:
        view = await run_blocking(
            reader.read,
            FactorDiagnosticsScope(
                factor_id=factor_id,
                snapshot_id=snapshot_id,
                start_date=start_date,
                end_date=end_date,
                registry_hash=registry_hash,
            ),
        )
    except AppProcessError as exc:
        code = exc.details.get("code")
        error_code = code if isinstance(code, str) else "INVALID_DIAGNOSTIC_SCOPE"
        raise UnprocessableEntityError(str(exc), error_code=error_code) from exc
    if view is None:
        raise APIError(
            f"Factor diagnostics not found: {factor_id}",
            status_code=404,
            error_code="FACTOR_NOT_FOUND",
        )
    return APIResponse(
        data=FactorDiagnosticsResponse(
            factor_id=view.factor_id,
            snapshot_id=view.snapshot_id,
            snapshot_hash=view.snapshot_hash,
            registry_hash=view.registry_hash,
            start_date=view.start_date,
            end_date=view.end_date,
            provenance=to_json_mapping(view.provenance),
            metrics=to_json_mapping(view.metrics),
            artifact_id=view.artifact_id,
            content_hash=view.content_hash,
        )
    )


class EvaluationSeriesQuery(BaseModel):
    """evaluation-series 的查询参数模型（FastAPI Query model，逐字段进 OpenAPI）。"""

    model_config = ConfigDict(frozen=True)

    version: int | None = Field(
        None, description="衍生 artifact 版本(缺省解析离线版本)"
    )
    start_date: date | None = Field(None, description="评估起始日(含)")
    end_date: date | None = Field(None, description="评估结束日(含)")
    holding_period: int = Field(5, ge=1, le=60, description="前向收益持有期(交易日)")
    n_quantiles: int = Field(5, ge=2, le=10, description="分位组数")
    rolling_ir_window: int = Field(20, ge=2, le=250, description="滚动 IR 窗口(交易日)")
    asset_class: Literal["stock", "etf"] = Field("etf", description="资产类别")
    adj: Literal["none", "qfq", "hfq"] = Field("none", description="复权类型")


@router.get(
    "/factors/{factor_id}/evaluation-series",
    response_model=APIResponse[FactorEvaluationSeriesResponse],
    operation_id="design_research_factor_evaluation_series",
)
@inject
async def get_research_factor_evaluation_series(
    factor_id: str,
    facade: Annotated[FactorEvaluationFacade, FromComponent()],
    query: Annotated[EvaluationSeriesQuery, Query()],
) -> APIResponse[FactorEvaluationSeriesResponse]:
    """Per-date factor evaluation series computed at read time (research only)."""
    series = await run_blocking(
        facade.evaluate_series,
        factor_id,
        query.version,
        options=EvaluationOptions(
            start=query.start_date.isoformat() if query.start_date else None,
            end=query.end_date.isoformat() if query.end_date else None,
            holding_period=query.holding_period,
            n_quantiles=query.n_quantiles,
            asset_class=query.asset_class,
            adj=query.adj,
        ),
        rolling_ir_window=query.rolling_ir_window,
    )

    dates = series.ic["trade_date"].cast(pl.String).to_list()
    ic = series.ic["ic"].to_list()
    rolling = series.rolling_ir["rolling_ir"].to_list()
    ls_nav = series.ls_nav["ls_nav"].to_list()
    quantile_nav = [
        QuantileNavColumn(
            quantile=quantile,
            nav=series.quantile_nav[f"q_{quantile}"].to_list(),
        )
        for quantile in range(1, series.n_quantiles + 1)
        if f"q_{quantile}" in series.quantile_nav.columns
    ]
    monthly = [
        MonthlyIcCell(
            year=int(row["year"]),
            month=int(row["month"]),
            mean_ic=row["mean_ic"],
            days=int(row["days"]),
        )
        for row in series.monthly_ic.to_dicts()
    ]
    return APIResponse(
        data=FactorEvaluationSeriesResponse(
            factor_id=series.factor_id,
            factor_version=series.factor_version,
            holding_period=series.holding_period,
            n_quantiles=series.n_quantiles,
            rolling_ir_window=query.rolling_ir_window,
            period_start=date.fromisoformat(series.period[0]),
            period_end=date.fromisoformat(series.period[1]),
            n_dates=series.n_dates,
            dates=dates,
            ic=[None if value is None else float(value) for value in ic],
            rolling_ir=[None if value is None else float(value) for value in rolling],
            quantile_nav=quantile_nav,
            ls_nav=[None if value is None else float(value) for value in ls_nav],
            monthly_ic=monthly,
        )
    )
