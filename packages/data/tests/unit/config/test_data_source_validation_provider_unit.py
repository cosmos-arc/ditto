"""DataSourceValidationProvider 单元测试."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from ditto_data.config.data_source_validation import DataSourceValidationProvider
from ditto_platform.foundation import InitScope


class TestDataSourceValidationProviderConstruction:
    """构造与基本属性测试."""

    def test_name_returns_data_source_validation(self) -> None:
        provider = DataSourceValidationProvider()
        assert provider.name == "data_source_validation"

    def test_scope_returns_startup(self) -> None:
        provider = DataSourceValidationProvider()
        assert provider.scope is InitScope.STARTUP

    def test_check_always_returns_true(self) -> None:
        provider = DataSourceValidationProvider()
        assert provider.check(Path("/tmp")) is True


class TestTushareTokenValidation:
    """TUSHARE_TOKEN 校验测试."""

    def test_missing_token_returns_failure(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TUSHARE_TOKEN", None)
            result = provider.initialize(tmp_path)

        assert result.success is False
        assert result.provider == "data_source_validation"
        assert "TUSHARE_TOKEN" in result.message

    def test_empty_token_returns_failure(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider()

        with patch.dict(os.environ, {"TUSHARE_TOKEN": ""}):
            result = provider.initialize(tmp_path)

        assert result.success is False
        assert "TUSHARE_TOKEN" in result.message

    def test_whitespace_token_returns_failure(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider()

        with patch.dict(os.environ, {"TUSHARE_TOKEN": "   "}):
            result = provider.initialize(tmp_path)

        assert result.success is False
        assert "TUSHARE_TOKEN" in result.message

    def test_valid_token_passes(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider()

        with patch.dict(os.environ, {"TUSHARE_TOKEN": "valid_token_123"}):
            result = provider.initialize(tmp_path)

        assert result.success is True

    def test_valid_token_with_env_source(self, tmp_path: Path) -> None:
        """Token 通过环境变量设置也应通过."""
        provider = DataSourceValidationProvider()

        with patch.dict(os.environ, {"TUSHARE_TOKEN": "env_token_xyz"}):
            result = provider.initialize(tmp_path)

        assert result.success is True
