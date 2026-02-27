"""FX (外汇) 域 API 路由."""

from fastapi import APIRouter

from ditto_port.models.common import APIResponse
from ditto_port.models.fx import FxBar, FxQuery

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/bars", response_model=APIResponse[list[FxBar]])
async def post_bars(
    query: FxQuery,
) -> APIResponse[list[FxBar]]:
    """
    查询外汇 K 线数据.

    Args:
        query: 查询参数
            - pairs: 货币对列表 (可选, 如 ["USDCNY", "EURCNY"])
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - limit: 返回数量限制 (默认 1000)

    Returns:
        APIResponse 包含外汇 K 线数据列表

    Note:
        当前为占位实现，返回空列表。
        后续将集成 FxService 实现完整查询功能。

    """
    # TODO: 集成 FxService 实现查询逻辑
    # service_query = FxServiceQuery(
    #     pairs=query.pairs,
    #     start=query.start_date.isoformat() if query.start_date else None,
    #     end=query.end_date.isoformat() if query.end_date else None,
    #     limit=query.limit,
    # )
    # df = await asyncio.to_thread(service.find_bars, service_query)
    # bars = to_fx_bar_list(df)
    # return APIResponse(data=bars)

    # 占位实现：返回空列表
    _ = query
    return APIResponse(data=[])
