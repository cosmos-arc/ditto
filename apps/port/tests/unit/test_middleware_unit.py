"""Tests for FastAPI middleware async handlers."""

import pytest
from ditto_port.middleware import (
    ditto_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


def create_mock_request(path: str = "/test") -> Request:
    """Create a mock Request with minimal required scope."""
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "path": path,
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "root_path": "",
        "app": None,
    }
    return Request(scope=scope)


@pytest.mark.unit
class TestDittoExceptionHandler:
    """Tests for ditto_exception_handler."""

    @pytest.mark.asyncio
    async def test_ditto_exception_handler(self):
        """Test ditto exception handler returns proper error response."""
        request = create_mock_request()
        exc = RuntimeError("Ditto error")

        response = await ditto_exception_handler(request, exc)

        assert response.status_code == 500


@pytest.mark.unit
class TestHTTPExceptionHandler:
    """Tests for http_exception_handler."""

    @pytest.mark.asyncio
    async def test_http_exception_handler_404(self):
        """Test HTTP exception handler with 404 error."""
        request = create_mock_request()
        exc = HTTPException(status_code=404, detail="Not found")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_http_exception_handler_500(self):
        """Test HTTP exception handler with 500 error."""
        request = create_mock_request()
        exc = HTTPException(status_code=500, detail="Internal error")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 500


@pytest.mark.unit
class TestValidationExceptionHandler:
    """Tests for validation_exception_handler."""

    @pytest.mark.asyncio
    async def test_validation_exception_handler(self):
        """Test validation exception handler."""
        request = create_mock_request()

        # Create a validation error with proper structure
        error = ValidationError.from_exception_data(
            "test",
            [
                {
                    "type": "missing",
                    "loc": ("field",),
                    "input": {},
                    "msg": "Field required",
                }
            ],
        )
        exc = RequestValidationError(error.errors())

        response = await validation_exception_handler(request, exc)

        assert response.status_code == 422


@pytest.mark.unit
class TestGeneralExceptionHandler:
    """Tests for general_exception_handler."""

    @pytest.mark.asyncio
    async def test_general_exception_handler_runtime_error(self):
        """Test general exception handler with RuntimeError."""
        request = create_mock_request()
        exc = RuntimeError("Unexpected error")

        response = await general_exception_handler(request, exc)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_general_exception_handler_value_error(self):
        """Test general exception handler with ValueError."""
        request = create_mock_request()
        exc = ValueError("Invalid value")

        response = await general_exception_handler(request, exc)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_general_exception_handler_generic_exception(self):
        """Test general exception handler with generic Exception."""
        request = create_mock_request()
        exc = Exception("Generic error")

        response = await general_exception_handler(request, exc)

        assert response.status_code == 500
