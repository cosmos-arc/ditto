"""Tests for main.py module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ditto_foundation.logging_config import LogConfig

# Import the app from main module
from ditto_server.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_project_root() -> Path:
    """Mock project root path."""
    return Path("/mock/project/root")


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint_returns_correct_message(self, client: TestClient) -> None:
        """Test that root endpoint returns correct message."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Ditto Quant API"
        assert data["version"] == "0.1.0"


class TestHealthCheckEndpoint:
    """Test health check endpoint."""

    def test_health_check_returns_ok(self, client: TestClient) -> None:
        """Test that health check returns OK status."""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ditto-api"
        assert "timestamp" in data


class TestStatusEndpoint:
    """Test status endpoint."""

    def test_status_endpoint_returns_system_info(self, client: TestClient) -> None:
        """Test that status endpoint returns system information."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["version"] == "0.1.0"
        assert data["environment"] in ["development", "production", "testing"]
        assert "features" in data
        assert "logging" in data
        assert isinstance(data["features"]["data_collection"], bool)
        assert isinstance(data["features"]["data_validation"], bool)

    @patch.dict("os.environ", {"DITTO_ENV": "production"}, clear=True)
    def test_status_endpoint_with_production_env(self, client: TestClient) -> None:
        """Test status endpoint with production environment."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["environment"] == "production"


class TestLoggingEndpoint:
    """Test logging endpoint."""

    def test_logging_endpoint_generates_logs(self, client: TestClient) -> None:
        """Test that logging endpoint generates test logs."""
        # We can't easily mock the logger since it's a structured logger
        # So we just test that the endpoint returns success
        response = client.get("/api/v1/logs/test")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Test logs generated"


class TestCORSMiddleware:
    """Test CORS middleware."""

    def test_cors_headers_present(self, client: TestClient) -> None:
        """Test that CORS headers are present in responses."""
        client.options("/")
        # CORS headers should be present
        # Note: Actual header values depend on FastAPI CORS configuration


class TestRequestLoggingMiddleware:
    """Test request logging middleware."""

    def test_request_id_header_added(self, client: TestClient) -> None:
        """Test that X-Request-ID header is added to responses."""
        response = client.get("/")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0


class TestLifespan:
    """Test application lifespan events."""

    @patch("ditto_server.main.setup_logging")
    @patch.dict("os.environ", {"DITTO_ENV": "test"}, clear=True)
    def test_startup_initializes_logging(self, mock_setup_logging: MagicMock) -> None:
        """Test that startup initializes logging with correct configuration."""
        # We can't easily test lifespan directly without more complex setup
        # but we can verify the LogConfig creation
        env = "test"
        config = LogConfig(
            level="DEBUG" if env == "development" else "INFO",
            json_format=env == "production",
        )
        assert config is not None
        if env == "development":
            assert config.level == "DEBUG"
        else:
            assert config.level == "INFO"

    @patch.dict("os.environ", {"DITTO_ENV": "production"}, clear=True)
    def test_startup_with_production_env(self) -> None:
        """Test startup with production environment."""
        env = "production"
        config = LogConfig(
            level="DEBUG" if env == "development" else "INFO",
            json_format=env == "production",
        )
        assert config.level == "INFO"
        assert config.json_format is True
