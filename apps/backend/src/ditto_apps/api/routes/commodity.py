"""
Commodity (商品) 域 API 路由.

maturity: experimental
"""

from __future__ import annotations

from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.commodity import CommodityQueryFacade
from fastapi import APIRouter

from ditto_apps.api.routes.shared_bars import handle_bars_post
from ditto_apps.models.commodity import (
    CommodityBar,
    CommodityQuery,
    to_commodity_bar_list,
)
from ditto_apps.models.common import APIResponse

router = APIRouter(prefix="/commodity", tags=["commodity"])


@router.post(
    "/bars",
    response_model=APIResponse[list[CommodityBar]],
    operation_id="commodity_post_bars",
)
@inject
async def post_bars(
    query: CommodityQuery,
    facade: Annotated[CommodityQueryFacade, FromComponent()],
) -> APIResponse[list[CommodityBar]]:
    """
    查询商品 K 线数据（latest_available：库内现存行，无 PIT 过滤，#628 标注）.

    commodity_daily 为 partial 覆盖（仅 2026-09 起，见 GET /datasets/coverage）；
    空结果与不覆盖经覆盖注册表区分.

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
