"""Post-market candidate reasons and next-day plan recording."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

import pytest
from ditto_application.exceptions import AppCommandError
from ditto_application.next_day_plan_contracts import (
    NextDayPlanMaterial,
    NextDayPlanView,
    PlanCandidateNoteView,
)
from ditto_application.processes.markets.record_next_day_plan import (
    RecordNextDayPlan,
    RecordNextDayPlanRequest,
)
from ditto_application.research_judgment_contracts import ResearchJudgmentView

_CREATED = datetime(2026, 11, 10, 15, 5, tzinfo=UTC)
_SAVED_JUDGMENT_ID = "research-judgment:sha256:" + "3" * 64


@dataclass(frozen=True)
class _StubNote:
    instrument_id: int
    reason: str


@dataclass(frozen=True)
class _StubView:
    material: NextDayPlanMaterial

    @property
    def plan_id(self) -> str:
        return f"next-day-plan:sha256:{hash(self.material) & 0xFFFFFFFFFFFFFFFF:016x}"

    @property
    def observation_date(self) -> date:
        return date.fromisoformat(self.material.observation_date)

    @property
    def candidate_notes(self) -> tuple[PlanCandidateNoteView, ...]:
        return tuple(_StubNote(i, r) for i, r in self.material.candidate_notes)

    @property
    def next_day_plan(self) -> str:
        return self.material.next_day_plan

    @property
    def created_at(self) -> datetime:
        return self.material.created_at

    @property
    def schema_version(self) -> int:
        return 1

    @property
    def source_judgment_id(self) -> str | None:
        return self.material.source_judgment_id


class _Factory:
    def __init__(self) -> None:
        self.materials: list[NextDayPlanMaterial] = []

    def create(self, material: NextDayPlanMaterial) -> NextDayPlanView:
        self.materials.append(material)
        return _StubView(material)


class _Recorder:
    def __init__(self) -> None:
        self.saved: list[NextDayPlanView] = []

    def save(self, plan: NextDayPlanView) -> NextDayPlanView:
        self.saved.append(plan)
        return plan


@dataclass(frozen=True)
class _SavedJudgment:
    """Minimal structural view standing in for one saved judgment."""

    judgment_id: str

    @property
    def run_ids(self) -> tuple[str, ...]:
        return ()

    @property
    def judgment(self) -> str:
        return "saved"

    @property
    def created_at(self) -> datetime:
        return _CREATED

    @property
    def strategy_id(self) -> str | None:
        return None

    @property
    def strategy_version(self) -> int | None:
        return None

    @property
    def schema_version(self) -> int:
        return 1


class _JudgmentReader:
    """Reader port stub exposing exactly the given saved judgments."""

    def __init__(self, *_judgment_ids: str) -> None:
        self._saved = {
            judgment_id: _SavedJudgment(judgment_id) for judgment_id in _judgment_ids
        }
        self.requested: list[str] = []

    def get(self, judgment_id: str) -> ResearchJudgmentView | None:
        self.requested.append(judgment_id)
        return self._saved.get(judgment_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchJudgmentView, ...]:
        return tuple(self._saved.values())


def _request() -> RecordNextDayPlanRequest:
    return RecordNextDayPlanRequest(
        observation_date="2026-11-10",
        candidate_notes=((600779, "缩量回踩半年线"), (510888, "跟随大盘缩量")),
        next_day_plan="次日开盘观察 600779 放量情况",
    )


def test_record_stamps_the_server_clock_and_persists_the_view() -> None:
    factory, recorder = _Factory(), _Recorder()
    process = RecordNextDayPlan(
        factory=factory,
        recorder=recorder,
        clock=lambda: _CREATED,
        judgment_reader=_JudgmentReader(_SAVED_JUDGMENT_ID),
    )

    view = process.record(_request())

    assert view.observation_date == date(2026, 11, 10)
    assert [(note.instrument_id, note.reason) for note in view.candidate_notes] == [
        (600779, "缩量回踩半年线"),
        (510888, "跟随大盘缩量"),
    ]
    assert view.created_at == _CREATED
    assert recorder.saved == [view]
    assert factory.materials[0].created_at == _CREATED


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: replace(r, observation_date="2026-13-40"),
        lambda r: replace(r, observation_date="not-a-date"),
        lambda r: replace(r, candidate_notes=()),
        lambda r: replace(r, candidate_notes=((600779, "a"), (600779, "b"))),
        lambda r: replace(r, candidate_notes=((0, "a"),)),
        lambda r: replace(r, candidate_notes=((600779, " "),)),
        lambda r: replace(r, candidate_notes=((600779, " padded "),)),
        lambda r: replace(r, next_day_plan=" "),
        lambda r: replace(r, next_day_plan=" padded "),
        lambda r: replace(r, source_judgment_id="next-day-plan:sha256:" + "1" * 64),
        lambda r: replace(r, source_judgment_id="research-judgment:md5:" + "1" * 32),
        lambda r: replace(r, source_judgment_id=" "),
        # 格式合法但从未保存过的判断身份同样 fail closed（悬空来源）。
        lambda r: replace(r, source_judgment_id="research-judgment:sha256:" + "9" * 64),
    ],
)
def test_record_rejects_invalid_user_input(
    mutation: Callable[[RecordNextDayPlanRequest], RecordNextDayPlanRequest],
) -> None:
    process = RecordNextDayPlan(
        factory=_Factory(),
        recorder=_Recorder(),
        clock=lambda: _CREATED,
        judgment_reader=_JudgmentReader(_SAVED_JUDGMENT_ID),
    )

    with pytest.raises(AppCommandError):
        process.record(mutation(_request()))


def test_record_rejects_a_source_judgment_that_was_never_saved() -> None:
    factory, recorder = _Factory(), _Recorder()
    reader = _JudgmentReader()  # 空判断库：任何来源身份都不可解析
    process = RecordNextDayPlan(
        factory=factory,
        recorder=recorder,
        clock=lambda: _CREATED,
        judgment_reader=reader,
    )
    missing = "research-judgment:sha256:" + "4" * 64

    with pytest.raises(AppCommandError, match="never been saved") as exc_info:
        process.record(replace(_request(), source_judgment_id=missing))

    assert exc_info.value.details["reason"] == "source_judgment_not_found"
    assert reader.requested == [missing]
    # Fail closed 发生在持久化之前：不落悬空引用。
    assert recorder.saved == []
    assert factory.materials == []


def test_record_carries_the_optional_source_judgment_reference() -> None:
    factory, recorder = _Factory(), _Recorder()
    process = RecordNextDayPlan(
        factory=factory,
        recorder=recorder,
        clock=lambda: _CREATED,
        judgment_reader=_JudgmentReader(_SAVED_JUDGMENT_ID),
    )

    view = process.record(replace(_request(), source_judgment_id=_SAVED_JUDGMENT_ID))

    assert view.source_judgment_id == _SAVED_JUDGMENT_ID
    assert factory.materials[0].source_judgment_id == _SAVED_JUDGMENT_ID
    assert recorder.saved == [view]
