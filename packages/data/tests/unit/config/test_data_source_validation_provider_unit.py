"""DataSourceValidationProvider 单元测试."""

from __future__ import annotations

from pathlib import Path

from ditto_data.config import DataSourceSettings
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
        provider = DataSourceValidationProvider(DataSourceSettings(tushare_token=""))
        result = provider.initialize(tmp_path)

        assert result.success is False
        assert result.provider == "data_source_validation"
        assert "TUSHARE_TOKEN" in result.message

    def test_empty_token_returns_failure(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider(DataSourceSettings(tushare_token=""))
        result = provider.initialize(tmp_path)

        assert result.success is False
        assert "TUSHARE_TOKEN" in result.message

    def test_whitespace_token_returns_failure(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider(DataSourceSettings(tushare_token="   "))
        result = provider.initialize(tmp_path)

        assert result.success is False
        assert "TUSHARE_TOKEN" in result.message

    def test_valid_token_passes(self, tmp_path: Path) -> None:
        provider = DataSourceValidationProvider(
            DataSourceSettings(tushare_token="valid_token_123")
        )
        result = provider.initialize(tmp_path)

        assert result.success is True

    def test_valid_token_from_resolved_settings_passes(self, tmp_path: Path) -> None:
        """Validation consumes the resolved env/keyring/config precedence result."""
        provider = DataSourceValidationProvider(
            DataSourceSettings(tushare_token="resolved_token_xyz")
        )
        result = provider.initialize(tmp_path)

        assert result.success is True
