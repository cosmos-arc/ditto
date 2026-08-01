"""Unit tests for research catalog routes — static node + factor registry surface."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.processes.experiments.factor_diagnostics_reader import (
    FactorDiagnosticsReader,
    FactorDiagnosticsView,
)
from ditto_application.queries.research_catalog import (
    FactorDescriptorInfo,
    NodeDescriptorInfo,
    ResearchCatalogQueryFacade,
)
from ditto_apps.api.routes.research_catalog_routes import (
    get_research_factor_diagnostics,
    list_research_factors,
    list_research_node_descriptors,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    FactorDescriptorResponse,
    FactorDiagnosticsResponse,
    NodeDescriptorResponse,
)

pytestmark = pytest.mark.asyncio

_NodeRoute = Callable[..., Awaitable[APIResponse[list[NodeDescriptorResponse]]]]
_FactorRoute = Callable[..., Awaitable[APIResponse[list[FactorDescriptorResponse]]]]
_DiagnosticsRoute = Callable[..., Awaitable[APIResponse[FactorDiagnosticsResponse]]]


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


async def test_factor_diagnostics_preserves_exact_scope_and_artifact_identity() -> None:
    reader = MagicMock(spec=FactorDiagnosticsReader)
    reader.read.return_value = FactorDiagnosticsView(
        factor_id="momentum_20",
        snapshot_id="snapshot-1",
        snapshot_hash="a" * 64,
        registry_hash="b" * 64,
        start_date=date(2020, 1, 1),
        end_date=date(2026, 7, 30),
        provenance={"dataset_id": "stock_daily"},
        metrics={"ic_mean": 0.08},
        artifact_id="factor-diagnostic-1",
        content_hash="c" * 64,
    )
    route = cast(_DiagnosticsRoute, _unwrap(get_research_factor_diagnostics))

    result = await route(
        factor_id="momentum_20",
        reader=reader,
        snapshot_id="snapshot-1",
        start_date=date(2020, 1, 1),
        end_date=date(2026, 7, 30),
        registry_hash="b" * 64,
    )

    scope = reader.read.call_args.args[0]
    assert scope.factor_id == "momentum_20"
    assert scope.snapshot_id == "snapshot-1"
    assert scope.registry_hash == "b" * 64
    assert result.data.artifact_id == "factor-diagnostic-1"
    assert result.data.content_hash == "c" * 64
