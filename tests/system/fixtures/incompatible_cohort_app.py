"""Network-visible peer for the Web's incompatible-cohort fail-closed test.

The production Ditto application correctly refuses unsupported build metadata
before readiness.  This deliberately tiny ASGI peer therefore represents a
different product cohort and truthfully reports ``v2`` over real loopback HTTP;
it does not patch browser traffic or weaken production metadata validation.
"""

from __future__ import annotations

import hashlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required")
    return value


_web_origin = _required_environment("DITTO_SYSTEM_WEB_ORIGIN")
if not _web_origin.startswith("http://127.0.0.1:"):
    raise RuntimeError("incompatible-cohort fixture only permits loopback Web origins")

app = FastAPI(title="Ditto incompatible cohort fixture")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_web_origin],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/v1/status")
async def status() -> dict[str, object]:
    return {
        "status": "running",
        "version": _required_environment("DITTO_PRODUCT_VERSION"),
        "product_version": _required_environment("DITTO_PRODUCT_VERSION"),
        "git_sha": _required_environment("DITTO_GIT_SHA"),
        "api_contract_version": "v2",
        "api_contract_sha256": hashlib.sha256(
            b"ditto-incompatible-v2-system-fixture"
        ).hexdigest(),
        "environment": "testing",
        "features": {
            "data_collection": False,
            "data_validation": False,
            "backtest": False,
            "trading": False,
        },
        "observability": {"level": "WARNING", "structured": True},
    }
