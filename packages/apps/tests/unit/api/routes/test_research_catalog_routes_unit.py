"""Unit tests for research catalog routes — static node + factor registry surface."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.research_catalog import (
    FactorDescriptorInfo,
    NodeDescriptorInfo,
    ResearchCatalogQueryFacade,
)
from ditto_apps.api.routes.research_catalog_routes import (
    list_research_factors,
    list_research_node_descriptors,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    FactorDescriptorResponse,
    NodeDescriptorResponse,
)

pytestmark = pytest.mark.asyncio

_NodeRoute = Callable[..., Awaitable[APIResponse[list[NodeDescriptorResponse]]]]
_FactorRoute = Callable[..., Awaitable[APIResponse[list[FactorDescriptorResponse]]]]


@pytest.fixture(autouse=True)
def _inline_catalog_route_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.research_catalog_routes.run_blocking", run_inline
    )


def _node_info() -> NodeDescriptorInfo:
    return NodeDescriptorInfo(
        node_type="momentum_scorer",
        version="1",
        category="scoring",
        display_name="Momentum Scorer",
        implementation_key="builtin:momentum_scorer:1",
        config_schema={"weight": "number"},
        default_config={"weight": 1.0},
        required_datasets=("stock_daily",),
        capability_tags=("stock_selection",),
        deterministic=True,
    )


def _factor_info() -> FactorDescriptorInfo:
    return FactorDescriptorInfo(
        factor_id="momentum_1m", resolved_payload={"id": "momentum_1m"}
    )


def _unwrap(route: Callable[..., object]) -> Callable[..., object]:
    return cast(Callable[..., object], getattr(route, "__dishka_orig_func__", route))


async def test_list_node_descriptors_returns_responses() -> None:
    facade = MagicMock(spec=ResearchCatalogQueryFacade)
    facade.list_node_descriptors.return_value = (_node_info(),)
    route = cast(_NodeRoute, _unwrap(list_research_node_descriptors))

    result = await route(facade=facade)

    assert result.data == [
        NodeDescriptorResponse(
            node_type="momentum_scorer",
            version="1",
            category="scoring",
            display_name="Momentum Scorer",
            implementation_key="builtin:momentum_scorer:1",
            config_schema={"weight": "number"},
            default_config={"weight": 1.0},
            required_datasets=["stock_daily"],
            capability_tags=["stock_selection"],
            deterministic=True,
        )
    ]


async def test_list_factors_returns_responses() -> None:
    facade = MagicMock(spec=ResearchCatalogQueryFacade)
    facade.list_factors.return_value = (_factor_info(),)
    route = cast(_FactorRoute, _unwrap(list_research_factors))

    result = await route(facade=facade)

    assert result.data == [
        FactorDescriptorResponse(
            factor_id="momentum_1m", resolved_payload={"id": "momentum_1m"}
        )
    ]


async def test_list_node_descriptors_empty() -> None:
    facade = MagicMock(spec=ResearchCatalogQueryFacade)
    facade.list_node_descriptors.return_value = ()
    route = cast(_NodeRoute, _unwrap(list_research_node_descriptors))

    result = await route(facade=facade)

    assert result.data == []
