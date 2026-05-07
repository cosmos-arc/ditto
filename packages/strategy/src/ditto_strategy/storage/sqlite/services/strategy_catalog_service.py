"""StrategyCatalogService -- 策略 Spec CRUD 与状态治理."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "StrategyCatalogService",
    "StrategySpecReaderProtocol",
    "StrategySpecWriterProtocol",
]


@runtime_checkable
class StrategySpecReaderProtocol(Protocol):
    """策略 Spec 读取协议."""

    def get(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """获取策略 Spec，version=None 返回最新版本."""
        ...

    def list_all(self) -> list[StrategySpecRecord]:
        """列出所有策略 Spec（最新版本）."""
        ...

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        """列出策略的所有版本."""
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
    """策略目录服务 -- Spec CRUD + DRAFT/PUBLISHED 状态治理."""

    def __init__(
        self,
        reader: StrategySpecReaderProtocol,
        writer: StrategySpecWriterProtocol,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def save_spec(self, record: StrategySpecRecord) -> None:
        """保存策略 Spec."""
        self._writer.save(record)

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        """获取策略 Spec，version=None 返回最新版本."""
        return self._reader.get(strategy_id, version)

    def list_specs(self) -> list[StrategySpecRecord]:
        """列出所有策略 Spec（最新版本）."""
        return self._reader.list_all()

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        """列出策略的所有版本."""
        return self._reader.list_versions(strategy_id)

    def publish_spec(self, strategy_id: str, version: int) -> bool:
        """发布策略 Spec（draft -> published）."""
        return self._writer.update_status(strategy_id, version, "published")
