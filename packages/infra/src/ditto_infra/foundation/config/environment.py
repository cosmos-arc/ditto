"""系统运行环境枚举."""

import os
import warnings
from enum import Enum


class Environment(str, Enum):
    """系统运行环境枚举."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

    @classmethod
    def from_str(cls, value: str) -> "Environment":
        """
        从字符串创建 Environment，带验证.

        Args:
            value: 环境字符串值（大小写不敏感）

        Returns:
            对应的 Environment 枚举值

        Raises:
            ValueError: 如果传入的值不是有效的环境名称

        """
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(e.value for e in cls)
            raise ValueError(
                f"Invalid environment '{value}'. Valid values: {valid}"
            ) from None

    @property
    def is_development(self) -> bool:
        """是否为开发环境."""
        return self == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        """是否为测试环境."""
        return self == Environment.TESTING

    @property
    def is_production(self) -> bool:
        """是否为生产环境."""
        return self == Environment.PRODUCTION


def get_environment() -> Environment:
    """
    获取当前运行环境（统一入口）。

    读取顺序：
    1. 环境变量 ENVIRONMENT
    2. 环境变量 DITTO_ENV（已弃用，显示 DeprecationWarning）
    3. 默认值 development

    Returns:
        Environment 枚举值

    Raises:
        ValueError: 环境变量值无效时

    """
    env_str: str | None
    ditto_env = os.getenv("DITTO_ENV")

    if ditto_env is not None:
        msg = (
            "DITTO_ENV is deprecated, use ENVIRONMENT instead. "
            "DITTO_ENV will be removed in a future version."
        )
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        env_str = ditto_env
    else:
        env_str = os.getenv("ENVIRONMENT", "development")

    return Environment.from_str(env_str)
