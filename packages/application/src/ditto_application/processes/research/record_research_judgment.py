"""Record one research judgment bound to explicit compared run identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_application.contracts import StrategySpecInfo
from ditto_application.exceptions import AppCommandError
from ditto_application.research_judgment_contracts import (
    JudgmentClock,
    ResearchJudgmentFactory,
    ResearchJudgmentMaterial,
    ResearchJudgmentRecorder,
    ResearchJudgmentView,
)

__all__ = [
    "JudgmentStrategyVersionReader",
    "RecordResearchJudgment",
    "RecordResearchJudgmentRequest",
]


@dataclass(frozen=True, slots=True)
class RecordResearchJudgmentRequest:
    """Exact user record: compared runs, the conclusion, optional follow-up."""

    run_ids: tuple[str, ...]
    judgment: str
    strategy_id: str | None = None
    strategy_version: int | None = None


class JudgmentStrategyVersionReader(Protocol):
    """Narrow read port proving a follow-up strategy version exists."""

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecInfo | None:
        """Return one cataloged strategy version or ``None`` when absent."""
        ...


class RecordResearchJudgment:
    """Validate one judgment, stamp the server clock and append it."""

    def __init__(
        self,
        *,
        factory: ResearchJudgmentFactory,
        recorder: ResearchJudgmentRecorder,
        clock: JudgmentClock,
        strategy_version_reader: JudgmentStrategyVersionReader,
    ) -> None:
        self._factory = factory
        self._recorder = recorder
        self._clock = clock
        self._strategy_version_reader = strategy_version_reader

    def record(self, request: RecordResearchJudgmentRequest) -> ResearchJudgmentView:
        """Persist one immutable judgment and return its exact view."""
        run_ids = _run_ids(request.run_ids)
        judgment_text = _text(request.judgment, field_name="judgment")
        strategy_id, strategy_version = self._existing_strategy_reference(
            *_strategy_reference(request.strategy_id, request.strategy_version)
        )
        view = self._factory.create(
            ResearchJudgmentMaterial(
                run_ids=run_ids,
                judgment=judgment_text,
                created_at=self._clock(),
                strategy_id=strategy_id,
                strategy_version=strategy_version,
            )
        )
        return self._recorder.save(view)

    def _existing_strategy_reference(
        self, strategy_id: str | None, strategy_version: int | None
    ) -> tuple[str | None, int | None]:
        """Fail closed: a cited follow-up strategy version must exist."""
        if strategy_id is None or strategy_version is None:
            return None, None
        if (
            self._strategy_version_reader.get_spec(strategy_id, strategy_version)
            is None
        ):
            raise AppCommandError(
                f"Strategy version not found: {strategy_id} v{strategy_version}",
                details={
                    "code": "STRATEGY_VERSION_NOT_FOUND",
                    "reason": "strategy_version_not_found",
                    "strategy_id": strategy_id,
                    "version": strategy_version,
                },
            )
        return strategy_id, strategy_version


def _run_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise AppCommandError("compared run identities are required")
    run_ids = tuple(_text(value, field_name="run id") for value in values)
    if len(set(run_ids)) != len(run_ids):
        raise AppCommandError("compared run identities must be unique")
    return run_ids


def _strategy_reference(
    strategy_id: str | None, strategy_version: int | None
) -> tuple[str | None, int | None]:
    if (strategy_id is None) != (strategy_version is None):
        raise AppCommandError(
            "strategy_id and strategy_version must be provided together"
        )
    if strategy_id is None or strategy_version is None:
        return None, None
    if strategy_version < 1:
        raise AppCommandError("strategy_version must be a positive integer")
    return _text(strategy_id, field_name="strategy_id"), strategy_version


def _text(value: str, *, field_name: str) -> str:
    if not value or value != value.strip():
        raise AppCommandError(f"{field_name} must be a non-empty unpadded text")
    return value
