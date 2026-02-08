"""元数据 API 路由."""

from fastapi import APIRouter

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/")
async def root() -> dict[str, str]:
    """Metadata root endpoint."""
    return {"module": "metadata", "status": "coming soon"}
