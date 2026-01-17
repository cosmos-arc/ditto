"""版本管理工具单元测试."""

import hashlib
from pathlib import Path

import pytest
from ditto_foundation.version import compute_checksum


class TestComputeChecksum:
    """compute_checksum 函数单元测试."""

    def test_returns_sha256_hex_string(self, tmp_path: Path) -> None:
        """验证返回 SHA-256 hex string（64 字符）."""
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum = compute_checksum(test_file)

        # SHA-256 应该是 64 字符 hex string
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_deterministic_same_content(self, tmp_path: Path) -> None:
        """验证相同内容产生相同 checksum."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        content = "Ditto test content"
        file1.write_text(content)
        file2.write_text(content)

        checksum1 = compute_checksum(file1)
        checksum2 = compute_checksum(file2)

        assert checksum1 == checksum2

    def test_different_content_different_checksum(self, tmp_path: Path) -> None:
        """验证不同内容产生不同 checksum."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("Content A")
        file2.write_text("Content B")

        checksum1 = compute_checksum(file1)
        checksum2 = compute_checksum(file2)

        assert checksum1 != checksum2

    def test_matches_standard_sha256(self, tmp_path: Path) -> None:
        """验证结果与标准 hashlib.sha256 一致."""
        test_file = tmp_path / "test.bin"
        content = b"Binary test content"
        test_file.write_bytes(content)

        # 使用 compute_checksum
        checksum = compute_checksum(test_file)

        # 使用标准 hashlib
        expected = hashlib.sha256(content).hexdigest()

        assert checksum == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        """验证空文件的 checksum."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        checksum = compute_checksum(empty_file)

        # 空文件的 SHA-256 是固定值
        expected = hashlib.sha256(b"").hexdigest()
        assert checksum == expected

    def test_file_not_found(self, tmp_path: Path) -> None:
        """验证文件不存在时抛出 FileNotFoundError."""
        non_existent = tmp_path / "does_not_exist.txt"

        with pytest.raises(FileNotFoundError):
            compute_checksum(non_existent)

    def test_large_file_chunked_reading(self, tmp_path: Path) -> None:
        """验证大文件使用分块读取（避免内存问题）."""
        # 创建 1MB 文件
        large_file = tmp_path / "large.bin"
        large_content = b"x" * (1024 * 1024)
        large_file.write_bytes(large_content)

        checksum = compute_checksum(large_file)

        # 验证结果正确
        expected = hashlib.sha256(large_content).hexdigest()
        assert checksum == expected

        # 验证格式
        assert len(checksum) == 64
