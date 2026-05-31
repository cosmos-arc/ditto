r"""Ditto 路径管理 - 遵循 XDG Base Directory 规范."""

from ._path_resolver import (
    AppConfig,
    EnvVarConfig,
    PathResolver,
    PathResolverConfig,
    PlatformConfig,
)
from ._xdg_paths import XDGPaths

__all__ = [
    "AppConfig",
    "EnvVarConfig",
    "PathResolver",
    "PathResolverConfig",
    "PlatformConfig",
    "XDGPaths",
]
