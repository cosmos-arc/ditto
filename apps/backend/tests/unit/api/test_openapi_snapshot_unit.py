"""Pure, canonical, and atomic static OpenAPI snapshot contract."""

from __future__ import annotations

import importlib.util
import stat
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx
import pytest
from ditto_apps.models.trade import DailyDecisionV2Response
from ditto_apps.openapi_contract import (
    canonical_openapi_bytes,
    create_openapi_app,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SNAPSHOT_PATH = _REPO_ROOT / "contracts/openapi/v1.json"
_DEBUG_PATH = "/api/v1/logs/test"


def _load_exporter() -> ModuleType:
    exporter_path = _REPO_ROOT / "tooling/contracts/export_openapi.py"
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


def _public_operations(schema: dict[str, Any]) -> list[dict[str, Any]]:
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    paths = cast("dict[str, dict[str, Any]]", schema["paths"])
    return [
        operation
        for path_item in paths.values()
        for method, operation in path_item.items()
        if method in methods
    ]


def test_static_openapi_matches_canonical_runtime_contract() -> None:
    """Static OpenAPI is exactly the exporter's runtime projection."""
    expected = exporter.canonical_runtime_openapi_bytes()

    assert _SNAPSHOT_PATH.read_bytes() == expected
    assert _DEBUG_PATH not in exporter.runtime_openapi_schema()["paths"]


def test_exporter_writes_canonical_bytes_through_real_entrypoint(
    tmp_path: Path,
) -> None:
    """The production exporter writes the same canonical contract to any target."""
    output_path = tmp_path / "nested" / "v1.json"

    exported_path = exporter.export_openapi(output_path)

    expected = exporter.canonical_runtime_openapi_bytes()
    assert exported_path == output_path
    assert output_path.read_bytes() == expected
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o644


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


def test_contract_metadata_declares_true_local_security_boundary() -> None:
    """The contract says exactly how the unauthenticated local API is reached."""
    schema = create_openapi_app(include_debug=False).openapi()

    assert schema["security"] == []
    assert schema["servers"] == [
        {
            "url": "/",
            "description": "Current local Ditto API origin",
        }
    ]
    assert schema["info"]["license"] == {
        "name": "Proprietary - All rights reserved",
        "identifier": "LicenseRef-Proprietary",
    }


def test_every_operation_preserves_error_envelope_for_contract_assertion() -> None:
    """The optional version header must preserve the existing typed v1 envelope."""
    schema = create_openapi_app(include_debug=False).openapi()

    operations = _public_operations(schema)
    assert operations
    for operation in operations:
        version_headers = [
            parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
            and parameter.get("name") == "X-Ditto-API-Contract-Version"
        ]
        assert len(version_headers) == 1
        assert version_headers[0]["required"] is False
        error_schema = operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ]
        assert error_schema == {"$ref": "#/components/schemas/ErrorResponse"}


@pytest.mark.asyncio
async def test_runtime_rejects_wrong_contract_version_with_v1_error_envelope() -> None:
    """The documented 422 is observable at the real runtime boundary."""
    from ditto_apps.main import app as runtime_app

    transport = httpx.ASGITransport(app=runtime_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/healthz",
            headers={"X-Ditto-API-Contract-Version": "v2"},
        )

    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {
        "detail",
        "error",
        "request_id",
        "status_code",
        "success",
        "timestamp",
    }
    assert payload["success"] is False
    assert payload["status_code"] == 422
    assert payload["error"] == "VALIDATION_ERROR"
    assert payload["detail"] == "Invalid request parameters"
    assert payload["request_id"] == response.headers["X-Request-ID"]


def test_daily_decision_v2_openapi_example_validates_against_provider_model() -> None:
    """Checked-in examples must remain executable provider-owned payloads."""
    model_schema = DailyDecisionV2Response.model_json_schema()

    DailyDecisionV2Response.model_validate(model_schema["example"])
