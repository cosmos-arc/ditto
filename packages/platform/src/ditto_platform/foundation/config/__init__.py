"""Ditto 配置管理模块。"""

from ditto_platform.foundation.config.environment import Environment, get_environment
from ditto_platform.foundation.config.errors import ConfigInitError
from ditto_platform.foundation.config.initializer import (
    ConfigInitCoordinator,
    ConfigInitProvider,
    InitResult,
    InitScope,
)
from ditto_platform.foundation.config.loader import ConfigLoader
from ditto_platform.foundation.config.paths import PathResolver, XDGPaths
from ditto_platform.foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
)

__all__ = [
    "ConfigInitCoordinator",
    "ConfigInitError",
    "ConfigInitProvider",
    "ConfigLoader",
    "Environment",
    "InitResult",
    "InitScope",
    "ObservabilitySettings",
    "PathResolver",
    "Settings",
    "SystemSettings",
    "XDGPaths",
    "get_environment",
]
