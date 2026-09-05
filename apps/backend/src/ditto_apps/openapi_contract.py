"""Pure OpenAPI app assembly and canonical serialization."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Final, Literal

from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.routing import APIRoute

from ditto_apps.api.app_metadata import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    generate_stable_operation_id,
    openapi_license_info,
    openapi_servers,
)
from ditto_apps.api.maturity import OPENAPI_TAGS, build_maturity_openapi_schema
from ditto_apps.api.routes import (
    account_ledger,
    agent_routes,
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
    paper,
    portfolio_comparison,
    research_candidate_routes,
    research_catalog_routes,
    research_experiment_routes,
    research_review_routes,
    research_selection_routes,
    selection,
    source,
    strategy,
    strategy_author_preview,
    system,
    technical_analysis,
    trade,
    universe,
)
from ditto_apps.api.routes.debug import debug_router
from ditto_apps.middleware import configure_exception_handlers
from ditto_apps.models.common import ErrorResponse

_CONTRACT_VERSION_HEADER = "X-Ditto-API-Contract-Version"
_OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_STANDARD_ERROR_DESCRIPTIONS: Final[dict[int | str, str]] = {
    400: "Bad request",
    403: "Forbidden",
    404: "Resource not found",
    409: "Request conflicts with current state",
    422: "Request or domain validation failed",
    500: "Internal server error",
    "default": "Structured Ditto API error",
}


def standard_error_responses() -> dict[int | str, dict[str, Any]]:
    """Describe the stable error envelope emitted by every public operation."""
    return {
        status_code: {
            "description": description,
            "model": ErrorResponse,
        }
        for status_code, description in _STANDARD_ERROR_DESCRIPTIONS.items()
    }


async def require_supported_contract_version(
    asserted_version: Literal["v1"] = Header(
        default=None,
        alias=_CONTRACT_VERSION_HEADER,
        description=(
            "Optional fail-closed assertion that the client targets the v1 "
            "HTTP contract. Omit when no assertion is required."
        ),
    ),
) -> None:
    """Let FastAPI reject unsupported explicit client contract assertions."""
    del asserted_version


def _include_contract_router(
    app: FastAPI,
    router: APIRouter,
    *,
    prefix: str = "",
) -> None:
    """Include a router under the shared client contract-version assertion."""
    app.include_router(
        router,
        prefix=prefix,
        dependencies=[Depends(require_supported_contract_version)],
    )


_V1_ROUTERS = (
    account_ledger.router,
    agent_routes.router,
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
    paper.router,
    portfolio_comparison.router,
    research_experiment_routes.router,
    research_catalog_routes.router,
    research_candidate_routes.router,
    research_review_routes.router,
    research_selection_routes.router,
    selection.router,
    source.router,
    strategy.router,
    strategy_author_preview.router,
    technical_analysis.router,
    trade.router,
    universe.router,
)


def configure_openapi(app: FastAPI) -> None:
    """Install the shared maturity-aware OpenAPI builder."""
    app.openapi = lambda: _validated_openapi_schema(app)


def _validated_openapi_schema(app: FastAPI) -> dict[str, Any]:
    operation_routes = [route for route in app.routes if isinstance(route, APIRoute)]
    missing = [route.path for route in operation_routes if route.operation_id is None]
    if missing:
        raise RuntimeError(
            "every HTTP route requires an explicit operation_id: "
            + ", ".join(sorted(missing))
        )
    operation_ids = [
        route.operation_id
        for route in operation_routes
        if route.operation_id is not None
    ]
    invalid = [
        operation_id
        for operation_id in operation_ids
        if _OPERATION_ID.fullmatch(operation_id) is None
    ]
    if invalid:
        raise RuntimeError(f"invalid explicit operation_id values: {sorted(invalid)}")
    if len(operation_ids) != len(set(operation_ids)):
        raise RuntimeError("explicit operation_id values must be globally unique")
    return build_maturity_openapi_schema(app)


def register_application_routes(app: FastAPI, *, include_debug: bool) -> None:
    """Register the one shared runtime/contract route list."""
    for router in _V1_ROUTERS:
        _include_contract_router(app, router, prefix="/api/v1")
    if include_debug:
        app.include_router(
            debug_router,
            prefix="/api/v1",
            tags=["debug"],
            dependencies=[Depends(require_supported_contract_version)],
        )
    _include_contract_router(app, system.router)


def create_openapi_app(*, include_debug: bool = False) -> FastAPI:
    """Create a side-effect-free app for schema generation only."""
    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=OPENAPI_TAGS,
        servers=openapi_servers(),
        license_info=openapi_license_info(),
        generate_unique_id_function=generate_stable_operation_id,
        responses=standard_error_responses(),
    )
    configure_openapi(app)
    configure_exception_handlers(app)
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


def canonical_contract_sha256() -> str:
    """Hash the public factory contract, independent of runtime-only routes."""
    public_schema = create_openapi_app(include_debug=False).openapi()
    return hashlib.sha256(canonical_openapi_bytes(public_schema)).hexdigest()
