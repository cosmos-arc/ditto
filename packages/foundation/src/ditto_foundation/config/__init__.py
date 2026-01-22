"""
Ditto 配置管理模块.

提供统一的配置管理, 支持环境变量、配置文件等多种配置源

⚠️ 注意：database、data_source、file_storage 配置已迁移到 DataHub 层
"""

from ditto_foundation.config.environment import Environment
from ditto_foundation.config.initializer import (
    ConfigInitCoordinator,
    ConfigInitProvider,
    InitResult,
    InitScope,
    get_config_coordinator,
    reset_coordinator_for_testing,
)
from ditto_foundation.config.loader import ConfigLoader
from ditto_foundation.config.paths import (
    PathResolver,
    XDGPaths,
    get_paths,
    reload_paths,
    reset_paths_for_testing,
)
from ditto_foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
)

__all__ = [
    "ConfigInitCoordinator",
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
    "get_config_coordinator",
    "get_paths",
    "reload_paths",
    "reset_coordinator_for_testing",
    "reset_paths_for_testing",
]
