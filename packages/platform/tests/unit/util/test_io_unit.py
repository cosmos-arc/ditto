"""Tests for IO utilities in ditto-foundation."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from ditto_platform.foundation.util.io import (
    atomic_bytes_write,
    atomic_write,
    file_md5,
)


class TestAtomicWrite:
    """Test cases for atomic_write function."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_atomic_write_creates_file(self) -> None:
        """Test atomic_write creates a new file."""
        df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        target_path = self.temp_path / "test.parquet"

        atomic_write(df, target_path)

        assert target_path.exists()

    def test_atomic_write_preserves_data(self) -> None:
        """Test atomic_write preserves DataFrame data."""
        original_df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0, 30.0],
            }
        )
        target_path = self.temp_path / "test.parquet"

        atomic_write(original_df, target_path)

        # Read back and verify
        loaded_df = pl.read_parquet(target_path)
        assert loaded_df.equals(original_df)

    def test_atomic_write_overwrites_existing(self) -> None:
        """Test atomic_write overwrites existing file."""
        df1 = pl.DataFrame({"a": [1, 2, 3]})
        df2 = pl.DataFrame({"a": [4, 5, 6]})
        target_path = self.temp_path / "test.parquet"

        atomic_write(df1, target_path)
        atomic_write(df2, target_path)

        # Should contain df2 data
        loaded_df = pl.read_parquet(target_path)
        assert loaded_df.equals(df2)

    def test_atomic_write_creates_parent_directories(self) -> None:
        """Test atomic_write creates parent directories if needed."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        target_path = self.temp_path / "subdir" / "test.parquet"

        atomic_write(df, target_path)

        assert target_path.exists()

    def test_atomic_write_uses_compression(self) -> None:
        """Test atomic_write uses zstd compression by default."""
        df = pl.DataFrame({"a": range(1000), "b": range(1000)})
        target_path = self.temp_path / "test.parquet"

        atomic_write(df, target_path)

        # File should exist and be readable
        assert target_path.exists()
        loaded = pl.read_parquet(target_path)
        assert len(loaded) == 1000

    def test_atomic_write_with_fsync(self) -> None:
        """Test atomic_write with fsync=True ensures data durability."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        target_path = self.temp_path / "test_fsync.parquet"

        # Test writing with fsync enabled
        atomic_write(df, target_path, fsync=True)

        # File should exist and contain correct data
        assert target_path.exists()
        loaded_df = pl.read_parquet(target_path)
        assert loaded_df.equals(df)

        # Additional verification: file should be flushed to disk
        # (We can't easily test the actual fsync behavior, but we can verify
        # the file is properly written and readable)

    def test_atomic_write_without_fsync(self) -> None:
        """Test atomic_write with fsync=False works normally."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        target_path = self.temp_path / "test_no_fsync.parquet"

        # Test writing with fsync disabled
        atomic_write(df, target_path, fsync=False)

        # File should exist and contain correct data
        assert target_path.exists()
        loaded_df = pl.read_parquet(target_path)
        assert loaded_df.equals(df)

    def test_atomic_write_fsync_default(self) -> None:
        """Test atomic_write default behavior includes fsync."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        target_path = self.temp_path / "test_default.parquet"

        # Test writing without specifying fsync (should default to True)
        atomic_write(df, target_path)

        # File should exist and contain correct data
        assert target_path.exists()
        loaded_df = pl.read_parquet(target_path)
        assert loaded_df.equals(df)

    def test_default_compression_zstd(self) -> None:
        """Default compression should be zstd (MAT-M-9)."""
        df = pl.DataFrame({"a": range(1000), "b": range(1000)})
        target_path = self.temp_path / "test_zstd.parquet"

        atomic_write(df, target_path)

        assert target_path.exists()
        loaded = pl.read_parquet(target_path)
        assert loaded.equals(df)

    def test_configurable_compression_snappy(self) -> None:
        """Explicit snappy compression should produce readable parquet (MAT-M-9)."""
        df = pl.DataFrame({"a": range(1000), "b": range(1000)})
        target_path = self.temp_path / "test_snappy.parquet"

        atomic_write(df, target_path, compression="snappy")

        assert target_path.exists()
        loaded = pl.read_parquet(target_path)
        assert loaded.equals(df)

    def test_configurable_compression_gzip(self) -> None:
        """Explicit gzip compression should produce readable parquet (MAT-M-9)."""
        df = pl.DataFrame({"a": range(1000), "b": range(1000)})
        target_path = self.temp_path / "test_gzip.parquet"

        atomic_write(df, target_path, compression="gzip")

        assert target_path.exists()
        loaded = pl.read_parquet(target_path)
        assert loaded.equals(df)

    def test_configurable_compression_none(self) -> None:
        """No compression should produce readable parquet (MAT-M-9)."""
        df = pl.DataFrame({"a": range(1000), "b": range(1000)})
        target_path = self.temp_path / "test_none.parquet"

        atomic_write(df, target_path, compression="uncompressed")

        assert target_path.exists()
        loaded = pl.read_parquet(target_path)
        assert loaded.equals(df)


