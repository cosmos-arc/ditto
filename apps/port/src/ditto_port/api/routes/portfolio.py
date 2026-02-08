"""Portfolio API routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/")
async def root() -> dict[str, str]:
    """Portfolio root endpoint."""
    return {"module": "portfolio", "status": "coming soon"}
