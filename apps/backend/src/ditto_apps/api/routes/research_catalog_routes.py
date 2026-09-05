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
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.factor_diagnostics_reader import (
    FactorDiagnosticsReader,
    FactorDiagnosticsScope,
)
from ditto_application.queries.research_catalog import (
    FactorDescriptorInfo,
    NodeDescriptorInfo,
    ResearchCatalogQueryFacade,
)
from fastapi import APIRouter, Query

from ditto_apps.api.errors import APIError, UnprocessableEntityError
from ditto_apps.api.json_values import to_json_mapping
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    FactorDescriptorResponse,
    FactorDiagnosticsResponse,
    NodeDescriptorResponse,
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
    """列出 R3 内置策略节点 descriptor（pipeline studio 事实源）."""
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
    """列出 R3 受控核心因子目录（governed catalog order）."""
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
