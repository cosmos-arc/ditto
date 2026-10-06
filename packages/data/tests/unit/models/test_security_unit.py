"""Unit tests for Models - instrument."""

from collections.abc import Callable
from dataclasses import asdict
from typing import TypedDict, cast

import pytest
from ditto_data.storage.metadata.instrument import InstrumentRegistration


class _RegistrationData(TypedDict):
    """反序列化输入的精确键型（kwargs 解包受检）."""

    source_ticker: str
    ticker: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str
    board: str


@pytest.mark.unit
class TestInstrumentRegistration:
    """Tests for InstrumentRegistration model."""

    def test_create_registration_with_required_fields(self) -> None:
        """Test creating InstrumentRegistration with required fields."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        assert registration.source_ticker == "600000.SH"
        assert registration.ticker == "600000"
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
            ticker="600000",
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
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        data = asdict(registration)

        assert data["source_ticker"] == "600000.SH"
        assert data["ticker"] == "600000"
        assert data["name"] == "浦发银行"
        assert data["exchange"] == "SSE"

    def test_model_deserialization_from_dict(self) -> None:
        """Test InstrumentRegistration can be deserialized from dict."""
        data: _RegistrationData = {
            "source_ticker": "600000.SH",
            "ticker": "600000",
            "name": "浦发银行",
            "exchange": "SSE",
            "asset_class": "stock",
            "list_date": "1999-11-10",
            "source": "tushare",
            "board": "主板",
        }

        registration = InstrumentRegistration(**data)

        assert registration.source_ticker == "600000.SH"
        assert registration.ticker == "600000"
        assert registration.board == "主板"

    def test_validation_fails_with_missing_required_field(self) -> None:
        """Test that validation fails when required field is missing."""
        # 负向测试：故意缺参触发 TypeError；cast 绕过构造器参数完整性检查。
        ctor = cast("Callable[..., object]", InstrumentRegistration)
        with pytest.raises(TypeError) as exc_info:
            ctor(source_ticker="600000.SH")

        # dataclass 会抛出 TypeError，提示缺少必需参数
        error_msg = str(exc_info.value).lower()
        assert "missing" in error_msg or "required" in error_msg

    def test_create_registration_with_delist_date(self) -> None:
        """Test creating InstrumentRegistration with delist_date."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
            delist_date="2025-06-30",
        )

        assert registration.delist_date == "2025-06-30"

    def test_create_registration_delist_date_defaults_to_none(self) -> None:
        """Test that delist_date defaults to None when not provided."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        assert registration.delist_date is None

    def test_model_serialization_includes_delist_date(self) -> None:
        """Test that serialization includes delist_date field."""
        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
            delist_date="2025-06-30",
        )

        data = asdict(registration)

        assert "delist_date" in data
        assert data["delist_date"] == "2025-06-30"

    def test_json_serialization(self) -> None:
        """Test InstrumentRegistration can be serialized to JSON."""
        import orjson

        registration = InstrumentRegistration(
            source_ticker="600000.SH",
            ticker="600000",
            name="浦发银行",
            exchange="SSE",
            asset_class="stock",
            list_date="1999-11-10",
        )

        json_bytes = orjson.dumps(asdict(registration))
        json_str = json_bytes.decode("utf-8")

        assert "600000.SH" in json_str
        assert "600000" in json_str
        assert "浦发银行" in json_str
