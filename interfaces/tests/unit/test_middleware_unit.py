"""Tests for FastAPI middleware async handlers."""

import pytest
from ditto_interfaces.middleware import (
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
        line_errors: list[dict[str, object]] = [
            {
                "type": "missing",
                "loc": ("field",),
                "input": None,
                "msg": "Field required",
            }
        ]
        error = ValidationError.from_exception_data(
            "test",
            line_errors,  # type: ignore[arg-type]
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


@pytest.mark.unit
class TestAPIErrorHandler:
    """Tests for api_error_handler middleware."""

    @pytest.mark.asyncio
    async def test_not_found_error(self):
        """NotFoundError 应返回 404."""
        from ditto_interfaces.api.errors import NotFoundError
        from ditto_interfaces.middleware import api_error_handler

        request = create_mock_request()
        exc = NotFoundError("Resource not found")
        response = await api_error_handler(request, exc)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_conflict_error(self):
        """ConflictError 应返回 409."""
        from ditto_interfaces.api.errors import ConflictError
        from ditto_interfaces.middleware import api_error_handler

        request = create_mock_request()
        exc = ConflictError("Status conflict")
        response = await api_error_handler(request, exc)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_bad_request_error(self):
        """BadRequestError 应返回 400."""
        from ditto_interfaces.api.errors import BadRequestError
        from ditto_interfaces.middleware import api_error_handler

        request = create_mock_request()
        exc = BadRequestError("Invalid input")
        response = await api_error_handler(request, exc)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_forbidden_error(self):
        """ForbiddenError 应返回 403."""
        from ditto_interfaces.api.errors import ForbiddenError
        from ditto_interfaces.middleware import api_error_handler

        request = create_mock_request()
        exc = ForbiddenError("Access denied")
        response = await api_error_handler(request, exc)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_api_error_delegates_to_general(self):
        """非 APIError 异常应委托给 general_exception_handler."""
        from ditto_interfaces.middleware import api_error_handler

        request = create_mock_request()
        exc = RuntimeError("Not an API error")
        response = await api_error_handler(request, exc)
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_ditto_exception_delegates_api_error_to_api_handler(self):
        """ditto_exception_handler 应将 APIError 委托给 api_error_handler."""
        from ditto_interfaces.api.errors import NotFoundError

        request = create_mock_request()
        exc = NotFoundError("Not found")
        response = await ditto_exception_handler(request, exc)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_ditto_exception_non_api_uses_original_logic(self):
        """非 APIError 的 DittoException 仍返回 400."""
        from ditto_interfaces.exceptions import DataNotFoundError

        request = create_mock_request()
        exc = DataNotFoundError("strategy", "missing")
        response = await ditto_exception_handler(request, exc)
        assert response.status_code == 400
