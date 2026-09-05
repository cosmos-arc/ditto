"""Compatibility tests for Ditto's long-standing validation-error envelope."""

from __future__ import annotations

from typing import cast

from ditto_apps.openapi_contract import create_openapi_app
from fastapi.testclient import TestClient


def test_invalid_contract_header_preserves_v1_error_envelope() -> None:
    """Contract assertions must preserve the runtime v1 error envelope."""
    app = create_openapi_app()

    response = TestClient(app).get(
        "/api/v1/status",
        headers={"X-Ditto-API-Contract-Version": "v2"},
    )

    assert response.status_code == 422
    payload = cast("dict[str, object]", response.json())
    assert set(payload) == {
        "detail",
        "error",
        "status_code",
        "success",
        "timestamp",
    }
    assert payload["success"] is False
    assert payload["status_code"] == 422
    assert payload["error"] == "VALIDATION_ERROR"
    assert payload["detail"] == "Invalid request parameters"
    assert isinstance(payload["timestamp"], float)

    response_schema = app.openapi()["paths"]["/api/v1/status"]["get"]["responses"][
        "422"
    ]["content"]["application/json"]["schema"]
    assert response_schema == {
        "$ref": "#/components/schemas/ErrorResponse",
    }


def test_every_operation_advertises_structured_error_responses() -> None:
    """Typed consumers must see the structured errors any operation may emit."""
    schema = create_openapi_app().openapi()

    paths = cast("dict[str, dict[str, object]]", schema["paths"])
    for path, path_item in paths.items():
        for method in ("get", "put", "post", "delete", "patch"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            responses = cast("dict[str, dict[str, object]]", operation["responses"])
            for status_code in ("400", "403", "404", "409", "422", "500", "default"):
                content = responses[status_code]["content"]
                assert isinstance(content, dict)
                media = content["application/json"]
                assert isinstance(media, dict)
                response_schema = media["schema"]
                assert response_schema == {
                    "$ref": "#/components/schemas/ErrorResponse",
                }, f"{method.upper()} {path} has an untyped {status_code} response"
