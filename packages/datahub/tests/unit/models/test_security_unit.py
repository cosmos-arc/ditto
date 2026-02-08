"""Unit tests for Models - instrument."""

from dataclasses import asdict

import pytest
from ditto_datahub.stores.metadata.instrument import InstrumentRegistration


@pytest.mark.unit
class TestInstrumentRegistration:
    """Tests for InstrumentRegistration model."""

    def test_create_registration_with_required_fields(self) -> None:
        """Test creating InstrumentRegistration with required fields."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        assert registration.source_ticker == "600000.SH"
        assert registration.symbol == "600000"
        assert registration.name == "浦发银行"
        assert registration.exchange == "SSE"
        assert registration.asset_class == "stock"
        assert registration.list_date == "1999-11-10"
        assert registration.source == "tushare"
        assert registration.board is None

    def test_create_registration_with_optional_fields(self) -> None:
        """Test creating InstrumentRegistration with optional fields."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
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
        """Test InstrumentRegistration can be serialized to dict."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        data = asdict(registration)

        assert data["source_ticker"] == "600000.SH"
        assert data["symbol"] == "600000"
        assert data["name"] == "浦发银行"
        assert data["exchange"] == "SSE"

    def test_model_deserialization_from_dict(self) -> None:
        """Test InstrumentRegistration can be deserialized from dict."""
        data = {
            "source_ticker": "600000.SH",
            "symbol": "600000",
            "name": "浦发银行",
            "exchange": "SSE",
            "asset_class": "stock",
            "list_date": "1999-11-10",
            "source": "tushare",
            "board": "主板",
        }

        registration = InstrumentRegistration(**data)

        assert registration.source_ticker == "600000.SH"
        assert registration.symbol == "600000"
        assert registration.board == "主板"

    def test_validation_fails_with_missing_required_field(self) -> None:
        """Test that validation fails when required field is missing."""
        with pytest.raises(TypeError) as exc_info:
            InstrumentRegistration(
                # Missing required fields
                source_ticker="600000.SH",
            )

        # dataclass 会抛出 TypeError，提示缺少必需参数
        error_msg = str(exc_info.value).lower()
        assert "missing" in error_msg or "required" in error_msg

    def test_json_serialization(self) -> None:
        """Test InstrumentRegistration can be serialized to JSON."""
        import json

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            symbol="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        # 使用 asdict + json.dumps 代替 model_dump_json
        json_str = json.dumps(asdict(registration), ensure_ascii=False)

        assert "600000.SH" in json_str
        assert "600000" in json_str
        assert "浦发银行" in json_str
