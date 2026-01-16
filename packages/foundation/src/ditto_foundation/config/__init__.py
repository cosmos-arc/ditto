"""
Ditto 配置管理模块.

提供统一的配置管理, 支持环境变量、配置文件等多种配置源
"""

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
    APISettings,
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
    "APISettings",
    "DataSourceSettings",
    "DatabaseSettings",
    "FileStorageSettings",
    "PathResolver",
    "PathsManager",
    "Settings",
    "SettingsManager",
    "SingletonManager",
    "SystemSettings",
    "XDGPaths",
    "get_paths",
    "get_settings",
    "reload_paths",
    "reload_settings",
    "reset_paths_for_testing",
]
