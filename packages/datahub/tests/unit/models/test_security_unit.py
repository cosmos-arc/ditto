"""Unit tests for Models - security."""

import pytest
from ditto_datahub.models.security import SecurityRegistration
from pydantic import ValidationError


@pytest.mark.unit
class TestSecurityRegistration:
    """Tests for SecurityRegistration model."""

    def test_create_registration_with_required_fields(self) -> None:
        """Test creating SecurityRegistration with required fields."""
        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        assert registration.src_code == "600000.SH"
        assert registration.symbol == "600000"
        assert registration.name == "浦发银行"
        assert registration.exchange == "SSE"
        assert registration.asset_class == "stock"
        assert registration.list_date == "1999-11-10"
        assert registration.source == "tushare"
        assert registration.board is None

    def test_create_registration_with_optional_fields(self) -> None:
        """Test creating SecurityRegistration with optional fields."""
        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
            source="akshare",
            board="主板",
        )

        assert registration.source == "akshare"
        assert registration.board == "主板"

    def test_model_serialization_to_dict(self) -> None:
        """Test SecurityRegistration can be serialized to dict."""
        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        data = registration.model_dump()

        assert data["src_code"] == "600000.SH"
        assert data["symbol"] == "600000"
        assert data["name"] == "浦发银行"
        assert data["exchange"] == "SSE"

    def test_model_deserialization_from_dict(self) -> None:
        """Test SecurityRegistration can be deserialized from dict."""
        data = {
            "src_code": "600000.SH",
            "symbol": "600000",
            "name": "浦发银行",
            "exchange": "SSE",
            "asset_class": "stock",
            "list_date": "1999-11-10",
            "source": "tushare",
            "board": "主板",
        }

        registration = SecurityRegistration(**data)

        assert registration.src_code == "600000.SH"
        assert registration.symbol == "600000"
        assert registration.board == "主板"

    def test_validation_fails_with_missing_required_field(self) -> None:
        """Test that validation fails when required field is missing."""
        with pytest.raises(ValidationError) as exc_info:
            SecurityRegistration(
                # Missing required fields
                src_code="600000.SH",
            )

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "symbol" in error_fields
        assert "name" in error_fields
        assert "exchange" in error_fields
        assert "asset_class" in error_fields
        assert "list_date" in error_fields

    def test_json_serialization(self) -> None:
        """Test SecurityRegistration can be serialized to JSON."""
        registration = SecurityRegistration(
            src_code="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        json_str = registration.model_dump_json()

        assert "600000.SH" in json_str
        assert "600000" in json_str
        assert "浦发银行" in json_str
