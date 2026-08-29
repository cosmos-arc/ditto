"""策略 Spec CRUD 命令 DTO + Handler — 创建/更新/发布策略（governance-backed）."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import cast

from ditto_strategy.governance.models import StrategyDecision, StrategyDecisionEvent
from ditto_strategy.governance.protocols import StrategyGovernanceEventIntegrityError
from ditto_strategy.governance.service import (
    GovernanceService,
    StrategyGovernanceError,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    StrategyGovernanceCasConflict,
)

from ditto_application.commands.strategy_governance_clock import (
    utc_now_iso as _utc_now_iso,
)
from ditto_application.contracts import StrategySpecInfo, to_spec_info
from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    canonical_resource_id,
    find_mutation_receipt_in_reasons,
    mutation_event_id,
    mutation_receipt_reason,
)
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


@dataclass(frozen=True)
class CreateStrategyCommand:
    """创建策略命令."""

    strategy_id: str
    name: str
    spec_json: dict[str, object]
    tags: tuple[str, ...] = ()
    idempotency: MutationIdempotency | None = None
    actor: str = _COMMAND_ACTOR
    reason: str = "create strategy draft"


@dataclass(frozen=True)
class UpdateStrategyCommand:
    """更新策略命令."""

    strategy_id: str
    name: str
    spec_json: dict[str, object]
    version: int | None = None
    tags: tuple[str, ...] = ()
    idempotency: MutationIdempotency | None = None
    actor: str = _COMMAND_ACTOR
    reason: str = "update strategy draft"


@dataclass(frozen=True)
class PublishStrategyCommand:
    """发布策略命令."""

    strategy_id: str
    version: int


def _spec_info_receipt(info: StrategySpecInfo) -> dict[str, object]:
    return {
        "strategy_id": info.strategy_id,
        "name": info.name,
        "spec_json": info.spec_json,
        "version": info.version,
        "status": info.status,
        "created_at": info.created_at,
        "tags": list(info.tags),
    }


def _spec_info_from_receipt(value: dict[str, object]) -> StrategySpecInfo:
    expected = {
        "strategy_id",
        "name",
        "spec_json",
        "version",
        "status",
        "created_at",
        "tags",
    }
    spec_json = value.get("spec_json")
    tags = value.get("tags")
    tag_values = () if not isinstance(tags, list) else cast("list[object]", tags)
    if (
        set(value) != expected
        or type(value["strategy_id"]) is not str
        or type(value["name"]) is not str
        or not isinstance(spec_json, dict)
        or type(value["version"]) is not int
        or type(value["status"]) is not str
        or type(value["created_at"]) is not str
        or not isinstance(tags, list)
        or any(type(item) is not str for item in tag_values)
    ):
        raise AppCommandError(
            "durable strategy receipt is invalid",
            details={
                "code": "IDEMPOTENCY_RECEIPT_INVALID",
                "reason": "idempotency_receipt_invalid",
            },
        )
    return StrategySpecInfo(
        strategy_id=value["strategy_id"],
        name=value["name"],
        spec_json=cast("dict[str, object]", spec_json),
        version=value["version"],
        status=value["status"],
        created_at=value["created_at"],
        tags=cast("tuple[str, ...]", tuple(tag_values)),
    )


def _replay_spec(
    governance: GovernanceService,
    identity: MutationIdempotency | None,
    *,
    strategy_id: str,
) -> StrategySpecInfo | None:
    if identity is None:
        return None
    event = governance.get_decision_event(mutation_event_id(identity))
    if event is None:
        return None
    expected_decision = {
        "strategies_create_strategy": StrategyDecision.AUDIT_CREATE_DRAFT,
        "strategies_update_strategy": StrategyDecision.AUDIT_UPDATE_DRAFT,
    }.get(identity.operation_id)
    if (
        expected_decision is None
        or event.event_id != mutation_event_id(identity)
        or identity.resource_id
        != canonical_resource_id("strategy", {"strategy_id": strategy_id})
        or event.strategy_id != strategy_id
        or event.decision is not expected_decision
        or not event.actor
        or not event.decided_at
    ):
        raise AppCommandError(
            "durable strategy receipt is invalid",
            details={
                "code": "IDEMPOTENCY_RECEIPT_INVALID",
                "reason": "idempotency_receipt_invalid",
            },
        )
    receipt = find_mutation_receipt_in_reasons((event.reason,), identity)
    if receipt is None:
        raise AppCommandError(
            "durable strategy receipt is invalid",
            details={
                "code": "IDEMPOTENCY_RECEIPT_INVALID",
                "reason": "idempotency_receipt_invalid",
            },
        )
    result = _spec_info_from_receipt(dict(receipt))
    version = governance.get_version(strategy_id, event.version)
    durable_record = governance.get_spec_record(strategy_id, event.version)
    reconstructed = StrategySpecRecord(
        strategy_id=result.strategy_id,
        name=result.name,
        spec_json=result.spec_json,
        version=result.version,
        parent_version=None if version is None else version.parent_version,
        created_at=result.created_at,
        tags=result.tags,
    )
    reconstructed = replace(
        reconstructed,
        spec_hash=canonical_spec_hash_for_record(reconstructed),
    )
    if (
        result.strategy_id != strategy_id
        or result.version != event.version
        or result.version <= 0
        or result.status != "draft"
        or version is None
        or version.strategy_id != strategy_id
        or version.version != result.version
        or version.created_at != result.created_at
        or event.decided_at != result.created_at
        or version.spec_hash != reconstructed.spec_hash
        or durable_record != reconstructed
        or (
            event.decision is StrategyDecision.AUDIT_CREATE_DRAFT
            and (result.version != 1 or version.parent_version is not None)
        )
        or (
            event.decision is StrategyDecision.AUDIT_UPDATE_DRAFT
            and (result.version <= 1 or version.parent_version is None)
        )
    ):
        raise AppCommandError(
            "durable strategy receipt is invalid",
            details={
                "code": "IDEMPOTENCY_RECEIPT_INVALID",
                "reason": "idempotency_receipt_invalid",
            },
        )
    return result


class CreateStrategyHandler:
    """创建策略 Spec — 经 governance 写 draft 版本（append-only）."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: CreateStrategyCommand) -> StrategySpecInfo:
        """处理创建策略命令（重复 strategy_id 抛 conflict）."""
        replay = _replay_spec(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
        )
        if replay is not None:
            return replay
        now = _utc_now_iso()
        record = StrategySpecRecord(
            strategy_id=command.strategy_id,
            name=command.name,
            spec_json=command.spec_json,
            tags=command.tags,
            version=1,
            created_at=now,
        )
        record = replace(record, spec_hash=canonical_spec_hash_for_record(record))
        result = to_spec_info(record, status="draft")
        audit_event = None
        if command.idempotency is not None:
            audit_event = StrategyDecisionEvent(
                event_id=mutation_event_id(command.idempotency),
                strategy_id=command.strategy_id,
                version=1,
                decision=StrategyDecision.AUDIT_CREATE_DRAFT,
                actor=command.actor,
                reason=mutation_receipt_reason(
                    command.idempotency,
                    response=_spec_info_receipt(result),
                    human_reason=command.reason,
                ),
                decided_at=now,
            )
        try:
            self._governance.create_draft(
                strategy_id=command.strategy_id,
                version=1,
                spec_record=record,
                created_at=now,
                audit_event=audit_event,
            )
        except StrategyGovernanceCasConflict as exc:
            replay = _replay_spec(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
            )
            if replay is not None:
                return replay
            raise AppCommandError(
                f"Strategy revision conflict for {command.strategy_id}: {exc}",
                details={
                    "code": "STRATEGY_REVISION_CONFLICT",
                    "strategy_id": command.strategy_id,
                    "version": 1,
                },
            ) from exc
        except StrategyGovernanceEventIntegrityError as exc:
            raise AppCommandError(
                "Strategy governance event integrity error for "
                + f"{command.strategy_id}: {exc}",
                details={
                    "code": "STRATEGY_GOVERNANCE_EVENT_INTEGRITY_ERROR",
                    "strategy_id": command.strategy_id,
                    "version": 1,
                },
            ) from exc
        except sqlite3.IntegrityError as exc:
            replay = _replay_spec(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
            )
            if replay is not None:
                return replay
            msg = f"Strategy already exists: {command.strategy_id}"
            raise AppCommandError(msg) from exc
        return result


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
        replay = _replay_spec(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
        )
        if replay is not None:
            return replay
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
            created_at=now,
            tags=command.tags,
        )
        record = replace(record, spec_hash=canonical_spec_hash_for_record(record))
        result = to_spec_info(record, status="draft")
        audit_event = None
        if command.idempotency is not None:
            audit_event = StrategyDecisionEvent(
                event_id=mutation_event_id(command.idempotency),
                strategy_id=command.strategy_id,
                version=new_version,
                decision=StrategyDecision.AUDIT_UPDATE_DRAFT,
                actor=command.actor,
                reason=mutation_receipt_reason(
                    command.idempotency,
                    response=_spec_info_receipt(result),
                    human_reason=command.reason,
                ),
                decided_at=now,
            )
        try:
            self._governance.create_draft(
                strategy_id=command.strategy_id,
                version=new_version,
                spec_record=record,
                created_at=now,
                audit_event=audit_event,
            )
        except StrategyGovernanceCasConflict as exc:
            replay = _replay_spec(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
            )
            if replay is not None:
                return replay
            raise AppCommandError(
                f"Strategy revision conflict for {command.strategy_id} "
                + f"v{new_version}: {exc}",
                details={
                    "code": "STRATEGY_REVISION_CONFLICT",
                    "strategy_id": command.strategy_id,
                    "version": new_version,
                },
            ) from exc
        except StrategyGovernanceEventIntegrityError as exc:
            raise AppCommandError(
                "Strategy governance event integrity error for "
                + f"{command.strategy_id} v{new_version}: {exc}",
                details={
                    "code": "STRATEGY_GOVERNANCE_EVENT_INTEGRITY_ERROR",
                    "strategy_id": command.strategy_id,
                    "version": new_version,
                },
            ) from exc
        except sqlite3.IntegrityError as exc:
            replay = _replay_spec(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
            )
            if replay is not None:
                return replay
            msg = (
                f"Strategy version already exists: {command.strategy_id} v{new_version}"
            )
            raise AppCommandError(msg) from exc
        return result


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
        except StrategyGovernanceCasConflict as exc:
            raise AppCommandError(
                f"Strategy revision conflict for {command.strategy_id} "
                + f"v{command.version}: {exc}",
                details={
                    "code": "STRATEGY_REVISION_CONFLICT",
                    "strategy_id": command.strategy_id,
                    "version": command.version,
                },
            ) from exc
        except StrategyGovernanceEventIntegrityError as exc:
            raise AppCommandError(
                "Strategy governance event integrity error for "
                + f"{command.strategy_id} v{command.version}: {exc}",
                details={
                    "code": "STRATEGY_GOVERNANCE_EVENT_INTEGRITY_ERROR",
                    "strategy_id": command.strategy_id,
                    "version": command.version,
                },
            ) from exc
        except StrategyGovernanceError as exc:
            msg = (
                f"Strategy version not found: {command.strategy_id} v{command.version}"
            )
            raise AppCommandError(msg) from exc
        return True
