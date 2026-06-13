"""Source fallback policy command handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy as DataCatalogSourceFallbackPolicy,
)
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyEventAction,
    CatalogSourceFallbackPolicyReader,
    CatalogSourceFallbackPolicyStatus,
    CatalogSourceFallbackPolicyWriter,
)

from ditto_application.exceptions import AppCommandError
from ditto_application.source_fallback_policy_state import (
    CatalogSourceFallbackPolicy,
    to_catalog_source_fallback_policy,
)

__all__ = [
    "ActivateCatalogSourceFallbackPolicyHandler",
    "ApproveCatalogSourceFallbackPolicyHandler",
    "CatalogSourceFallbackPolicyDraftCommand",
    "CatalogSourceFallbackPolicyDraftResult",
    "CatalogSourceFallbackPolicyLifecycleCommand",
    "CatalogSourceFallbackPolicyLifecycleResult",
    "DraftCatalogSourceFallbackPolicyHandler",
    "RetireCatalogSourceFallbackPolicyHandler",
]


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicyDraftCommand:
    """Persist one source fallback dry-run decision as a draft policy."""

    dataset_id: str
    namespace: str
    trade_date: str
    default_source: str
    selected_source: str
    recommended_source: str | None
    created_by: str
    recommended_actions: tuple[str, ...]
    reason_codes: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    unsupported_sources: tuple[str, ...]
    source_selection_status: str
    source_selection_blockers: tuple[str, ...]
    approval_required: bool
    execution_allowed: bool
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicyDraftResult:
    """Current draft policy state after persisting a dry-run decision."""

    policy: CatalogSourceFallbackPolicy


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicyLifecycleCommand:
    """Operator request to transition one source fallback policy state."""

    policy_id: str
    actor: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogSourceFallbackPolicyLifecycleResult:
    """Current policy state after a lifecycle transition."""

    policy: CatalogSourceFallbackPolicy


class DraftCatalogSourceFallbackPolicyHandler:
    """Persist draft fallback policy state without activating automation."""

    def __init__(
        self,
        policy_writer: CatalogSourceFallbackPolicyWriter,
        *,
        now: Callable[[], datetime] | None = None,
        policy_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._policy_writer = policy_writer
        self._now = now or _utcnow
        self._policy_id_factory = policy_id_factory or _new_policy_id

    def handle(
        self,
        command: CatalogSourceFallbackPolicyDraftCommand,
    ) -> CatalogSourceFallbackPolicyDraftResult:
        """Create draft current state and append a drafted audit event."""
        created_at = self._now()
        policy = DataCatalogSourceFallbackPolicy(
            policy_id=self._policy_id_factory(),
            dataset_id=command.dataset_id,
            namespace=command.namespace,
            trade_date=command.trade_date,
            default_source=command.default_source,
            selected_source=command.selected_source,
            recommended_source=command.recommended_source,
            status="draft",
            created_by=command.created_by,
            created_at=created_at,
            recommended_actions=command.recommended_actions,
            reason_codes=command.reason_codes,
            fallback_sources=command.fallback_sources,
            unsupported_sources=command.unsupported_sources,
            source_selection_status=command.source_selection_status,
            source_selection_blockers=command.source_selection_blockers,
            approval_required=command.approval_required,
            execution_allowed=command.execution_allowed,
            notes=command.notes,
        )
        event = CatalogSourceFallbackPolicyEvent(
            policy_id=policy.policy_id,
            action="drafted",
            actor=command.created_by,
            action_at=created_at,
            status="draft",
            notes=command.notes,
        )
        self._policy_writer.upsert_source_fallback_policy(policy)
        self._policy_writer.append_source_fallback_policy_event(event)
        return CatalogSourceFallbackPolicyDraftResult(
            policy=to_catalog_source_fallback_policy(policy),
        )


class ApproveCatalogSourceFallbackPolicyHandler:
    """Approve a draft fallback policy without activating automation."""

    def __init__(
        self,
        policy_reader: CatalogSourceFallbackPolicyReader,
        policy_writer: CatalogSourceFallbackPolicyWriter,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._handler = _TransitionCatalogSourceFallbackPolicyHandler(
            policy_reader=policy_reader,
            policy_writer=policy_writer,
            required_status="draft",
            next_status="approved",
            event_action="approved",
            command="approve_catalog_source_fallback_policy",
            now=now,
        )

    def handle(
        self,
        command: CatalogSourceFallbackPolicyLifecycleCommand,
    ) -> CatalogSourceFallbackPolicyLifecycleResult:
        """Approve a draft source fallback policy state."""
        return self._handler.handle(command)


class ActivateCatalogSourceFallbackPolicyHandler:
    """Activate an approved fallback policy resource without source mutation."""

    def __init__(
        self,
        policy_reader: CatalogSourceFallbackPolicyReader,
        policy_writer: CatalogSourceFallbackPolicyWriter,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._handler = _TransitionCatalogSourceFallbackPolicyHandler(
            policy_reader=policy_reader,
            policy_writer=policy_writer,
            required_status="approved",
            next_status="active",
            event_action="activated",
            command="activate_catalog_source_fallback_policy",
            now=now,
        )

    def handle(
        self,
        command: CatalogSourceFallbackPolicyLifecycleCommand,
    ) -> CatalogSourceFallbackPolicyLifecycleResult:
        """Activate an approved source fallback policy resource."""
        return self._handler.handle(command)


class RetireCatalogSourceFallbackPolicyHandler:
    """Retire an active fallback policy resource."""

    def __init__(
        self,
        policy_reader: CatalogSourceFallbackPolicyReader,
        policy_writer: CatalogSourceFallbackPolicyWriter,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._handler = _TransitionCatalogSourceFallbackPolicyHandler(
            policy_reader=policy_reader,
            policy_writer=policy_writer,
            required_status="active",
            next_status="retired",
            event_action="retired",
            command="retire_catalog_source_fallback_policy",
            now=now,
        )

    def handle(
        self,
        command: CatalogSourceFallbackPolicyLifecycleCommand,
    ) -> CatalogSourceFallbackPolicyLifecycleResult:
        """Retire an active source fallback policy resource."""
        return self._handler.handle(command)


class _TransitionCatalogSourceFallbackPolicyHandler:
    def __init__(
        self,
        *,
        policy_reader: CatalogSourceFallbackPolicyReader,
        policy_writer: CatalogSourceFallbackPolicyWriter,
        required_status: CatalogSourceFallbackPolicyStatus,
        next_status: CatalogSourceFallbackPolicyStatus,
        event_action: CatalogSourceFallbackPolicyEventAction,
        command: str,
        now: Callable[[], datetime] | None,
    ) -> None:
        self._policy_reader = policy_reader
        self._policy_writer = policy_writer
        self._required_status: CatalogSourceFallbackPolicyStatus = required_status
        self._next_status: CatalogSourceFallbackPolicyStatus = next_status
        self._event_action: CatalogSourceFallbackPolicyEventAction = event_action
        self._command = command
        self._now = now or _utcnow

    def handle(
        self,
        command: CatalogSourceFallbackPolicyLifecycleCommand,
    ) -> CatalogSourceFallbackPolicyLifecycleResult:
        current = self._policy_reader.get_source_fallback_policy(command.policy_id)
        if current is None:
            raise AppCommandError(
                f"Unknown source fallback policy: {command.policy_id}",
                command=self._command,
                policy_id=command.policy_id,
            )
        if current.status != self._required_status:
            raise AppCommandError(
                (
                    "Source fallback policy is not "
                    f"{self._required_status}: {command.policy_id}"
                ),
                command=self._command,
                policy_id=command.policy_id,
                status=current.status,
            )

        transitioned_at = self._now()
        updated = self._transition(current, command, transitioned_at)
        event = CatalogSourceFallbackPolicyEvent(
            policy_id=command.policy_id,
            action=self._event_action,
            actor=command.actor,
            action_at=transitioned_at,
            status=self._next_status,
            notes=command.notes,
        )
        self._policy_writer.upsert_source_fallback_policy(updated)
        self._policy_writer.append_source_fallback_policy_event(event)
        return CatalogSourceFallbackPolicyLifecycleResult(
            policy=to_catalog_source_fallback_policy(updated),
        )

    def _transition(
        self,
        current: DataCatalogSourceFallbackPolicy,
        command: CatalogSourceFallbackPolicyLifecycleCommand,
        transitioned_at: datetime,
    ) -> DataCatalogSourceFallbackPolicy:
        if self._next_status == "approved":
            return replace(
                current,
                status=self._next_status,
                decided_by=command.actor,
                decided_at=transitioned_at,
                decision_notes=command.notes,
            )
        return replace(current, status=self._next_status)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_policy_id() -> str:
    return f"source-fallback-policy-{uuid4()}"
