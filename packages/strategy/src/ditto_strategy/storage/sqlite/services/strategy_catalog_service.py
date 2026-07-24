"""
StrategyCatalogService -- 策略 Spec CRUD 与 governance active pointer 读取.

Protocol 方法名与 contracts.py 对齐：get_spec / list_specs / list_versions。
governance active pointer 读取通过可选窄 port 注入，无注入时 get_active_published
返回 None（调用方走 NO_ACTIVE_STRATEGY fail-closed）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.governance.protocols import (
    StrategyActivePointerReader,
    StrategyVersionStateReader,
)
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


@runtime_checkable
class StrategySpecWriterProtocol(Protocol):
    """策略 Spec 写入协议（append-only immutable payload）."""

    def save(self, record: StrategySpecRecord) -> None:
        """保存策略 Spec 记录."""
        ...


class StrategyCatalogService:
    """策略目录服务 -- Spec CRUD + governance active pointer 读取."""

    def __init__(
        self,
        reader: StrategySpecReaderProtocol,
        writer: StrategySpecWriterProtocol,
        active_pointer_reader: StrategyActivePointerReader | None = None,
        version_state_reader: StrategyVersionStateReader | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._active_pointer_reader = active_pointer_reader
        self._version_state_reader = version_state_reader

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

    def get_version_state(self, strategy_id: str, version: int) -> str | None:
        """
        返回 governance 版本状态字符串（draft/review/published/deprecated）.

        research runtime 的 I/O-free builder 通过此方法获取 version_status，
        不再读 StrategySpecRecord.status。无 state reader 或版本未在 governance
        登记时返回 None（调用方走 fail-closed）。
        """
        if self._version_state_reader is None:
            return None
        state_record = self._version_state_reader.get_state(strategy_id, version)
        if state_record is None:
            return None
        return str(state_record.state)
