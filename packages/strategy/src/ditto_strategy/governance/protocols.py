"""Storage protocols consumed by the governance service and its callers."""

from __future__ import annotations

from typing import Protocol

from ditto_strategy.governance.models import (
    ReviewOutcome,
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecisionEvent,
    StrategyVersion,
    StrategyVersionState,
    StrategyVersionStateRecord,
)
from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "StrategyActivePointerReader",
    "StrategyGovernanceStoreProtocol",
    "StrategyGovernanceVersionReader",
    "StrategyVersionStateReader",
]


class StrategyGovernanceStoreProtocol(Protocol):
    """Append-only governance store contract used by the service layer."""

    def insert_version(self, version: StrategyVersion) -> None:
        """Insert one immutable version plus its initial draft state."""
        ...

    def create_draft_version(
        self,
        spec_record: StrategySpecRecord,
        version: StrategyVersion,
        audit_event: StrategyDecisionEvent | None = None,
    ) -> None:
        """Persist payload/version/state and an optional audit receipt atomically."""
        ...

    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        """Return one immutable version, or None if absent."""
        ...

    def get_spec_record(
        self,
        strategy_id: str,
        version: int,
    ) -> StrategySpecRecord | None:
        """Return the immutable spec payload for one governance version."""
        ...

    def list_versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]:
        """List every immutable version for a strategy, newest first."""
        ...

    def get_state(
        self, strategy_id: str, version: int
    ) -> StrategyVersionStateRecord | None:
        """Return the rebuildable lifecycle projection for one version."""
        ...

    def get_decision_event(self, event_id: str) -> StrategyDecisionEvent | None:
        """Return one immutable decision/audit event by primary key."""
        ...

    def append_decision(
        self,
        event: StrategyDecisionEvent,
        new_state: StrategyVersionState,
        new_review: ReviewOutcome,
        expected_revision: int,
    ) -> StrategyVersionStateRecord:
        """Append one decision event and CAS-advance the state projection."""
        ...

    def publish_reviewed_and_activate(
        self,
        publish_event: StrategyDecisionEvent,
        activation_event: StrategyActivationEvent,
        *,
        expected_state_revision: int,
        expected_pointer_revision: int,
    ) -> StrategyActivePointer:
        """Atomically publish one approved review and switch its active pointer."""
        ...

    def activate(
        self,
        strategy_id: str,
        target_version: int,
        event: StrategyActivationEvent,
        expected_pointer_revision: int,
    ) -> StrategyActivePointer:
        """Append an activation event and CAS-swap the active pointer."""
        ...

    def get_active_pointer(self, strategy_id: str) -> StrategyActivePointer | None:
        """Return the single active pointer for a strategy, or None."""
        ...

    def get_activation_event(self, event_id: str) -> StrategyActivationEvent | None:
        """Return one immutable activation event by primary key."""
        ...


class StrategyActivePointerReader(Protocol):
    """Narrow read port for resolving the active strategy version."""

    def get_active_pointer(self, strategy_id: str) -> StrategyActivePointer | None:
        """Return the single active pointer for a strategy, or None."""
        ...


class StrategyVersionStateReader(Protocol):
    """Narrow read port for resolving one version's governance lifecycle state."""

    def get_state(
        self, strategy_id: str, version: int
    ) -> StrategyVersionStateRecord | None:
        """Return the rebuildable lifecycle projection for one version, or None."""
        ...


class StrategyGovernanceVersionReader(Protocol):
    """Narrow read port for listing versions and resolving the active pointer."""

    def list_versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]:
        """List every immutable version for a strategy, newest first."""
        ...

    def list_versions_by_state(
        self, state: StrategyVersionState
    ) -> tuple[StrategyVersion, ...]:
        """List every version currently in one lifecycle state, newest first."""
        ...

    def get_active_pointer(self, strategy_id: str) -> StrategyActivePointer | None:
        """Return the single active pointer for a strategy, or None."""
        ...
