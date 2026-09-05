"""Deterministic field-level diffs for canonical strategy payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ditto_platform.foundation.json_types import JsonValue

from ditto_application.contracts import SpecChange

__all__ = ["diff_canonical_payloads"]

_KEYED_LIST_FIELDS: Mapping[str, str] = {
    "parameter_schema": "name",
    "pipeline.nodes": "node_id",
}


def diff_canonical_payloads(
    base: dict[str, object],
    target: dict[str, object],
) -> tuple[SpecChange, ...]:
    """
    递归比较两个 canonical spec payload，返回字段级变更.

    dict 按 key（sorted）遍历，list 按 index 对齐；非 dict/list leaf 用相等
    判定。type 不匹配（如 dict vs scalar）整体记为 ``changed``，不递归。
    """
    changes: list[SpecChange] = []
    _collect_payload_changes(
        "",
        cast("JsonValue", base),
        cast("JsonValue", target),
        changes,
    )
    return tuple(changes)


def _collect_payload_changes(
    prefix: str,
    base: JsonValue,
    target: JsonValue,
    changes: list[SpecChange],
) -> None:
    if isinstance(base, dict) and isinstance(target, dict):
        for key in sorted(set(base) | set(target), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in base:
                changes.append(
                    SpecChange(
                        path=path,
                        op="added",
                        old_value=None,
                        new_value=target[key],
                    ),
                )
            elif key not in target:
                changes.append(
                    SpecChange(
                        path=path,
                        op="removed",
                        old_value=base[key],
                        new_value=None,
                    ),
                )
            else:
                _collect_payload_changes(path, base[key], target[key], changes)
    elif isinstance(base, list) and isinstance(target, list):
        key_field = _KEYED_LIST_FIELDS.get(prefix)
        if key_field is None:
            _collect_indexed_list(prefix, base, target, changes)
        else:
            _collect_keyed_list(prefix, key_field, base, target, changes)
    elif base != target:
        changes.append(
            SpecChange(path=prefix, op="changed", old_value=base, new_value=target),
        )


def _collect_indexed_list(
    prefix: str,
    base: list[JsonValue],
    target: list[JsonValue],
    changes: list[SpecChange],
) -> None:
    for index in range(max(len(base), len(target))):
        path = f"{prefix}[{index}]"
        if index >= len(base):
            changes.append(
                SpecChange(
                    path=path,
                    op="added",
                    old_value=None,
                    new_value=target[index],
                ),
            )
        elif index >= len(target):
            changes.append(
                SpecChange(
                    path=path,
                    op="removed",
                    old_value=base[index],
                    new_value=None,
                ),
            )
        else:
            _collect_payload_changes(path, base[index], target[index], changes)


def _collect_keyed_list(
    prefix: str,
    key_field: str,
    base: list[JsonValue],
    target: list[JsonValue],
    changes: list[SpecChange],
) -> None:
    """
    对按键字段定位身份的 list（parameter_schema/pipeline.nodes）按键 diff.

    避免 index 对齐在中间插入/删除时级联假变更——按 name/node_id 匹配元素身份。
    """
    base_map = {_list_key(item, key_field): item for item in base}
    target_map = {_list_key(item, key_field): item for item in target}
    for key in sorted(set(base_map) | set(target_map), key=str):
        path = f"{prefix}[{key}]"
        if key not in base_map:
            changes.append(
                SpecChange(
                    path=path,
                    op="added",
                    old_value=None,
                    new_value=target_map[key],
                ),
            )
        elif key not in target_map:
            changes.append(
                SpecChange(
                    path=path,
                    op="removed",
                    old_value=base_map[key],
                    new_value=None,
                ),
            )
        else:
            _collect_payload_changes(path, base_map[key], target_map[key], changes)


def _list_key(item: JsonValue, key_field: str) -> str:
    if isinstance(item, dict):
        value = item.get(key_field)
        return value if isinstance(value, str) else ""
    return ""