class TestAtomicBytesWrite:
    """Test cases for atomic_bytes_write function."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_creates_file(self) -> None:
        """atomic_bytes_write should create a new file."""
        target_path = self.temp_path / "test.json"
        data = b'{"key": "value"}'

        atomic_bytes_write(data, target_path)

        assert target_path.exists()
        assert target_path.read_bytes() == data

    def test_preserves_data(self) -> None:
        """atomic_bytes_write should preserve written bytes exactly."""
        target_path = self.temp_path / "data.bin"
        data = b"\x00\x01\x02\xff\xfe\xfd"

        atomic_bytes_write(data, target_path)

        assert target_path.read_bytes() == data

    def test_overwrites_existing(self) -> None:
        """atomic_bytes_write should overwrite existing file atomically."""
        target_path = self.temp_path / "test.json"

        atomic_bytes_write(b'{"version": 1}', target_path)
        atomic_bytes_write(b'{"version": 2}', target_path)

        assert target_path.read_bytes() == b'{"version": 2}'

    def test_creates_parent_directories(self) -> None:
        """atomic_bytes_write should create parent directories if needed."""
        target_path = self.temp_path / "subdir" / "nested" / "test.json"

        atomic_bytes_write(b"content", target_path)

        assert target_path.exists()

    def test_no_temp_file_left_on_success(self) -> None:
        """atomic_bytes_write should clean up the temp file after rename."""
        target_path = self.temp_path / "test.json"

        atomic_bytes_write(b"data", target_path)

        assert not (target_path.with_suffix(".json.tmp")).exists()
        assert target_path.exists()


class TestFileMd5:
    """Test cases for file_md5 function."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_file_md5_returns_hash(self) -> None:
        """Test file_md5 returns MD5 hash string."""
        test_file = self.temp_path / "test.txt"
        test_file.write_text("hello world")

        md5_hash = file_md5(test_file)

        # Should be a 32-character hex string
        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32

    def test_file_md5_consistent_for_same_content(self) -> None:
        """Test file_md5 returns same hash for same content."""
        test_file1 = self.temp_path / "test1.txt"
        test_file2 = self.temp_path / "test2.txt"
        content = "test content"

        test_file1.write_text(content)
        test_file2.write_text(content)

        hash1 = file_md5(test_file1)
        hash2 = file_md5(test_file2)

        assert hash1 == hash2

    def test_file_md5_different_for_different_content(self) -> None:
        """Test file_md5 returns different hashes for different content."""
        test_file = self.temp_path / "test.txt"

        test_file.write_text("content1")
        hash1 = file_md5(test_file)

        test_file.write_text("content2")
        hash2 = file_md5(test_file)

        assert hash1 != hash2

    def test_file_md5_matches_known_value(self) -> None:
        """Test file_md5 matches known MD5 hash."""
        test_file = self.temp_path / "test.txt"
        # MD5 of "hello world" is known: 5eb63bbbe01eeed093cb22bb8f5acdc3
        test_file.write_text("hello world")

        md5_hash = file_md5(test_file)

        assert md5_hash == "5eb63bbbe01eeed093cb22bb8f5acdc3"

    def test_file_md5_works_on_parquet_files(self) -> None:
        """Test file_md5 works on Parquet files."""
        df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        test_file = self.temp_path / "test.parquet"
        df.write_parquet(test_file)

        md5_hash = file_md5(test_file)

        assert isinstance(md5_hash, str)
        assert len(md5_hash) == 32


