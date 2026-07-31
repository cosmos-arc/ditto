"""Pure OpenAPI app assembly and canonical serialization."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI

from ditto_apps.api.app_metadata import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    generate_stable_operation_id,
)
from ditto_apps.api.maturity import OPENAPI_TAGS, build_maturity_openapi_schema
from ditto_apps.api.routes import (
    backtest,
    capital,
    commodity,
    data_products,
    fundamental,
    fx,
    ingestion,
    macro,
    market,
    metadata,
    research_catalog_routes,
    research_experiment_routes,
    research_review_routes,
    source,
    strategy,
    system,
    trade,
    universe,
)
from ditto_apps.api.routes.debug import debug_router

_V1_ROUTERS = (
    backtest.router,
    capital.router,
    commodity.router,
    data_products.router,
    fundamental.router,
    fx.router,
    ingestion.router,
    macro.router,
    market.router,
    metadata.router,
    research_experiment_routes.router,
    research_catalog_routes.router,
    research_review_routes.router,
    source.router,
    strategy.router,
    trade.router,
    universe.router,
)


def configure_openapi(app: FastAPI) -> None:
    """Install the shared maturity-aware OpenAPI builder."""
    app.openapi = lambda: build_maturity_openapi_schema(app)


def register_application_routes(app: FastAPI, *, include_debug: bool) -> None:
    """Register the one shared runtime/contract route list."""
    for router in _V1_ROUTERS:
        app.include_router(router, prefix="/api/v1")
    if include_debug:
        app.include_router(debug_router, prefix="/api/v1", tags=["debug"])
    app.include_router(system.router)


def create_openapi_app(*, include_debug: bool = False) -> FastAPI:
    """Create a side-effect-free app for schema generation only."""
    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=OPENAPI_TAGS,
        generate_unique_id_function=generate_stable_operation_id,
    )
    configure_openapi(app)
    register_application_routes(app, include_debug=include_debug)
    return app


def canonical_openapi_bytes(schema: dict[str, Any]) -> bytes:
    """Serialize an OpenAPI document with stable key order and one final newline."""
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{payload}\n".encode()
