"""SourceRegistry — 按 Protocol 能力注册和查找数据源。"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


class SourceRegistry:
    """数据源注册中心 — 按 name + Protocol 类型注册和查找。"""

    def __init__(self) -> None:
        self._entries: dict[str, dict[type[Any], Any]] = {}

    def register(self, name: str, protocol: type[T], source: T) -> None:
        """注册数据源到指定 name + Protocol 组合."""
        self._entries.setdefault(name, {})[protocol] = source

    def get(self, name: str, protocol: type[T]) -> T:
        """按 name + Protocol 查找数据源，未找到则抛出 ValueError."""
        name_entries = self._entries.get(name, {})
        source = name_entries.get(protocol)
        if source is None:
            available = list(name_entries.keys()) if name_entries else []
            msg = (
                f"No source registered for {protocol.__name__} "
                f"under '{name}'. Available: {available}"
            )
            raise ValueError(msg)
        return source

    def get_all(self, protocol: type[T]) -> list[T]:
        """获取所有注册了指定 Protocol 的数据源."""
        results: list[T] = []
        for name_entries in self._entries.values():
            source = name_entries.get(protocol)
            if source is not None:
                results.append(source)
        return results
