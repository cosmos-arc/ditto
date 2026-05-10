"""
Shared JSON type aliases and field validators.

Pure type definitions with zero external dependencies, used across
data and features packages for JSON record (de)serialization.

准入依据:
- 跨层使用: 被 data 和 features 两个业务包直接导入
- 零业务行为: 纯类型别名和字段提取函数
- 稳定性高: JSON 基础类型不会随子域迭代变更
- 无外部依赖: 仅使用 Python 标准库
- 纯值语义: 不含序列化、持久化关注点
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

__all__ = [
    "JsonDict",
    "JsonPrimitive",
    "JsonValue",
    "require_bool",
    "require_int",
    "require_payload",
    "require_str",
]

# ---------------------------------------------------------------------------
# JSON type aliases
# ---------------------------------------------------------------------------

type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
type JsonDict = dict[str, JsonValue]


# ---------------------------------------------------------------------------
# JSON record field validators
# ---------------------------------------------------------------------------


def require_str(data: Mapping[str, JsonValue], key: str) -> str:
    """Extract a required string field from JSON payload."""
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def require_int(data: Mapping[str, JsonValue], key: str) -> int:
    """Extract a required int field from JSON payload."""
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int")
    return value


def require_bool(data: Mapping[str, JsonValue], key: str) -> bool:
    """Extract a required bool field from JSON payload."""
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a bool")
    return value


def require_payload(data: Mapping[str, JsonValue], key: str) -> JsonDict:
    """Extract a required JSON object field from payload."""
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a JSON object")
    return cast(JsonDict, value)
