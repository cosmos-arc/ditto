"""Pure, canonical, and atomic static OpenAPI snapshot contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from ditto_apps.openapi_contract import (
    canonical_openapi_bytes,
    create_openapi_app,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SNAPSHOT_PATH = _REPO_ROOT / "docs/openapi/v1.json"
_DEBUG_PATH = "/api/v1/logs/test"


def _load_exporter() -> ModuleType:
    exporter_path = _REPO_ROOT / "scripts/export_openapi.py"
    spec = importlib.util.spec_from_file_location("ditto_export_openapi", exporter_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = _load_exporter()


def _operation_signatures(app: FastAPI) -> set[tuple[str, str, str]]:
    routes = app.routes
    return {
        (method, route.path, route.operation_id or route.name)
        for route in routes
        if isinstance(route, APIRoute) and route.path != _DEBUG_PATH
        for method in route.methods
    }


def test_static_openapi_matches_pure_non_debug_contract() -> None:
    """Static OpenAPI is exactly the pure deterministic projection."""
    contract_app = create_openapi_app(include_debug=False)
    expected = canonical_openapi_bytes(contract_app.openapi())

    assert _SNAPSHOT_PATH.read_bytes() == expected
    assert _DEBUG_PATH not in contract_app.openapi()["paths"]


def test_exporter_writes_canonical_bytes_through_real_entrypoint(
    tmp_path: Path,
) -> None:
    """The production exporter writes the same canonical contract to any target."""
    output_path = tmp_path / "nested" / "v1.json"

    exported_path = exporter.export_openapi(output_path)

    expected = canonical_openapi_bytes(
        create_openapi_app(include_debug=False).openapi()
    )
    assert exported_path == output_path
    assert output_path.read_bytes() == expected


def test_exporter_failure_preserves_old_file_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed atomic replace never corrupts the last known-good snapshot."""
    output_path = tmp_path / "v1.json"
    sentinel = b'{"sentinel":"old"}\n'
    output_path.write_bytes(sentinel)

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError(f"replace failed: {source} -> {destination}")

    monkeypatch.setattr(exporter.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        exporter.export_openapi(output_path)

    assert output_path.read_bytes() == sentinel
    assert list(tmp_path.glob(f".{output_path.name}.*.tmp")) == []


def test_factory_debug_surface_is_explicit_and_environment_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENVIRONMENT cannot alter the canonical app; only include_debug can."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    production_named = create_openapi_app(include_debug=False)
    monkeypatch.setenv("ENVIRONMENT", "testing")
    testing_named = create_openapi_app(include_debug=False)
    debug_app = create_openapi_app(include_debug=True)

    assert canonical_openapi_bytes(
        production_named.openapi()
    ) == canonical_openapi_bytes(testing_named.openapi())
    assert _DEBUG_PATH not in production_named.openapi()["paths"]
    assert _DEBUG_PATH not in testing_named.openapi()["paths"]
    assert _DEBUG_PATH in debug_app.openapi()["paths"]
    assert not hasattr(production_named.state, "dishka_container")


def test_runtime_and_pure_factory_share_non_debug_route_registration() -> None:
    """Runtime assembly and the pure contract factory cannot drift."""
    from ditto_apps.main import app as runtime_app

    contract_app = create_openapi_app(include_debug=False)

    assert _operation_signatures(runtime_app) == _operation_signatures(contract_app)
