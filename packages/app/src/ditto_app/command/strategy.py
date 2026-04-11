"""策略 Spec CRUD 命令 DTO + Handler — 创建/更新/发布策略."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)

__all__ = [
    "CreateStrategyCommand",
    "CreateStrategyHandler",
    "PublishStrategyCommand",
    "PublishStrategyHandler",
    "UpdateStrategyCommand",
    "UpdateStrategyHandler",
]


@dataclass(frozen=True)
class CreateStrategyCommand:
    """创建策略命令."""

    strategy_id: str
    name: str
    spec_json: dict[str, object]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpdateStrategyCommand:
    """更新策略命令."""

    strategy_id: str
    name: str
    spec_json: dict[str, object]
    version: int = 1
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublishStrategyCommand:
    """发布策略命令."""

    strategy_id: str
    version: int


class CreateStrategyHandler:
    """创建策略 Spec — Command Handler."""

    def __init__(self, catalog_service: StrategyCatalogService) -> None:
        self._service = catalog_service

    def handle(self, command: CreateStrategyCommand) -> StrategySpecRecord:
        """处理创建策略命令."""
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = StrategySpecRecord(
            strategy_id=command.strategy_id,
            name=command.name,
            spec_json=command.spec_json,
            tags=command.tags,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        self._service.save_spec(record)
        return record


class UpdateStrategyHandler:
    """更新策略 Spec — Command Handler."""

    def __init__(self, catalog_service: StrategyCatalogService) -> None:
        self._service = catalog_service

    def handle(self, command: UpdateStrategyCommand) -> StrategySpecRecord:
        """处理更新策略命令."""
        existing = self._service.get_spec(command.strategy_id)
        if existing is None:
            msg = f"Strategy not found: {command.strategy_id}"
            raise ValueError(msg)

        if existing.version != command.version:
            msg = (
                f"Version conflict for strategy {command.strategy_id}: "
                f"expected {existing.version}, got {command.version}"
            )
            raise ValueError(msg)

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_version = existing.version + 1
        record = StrategySpecRecord(
            strategy_id=command.strategy_id,
            name=command.name,
            spec_json=command.spec_json,
            version=new_version,
            status="draft",
            created_at=existing.created_at,
            updated_at=now,
            tags=command.tags,
        )
        self._service.save_spec(record)
        return record


class PublishStrategyHandler:
    """发布策略 Spec — Command Handler."""

    def __init__(self, catalog_service: StrategyCatalogService) -> None:
        self._service = catalog_service

    def handle(self, command: PublishStrategyCommand) -> bool:
        """处理发布策略命令."""
        existing = self._service.get_spec(command.strategy_id, command.version)
        if existing is None:
            msg = f"Strategy not found: {command.strategy_id} v{command.version}"
            raise ValueError(msg)
        return self._service.publish_spec(command.strategy_id, command.version)
