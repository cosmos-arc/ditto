"""API 公共依赖."""

from __future__ import annotations

from fastapi import Query

from ditto_interfaces.models.common import (
    APIResponse,
    PaginationRequest,
    PaginationResponse,
)


def pagination_params(
    limit: int = Query(default=20, ge=1, le=100, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> PaginationRequest:
    """标准分页参数依赖."""
    return PaginationRequest(limit=limit, offset=offset)


# TODO: 当前 paginate 在内存中对全量列表分页。当 items 量大时应改为
# 数据库层分页（LIMIT/OFFSET 或 cursor-based），避免将全量数据加载到内存。
def paginate[T](items: list[T], params: PaginationRequest) -> APIResponse[list[T]]:
    """对列表进行分页，返回包含 pagination 元数据的 APIResponse."""
    total = len(items)
    page = items[params.offset : params.offset + params.limit]
    return APIResponse(
        data=page,
        pagination=PaginationResponse(
            total=total, limit=params.limit, offset=params.offset
        ),
    )
