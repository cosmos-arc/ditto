"""Tests for TdxReader."""

import struct
from pathlib import Path

import pytest
from ditto_data.sources.tdx.reader import TdxReader


@pytest.mark.unit
class TestTdxReader:
    """Tests for TdxReader."""

    def setup_method(self) -> None:
        """Set up test reader and mock TDX files."""
        import tempfile

        self.temp_dir = tempfile.mkdtemp()
        self.tdx_path = Path(self.temp_dir)

        # Create mock directory structure
        (self.tdx_path / "sh" / "lday").mkdir(parents=True, exist_ok=True)
        (self.tdx_path / "sz" / "lday").mkdir(parents=True, exist_ok=True)

        self.reader = TdxReader(self.tdx_path)

    def teardown_method(self) -> None:
        """Clean up after test."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_day_file(
        self,
        market: str,
        symbol: str,
        records: list[tuple],
    ) -> Path:
        """Create a mock .day file with test data."""
        day_file = self.tdx_path / market / "lday" / f"{symbol}.day"

        packed_records = []
        for record in records:
            packed_records.append(struct.pack("<IIIIIfII", *record))

        with day_file.open("wb") as f:
            f.write(b"".join(packed_records))

        return day_file

    def test_tdx_reader_init(self) -> None:
        """Test TdxReader initialization."""
        assert self.reader.tdx_path == self.tdx_path
        assert self.reader.RECORD_SIZE == 32
        assert self.reader.RECORD_FORMAT == "<IIIIIfII"

    def test_parse_market(self) -> None:
        """Test market code parsing."""
        assert self.reader._parse_market("000001.SZ") == "sz"
        assert self.reader._parse_market("600000.SH") == "sh"
        assert self.reader._parse_market("800000.BJ") == "bj"
        assert self.reader._parse_market("invalid") == "sz"  # default

    def test_locate_day_file(self) -> None:
        """Test .day file location."""
        path = self.reader._locate_day_file("sz", "000001")
        assert path == self.tdx_path / "sz" / "lday" / "000001.day"

        path = self.reader._locate_day_file("sh", "600000")
        assert path == self.tdx_path / "sh" / "lday" / "600000.day"

    def test_schema(self) -> None:
        """Test output schema."""
        schema = self.reader._schema()
        assert "trade_date" in schema
        assert "open" in schema
        assert "high" in schema
        assert "low" in schema
        assert "close" in schema
        assert "volume" in schema
        assert "amount" in schema

    def test_read_daily_basic(self) -> None:
        """Test basic daily data reading."""
        # Create mock .day file
        # Format: date, open, high, low, close, amount, vol, reserved
        # Prices are in cents (* 100), volume is in lots
        records = [
            (20240101, 10500, 10600, 10400, 10550, 1000000, 1000, 0),
            (20240102, 10550, 10700, 10500, 10650, 1200000, 1200, 0),
        ]
        self._create_mock_day_file("sz", "000001", records)

        df = self.reader.read_daily("000001.SZ")

        assert df.height == 2
        assert "trade_date" in df.columns
        assert "open" in df.columns
        assert "close" in df.columns

        # Check price conversion (÷100)
        assert df["open"][0] == 105.0
        assert df["close"][1] == 106.5

        # Check volume conversion (×100)
        assert df["volume"][0] == 100000

    def test_read_daily_with_date_filter(self) -> None:
        """Test reading with date filter."""
        records = [
            (20240101, 10500, 10600, 10400, 10550, 1000000, 1000, 0),
            (20240102, 10550, 10700, 10500, 10650, 1200000, 1200, 0),
            (20240103, 10650, 10800, 10600, 10750, 1300000, 1300, 0),
        ]
        self._create_mock_day_file("sz", "000001", records)

        # Filter by start_date
        df = self.reader.read_daily("000001.SZ", start_date="20240102")
        assert df.height == 2
        assert df["trade_date"][0] == "20240102"

        # Filter by end_date
        df = self.reader.read_daily("000001.SZ", end_date="20240102")
        assert df.height == 2
        assert df["trade_date"][-1] == "20240102"

        # Filter by both
        df = self.reader.read_daily(
            "000001.SZ", start_date="20240102", end_date="20240102"
        )
        assert df.height == 1
        assert df["trade_date"][0] == "20240102"

    def test_read_daily_nonexistent_file(self) -> None:
        """Test reading non-existent file returns empty DataFrame."""
        df = self.reader.read_daily("999999.SZ")

        assert df.is_empty()
        assert "trade_date" in df.columns

    def test_fetch_stock_daily_bars_single(self) -> None:
        """Test fetching single stock daily bars."""
        records = [(20240101, 10500, 10600, 10400, 10550, 1000000, 1000, 0)]
        self._create_mock_day_file("sz", "000001", records)

        df = self.reader.fetch_stock_daily_bars(["000001.SZ"], "20240101")

        assert df.height == 1
        assert "source_ticker" in df.columns
        assert df["source_ticker"][0] == "000001.SZ"

    def test_fetch_stock_daily_bars_multiple(self) -> None:
        """Test fetching multiple stocks daily bars."""
        records1 = [(20240101, 10500, 10600, 10400, 10550, 1000000, 1000, 0)]
        records2 = [(20240101, 20500, 20600, 20400, 20550, 2000000, 2000, 0)]

        self._create_mock_day_file("sz", "000001", records1)
        self._create_mock_day_file("sz", "000002", records2)

        df = self.reader.fetch_stock_daily_bars(["000001.SZ", "000002.SZ"], "20240101")

        assert df.height == 2
        assert df["source_ticker"].to_list() == ["000001.SZ", "000002.SZ"]

    def test_fetch_stock_daily_bars_empty(self) -> None:
        """Test fetching with no matching data."""
        df = self.reader.fetch_stock_daily_bars(["999999.SZ"], "20240101")

        assert df.is_empty()
        assert "source_ticker" in df.columns
