"""Application-owned contract for saved research judgments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

__all__ = [
    "JudgmentClock",
    "ResearchJudgmentFactory",
    "ResearchJudgmentMaterial",
    "ResearchJudgmentReader",
    "ResearchJudgmentRecorder",
    "ResearchJudgmentView",
]


@dataclass(frozen=True, slots=True)
class ResearchJudgmentMaterial:
    """Complete immutable material passed to the isolated analysis plane."""

    run_ids: tuple[str, ...]
    judgment: str
    created_at: datetime
    strategy_id: str | None = None
    strategy_version: int | None = None


class ResearchJudgmentView(Protocol):
    """Narrow structural result returned by an analysis-plane factory."""

    @property
    def judgment_id(self) -> str:
        """Return the immutable research-judgment identity."""
        ...

    @property
    def run_ids(self) -> tuple[str, ...]:
        """Return the exact compared run identities in recorder order."""
        ...

    @property
    def judgment(self) -> str:
        """Return the recorded research conclusion text."""
        ...

    @property
    def created_at(self) -> datetime:
        """Return the server-stamped recording instant."""
        ...

    @property
    def strategy_id(self) -> str | None:
        """Return the optional follow-up verification strategy identity."""
        ...

    @property
    def strategy_version(self) -> int | None:
        """Return the optional follow-up verification strategy version."""
        ...

    @property
    def schema_version(self) -> int:
        """Return the judgment schema version."""
        ...


class ResearchJudgmentFactory(Protocol):
    """Port implemented only at the apps composition boundary."""

    def create(self, material: ResearchJudgmentMaterial) -> ResearchJudgmentView:
        """Validate and create one immutable analysis-owned judgment."""
        ...


class ResearchJudgmentRecorder(Protocol):
    """Append-only persistence port for saved judgments."""

    def save(self, judgment: ResearchJudgmentView) -> ResearchJudgmentView:
        """
        Persist one judgment and return the authoritative stored entry.

        An exact replay keeps the first-recorded entry (and its timestamp).
        """
        ...


class ResearchJudgmentReader(Protocol):
    """Exact read port backed by the append-only judgment store."""

    def get(self, judgment_id: str) -> ResearchJudgmentView | None:
        """Return one exact judgment or None when never saved."""
        ...

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchJudgmentView, ...]:
        """Return the most recently saved judgments, newest first."""
        ...


JudgmentClock = Callable[[], datetime]
