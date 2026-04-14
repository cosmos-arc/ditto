"""API 公共依赖."""

from __future__ import annotations

from fastapi import Query

from ditto_interfaces.models.common import PaginationRequest


def pagination_params(
    limit: int = Query(default=20, ge=1, le=100, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> PaginationRequest:
    """标准分页参数依赖."""
    return PaginationRequest(limit=limit, offset=offset)
