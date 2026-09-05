"""CORS deployment allowlist tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from ditto_apps.api.cors import configure_cors
from ditto_apps.config.runtime import (
    RuntimeConfigurationError,
    resolve_cors_origins,
)
from ditto_apps.middleware import HTTPObservabilityMiddleware
from ditto_platform.foundation import Metrics
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


def test_cors_defaults_to_actual_loopback_web_origins() -> None:
    assert resolve_cors_origins({}) == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )


def test_ditto_cors_origins_supports_dynamic_supervisor_ports() -> None:
    origins = resolve_cors_origins(
        {"DITTO_CORS_ORIGINS": ("http://127.0.0.1:43123, http://localhost:43123")}
    )

    assert origins == (
        "http://127.0.0.1:43123",
        "http://localhost:43123",
    )


def test_new_cors_variable_precedes_legacy_alias() -> None:
    origins = resolve_cors_origins(
        {
            "DITTO_CORS_ORIGINS": "http://127.0.0.1:43123",
            "CORS_ORIGINS": "http://127.0.0.1:9999",
        }
    )

    assert origins == ("http://127.0.0.1:43123",)


def test_legacy_cors_variable_remains_a_transition_alias() -> None:
    origins = resolve_cors_origins({"CORS_ORIGINS": "https://ditto.example.test"})

    assert origins == ("https://ditto.example.test",)


@pytest.mark.parametrize(
    "origin",
    ["*", "https://*.example.test", "https://example.test/path", "example.test"],
)
def test_cors_rejects_wildcards_and_non_origin_values(origin: str) -> None:
    with pytest.raises(RuntimeConfigurationError, match="origin"):
        resolve_cors_origins({"DITTO_CORS_ORIGINS": origin})


def test_configure_cors_installs_exact_resolved_allowlist() -> None:
    test_app = FastAPI()

    configure_cors(
        test_app,
        environ={"DITTO_CORS_ORIGINS": "http://127.0.0.1:45678"},
    )

    middleware = next(
        item for item in test_app.user_middleware if item.cls is CORSMiddleware
    )
    assert middleware.kwargs["allow_origins"] == ["http://127.0.0.1:45678"]
    assert middleware.kwargs["allow_credentials"] is True
    assert middleware.kwargs["expose_headers"] == ["X-Request-ID", "X-Trace-ID"]


def test_cors_preflight_allows_only_the_explicit_dynamic_origin() -> None:
    test_app = FastAPI()
    configure_cors(
        test_app,
        environ={"DITTO_CORS_ORIGINS": "http://127.0.0.1:45678"},
    )
    client = TestClient(test_app)
    request_headers = {"Access-Control-Request-Method": "GET"}

    allowed = client.options(
        "/",
        headers={"Origin": "http://127.0.0.1:45678", **request_headers},
    )
    denied = client.options(
        "/",
        headers={"Origin": "http://127.0.0.1:45679", **request_headers},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ("http://127.0.0.1:45678")
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_disallowed_simple_origin_is_rejected_before_mutation() -> None:
    """CORS policy is an execution boundary, not only a response-header policy."""
    test_app = FastAPI()
    mutations = 0

    @test_app.post("/mutate")
    async def mutate() -> dict[str, bool]:
        nonlocal mutations
        mutations += 1
        return {"mutated": True}

    configure_cors(
        test_app,
        environ={"DITTO_CORS_ORIGINS": "http://127.0.0.1:45678"},
    )
    response = TestClient(test_app).post(
        "/mutate",
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "CORS_ORIGIN_DENIED"
    assert mutations == 0
    assert "access-control-allow-origin" not in response.headers


def test_allowed_origin_receives_structured_unhandled_error() -> None:
    """CORS must wrap the HTTP error boundary so Web can read typed 500 bodies."""
    test_app = FastAPI()

    @test_app.get("/fail")
    async def fail() -> None:
        raise RuntimeError("boom")

    test_app.add_middleware(HTTPObservabilityMiddleware)
    configure_cors(
        test_app,
        environ={"DITTO_CORS_ORIGINS": "http://127.0.0.1:45678"},
    )
    response = TestClient(test_app, raise_server_exceptions=False).get(
        "/fail",
        headers={"Origin": "http://127.0.0.1:45678"},
    )

    assert response.status_code == 500
    assert response.json()["error"] == "INTERNAL_SERVER_ERROR"
    assert response.headers["access-control-allow-origin"] == ("http://127.0.0.1:45678")


def test_runtime_cors_wraps_an_observable_origin_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Denied browser requests remain correlated and bounded in HTTP evidence."""
    from ditto_apps.main import app

    records: list[dict[str, object]] = []
    monkeypatch.setattr(
        Metrics.api_requests,
        "add",
        lambda _amount, attributes=None: records.append(attributes or {}),
    )
    middleware = [entry.cls for entry in app.user_middleware]
    assert middleware[0] is CORSMiddleware
    assert next(i for i, cls in enumerate(middleware) if cls is CORSMiddleware) < next(
        i for i, cls in enumerate(middleware) if cls is HTTPObservabilityMiddleware
    )

    response = TestClient(app).post(
        "/api/v1/backtests/runs/not-executed/cancel",
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    UUID(response.headers["X-Request-ID"])
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert records == [
        {
            "method": "POST",
            "route": "unmatched",
            "status_code": 403,
        }
    ]
