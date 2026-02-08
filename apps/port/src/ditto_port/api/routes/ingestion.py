"""Ingestion API routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/")
async def root() -> dict[str, str]:
    """Ingestion root endpoint."""
    return {"module": "ingestion", "status": "coming soon"}
