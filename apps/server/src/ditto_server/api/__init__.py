"""API路由包."""

from .data import router as data_router
from .update import router as update_router

__all__ = ["data_router", "update_router"]
