"""Commodity (商品) 域 API 路由."""

from fastapi import APIRouter

from ditto_port.models.commodity import CommodityBar, CommodityQuery
from ditto_port.models.common import APIResponse

router = APIRouter(prefix="/commodity", tags=["commodity"])


@router.post("/bars", response_model=APIResponse[list[CommodityBar]])
async def post_bars(
    query: CommodityQuery,
) -> APIResponse[list[CommodityBar]]:
    """
    查询商品 K 线数据.

    Args:
        query: 查询参数
            - symbols: 商品代码列表 (可选, 如 ["AU", "AG", "CU"])
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000)

    Returns:
        APIResponse 包含商品 K 线数据列表

    Note:
        当前为占位实现，返回空列表。
        后续将集成 CommodityService 实现完整查询功能。

    """
    # TODO: 集成 CommodityService 实现查询逻辑
    # service_query = CommodityServiceQuery(
    #     symbols=query.symbols,
    #     start=query.start_date.isoformat() if query.start_date else None,
    #     end=query.end_date.isoformat() if query.end_date else None,
    #     limit=query.limit,
    # )
    # df = await asyncio.to_thread(service.find_bars, service_query)
    # bars = to_commodity_bar_list(df)
    # return APIResponse(data=bars)

    # 占位实现：返回空列表
    _ = query
    return APIResponse(data=[])
