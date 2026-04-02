"""Tests for GoldenDatasetProvider YAML loading."""

from pathlib import Path

import pytest
from ditto_interfaces.registry.core.golden import GoldenDatasetProvider


@pytest.mark.unit
class TestGoldenDatasetProviderLoad:
    """测试 GoldenDatasetProvider 配置加载."""

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        """加载有效的 YAML 配置."""
        config_file = tmp_path / "golden.yml"
        config_file.write_text(
            """
description: Test config
tickers:
  - "600519"
  - "000001"
""",
            encoding="utf-8",
        )

        provider = GoldenDatasetProvider()
        result = provider._load_from_file(config_file)

        assert result is not None
        assert result.description == "Test config"
        assert "600519" in result.tickers

    def test_load_empty_yaml_returns_none(self, tmp_path: Path) -> None:
        """空 YAML 返回 None."""
        config_file = tmp_path / "empty.yml"
        config_file.write_text("", encoding="utf-8")

        provider = GoldenDatasetProvider()
        result = provider._load_from_file(config_file)

        assert result is None

    def test_load_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        """不存在的文件返回 None."""
        provider = GoldenDatasetProvider()
        result = provider._load_from_file(tmp_path / "nonexistent.yml")

        assert result is None

    def test_load_list_yaml_gracefully_returns_none(self, tmp_path: Path) -> None:
        """非字典 YAML（如列表）优雅返回 None 而非崩溃.

        这是常见的 YAML 误写场景：
        - item1
        - item2
        """
        config_file = tmp_path / "list.yml"
        config_file.write_text(
            """
- item1
- item2
""",
            encoding="utf-8",
        )

        provider = GoldenDatasetProvider()
        # 应该返回 None 而非抛出 TypeError
        result = provider._load_from_file(config_file)

        assert result is None

    def test_load_scalar_yaml_gracefully_returns_none(self, tmp_path: Path) -> None:
        """标量 YAML 优雅返回 None."""
        config_file = tmp_path / "scalar.yml"
        config_file.write_text("just a string", encoding="utf-8")

        provider = GoldenDatasetProvider()
        result = provider._load_from_file(config_file)

        assert result is None

    def test_load_invalid_yaml_syntax_returns_none(self, tmp_path: Path) -> None:
        """无效 YAML 语法返回 None."""
        config_file = tmp_path / "invalid.yml"
        config_file.write_text(
            """
invalid: [
  unclosed bracket
""",
            encoding="utf-8",
        )

        provider = GoldenDatasetProvider()
        result = provider._load_from_file(config_file)

        assert result is None

    def test_load_validation_error_returns_none(self, tmp_path: Path) -> None:
        """Pydantic 验证错误返回 None.

        例如 tickers 是字符串而非列表
        """
        config_file = tmp_path / "invalid_tickers.yml"
        config_file.write_text(
            """
tickers: "600519"
""",
            encoding="utf-8",
        )

        provider = GoldenDatasetProvider()
        result = provider._load_from_file(config_file)

        assert result is None
