"""Tests for common models in models/common.py."""

import pytest
from ditto_port.models.common import ErrorResponse


@pytest.mark.unit
class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_error_response_creation_with_all_fields(self):
        """Test ErrorResponse creation with all fields provided."""
        response = ErrorResponse(
            status_code=400,
            error="BadRequest",
            detail="Invalid input",
            error_code="ERR_001",
            request_id="req-123",
            timestamp=1234567890.0,
        )

        assert response.status_code == 400
        assert response.error == "BadRequest"
        assert response.detail == "Invalid input"
        assert response.error_code == "ERR_001"
        assert response.request_id == "req-123"
        assert response.timestamp == 1234567890.0

    def test_error_response_creation_with_required_fields_only(self):
        """Test ErrorResponse creation with only required fields."""
        response = ErrorResponse(
            status_code=500,
            error="InternalError",
        )

        assert response.status_code == 500
        assert response.error == "InternalError"
        assert response.detail is None
        assert response.error_code is None
        assert response.request_id is None
        assert response.timestamp is None

    def test_error_response_model_dump(self):
        """Test ErrorResponse model_dump for JSON serialization."""
        response = ErrorResponse(
            status_code=422,
            error="ValidationError",
            detail="Invalid request parameters",
            error_code="VAL_001",
        )

        data = response.model_dump()

        assert data["status_code"] == 422
        assert data["error"] == "ValidationError"
        assert data["detail"] == "Invalid request parameters"
        assert data["error_code"] == "VAL_001"
        assert "request_id" not in data or data["request_id"] is None
        assert "timestamp" not in data or data["timestamp"] is None

    def test_error_response_model_dump_exclude_none(self):
        """Test ErrorResponse model_dump with exclude_none."""
        response = ErrorResponse(
            status_code=404,
            error="NotFound",
            detail="Resource not found",
        )

        data = response.model_dump(exclude_none=True)

        assert data["status_code"] == 404
        assert data["error"] == "NotFound"
        assert data["detail"] == "Resource not found"
        assert "error_code" not in data
        assert "request_id" not in data
        assert "timestamp" not in data

    def test_error_response_is_mutable(self):
        """Test that ErrorResponse fields are mutable (Pydantic BaseModel default)."""
        response = ErrorResponse(
            status_code=400,
            error="BadRequest",
        )

        # API response models should be mutable for flexibility
        response.status_code = 500
        assert response.status_code == 500

        response.detail = "Updated detail"
        assert response.detail == "Updated detail"

    def test_error_response_json_serialization(self):
        """Test ErrorResponse JSON serialization."""
        response = ErrorResponse(
            status_code=400,
            error="BadRequest",
            detail="Invalid input",
            error_code="ERR_001",
        )

        json_str = response.model_dump_json()

        assert "status_code" in json_str
        assert "BadRequest" in json_str
        assert "Invalid input" in json_str
        assert "ERR_001" in json_str
