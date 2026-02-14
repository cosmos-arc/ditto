"""Environment 枚举单元测试."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from ditto_infra.foundation.config.environment import Environment


class TestEnvironment:
    """Environment 枚举测试."""

    def test_enum_values(self) -> None:
        """Environment 应该有三个值."""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.TESTING.value == "testing"
        assert Environment.PRODUCTION.value == "production"

    def test_is_string_enum(self) -> None:
        """Environment 应该是字符串枚举."""
        assert isinstance(Environment.DEVELOPMENT, str)
        assert Environment.DEVELOPMENT == "development"

    def test_from_str_valid_values(self) -> None:
        """from_str() 应该接受有效值."""
        assert Environment.from_str("development") == Environment.DEVELOPMENT
        assert Environment.from_str("testing") == Environment.TESTING
        assert Environment.from_str("production") == Environment.PRODUCTION

    def test_from_str_case_insensitive(self) -> None:
        """from_str() 应该大小写不敏感."""
        assert Environment.from_str("DEVELOPMENT") == Environment.DEVELOPMENT
        assert Environment.from_str("Testing") == Environment.TESTING
        assert Environment.from_str("PRODUCTION") == Environment.PRODUCTION

    def test_from_str_invalid_value(self) -> None:
        """from_str() 应该拒绝无效值."""
        with pytest.raises(ValueError, match="Invalid environment"):
            Environment.from_str("staging")

        with pytest.raises(ValueError, match="Invalid environment"):
            Environment.from_str("dev")

    def test_from_str_error_message(self) -> None:
        """from_str() 错误消息应该包含有效值."""
        with pytest.raises(ValueError) as exc_info:
            Environment.from_str("invalid")

        error_msg = str(exc_info.value)
        assert "development" in error_msg
        assert "testing" in error_msg
        assert "production" in error_msg

    def test_is_development_property(self) -> None:
        """is_development 属性应该只在 DEVELOPMENT 时为 True."""
        assert Environment.DEVELOPMENT.is_development is True
        assert Environment.TESTING.is_development is False
        assert Environment.PRODUCTION.is_development is False

    def test_is_testing_property(self) -> None:
        """is_testing 属性应该只在 TESTING 时为 True."""
        assert Environment.DEVELOPMENT.is_testing is False
        assert Environment.TESTING.is_testing is True
        assert Environment.PRODUCTION.is_testing is False

    def test_is_production_property(self) -> None:
        """is_production 属性应该只在 PRODUCTION 时为 True."""
        assert Environment.DEVELOPMENT.is_production is False
        assert Environment.TESTING.is_production is False
        assert Environment.PRODUCTION.is_production is True

    def test_string_comparison(self) -> None:
        """Environment 枚举值应该能与字符串比较."""
        assert Environment.DEVELOPMENT == "development"
        assert Environment.TESTING == "testing"
        assert Environment.PRODUCTION == "production"

        assert Environment.DEVELOPMENT != "production"
        assert Environment.TESTING != "development"


class TestGetEnvironment:
    """get_environment() 测试."""

    def test_default_is_development(self) -> None:
        """默认返回 development."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENVIRONMENT", None)
            from ditto_infra.foundation.config.environment import get_environment

            result = get_environment()
            assert result == Environment.DEVELOPMENT

    def test_reads_environment_variable(self) -> None:
        """从 ENVIRONMENT 环境变量读取."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            from ditto_infra.foundation.config.environment import get_environment

            result = get_environment()
            assert result == Environment.PRODUCTION

    def test_case_insensitive(self) -> None:
        """大小写不敏感."""
        with patch.dict(os.environ, {"ENVIRONMENT": "TESTING"}):
            from ditto_infra.foundation.config.environment import get_environment

            result = get_environment()
            assert result == Environment.TESTING

    def test_invalid_value_raises(self) -> None:
        """无效值抛出 ValueError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "invalid"}):
            from ditto_infra.foundation.config.environment import get_environment

            with pytest.raises(ValueError, match="Invalid environment"):
                get_environment()


class TestGetEnvironmentBackwardCompatibility:
    """get_environment() DITTO_ENV 向后兼容测试."""

    def test_ditto_env_reads_value(self) -> None:
        """DITTO_ENV 仍可读取值."""
        import warnings

        with patch.dict(os.environ, {"DITTO_ENV": "production"}, clear=True):
            os.environ.pop("ENVIRONMENT", None)
            from ditto_infra.foundation.config.environment import get_environment

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = get_environment()
                assert result == Environment.PRODUCTION
                # 应该有弃用警告
                assert len(w) == 1
                assert issubclass(w[0].category, DeprecationWarning)
                assert "DITTO_ENV" in str(w[0].message)
                assert "deprecated" in str(w[0].message)

    def test_ditto_env_shows_deprecation_warning(self) -> None:
        """DITTO_ENV 显示弃用警告."""
        import warnings

        with patch.dict(os.environ, {"DITTO_ENV": "testing"}, clear=True):
            os.environ.pop("ENVIRONMENT", None)
            from ditto_infra.foundation.config.environment import get_environment

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                get_environment()
                assert len(w) == 1
                assert issubclass(w[0].category, DeprecationWarning)
                assert "ENVIRONMENT" in str(w[0].message)

    def test_environment_takes_precedence(self) -> None:
        """ENVIRONMENT 优先级高于 DITTO_ENV."""
        import warnings

        with patch.dict(
            os.environ, {"ENVIRONMENT": "testing", "DITTO_ENV": "production"}
        ):
            from ditto_infra.foundation.config.environment import get_environment

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = get_environment()
                # ENVIRONMENT 优先
                assert result == Environment.TESTING
                # 没有 DITTO_ENV 警告，因为 ENVIRONMENT 存在
                assert len(w) == 0

    def test_ditto_env_case_insensitive(self) -> None:
        """DITTO_ENV 大小写不敏感."""
        import warnings

        with patch.dict(os.environ, {"DITTO_ENV": "PRODUCTION"}, clear=True):
            os.environ.pop("ENVIRONMENT", None)
            from ditto_infra.foundation.config.environment import get_environment

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = get_environment()
                assert result == Environment.PRODUCTION
                assert len(w) == 1  # 仍有弃用警告