class TestWriterUniqueTmp:
    """#641：tmp 路径写入者唯一——重叠写入/进程终止不再共享 tmp 名撕裂目标."""

    def setup_method(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def teardown_method(self) -> None:
        self.temp_dir.cleanup()

    def test_concurrent_writers_target_always_complete(self) -> None:
        """票面验收①：两写入者竞写同一目标，目标恒为二者之一的完整版本."""
        import threading

        frame_a = pl.DataFrame({"a": range(50), "tag": ["A"] * 50})
        frame_b = pl.DataFrame({"a": range(50), "tag": ["B"] * 50})
        target = self.temp_path / "race.parquet"
        atomic_write(frame_a, target)

        def churn(frame: pl.DataFrame) -> None:
            for _ in range(50):
                atomic_write(frame, target, fsync=False)

        threads = [
            threading.Thread(target=churn, args=(frame,))
            for frame in (frame_a, frame_b)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = pl.read_parquet(target)
        assert loaded["tag"][0] in {"A", "B"}
        assert loaded.height == 50

    def test_interrupted_write_keeps_old_target(self, monkeypatch) -> None:
        """票面验收②：写入中途失败/被杀，目标保持旧完整版本（rename 前不落半成品）."""
        old = pl.DataFrame({"a": [1, 2, 3]})
        target = self.temp_path / "keep.parquet"
        atomic_write(old, target)

        def partial_then_raise(df_self, path, *args, **kwargs):
            Path(path).write_bytes(b"PAR1-half-written")  # 半成品落 tmp
            raise RuntimeError("simulated kill mid-write")

        monkeypatch.setattr(pl.DataFrame, "write_parquet", partial_then_raise)
        try:
            atomic_write(pl.DataFrame({"a": [9]}), target, fsync=False)
        except RuntimeError:
            pass

        # 目标仍是旧完整版本；共享名 tmp 不存在，残留为写入者唯一名
        assert pl.read_parquet(target).equals(old)
        assert not (target.parent / "keep.parquet.tmp").exists()
        leftovers = list(target.parent.glob("keep.parquet.*.tmp"))
        assert len(leftovers) == 1
        assert str(os.getpid()) in leftovers[0].name

    def test_tmp_names_unique_across_interrupted_calls(self, monkeypatch) -> None:
        """两次中断写入留下两个互不相同的 tmp 名——写入者唯一性核心断言."""
        target = self.temp_path / "uniq.parquet"

        def partial_then_raise(df_self, path, *args, **kwargs):
            Path(path).write_bytes(b"x")
            raise RuntimeError("kill")

        monkeypatch.setattr(pl.DataFrame, "write_parquet", partial_then_raise)
        for _ in range(2):
            try:
                atomic_write(pl.DataFrame({"a": [1]}), target, fsync=False)
            except RuntimeError:
                pass

        leftovers = sorted(p.name for p in target.parent.glob("uniq.parquet.*.tmp"))
        assert len(leftovers) == 2
        assert len(set(leftovers)) == 2

    def test_no_tmp_leftover_after_success_any_name(self) -> None:
        """成功写入不留任何名字的 tmp（覆盖旧 .tmp 固定名断言）."""
        target = self.temp_path / "clean.json"
        atomic_bytes_write(b"payload", target)
        assert target.read_bytes() == b"payload"
        assert not list(target.parent.glob("*.tmp"))
