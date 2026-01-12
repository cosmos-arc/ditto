"""Unit tests for _collect_checksums() refactoring."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ditto_datahub.runtime.freeze_manager import FreezeManager


class TestFreezeManagerCollectChecksumsRefactor:
    """Test cases for _collect_checksums() refactored methods."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.manager = FreezeManager(str(self.data_root))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_try_single_file_mode_success(self) -> None:
        """Test _try_single_file_mode returns success when file exists."""
        # Create test file
        test_file = self.data_root / "bars" / "stock_daily.parquet"
        test_file.parent.mkdir(parents=True)
        test_file.write_bytes(b"test_data")

        # Call method
        success, checksums = self.manager._try_single_file_mode("bars/stock_daily")

        # Assertions
        assert success is True
        assert checksums is not None
        assert "bars/stock_daily.parquet" in checksums
        # SHA-256 hash of "test_data" (9 bytes)
        # Verify hash is 64 hex chars (SHA-256 format)
        assert len(checksums["bars/stock_daily.parquet"]) == 64
        assert all(
            c in "0123456789abcdef" for c in checksums["bars/stock_daily.parquet"]
        )

    def test_try_single_file_mode_failure(self) -> None:
        """Test _try_single_file_mode returns failure when file not found."""
        # Don't create any file

        # Call method
        success, checksums = self.manager._try_single_file_mode("bars/nonexistent")

        # Assertions
        assert success is False
        assert checksums is None

    def test_try_partitioned_directory_mode_success(self) -> None:
        """Test _try_partitioned_directory_mode returns success when dir exists."""
        # Create partitioned directory structure
        dataset_dir = self.data_root / "bars" / "stock_daily"
        dataset_dir.mkdir(parents=True)

        # Create multiple parquet files
        (dataset_dir / "part1.parquet").write_bytes(b"data1")
        (dataset_dir / "part2.parquet").write_bytes(b"data2")
        subdir = dataset_dir / "subdir"
        subdir.mkdir()
        (subdir / "part3.parquet").write_bytes(b"data3")

        # Call method
        success, checksums = self.manager._try_partitioned_directory_mode(
            "bars/stock_daily"
        )

        # Assertions
        assert success is True
        assert checksums is not None
        assert len(checksums) == 3
        assert "bars/stock_daily/part1.parquet" in checksums
        assert "bars/stock_daily/part2.parquet" in checksums
        assert "bars/stock_daily/subdir/part3.parquet" in checksums

    def test_try_partitioned_directory_mode_failure_no_directory(self) -> None:
        """Test _try_partitioned_directory_mode returns failure when dir not found."""
        # Don't create any directory

        # Call method
        success, checksums = self.manager._try_partitioned_directory_mode(
            "bars/nonexistent"
        )

        # Assertions
        assert success is False
        assert checksums is None

    def test_try_partitioned_directory_mode_failure_empty_directory(self) -> None:
        """Test _try_partitioned_directory_mode returns failure when dir is empty."""
        # Create empty directory
        dataset_dir = self.data_root / "bars" / "empty_dataset"
        dataset_dir.mkdir(parents=True)

        # Call method
        success, checksums = self.manager._try_partitioned_directory_mode(
            "bars/empty_dataset"
        )

        # Assertions
        assert success is False
        assert checksums is None

    def test_get_missing_path_with_parent_exists(self) -> None:
        """Test _get_missing_path returns relative path when parent exists."""
        # Create parent directory
        bars_dir = self.data_root / "bars"
        bars_dir.mkdir(parents=True)

        # Call method
        missing_path = self.manager._get_missing_path("bars/stock_daily")

        # Assertions
        assert missing_path == "bars/stock_daily.parquet"

    def test_get_missing_path_without_parent(self) -> None:
        """Test _get_missing_path returns simple path when parent doesn't exist."""
        # Don't create any directory

        # Call method
        missing_path = self.manager._get_missing_path("bars/stock_daily")

        # Assertions
        assert missing_path == "bars/stock_daily.parquet"

    def test_handle_missing_files_raises_error(self) -> None:
        """Test _handle_missing_files raises FileNotFoundError."""
        missing_files = ["bars/stock_daily.parquet", "bars/etf_daily.parquet"]

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            self.manager._handle_missing_files("test_freeze", missing_files)

        # Check error message
        assert "Datasets not found for freeze 'test_freeze'" in str(exc_info.value)
        assert "bars/stock_daily.parquet" in str(exc_info.value)
        assert "bars/etf_daily.parquet" in str(exc_info.value)

    def test_handle_missing_files_empty_list_no_error(self) -> None:
        """Test _handle_missing_files does not raise when list is empty."""
        # Should not raise
        self.manager._handle_missing_files("test_freeze", [])

    def test_collect_checksums_integration_single_file(self) -> None:
        """Test _collect_checksums with single file mode."""
        # Create test file
        test_file = self.data_root / "bars" / "stock_daily.parquet"
        test_file.parent.mkdir(parents=True)
        test_file.write_bytes(b"test_data")

        # Call method
        checksums = self.manager._collect_checksums(
            "test_freeze",
            ["bars/stock_daily"],
        )

        # Assertions
        assert len(checksums) == 1
        assert "bars/stock_daily.parquet" in checksums

    def test_collect_checksums_integration_partitioned(self) -> None:
        """Test _collect_checksums with partitioned directory mode."""
        # Create partitioned directory structure
        dataset_dir = self.data_root / "bars" / "stock_daily"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "part1.parquet").write_bytes(b"data1")
        (dataset_dir / "part2.parquet").write_bytes(b"data2")

        # Call method
        checksums = self.manager._collect_checksums(
            "test_freeze",
            ["bars/stock_daily"],
        )

        # Assertions
        assert len(checksums) == 2
        assert "bars/stock_daily/part1.parquet" in checksums
        assert "bars/stock_daily/part2.parquet" in checksums

    def test_collect_checksums_integration_mixed_modes(self) -> None:
        """Test _collect_checksums with mixed single file and partitioned modes."""
        # Create single file
        single_file = self.data_root / "bars" / "stock_daily.parquet"
        single_file.parent.mkdir(parents=True)
        single_file.write_bytes(b"single")

        # Create partitioned directory
        dataset_dir = self.data_root / "bars" / "etf_daily"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "part1.parquet").write_bytes(b"part1")
        (dataset_dir / "part2.parquet").write_bytes(b"part2")

        # Call method
        checksums = self.manager._collect_checksums(
            "test_freeze",
            ["bars/stock_daily", "bars/etf_daily"],
        )

        # Assertions
        assert len(checksums) == 3
        assert "bars/stock_daily.parquet" in checksums
        assert "bars/etf_daily/part1.parquet" in checksums
        assert "bars/etf_daily/part2.parquet" in checksums

    def test_collect_checksums_integration_missing_files(self) -> None:
        """Test _collect_checksums raises FileNotFoundError when files are missing."""
        # Create only one file
        test_file = self.data_root / "bars" / "stock_daily.parquet"
        test_file.parent.mkdir(parents=True)
        test_file.write_bytes(b"test_data")

        # Call method with one existing and one missing dataset
        with pytest.raises(FileNotFoundError) as exc_info:
            self.manager._collect_checksums(
                "test_freeze",
                ["bars/stock_daily", "bars/nonexistent"],
            )

        # Check error message
        assert "Datasets not found for freeze 'test_freeze'" in str(exc_info.value)
        assert "bars/nonexistent.parquet" in str(exc_info.value)
