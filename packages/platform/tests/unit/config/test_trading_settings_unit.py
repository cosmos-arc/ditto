"""TradingSettings 单元测试."""

from __future__ import annotations

import pytest
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
    TradingSettings,
)


class TestTradingSettings:
    """TradingSettings 配置模型测试."""

    def test_default_values(self) -> None:
        """TradingSettings 应该有合理的默认值."""
        settings = TradingSettings()

        assert settings.default_universe == "csi300"
        assert settings.max_position_pct == 0.1
        assert settings.risk_free_rate == 0.025
        assert settings.benchmark == "000300.SH"
        assert settings.cost_bps == 3.0
        assert settings.slippage_bps == 1.0

    def test_custom_values(self) -> None:
        """TradingSettings 应该接受自定义值."""
        settings = TradingSettings(
            default_universe="csi500",
            max_position_pct=0.05,
            risk_free_rate=0.03,
            benchmark="000905.SH",
            cost_bps=5.0,
            slippage_bps=2.0,
        )

        assert settings.default_universe == "csi500"
        assert settings.max_position_pct == 0.05
        assert settings.risk_free_rate == 0.03
        assert settings.benchmark == "000905.SH"
        assert settings.cost_bps == 5.0
        assert settings.slippage_bps == 2.0

    def test_max_position_pct_must_be_positive(self) -> None:
        """max_position_pct 必须大于 0."""
        with pytest.raises(ValueError, match="max_position_pct"):
            TradingSettings(max_position_pct=0.0)

    def test_max_position_pct_must_not_exceed_one(self) -> None:
        """max_position_pct 不能超过 1."""
        with pytest.raises(ValueError, match="max_position_pct"):
            TradingSettings(max_position_pct=1.5)

    def test_max_position_pct_boundary_one(self) -> None:
        """max_position_pct = 1.0 应该是合法的."""
        settings = TradingSettings(max_position_pct=1.0)
        assert settings.max_position_pct == 1.0

    def test_extra_fields_ignored(self) -> None:
        """TradingSettings 应该忽略额外字段."""
        settings = TradingSettings.model_validate(
            {
                "default_universe": "csi300",
                "unknown_field": "should_be_ignored",
            }
        )
        assert settings.default_universe == "csi300"


class TestSettingsWithTrading:
    """Settings 聚合中 trading 字段测试."""

    def test_settings_without_trading(self) -> None:
        """Settings 在不提供 trading 时应该正常工作."""
        settings = Settings(
            system=SystemSettings(environment=Environment.TESTING),
            observability=ObservabilitySettings(),
        )

        assert settings.trading is None

    def test_settings_with_trading(self) -> None:
        """Settings 应该能包含 trading 配置."""
        trading = TradingSettings(
            default_universe="csi500",
            max_position_pct=0.2,
        )
        settings = Settings(
            system=SystemSettings(environment=Environment.TESTING),
            observability=ObservabilitySettings(),
            trading=trading,
        )

        assert settings.trading is not None
        assert settings.trading.default_universe == "csi500"
        assert settings.trading.max_position_pct == 0.2

    def test_settings_trading_none_explicit(self) -> None:
        """Settings 显式传入 trading=None 应该正常工作."""
        settings = Settings(
            system=SystemSettings(environment=Environment.TESTING),
            observability=ObservabilitySettings(),
            trading=None,
        )

        assert settings.trading is None

    def test_settings_properties_work_with_trading(self) -> None:
        """Settings 的环境属性在包含 trading 时仍然正常工作."""
        settings = Settings(
            system=SystemSettings(environment=Environment.TESTING),
            observability=ObservabilitySettings(),
            trading=TradingSettings(),
        )

        assert settings.is_testing is True
        assert settings.is_development is False
        assert settings.is_production is False
