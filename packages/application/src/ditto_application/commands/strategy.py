"""策略 Spec CRUD 命令 DTO + Handler — 创建/更新/发布策略（governance-backed）."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ditto_strategy.governance.service import (
    GovernanceService,
    StrategyGovernanceError,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

from ditto_application.contracts import StrategySpecInfo, to_spec_info
from ditto_application.exceptions import AppCommandError
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)

__all__ = [
    "CreateStrategyCommand",
    "CreateStrategyHandler",
    "PublishStrategyCommand",
    "PublishStrategyHandler",
    "UpdateStrategyCommand",
    "UpdateStrategyHandler",
]

_COMMAND_ACTOR = "command"
_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _utc_now_iso() -> str:
    """Stable ISO-8601 UTC timestamp for governance events."""
    return datetime.now(UTC).strftime(_UTC_FMT)


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
    version: int | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublishStrategyCommand:
    """发布策略命令."""

    strategy_id: str
    version: int


class CreateStrategyHandler:
    """创建策略 Spec — 经 governance 写 draft 版本（append-only）."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: CreateStrategyCommand) -> StrategySpecInfo:
        """处理创建策略命令（重复 strategy_id 抛 conflict）."""
        now = _utc_now_iso()
        record = StrategySpecRecord(
            strategy_id=command.strategy_id,
            name=command.name,
            spec_json=command.spec_json,
            tags=command.tags,
            version=1,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        record = replace(record, spec_hash=canonical_spec_hash_for_record(record))
        try:
            self._governance.create_draft(
                strategy_id=command.strategy_id,
                version=1,
                spec_record=record,
                created_at=now,
            )
        except sqlite3.IntegrityError as exc:
            msg = f"Strategy already exists: {command.strategy_id}"
            raise AppCommandError(msg) from exc
        return to_spec_info(record, status="draft")


class UpdateStrategyHandler:
    """更新策略 Spec — append-only 派生新 governance draft 版本."""

    def __init__(
        self,
        catalog_service: StrategyCatalogService,
        governance: GovernanceService,
    ) -> None:
        self._catalog = catalog_service
        self._governance = governance

    def handle(self, command: UpdateStrategyCommand) -> StrategySpecInfo:
        """处理更新策略命令（基于 existing 版本派生 new version）."""
        existing = self._catalog.get_spec(command.strategy_id)
        if existing is None:
            msg = f"Strategy not found: {command.strategy_id}"
            raise AppCommandError(msg)

        # version=None 时自动使用当前版本（跳过乐观锁）
        effective_version = (
            command.version if command.version is not None else existing.version
        )

        if existing.version != effective_version:
            msg = (
                f"Version conflict for strategy {command.strategy_id}: "
                f"expected {existing.version}, got {effective_version}"
            )
            raise AppCommandError(msg)

        now = _utc_now_iso()
        new_version = existing.version + 1
        record = StrategySpecRecord(
            strategy_id=command.strategy_id,
            name=command.name,
            spec_json=command.spec_json,
            version=new_version,
            parent_version=existing.version,
            status="draft",
            created_at=existing.created_at,
            updated_at=now,
            tags=command.tags,
        )
        record = replace(record, spec_hash=canonical_spec_hash_for_record(record))
        try:
            self._governance.create_draft(
                strategy_id=command.strategy_id,
                version=new_version,
                spec_record=record,
                created_at=now,
            )
        except sqlite3.IntegrityError as exc:
            msg = (
                f"Strategy version already exists: {command.strategy_id} v{new_version}"
            )
            raise AppCommandError(msg) from exc
        return to_spec_info(record, status="draft")


class PublishStrategyHandler:
    """发布策略 Spec — 经 governance publish_and_activate（幂等）."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: PublishStrategyCommand) -> bool:
        """处理发布策略命令（version 不存在或已 deprecated 抛 conflict）."""
        try:
            self._governance.publish_and_activate(
                strategy_id=command.strategy_id,
                version=command.version,
                actor=_COMMAND_ACTOR,
                reason="strategy publish command",
                decided_at=_utc_now_iso(),
            )
        except StrategyGovernanceError as exc:
            msg = (
                f"Strategy version not found: {command.strategy_id} v{command.version}"
            )
            raise AppCommandError(msg) from exc
        return True
