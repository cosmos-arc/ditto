"""Universe CRUD Command DTO + Handler — 创建/更新/删除自定义 Universe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ditto_data.services.metadata_service import MetadataService

from ditto_application.exceptions import AppCommandError

__all__ = [
    "CreateCustomUniverseCommand",
    "CreateCustomUniverseHandler",
    "DeleteCustomUniverseCommand",
    "DeleteCustomUniverseHandler",
    "UpdateCustomUniverseCommand",
    "UpdateCustomUniverseHandler",
]


@dataclass(frozen=True)
class CreateCustomUniverseCommand:
    """创建自定义 Universe 命令."""

    universe_id: str
    name: str
    description: str | None = None


@dataclass(frozen=True)
class UpdateCustomUniverseCommand:
    """更新自定义 Universe 命令."""

    universe_id: str
    name: str
    description: str | None = None
    members: list[str] | None = None
    effective_date: str | None = None


@dataclass(frozen=True)
class DeleteCustomUniverseCommand:
    """删除自定义 Universe 命令."""

    universe_id: str


class CreateCustomUniverseHandler:
    """创建自定义 Universe — Command Handler."""

    def __init__(self, metadata_service: MetadataService) -> None:
        self._service = metadata_service

    def handle(self, command: CreateCustomUniverseCommand) -> dict[str, str | None]:
        """创建自定义 universe 并返回详情."""
        self._service.create_universe(
            universe_id=command.universe_id,
            name=command.name,
            description=command.description,
            universe_type="custom",
            source_ref=None,
        )
        detail = self._service.get_universe_detail(command.universe_id)
        return (
            detail
            if detail is not None
            else {
                "universe_id": command.universe_id,
                "name": command.name,
            }
        )


class UpdateCustomUniverseHandler:
    """更新自定义 Universe — Command Handler."""

    def __init__(self, metadata_service: MetadataService) -> None:
        self._service = metadata_service

    def handle(self, command: UpdateCustomUniverseCommand) -> dict[str, str | None]:
        """更新自定义 universe 元数据（预设 universe 不可修改）。"""
        existing = self._service.get_universe_detail(command.universe_id)
        if existing is None:
            msg = f"Universe not found: {command.universe_id}"
            raise AppCommandError(
                msg,
                universe_id=command.universe_id,
                reason="not_found",
            )
        universe_type = existing.get("universe_type", "custom")
        if universe_type != "custom":
            msg = (
                f"Preset universe cannot be modified"
                f" '{command.universe_id}' (type={universe_type})"
            )
            raise AppCommandError(
                msg,
                universe_id=command.universe_id,
                reason="non_custom_universe",
                universe_type=universe_type,
                operation="update",
            )
        self._service.update_universe(
            command.universe_id,
            command.name,
            command.description,
        )
        # 成分替换（可选）
        if command.members is not None:
            eff_date = command.effective_date or ""
            records: list[dict[str, Any]] = []
            for index, member in enumerate(command.members):
                try:
                    instrument_id = int(member)
                except ValueError:
                    msg = (
                        f"invalid members[{index}] for universe_id="
                        f"{command.universe_id}: {member}"
                    )
                    raise AppCommandError(
                        msg,
                        universe_id=command.universe_id,
                        field="members",
                        index=index,
                        value=member,
                    ) from None
                records.append(
                    {"instrument_id": instrument_id, "effective_from": eff_date}
                )
            self._service.replace_constituents(
                command.universe_id,
                records,
                command.effective_date or "",
            )
        return self._service.get_universe_detail(command.universe_id) or existing


class DeleteCustomUniverseHandler:
    """删除自定义 Universe — Command Handler."""

    def __init__(self, metadata_service: MetadataService) -> None:
        self._service = metadata_service

    def handle(self, command: DeleteCustomUniverseCommand) -> bool:
        """删除自定义 universe（预设 universe 不可删除）."""
        existing = self._service.get_universe_detail(command.universe_id)
        if existing is None:
            msg = f"Universe not found: {command.universe_id}"
            raise AppCommandError(
                msg,
                universe_id=command.universe_id,
                reason="not_found",
            )
        universe_type = existing.get("universe_type", "custom")
        if universe_type != "custom":
            msg = (
                f"Cannot delete preset universe"
                f" '{command.universe_id}' (type={universe_type})"
            )
            raise AppCommandError(
                msg,
                universe_id=command.universe_id,
                reason="non_custom_universe",
                universe_type=universe_type,
                operation="delete",
            )
        self._service.delete_universe(command.universe_id)
        return True
