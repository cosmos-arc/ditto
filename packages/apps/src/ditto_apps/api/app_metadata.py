"""Stable application metadata shared by runtime and contract apps."""

from __future__ import annotations

import importlib.metadata

from fastapi.routing import APIRoute

APP_TITLE = "Ditto Quant API"
APP_DESCRIPTION = "量化投资系统API"


def _load_app_version() -> str:
    """Return the installed API package version, with a local-dev fallback."""
    try:
        return importlib.metadata.version("ditto-apps")
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


APP_VERSION = _load_app_version()


def generate_stable_operation_id(route: APIRoute) -> str:
    """Generate tag-scoped OpenAPI operation IDs for frontend clients."""
    tag = str(route.tags[0]) if route.tags else "system"
    return f"{tag.replace('-', '_')}_{route.name}"
