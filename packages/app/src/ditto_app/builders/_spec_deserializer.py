"""Spec 反序列化工具函数."""

from __future__ import annotations

from typing import cast

__all__ = [
    "as_float_tuple",
    "as_object_dict",
    "as_sequence",
    "as_str_tuple",
    "read_bool",
    "read_float",
    "read_int",
    "read_optional_float",
    "read_optional_int",
    "read_optional_str",
    "read_required_str",
    "read_str_value",
]


def as_object_dict(
    raw_value: object,
    *,
    field_name: str,
) -> dict[str, object]:
    """
    校验对象形态并返回 ``dict[str, object]``。

    允许 value 为 ``None``（下游通过 ``read_optional_*`` 处理）。
    """
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        msg = f"{field_name} 必须是 object/dict"
        raise ValueError(msg)
    raw_dict = cast("dict[object, object]", raw_value)
    result: dict[str, object] = {}
    for key, value in raw_dict.items():
        if not isinstance(key, str):
            msg = f"{field_name} 的 key 必须是 str"
            raise ValueError(msg)
        result[key] = value
    return result


def as_sequence(
    raw_value: object,
    *,
    field_name: str,
) -> tuple[object, ...]:
    """校验序列形态并返回 tuple。"""
    if raw_value is None:
        return ()
    if isinstance(raw_value, tuple):
        return cast("tuple[object, ...]", raw_value)
    if isinstance(raw_value, list):
        return tuple(cast("list[object]", raw_value))
    msg = f"{field_name} 必须是 list/tuple"
    raise ValueError(msg)


def as_str_tuple(
    raw_value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """将字符串序列标准化为 tuple。"""
    items = as_sequence(raw_value, field_name=field_name)
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            msg = f"{field_name} 的元素必须是 str"
            raise ValueError(msg)
        result.append(item)
    return tuple(result)


def as_float_tuple(
    raw_value: object,
    *,
    field_name: str,
) -> tuple[float, ...]:
    """将数值序列标准化为 tuple[float, ...]。"""
    items = as_sequence(raw_value, field_name=field_name)
    result: list[float] = []
    for item in items:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            msg = f"{field_name} 的元素必须是数字"
            raise ValueError(msg)
        result.append(float(item))
    return tuple(result)


def read_required_str(payload: dict[str, object], field_name: str) -> str:
    """读取必填字符串字段。"""
    value = payload.get(field_name)
    if not isinstance(value, str) or value == "":
        msg = f"{field_name} 必须是非空字符串"
        raise ValueError(msg)
    return value


def read_optional_str(raw_value: object, *, field_name: str = "字段") -> str | None:
    """读取可选字符串字段。"""
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        msg = f"{field_name} 必须是字符串"
        raise ValueError(msg)
    return raw_value


def read_str_value(raw_value: object, *, field_name: str) -> str:
    """读取字符串值（委托 read_required_str，入参形式不同）."""
    return read_required_str({field_name: raw_value}, field_name)


def read_int(raw_value: object, *, field_name: str) -> int:
    """读取整数值。"""
    if not isinstance(raw_value, int) or isinstance(raw_value, bool):
        msg = f"{field_name} 必须是 int"
        raise ValueError(msg)
    return raw_value


def read_optional_int(raw_value: object, *, field_name: str) -> int | None:
    """读取可选整数值。"""
    if raw_value is None:
        return None
    return read_int(raw_value, field_name=field_name)


def read_float(raw_value: object, *, field_name: str) -> float:
    """读取浮点值，允许 int 自动提升。"""
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        msg = f"{field_name} 必须是数字"
        raise ValueError(msg)
    return float(raw_value)


def read_optional_float(
    raw_value: object,
    *,
    field_name: str,
) -> float | None:
    """读取可选浮点值。"""
    if raw_value is None:
        return None
    return read_float(raw_value, field_name=field_name)


def read_bool(raw_value: object, *, field_name: str) -> bool:
    """读取布尔值。"""
    if not isinstance(raw_value, bool):
        msg = f"{field_name} 必须是 bool"
        raise ValueError(msg)
    return raw_value
