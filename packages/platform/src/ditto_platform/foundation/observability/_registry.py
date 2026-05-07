"""观测系统全局状态注册表。"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ObservabilityConfig


@dataclass
class ObservabilityRegistry:
    """模块级状态注册表（单例模式）。"""

    initialized: bool = False
    config: ObservabilityConfig | None = None

    @classmethod
    def is_initialized(cls) -> bool:
        return cls.initialized

    @classmethod
    def set_initialized(cls, value: bool) -> None:
        cls.initialized = value

    @classmethod
    def set_config(cls, config: ObservabilityConfig) -> None:
        cls.config = config

    @classmethod
    def reset(cls) -> None:
        cls.initialized = False
        cls.config = None
