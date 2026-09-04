"""DataSourceValidationProvider 单元测试."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_data.config import DataSourceSettings
from ditto_data.config.data_source_validation import DataSourceValidationProvider
from ditto_platform.foundation import Environment, InitScope


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

    @pytest.mark.parametrize(
        "token",
        [
            "your_token_here",
            "YourTokenHere",
            "YOUR-TUSHARE-TOKEN",
            "<replace-with-your-token>",
            "${TUSHARE_TOKEN}",
            "example_token",
            "ditto-isolated-placeholder",
        ],
    )
    def test_production_documentation_placeholder_token_fails_closed(
        self,
        tmp_path: Path,
        token: str,
    ) -> None:
        """Documentation sentinels must never earn production readiness."""
        provider = DataSourceValidationProvider(
            DataSourceSettings(tushare_token=token),
            environment=Environment.PRODUCTION,
        )

        result = provider.initialize(tmp_path)

        assert result.success is False
        assert result.message == "TUSHARE_TOKEN is a documentation placeholder"

    def test_development_can_use_explicit_offline_placeholder(
        self,
        tmp_path: Path,
    ) -> None:
        """The isolated development profile remains network-independent."""
        provider = DataSourceValidationProvider(
            DataSourceSettings(tushare_token="ditto-isolated-placeholder"),
            environment=Environment.DEVELOPMENT,
        )

        result = provider.initialize(tmp_path)

        assert result.success is True
