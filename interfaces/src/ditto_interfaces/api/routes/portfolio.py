"""投资组合 API 路由."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/")
async def root() -> dict[str, str]:
    """Portfolio root endpoint."""
    return {"module": "portfolio", "status": "coming soon"}
