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
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.research_catalog import (
    FactorDescriptorInfo,
    NodeDescriptorInfo,
    ResearchCatalogQueryFacade,
)
from fastapi import APIRouter

from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    FactorDescriptorResponse,
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
        default_config=dict(info.default_config),
        required_datasets=list(info.required_datasets),
        capability_tags=list(info.capability_tags),
        deterministic=info.deterministic,
    )


def _to_factor_response(info: FactorDescriptorInfo) -> FactorDescriptorResponse:
    """将 application read model 转 API 响应."""
    return FactorDescriptorResponse(
        factor_id=info.factor_id,
        resolved_payload=dict(info.resolved_payload),
    )


@router.get(
    "/node-descriptors",
    response_model=APIResponse[list[NodeDescriptorResponse]],
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
)
@inject
async def list_research_factors(
    facade: Annotated[ResearchCatalogQueryFacade, FromComponent()],
) -> APIResponse[list[FactorDescriptorResponse]]:
    """列出 R3 受控核心因子目录（governed catalog order）."""
    factors = await run_blocking(facade.list_factors)
    return APIResponse(data=[_to_factor_response(factor) for factor in factors])
