"""Commodity (商品) 域 API 路由."""

from __future__ import annotations

from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.query.commodity import CommodityQueryFacade
from fastapi import APIRouter

from ditto_apps.api.routes.shared_bars import handle_bars_post
from ditto_apps.models.commodity import (
    CommodityBar,
    CommodityQuery,
    to_commodity_bar_list,
)
from ditto_apps.models.common import APIResponse

router = APIRouter(prefix="/commodity", tags=["commodity"])


@router.post("/bars", response_model=APIResponse[list[CommodityBar]])
@inject
async def post_bars(
    query: CommodityQuery,
    facade: Annotated[CommodityQueryFacade, FromComponent()],
) -> APIResponse[list[CommodityBar]]:
    """
    查询商品 K 线数据.

    Args:
        query: 查询参数
            - commodity_codes: 商品代码列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000, 范围 1-10000)
        facade: CommodityQueryFacade 依赖注入

    Returns:
        APIResponse 包含商品 K 线数据列表

    """
    return await handle_bars_post(
        facade=facade,
        codes=query.commodity_codes,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        alias="commodity_code",
        converter=to_commodity_bar_list,
    )
