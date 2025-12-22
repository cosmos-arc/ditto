"""Tests for BarsStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_datahub.stores.bars_store import BarsStore


class TestBarsStore:
    """Tests for BarsStore."""

    @pytest.fixture
    def temp_data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        data_root = tmp_path / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        return data_root

    @pytest.fixture
    def bars_store(self, temp_data_root: Path) -> BarsStore:
        """Create BarsStore instance."""
        return BarsStore(temp_data_root)

    @pytest.fixture
    def sample_df(self) -> pl.DataFrame:
        """Create sample market daily data."""
        data: dict[str, list[Any]] = {
            "sid": [100000001, 100000001, 100000001, 100000002],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 2),
            ],
            "source": ["tushare", "tushare", "tushare", "tushare"],
            "src_code": ["000001.SZ", "000001.SZ", "000001.SZ", "000002.SZ"],
            "open": [10.0, 10.5, 11.0, 20.0],
            "high": [10.5, 11.0, 11.5, 20.5],
            "low": [9.8, 10.2, 10.8, 19.8],
            "close": [10.3, 10.8, 11.2, 20.2],
            "pre_close": [9.8, 10.3, 10.8, 19.5],
            "volume": [1000000, 1200000, 900000, 800000],
            "amount": [10300000, 12960000, 10080000, 16160000],
            "pct_change": [5.1, 4.85, 3.7, 3.59],
            "turnover": [0.5, 0.6, 0.45, 0.4],
            "is_suspended": [False, False, False, False],
            "is_limit_up": [False, False, False, False],
            "is_limit_down": [False, False, False, False],
            "is_st": [False, False, False, False],
        }
        return pl.DataFrame(data)

    # ============ _get_path tests ============

    def test_get_path(self, bars_store: BarsStore, temp_data_root: Path) -> None:
        """Test getting file path for year partition."""
        path = bars_store._get_path("market_daily", 2024)
        expected = temp_data_root / "market_daily" / "2024.parquet"
        assert path == expected

    # ============ _collect_paths tests ============

    def test_collect_paths_empty(self, bars_store: BarsStore) -> None:
        """Test collecting paths when no files exist."""
        paths = bars_store._collect_paths("market_daily", 2020, 2024)
        assert paths == []

    def test_collect_paths_partial(
        self, bars_store: BarsStore, temp_data_root: Path
    ) -> None:
        """Test collecting paths when only some years exist."""
        market_dir = temp_data_root / "market_daily"
        market_dir.mkdir(parents=True, exist_ok=True)

        # Create files for 2021, 2022, 2024 (skip 2020, 2023)
        for year in [2021, 2022, 2024]:
            (market_dir / f"{year}.parquet").touch()

        paths = bars_store._collect_paths("market_daily", 2020, 2024)
        assert len(paths) == 3
        assert all(
            p.name == f"{y}.parquet"
            for p, y in zip(paths, [2021, 2022, 2024], strict=False)
        )

    # ============ read tests ============

    def test_read_empty(self, bars_store: BarsStore) -> None:
        """Test reading when no data exists."""
        df = bars_store.read("market_daily")
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0

    def test_read_no_filters(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test reading all data without filters."""
        # Write test data
        bars_store.write("market_daily", sample_df, 2024)

        # Read back
        result = bars_store.read("market_daily")
        assert len(result) == len(sample_df)
        assert set(result.columns) >= {"sid", "trade_date", "open", "close"}

    def test_read_filter_by_sids(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test reading filtered by security IDs."""
        bars_store.write("market_daily", sample_df, 2024)

        result = bars_store.read("market_daily", sids=[100000001])
        assert len(result) == 3
        assert result["sid"].unique().to_list() == [100000001]

    def test_read_filter_by_date_range(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test reading filtered by date range."""
        bars_store.write("market_daily", sample_df, 2024)

        result = bars_store.read(
            "market_daily", start_date="2024-01-02", end_date="2024-01-02"
        )
        # Sample data has 2 records on 2024-01-02 (both securities)
        assert len(result) == 2

    def test_read_multiple_years(self, bars_store: BarsStore) -> None:
        """Test reading across multiple year partitions."""
        # Create data for multiple years
        df_2023 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2023, 12, 31)],
                "close": [10.0],
            }
        )
        df_2024 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 2)],
                "close": [10.5],
            }
        )

        bars_store.write("market_daily", df_2023, 2023)
        bars_store.write("market_daily", df_2024, 2024)

        result = bars_store.read("market_daily", start_date="2023-12-01")
        assert len(result) == 2
        assert result["trade_date"].min() == date(2023, 12, 31)

    # ============ write tests ============

    def test_write_new_file(
        self, bars_store: BarsStore, sample_df: pl.DataFrame, temp_data_root: Path
    ) -> None:
        """Test writing to a new file."""
        path, checksum = bars_store.write("market_daily", sample_df, 2024)

        assert path == str(temp_data_root / "market_daily" / "2024.parquet")
        assert isinstance(checksum, str)
        assert len(checksum) == 32  # MD5 hash length
        assert Path(path).exists()

    def test_write_merge_with_existing(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test writing merges with existing data."""
        # Write initial data
        initial_df = sample_df.filter(pl.col("trade_date") == date(2024, 1, 2))
        bars_store.write("market_daily", initial_df, 2024)

        # Write more data
        additional_df = sample_df.filter(pl.col("trade_date") != date(2024, 1, 2))
        bars_store.write("market_daily", additional_df, 2024)

        # Read back and verify merge
        result = bars_store.read("market_daily")
        assert len(result) == len(sample_df)

    def test_write_overwrite_existing(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test writing overwrites existing records (keep='last')."""
        # Write initial data
        initial_df = sample_df.clone()
        bars_store.write("market_daily", initial_df, 2024)

        # Write updated data for same sid/date
        updated_df = sample_df.with_columns(
            pl.col("close").mul(2.0)  # Double the close prices
        )
        bars_store.write("market_daily", updated_df, 2024)

        # Verify new data took precedence
        result = bars_store.read("market_daily").sort(["sid", "trade_date"])
        original_close = sample_df.sort(["sid", "trade_date"])["close"].to_list()
        new_close = result["close"].to_list()

        # All values should be doubled
        for orig, new in zip(original_close, new_close, strict=False):
            assert new == orig * 2.0

    def test_write_creates_directory(
        self, bars_store: BarsStore, sample_df: pl.DataFrame, temp_data_root: Path
    ) -> None:
        """Test that write creates parent directories."""
        market_dir = temp_data_root / "market_daily"

        # Directory shouldn't exist yet
        assert not market_dir.exists()

        # Write should create it
        bars_store.write("market_daily", sample_df, 2024)

        assert market_dir.exists()

    # ============ get_years tests ============

    def test_get_years_empty(self, bars_store: BarsStore) -> None:
        """Test getting years when no data exists."""
        years = bars_store.get_years("market_daily")
        assert years == []

    def test_get_years(self, bars_store: BarsStore, sample_df: pl.DataFrame) -> None:
        """Test getting list of available years."""
        for year in [2020, 2021, 2023, 2024]:
            bars_store.write("market_daily", sample_df, year)

        years = bars_store.get_years("market_daily")
        assert set(years) == {2020, 2021, 2023, 2024}

    def test_get_years_ignores_invalid_files(
        self, bars_store: BarsStore, temp_data_root: Path, sample_df: pl.DataFrame
    ) -> None:
        """Test that get_years ignores non-integer filenames."""
        market_dir = temp_data_root / "market_daily"
        market_dir.mkdir(parents=True, exist_ok=True)

        # Create valid and invalid files
        bars_store.write("market_daily", sample_df, 2024)
        (market_dir / "README.md").touch()
        (market_dir / "2024.tmp").touch()

        years = bars_store.get_years("market_daily")
        assert years == [2024]

    # ============ delete tests ============

    def test_delete_year(
        self, bars_store: BarsStore, sample_df: pl.DataFrame, temp_data_root: Path
    ) -> None:
        """Test deleting a specific year partition."""
        # Write data for multiple years
        bars_store.write("market_daily", sample_df, 2023)
        bars_store.write("market_daily", sample_df, 2024)

        # Delete 2023
        deleted = bars_store.delete("market_daily", 2023)
        assert deleted is True

        # Verify 2023 is gone but 2024 remains
        years = bars_store.get_years("market_daily")
        assert years == [2024]

    def test_delete_nonexistent_year(self, bars_store: BarsStore) -> None:
        """Test deleting a year that doesn't exist."""
        deleted = bars_store.delete("market_daily", 2024)
        assert deleted is False

    # ============ get_checksum tests ============

    def test_get_checksum(self, bars_store: BarsStore, sample_df: pl.DataFrame) -> None:
        """Test getting file checksum."""
        bars_store.write("market_daily", sample_df, 2024)

        checksum = bars_store.get_checksum("market_daily", 2024)
        assert isinstance(checksum, str)
        assert len(checksum) == 32

    def test_get_checksum_missing_file(self, bars_store: BarsStore) -> None:
        """Test getting checksum for non-existent file."""
        checksum = bars_store.get_checksum("market_daily", 2024)
        assert checksum == ""

    # ============ count tests ============

    def test_count_empty(self, bars_store: BarsStore) -> None:
        """Test counting when no data exists."""
        count = bars_store.count("market_daily")
        assert count == 0

    def test_count(self, bars_store: BarsStore, sample_df: pl.DataFrame) -> None:
        """Test counting records."""
        bars_store.write("market_daily", sample_df, 2024)

        count = bars_store.count("market_daily")
        assert count == len(sample_df)

    def test_count_with_filters(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test counting with date filter."""
        bars_store.write("market_daily", sample_df, 2024)

        count = bars_store.count(
            "market_daily", start_date="2024-01-02", end_date="2024-01-02"
        )
        assert count == 2

    # ============ get_date_range tests ============

    def test_get_date_range_empty(self, bars_store: BarsStore) -> None:
        """Test getting date range when no data exists."""
        start, end = bars_store.get_date_range("market_daily")
        assert start is None
        assert end is None

    def test_get_date_range(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test getting overall date range."""
        bars_store.write("market_daily", sample_df, 2024)

        start, end = bars_store.get_date_range("market_daily")
        assert start == "2024-01-02"
        assert end == "2024-01-04"

    def test_get_date_range_multiple_years(
        self, bars_store: BarsStore, sample_df: pl.DataFrame
    ) -> None:
        """Test getting date range across multiple years."""
        df_2023 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2023, 12, 31)],
                "close": [10.0],
            }
        )
        df_2024 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 2)],
                "close": [10.5],
            }
        )

        bars_store.write("market_daily", df_2023, 2023)
        bars_store.write("market_daily", df_2024, 2024)

        start, end = bars_store.get_date_range("market_daily")
        assert start == "2023-12-31"
        assert end == "2024-01-02"

    # ============ list_sids tests ============

    def test_list_sids_empty(self, bars_store: BarsStore) -> None:
        """Test listing sids when no data exists."""
        sids = bars_store.list_sids("market_daily")
        assert sids == []

    def test_list_sids(self, bars_store: BarsStore, sample_df: pl.DataFrame) -> None:
        """Test listing unique security IDs."""
        bars_store.write("market_daily", sample_df, 2024)

        sids = bars_store.list_sids("market_daily")
        assert set(sids) == {100000001, 100000002}
