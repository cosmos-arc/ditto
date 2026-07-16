"""OpenAPI capability maturity annotations."""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

type ApiMaturity = Literal[
    "initial-focus",
    "experimental",
    "infrastructure",
    "debug",
]

MATURITY_NOTE_BY_LEVEL: dict[ApiMaturity, str] = {
    "initial-focus": "Primary near-term product scope under architecture review.",
    "experimental": "Implemented or partly implemented; not production scope.",
    "infrastructure": "Foundation surface supporting product workflows.",
    "debug": "Debug-only surface; must not be exposed in production.",
}

ROUTE_MATURITY_BY_PREFIX: dict[str, ApiMaturity] = {
    "/": "infrastructure",
    "/healthz": "infrastructure",
    "/api/v1/status": "infrastructure",
    "/api/v1/backtests": "initial-focus",
    "/api/v1/market": "initial-focus",
    "/api/v1/metadata": "initial-focus",
    "/api/v1/strategies": "initial-focus",
    "/api/v1/universes": "initial-focus",
    "/api/v1/capital": "experimental",
    "/api/v1/commodity": "experimental",
    "/api/v1/fundamental": "experimental",
    "/api/v1/fx": "experimental",
    "/api/v1/macro": "experimental",
    "/api/v1/trade": "initial-focus",
    "/api/v1/ingestion": "infrastructure",
    "/api/v1/source": "infrastructure",
    "/api/v1/logs": "debug",
}

_TAG_MATURITY: tuple[tuple[str, ApiMaturity], ...] = (
    ("backtests", "initial-focus"),
    ("market", "initial-focus"),
    ("metadata", "initial-focus"),
    ("strategies", "initial-focus"),
    ("universes", "initial-focus"),
    ("capital", "experimental"),
    ("commodity", "experimental"),
    ("fundamental", "experimental"),
    ("fx", "experimental"),
    ("macro", "experimental"),
    ("trade", "initial-focus"),
    ("ingestion", "infrastructure"),
    ("source", "infrastructure"),
    ("debug", "debug"),
)

OPENAPI_TAGS: list[dict[str, Any]] = [
    {
        "name": name,
        "description": (
            f"Capability maturity: `{maturity}`. {MATURITY_NOTE_BY_LEVEL[maturity]}"
        ),
        "x-ditto-maturity": maturity,
    }
    for name, maturity in _TAG_MATURITY
]


def route_maturity_for_path(path: str) -> ApiMaturity | None:
    """Return the maturity level for an OpenAPI path."""
    for prefix, maturity in sorted(
        ROUTE_MATURITY_BY_PREFIX.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if path == prefix or path.startswith(f"{prefix}/"):
            return maturity
    return None


def build_maturity_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Build OpenAPI schema with per-operation Ditto maturity metadata."""
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    _annotate_openapi_operations(schema)
    app.openapi_schema = schema
    return schema


def _annotate_openapi_operations(schema: dict[str, Any]) -> None:
    raw_paths = schema.get("paths", {})
    if not isinstance(raw_paths, dict):
        return
    paths = cast(dict[str, Any], raw_paths)

    for path, raw_methods in paths.items():
        if not isinstance(raw_methods, dict):
            continue
        methods = cast(dict[str, Any], raw_methods)
        maturity = route_maturity_for_path(path)
        if maturity is None:
            continue
        for method, raw_operation in methods.items():
            if method == "parameters" or not isinstance(raw_operation, dict):
                continue
            operation = cast(dict[str, Any], raw_operation)
            operation["x-ditto-maturity"] = maturity
            _append_maturity_description(operation, maturity)


def _append_maturity_description(
    operation: dict[str, Any],
    maturity: ApiMaturity,
) -> None:
    note = f"Capability maturity: `{maturity}`. {MATURITY_NOTE_BY_LEVEL[maturity]}"
    description = operation.get("description")
    if not isinstance(description, str) or not description:
        operation["description"] = note
        return
    if note in description:
        return
    operation["description"] = f"{description}\n\n{note}"
