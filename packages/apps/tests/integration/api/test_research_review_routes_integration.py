"""Integration test: research review queue route OpenAPI metadata.

Verifies GET /research/reviews is exposed in the OpenAPI schema with
experimental maturity. Uses the production app object so the maturity-aware
openapi schema (build_maturity_openapi_schema) is exercised.
"""

from __future__ import annotations

import pytest
from ditto_apps.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_review_route_exposed_with_experimental_maturity(
    client: TestClient,
) -> None:
    """GET /research/reviews exists in OpenAPI with experimental maturity."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    path = "/api/v1/research/reviews"
    assert path in paths, f"missing review queue route {path}"
    get = paths[path]["get"]
    assert get["x-ditto-maturity"] == "experimental"
