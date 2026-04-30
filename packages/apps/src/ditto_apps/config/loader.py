"""配置文件加载器（仅 Port 层使用）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ditto_platform.foundation.config import ConfigLoader
from dotenv import dotenv_values

__all__ = ["load_env_file", "normalize_env_values"]


def normalize_env_values(values: Mapping[str, Any | None]) -> dict[str, Any]:
    """统一化 dotenv 值：小写 key、空字符串转 None、忽略空键。"""
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        lowered = key.lower()
        normalized[lowered] = None if value == "" else value
    return normalized


def load_env_file(loader: ConfigLoader, name: str) -> dict[str, Any]:
    """加载 config/{env}/{name}.env 并标准化键名。"""
    values = dotenv_values(loader.get_env_file(name))
    return normalize_env_values(values)
