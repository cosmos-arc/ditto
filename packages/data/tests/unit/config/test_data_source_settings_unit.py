"""DataSourceSettings 单元测试."""

import pytest
from ditto_data.config.data_source import DataSourceSettings
from pydantic import ValidationError


class TestDataSourceSettings:
    """DataSourceSettings 测试类."""

    def test_default_values(self):
        """测试默认值."""
        # 清除环境变量
        settings = DataSourceSettings.model_validate({"unknown_field": "some_value"})

        # HTTP 配置默认值
        assert settings.http_base_url == "http://api.tushare.pro"
        assert settings.http_timeout == 30.0

        # 重试配置默认值
        assert settings.retry_max_attempts == 3
        assert settings.retry_multiplier == 1.0
        assert settings.retry_min_wait == 1.0
        assert settings.retry_max_wait == 10.0

        # 限流配置默认值
        assert settings.rate_limit_profile == "free"
        assert settings.rate_limit_global_rate is None
        assert settings.rate_limit_daily_rate is None

        # Token 默认值
        assert settings.tushare_token == ""

    def test_explicit_overrides(self):
        """测试环境变量前缀."""
        settings = DataSourceSettings(
            http_base_url="https://api.example.com",
            tushare_token="test_token_123",
        )

        assert settings.http_base_url == "https://api.example.com"
        assert settings.tushare_token == "test_token_123"

    def test_http_timeout_validation(self):
        """测试 http_timeout 验证."""
        # 测试最小值边界
        settings = DataSourceSettings(http_timeout=1.0)
        assert settings.http_timeout == 1.0

        # 测试最大值边界
        settings = DataSourceSettings(http_timeout=300.0)
        assert settings.http_timeout == 300.0

        # 测试超出范围（小于最小值）
        with pytest.raises(ValidationError):
            DataSourceSettings(http_timeout=0.5)

        # 测试超出范围（大于最大值）
        with pytest.raises(ValidationError):
            DataSourceSettings(http_timeout=301.0)

    def test_retry_max_attempts_validation(self):
        """测试 retry_max_attempts 验证."""
        # 测试最小值边界
        settings = DataSourceSettings(retry_max_attempts=1)
        assert settings.retry_max_attempts == 1

        # 测试最大值边界
        settings = DataSourceSettings(retry_max_attempts=10)
        assert settings.retry_max_attempts == 10

        # 测试超出范围（小于最小值）
        with pytest.raises(ValidationError):
            DataSourceSettings(retry_max_attempts=0)

        # 测试超出范围（大于最大值）
        with pytest.raises(ValidationError):
            DataSourceSettings(retry_max_attempts=11)

    def test_retry_multiplier_validation(self):
        """测试 retry_multiplier 验证."""
        # 测试最小值边界
        settings = DataSourceSettings(retry_multiplier=0.1)
        assert settings.retry_multiplier == 0.1

        # 测试超出范围（小于最小值）
        with pytest.raises(ValidationError):
            DataSourceSettings(retry_multiplier=0.05)

    def test_retry_min_wait_validation(self):
        """测试 retry_min_wait 验证."""
        # 测试最小值边界
        settings = DataSourceSettings(retry_min_wait=0.1)
        assert settings.retry_min_wait == 0.1

        # 测试超出范围（小于最小值）
        with pytest.raises(ValidationError):
            DataSourceSettings(retry_min_wait=0.05)

    def test_retry_max_wait_validation(self):
        """测试 retry_max_wait 验证."""
        # 测试最小值边界
        settings = DataSourceSettings(retry_max_wait=1.0)
        assert settings.retry_max_wait == 1.0

        # 测试超出范围（小于最小值）
        with pytest.raises(ValidationError):
            DataSourceSettings(retry_max_wait=0.5)

    def test_rate_limit_profile(self):
        """测试 rate_limit_profile."""
        settings = DataSourceSettings(rate_limit_profile="premium")
        assert settings.rate_limit_profile == "premium"

    def test_rate_limit_global_rate(self):
        """测试 rate_limit_global_rate."""
        settings = DataSourceSettings(rate_limit_global_rate=1000)
        assert settings.rate_limit_global_rate == 1000

    def test_rate_limit_daily_rate(self):
        """测试 rate_limit_daily_rate."""
        settings = DataSourceSettings(rate_limit_daily_rate=50000)
        assert settings.rate_limit_daily_rate == 50000

    def test_model_validate(self):
        """测试 model_validate 方法."""
        data = {
            "http_base_url": "https://api.example.com",
            "http_timeout": 60.0,
            "retry_max_attempts": 5,
            "tushare_token": "test_token",
        }

        settings = DataSourceSettings.model_validate(data)

        assert settings.http_base_url == "https://api.example.com"
        assert settings.http_timeout == 60.0
        assert settings.retry_max_attempts == 5
        assert settings.tushare_token == "test_token"

    def test_extra_ignore(self):
        """测试 extra='ignore' 忽略额外字段."""
        # 不应该抛出错误
        settings = DataSourceSettings()
        assert settings is not None
