"""调试路由模块（仅非生产环境可用）"""

from __future__ import annotations

from ditto_platform.foundation.observability import logger
from fastapi import APIRouter

debug_router = APIRouter()


@debug_router.get("/logs/test")
async def generate_test_logs() -> dict[str, str]:
    """测试日志记录功能（仅开发/测试环境可用）."""
    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}
