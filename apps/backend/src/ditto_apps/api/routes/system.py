"""System routes shared by runtime and pure OpenAPI contract apps."""

from __future__ import annotations

import time
from typing import Any

from ditto_platform.foundation import logger
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ditto_apps.api.app_metadata import APP_VERSION, BuildMetadata
from ditto_apps.config.runtime import RuntimePaths, evaluate_runtime_readiness
from ditto_apps.models.system import (
    HealthResponse,
    ReadinessResponse,
    SystemStatusResponse,
)

router = APIRouter()


@router.get("/", operation_id="system_root")
async def root() -> dict[str, str]:
    """根路径."""
    logger.info("Root endpoint accessed")
    return {"message": "Ditto Quant API", "version": APP_VERSION}


@router.get(
    "/healthz", response_model=HealthResponse, operation_id="system_health_check"
)
async def health_check() -> dict[str, Any]:
    """Report process liveness without consulting downstream dependencies."""
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


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    operation_id="system_readiness_check",
)
async def readiness_check(request: Request) -> JSONResponse:
    """Report whether startup completed and required filesystem roots are usable."""
    paths = getattr(request.app.state, "runtime_paths", None)
    runtime_paths = paths if isinstance(paths, RuntimePaths) else None
    checks = evaluate_runtime_readiness(
        runtime_paths,
        initialized=bool(getattr(request.app.state, "runtime_initialized", False)),
    )
    ready = all(check.ok for check in checks.values())
    payload = ReadinessResponse.model_validate(
        {
            "status": "ready" if ready else "not_ready",
            "service": "ditto-api",
            "checks": {
                name: {"ok": check.ok, "detail": check.detail}
                for name, check in checks.items()
            },
        }
    )
    return JSONResponse(
        status_code=200 if ready else 503,
        content=payload.model_dump(mode="json"),
    )


@router.get(
    "/api/v1/status",
    response_model=SystemStatusResponse,
    operation_id="system_get_status",
)
async def get_status(request: Request) -> dict[str, Any]:
    """获取系统状态."""
    logger.info("Status endpoint accessed")
    metadata = getattr(request.app.state, "build_metadata", None)
    if not isinstance(metadata, BuildMetadata):
        raise RuntimeError(
            "system status requires verified build metadata from the composition root"
        )
    return {
        "status": "running",
        "version": APP_VERSION,
        "product_version": metadata.product_version,
        "git_sha": metadata.git_sha,
        "api_contract_version": metadata.api_contract_version,
        "api_contract_sha256": metadata.api_contract_sha256,
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
