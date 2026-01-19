"""系统运行环境枚举."""

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
