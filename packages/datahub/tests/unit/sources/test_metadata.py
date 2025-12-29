"""Tests for ingestion metadata models."""

from ditto_datahub.sources.metadata import (
    IncrementalMode,
    IngestionMetadata,
)


class TestIncrementalMode:
    """Tests for IncrementalMode enum."""

    def test_quick_mode_value(self) -> None:
        """Test QUICK mode has correct value."""
        assert IncrementalMode.QUICK.value == "quick"

    def test_precise_mode_value(self) -> None:
        """Test PRECISE mode has correct value."""
        assert IncrementalMode.PRECISE.value == "precise"

    def test_enum_members(self) -> None:
        """Test enum has exactly two members."""
        assert len(IncrementalMode) == 2
        assert set(IncrementalMode) == {IncrementalMode.QUICK, IncrementalMode.PRECISE}


class TestIngestionMetadata:
    """Tests for IngestionMetadata dataclass."""

    def test_initialization_with_all_fields(self) -> None:
        """Test initialization with all fields provided."""
        metadata = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )
        assert metadata.dataset == "etf_daily"
        assert metadata.source == "tushare"
        assert metadata.last_trade_date == "2024-12-27"
        assert metadata.last_checksum == "abc123"
        assert metadata.last_rows == 5000
        assert metadata.last_updated_at == "2024-12-27T18:00:00"

    def test_initialization_with_optional_none(self) -> None:
        """Test initialization with optional fields as None."""
        metadata = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date=None,
            last_checksum=None,
            last_rows=0,
            last_updated_at="2024-12-27T10:00:00",
        )
        assert metadata.last_trade_date is None
        assert metadata.last_checksum is None
        assert metadata.last_rows == 0

    def test_equality(self) -> None:
        """Test metadata equality."""
        metadata1 = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )
        metadata2 = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )
        assert metadata1 == metadata2

    def test_inequality_different_dataset(self) -> None:
        """Test metadata inequality with different dataset."""
        metadata1 = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )
        metadata2 = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )
        assert metadata1 != metadata2
