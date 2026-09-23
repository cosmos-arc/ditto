"""Production app and DI over the three-leg history-comparison journey fixture.

No agent model is involved: the fixture only seeds isolated real stores and
exposes the journey identity plus a one-shot failure arm for retry recovery.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from scripts.evidence.portfolio_history_comparison_live_fixture import seed

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("history comparison fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("history comparison fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "DITTO_TRADING_SQLITE_PATH": str(_state / "trading/trading.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

from ditto_apps.registry.fresh_runtime import create_fresh_runtime  # noqa: E402

create_fresh_runtime(_state)
_identity = seed(_state)
_failure_armed = {"active": False}

app = importlib.import_module("ditto_apps.main").app
_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _wrapped_lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with _lifespan(application):
        yield


app.router.lifespan_context = _wrapped_lifespan


@app.middleware("http")
async def _one_shot_comparison_failure(request, call_next):
    """Serve exactly one injected 500 so the journey can exercise retry."""
    if (
        request.url.path == "/api/v1/portfolio/history-comparison"
        and request.method == "GET"
        and _failure_armed["active"]
    ):
        _failure_armed["active"] = False
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"detail": "fixture injected comparison failure"}, status_code=500
        )
    return await call_next(request)


@app.post("/system-fixture/portfolio-history/arm-failure")
async def arm_failure() -> dict[str, object]:
    """Arm the next comparison GET to fail once."""
    _failure_armed["active"] = True
    return {"armed": True}


@app.get("/system-fixture/portfolio-history")
async def fixture_evidence() -> dict[str, object]:
    """Expose the journey identity and immutable business-row hashes."""
    business_hashes: dict[str, str] = {}
    for name in ("metadata", "trading"):
        connection = sqlite3.connect(
            f"file:{_state / name / (name + '.sqlite')}?mode=ro", uri=True
        )
        try:
            rows = "\n".join(
                line for line in connection.iterdump() if line.startswith("INSERT INTO")
            )
            business_hashes[name] = hashlib.sha256(rows.encode()).hexdigest()
        finally:
            connection.close()
    return {
        "identity": jsonable_encoder(_identity),
        "business_hashes": business_hashes,
    }
