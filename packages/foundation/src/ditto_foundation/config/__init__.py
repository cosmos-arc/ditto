"""
Ditto 配置管理模块.

提供统一的配置管理, 支持环境变量、配置文件等多种配置源
"""

from ditto_foundation.config.initializer import (
    ConfigInitCoordinator,
    ConfigInitProvider,
    InitResult,
    InitScope,
    get_config_coordinator,
    reset_coordinator_for_testing,
)
from ditto_foundation.config.manager import (
    PathsManager,
    SingletonManager,
)
from ditto_foundation.config.paths import (
    PathResolver,
    XDGPaths,
    get_paths,
    reload_paths,
    reset_paths_for_testing,
)
from ditto_foundation.config.settings import (
    DatabaseSettings,
    DataSourceSettings,
    FileStorageSettings,
    Settings,
    SettingsManager,
    SystemSettings,
    get_settings,
    reload_settings,
)

__all__ = [
    "ConfigInitCoordinator",
    "ConfigInitProvider",
    "DataSourceSettings",
    "DatabaseSettings",
    "FileStorageSettings",
    "InitResult",
    "InitScope",
    "PathResolver",
    "PathsManager",
    "Settings",
    "SettingsManager",
    "SingletonManager",
    "SystemSettings",
    "XDGPaths",
    "get_config_coordinator",
    "get_paths",
    "get_settings",
    "reload_paths",
    "reload_settings",
    "reset_coordinator_for_testing",
    "reset_paths_for_testing",
]
