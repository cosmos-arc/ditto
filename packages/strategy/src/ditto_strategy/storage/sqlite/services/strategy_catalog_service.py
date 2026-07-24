"""
StrategyCatalogService -- 策略 Spec CRUD 与 governance active pointer 读取.

Protocol 方法名与 contracts.py 对齐：get_spec / list_specs / list_versions。
governance active pointer 读取通过可选窄 port 注入，无注入时 get_active_published
返回 None（调用方走 NO_ACTIVE_STRATEGY fail-closed）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.governance.protocols import StrategyActivePointerReader
from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "StrategyCatalogService",
    "StrategySpecReaderProtocol",
    "StrategySpecWriterProtocol",
]


@runtime_checkable
class StrategySpecReaderProtocol(Protocol):
    """策略 Spec 读取协议 — 方法名与 contracts.StrategyCatalogReader 对齐."""

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """获取策略 Spec，version=None 返回最新版本."""
        ...

    def list_specs(self) -> list[StrategySpecRecord]:
        """列出所有策略 Spec（最新版本）."""
        ...

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        """列出策略的所有版本."""
        ...

    def get_latest_published(self, strategy_id: str) -> StrategySpecRecord | None:
        """获取最高 published 版本，忽略更新的草稿."""
        ...

    def list_latest_published(self) -> list[StrategySpecRecord]:
        """列出每个策略的最高 published 版本."""
        ...


@runtime_checkable
class StrategySpecWriterProtocol(Protocol):
    """策略 Spec 写入协议."""

    def save(self, record: StrategySpecRecord) -> None:
        """保存策略 Spec 记录."""
        ...

    def update_status(self, strategy_id: str, version: int, status: str) -> bool:
        """更新策略 Spec 状态，成功返回 True."""
        ...


class StrategyCatalogService:
    """策略目录服务 -- Spec CRUD + governance active pointer 读取."""

    def __init__(
        self,
        reader: StrategySpecReaderProtocol,
        writer: StrategySpecWriterProtocol,
        active_pointer_reader: StrategyActivePointerReader | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._active_pointer_reader = active_pointer_reader

    def save_spec(self, record: StrategySpecRecord) -> None:
        """保存策略 Spec."""
        self._writer.save(record)

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """获取策略 Spec，version=None 返回最新版本."""
        return self._reader.get_spec(strategy_id, version)

    def list_specs(self) -> list[StrategySpecRecord]:
        """列出所有策略 Spec（最新版本）."""
        return self._reader.list_specs()

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        """列出策略的所有版本."""
        return self._reader.list_versions(strategy_id)

    def get_active_published(self, strategy_id: str) -> StrategySpecRecord | None:
        """
        返回 governance active pointer 指向的 spec payload.

        解析顺序：governance active pointer → 回查 spec payload。无 active
        pointer reader、无 pointer 或 pointer 指向的 payload 缺失时返回
        None，由调用方走 NO_ACTIVE_STRATEGY fail-closed。
        """
        if self._active_pointer_reader is None:
            return None
        pointer = self._active_pointer_reader.get_active_pointer(strategy_id)
        if pointer is None:
            return None
        return self._reader.get_spec(strategy_id, pointer.active_version)

    def get_latest_published(self, strategy_id: str) -> StrategySpecRecord | None:
        """获取最高 published 版本，忽略更新的草稿."""
        return self._reader.get_latest_published(strategy_id)

    def list_latest_published(self) -> list[StrategySpecRecord]:
        """列出每个策略的最高 published 版本."""
        return self._reader.list_latest_published()

    def publish_spec(self, strategy_id: str, version: int) -> bool:
        """发布策略 Spec（draft -> published）."""
        return self._writer.update_status(strategy_id, version, "published")
