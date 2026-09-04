"""
Research review REST routes — cross-strategy review queue aggregation.

Maturity: experimental — R3 research control-plane surface exposing the
governance review queue (``state=REVIEW`` versions across all strategies) via
the application-owned :class:`StrategyQueryFacade`. The route reuses the
``StrategyVersionResponse`` shape (no ``experiment_id`` — governance does not
own experiment identity; the spec_hash cross-domain bridge to the review
packet is deferred to T20 frontend wiring). No capability imports and no
mutation authority live here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.strategy import StrategyQueryFacade
from fastapi import APIRouter

from ditto_apps.api.routes.strategy import to_version_response
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import StrategyVersionResponse

router = APIRouter(prefix="/research", tags=["research"])


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


@router.get(
    "/reviews",
    response_model=APIResponse[list[StrategyVersionResponse]],
)
@inject
async def list_research_reviews(
    facade: Annotated[StrategyQueryFacade, FromComponent()],
) -> APIResponse[list[StrategyVersionResponse]]:
    """列出跨 strategy 的 review queue（state=REVIEW 版本，newest first）."""
    reviews = await run_blocking(facade.list_reviews)
    return APIResponse(data=[to_version_response(review) for review in reviews])
