"""
FX (外汇) 模 API 路由.

maturity: experimental
"""

from __future__ import annotations

from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.fx import FXQueryFacade
from fastapi import APIRouter

from ditto_apps.api.routes.shared_bars import handle_bars_post
from ditto_apps.models.common import APIResponse
from ditto_apps.models.fx import FxBar, FxQuery, to_fx_bar_list

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/bars", response_model=APIResponse[list[FxBar]])
@inject
async def post_bars(
    query: FxQuery,
    facade: Annotated[FXQueryFacade, FromComponent()],
) -> APIResponse[list[FxBar]]:
    """
    查询外汇 K 线数据.

    Args:
        query: 查询参数
            - currency_pairs: 货币对列表 (可选, 如 ["USDCNH.FXCM", "EURUSD.FXCM"])
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000, 范围 1-10000)
        facade: FXQueryFacade 依赖注入

    Returns:
        APIResponse 包含外汇 K 线数据列表

    """
    return await handle_bars_post(
        facade=facade,
        codes=query.currency_pairs,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        alias="currency_pair",
        converter=to_fx_bar_list,
    )
