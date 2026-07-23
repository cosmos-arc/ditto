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

__all__ = ["StrategyGovernanceStoreProtocol"]


class StrategyGovernanceStoreProtocol(Protocol):
    """Append-only governance store contract used by the service layer."""

    def insert_version(self, version: StrategyVersion) -> None:
        """Insert one immutable version plus its initial draft state."""
        ...

    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        """Return one immutable version, or None if absent."""
        ...

    def list_versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]:
        """List every immutable version for a strategy, newest first."""
        ...

    def get_state(
        self, strategy_id: str, version: int
    ) -> StrategyVersionStateRecord | None:
        """Return the rebuildable lifecycle projection for one version."""
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
