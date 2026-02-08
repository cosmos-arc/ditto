"""Market data API routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/")
async def root() -> dict[str, str]:
    """Market root endpoint."""
    return {"module": "market", "status": "coming soon"}
