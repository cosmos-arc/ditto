"""DataSourceSettings 单元测试."""

import os

import pytest
from ditto_datahub.config.data_source import DataSourceSettings
from pydantic import ValidationError


class TestDataSourceSettings:
    """DataSourceSettings 测试类."""

    def test_default_values(self, monkeypatch):
        """测试默认值."""
        # 清除环境变量
        for key in list(os.environ.keys()):
            if key.startswith("DATASOURCE_"):
                monkeypatch.delenv(key, raising=False)

        settings = DataSourceSettings()

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

    def test_env_prefix(self, monkeypatch):
        """测试环境变量前缀."""
        monkeypatch.setenv("DATASOURCE_HTTP_BASE_URL", "https://api.example.com")
        monkeypatch.setenv("DATASOURCE_TUSHARE_TOKEN", "test_token_123")

        settings = DataSourceSettings()

        assert settings.http_base_url == "https://api.example.com"
        assert settings.tushare_token == "test_token_123"

    def test_http_timeout_validation(self, monkeypatch):
        """测试 http_timeout 验证."""
        # 测试最小值边界
        monkeypatch.setenv("DATASOURCE_HTTP_TIMEOUT", "1.0")
        settings = DataSourceSettings()
        assert settings.http_timeout == 1.0

        # 测试最大值边界
        monkeypatch.setenv("DATASOURCE_HTTP_TIMEOUT", "300.0")
        settings = DataSourceSettings()
        assert settings.http_timeout == 300.0

        # 测试超出范围（小于最小值）
        monkeypatch.setenv("DATASOURCE_HTTP_TIMEOUT", "0.5")
        with pytest.raises(ValidationError):
            DataSourceSettings()

        # 测试超出范围（大于最大值）
        monkeypatch.setenv("DATASOURCE_HTTP_TIMEOUT", "301.0")
        with pytest.raises(ValidationError):
            DataSourceSettings()

    def test_retry_max_attempts_validation(self, monkeypatch):
        """测试 retry_max_attempts 验证."""
        # 测试最小值边界
        monkeypatch.setenv("DATASOURCE_RETRY_MAX_ATTEMPTS", "1")
        settings = DataSourceSettings()
        assert settings.retry_max_attempts == 1

        # 测试最大值边界
        monkeypatch.setenv("DATASOURCE_RETRY_MAX_ATTEMPTS", "10")
        settings = DataSourceSettings()
        assert settings.retry_max_attempts == 10

        # 测试超出范围（小于最小值）
        monkeypatch.setenv("DATASOURCE_RETRY_MAX_ATTEMPTS", "0")
        with pytest.raises(ValidationError):
            DataSourceSettings()

        # 测试超出范围（大于最大值）
        monkeypatch.setenv("DATASOURCE_RETRY_MAX_ATTEMPTS", "11")
        with pytest.raises(ValidationError):
            DataSourceSettings()

    def test_retry_multiplier_validation(self, monkeypatch):
        """测试 retry_multiplier 验证."""
        # 测试最小值边界
        monkeypatch.setenv("DATASOURCE_RETRY_MULTIPLIER", "0.1")
        settings = DataSourceSettings()
        assert settings.retry_multiplier == 0.1

        # 测试超出范围（小于最小值）
        monkeypatch.setenv("DATASOURCE_RETRY_MULTIPLIER", "0.05")
        with pytest.raises(ValidationError):
            DataSourceSettings()

    def test_retry_min_wait_validation(self, monkeypatch):
        """测试 retry_min_wait 验证."""
        # 测试最小值边界
        monkeypatch.setenv("DATASOURCE_RETRY_MIN_WAIT", "0.1")
        settings = DataSourceSettings()
        assert settings.retry_min_wait == 0.1

        # 测试超出范围（小于最小值）
        monkeypatch.setenv("DATASOURCE_RETRY_MIN_WAIT", "0.05")
        with pytest.raises(ValidationError):
            DataSourceSettings()

    def test_retry_max_wait_validation(self, monkeypatch):
        """测试 retry_max_wait 验证."""
        # 测试最小值边界
        monkeypatch.setenv("DATASOURCE_RETRY_MAX_WAIT", "1.0")
        settings = DataSourceSettings()
        assert settings.retry_max_wait == 1.0

        # 测试超出范围（小于最小值）
        monkeypatch.setenv("DATASOURCE_RETRY_MAX_WAIT", "0.5")
        with pytest.raises(ValidationError):
            DataSourceSettings()

    def test_rate_limit_profile(self, monkeypatch):
        """测试 rate_limit_profile."""
        monkeypatch.setenv("DATASOURCE_RATE_LIMIT_PROFILE", "premium")
        settings = DataSourceSettings()
        assert settings.rate_limit_profile == "premium"

    def test_rate_limit_global_rate(self, monkeypatch):
        """测试 rate_limit_global_rate."""
        monkeypatch.setenv("DATASOURCE_RATE_LIMIT_GLOBAL_RATE", "1000")
        settings = DataSourceSettings()
        assert settings.rate_limit_global_rate == 1000

    def test_rate_limit_daily_rate(self, monkeypatch):
        """测试 rate_limit_daily_rate."""
        monkeypatch.setenv("DATASOURCE_RATE_LIMIT_DAILY_RATE", "50000")
        settings = DataSourceSettings()
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

    def test_extra_ignore(self, monkeypatch):
        """测试 extra='ignore' 忽略额外字段."""
        monkeypatch.setenv("DATASOURCE_UNKNOWN_FIELD", "some_value")
        # 不应该抛出错误
        settings = DataSourceSettings()
        assert settings is not None
