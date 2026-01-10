"""Tests for FastAPI main application async endpoints."""

import pytest
from ditto_server.main import get_status, health_check, root, test_logging


class TestFastAPIEndpoints:
    """Tests for FastAPI async endpoint functions."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test root endpoint returns expected message."""
        response = await root()
        assert response == {"message": "Ditto Quant API", "version": "0.1.0"}

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self):
        """Test health check endpoint returns ok status."""
        response = await health_check()
        assert response["status"] == "ok"
        assert response["service"] == "ditto-api"
        assert "timestamp" in response
        assert response["features"]["prefect"] is True
        assert response["features"]["observability"] is True

    @pytest.mark.asyncio
    async def test_get_status_endpoint(self):
        """Test get status endpoint returns system status."""
        response = await get_status()
        assert response["status"] == "running"
        assert response["version"] == "0.1.0"
        assert "environment" in response
        assert response["features"]["data_collection"] is True
        assert response["features"]["data_validation"] is True

    @pytest.mark.asyncio
    async def test_test_logging_endpoint(self):
        """Test test logging endpoint generates logs."""
        response = await test_logging()
        assert response == {"message": "Test logs generated"}
