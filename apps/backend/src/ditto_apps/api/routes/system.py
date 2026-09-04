"""System routes shared by runtime and pure OpenAPI contract apps."""

from __future__ import annotations

import time
from typing import Any

from ditto_platform.foundation import logger
from fastapi import APIRouter, Request

from ditto_apps.api.app_metadata import APP_VERSION

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    """根路径."""
    logger.info("Root endpoint accessed")
    return {"message": "Ditto Quant API", "version": APP_VERSION}


@router.get("/healthz")
async def health_check() -> dict[str, Any]:
    """健康检查端点."""
    logger.debug("Health check endpoint accessed", event="health_check")
    return {
        "status": "ok",
        "service": "ditto-api",
        "timestamp": time.time(),
        "features": {
            "prefect": True,
            "observability": True,
        },
    }


@router.get("/api/v1/status")
async def get_status(request: Request) -> dict[str, Any]:
    """获取系统状态."""
    logger.info("Status endpoint accessed")
    return {
        "status": "running",
        "version": APP_VERSION,
        "environment": request.app.state.settings.system.environment.value,
        "features": {
            "data_collection": True,
            "data_validation": True,
            "backtest": True,
            "trading": True,
        },
        "observability": {
            "level": request.app.state.settings.observability.log_level,
            "structured": True,
        },
    }
