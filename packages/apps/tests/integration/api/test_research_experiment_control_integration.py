"""Integration test: research experiment control routes OpenAPI metadata.

Verifies the 4 control routes (pause/cancel/resume/retry-fold) are exposed in
the OpenAPI schema with experimental maturity. Uses the production app object
so the maturity-aware openapi schema (build_maturity_openapi_schema) is exercised.
"""

from __future__ import annotations

import pytest
from ditto_apps.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_control_routes_exposed_with_experimental_maturity(
    client: TestClient,
) -> None:
    """4 control routes exist in OpenAPI with experimental maturity."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for suffix in ("/pause", "/cancel", "/resume", "/retry-fold"):
        path = f"/api/v1/research/experiments/{{experiment_id}}{suffix}"
        assert path in paths, f"missing control route {path}"
        post = paths[path]["post"]
        assert post["x-ditto-maturity"] == "experimental"
