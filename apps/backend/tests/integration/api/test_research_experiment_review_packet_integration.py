"""Integration test: review-packet route OpenAPI metadata.

Verifies GET /research/experiments/{experiment_id}/review-packet is exposed in
the OpenAPI schema with experimental maturity. Uses the production app object
so the maturity-aware openapi schema (build_maturity_openapi_schema) is
exercised.
"""

from __future__ import annotations

import pytest
from ditto_apps.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_review_packet_route_exposed_with_experimental_maturity(
    client: TestClient,
) -> None:
    """Review-packet route is exposed with experimental maturity."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    path = "/api/v1/research/experiments/{experiment_id}/review-packet"
    assert path in paths, f"missing review-packet route {path}"
    get = paths[path]["get"]
    assert get["x-ditto-maturity"] == "experimental"
