"""Research judgment recording bound to explicit compared run identities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.research.record_research_judgment import (
    RecordResearchJudgment,
    RecordResearchJudgmentRequest,
)
from ditto_application.research_judgment_contracts import (
    ResearchJudgmentMaterial,
    ResearchJudgmentView,
)

_CREATED = datetime(2026, 11, 10, 15, 5, tzinfo=UTC)


@dataclass(frozen=True)
class _StubView:
    material: ResearchJudgmentMaterial

    @property
    def judgment_id(self) -> str:
        digest = hash(self.material) & 0xFFFFFFFFFFFFFFFF
        return f"research-judgment:sha256:{digest:016x}"

    @property
    def run_ids(self) -> tuple[str, ...]:
        return self.material.run_ids

    @property
    def judgment(self) -> str:
        return self.material.judgment

    @property
    def created_at(self) -> datetime:
        return self.material.created_at

    @property
    def strategy_id(self) -> str | None:
        return self.material.strategy_id

    @property
    def strategy_version(self) -> int | None:
        return self.material.strategy_version

    @property
    def schema_version(self) -> int:
        return 1


class _Factory:
    def __init__(self) -> None:
        self.materials: list[ResearchJudgmentMaterial] = []

    def create(self, material: ResearchJudgmentMaterial) -> ResearchJudgmentView:
        self.materials.append(material)
        return _StubView(material)


class _Recorder:
    def __init__(self) -> None:
        self.saved: list[ResearchJudgmentView] = []

    def save(self, judgment: ResearchJudgmentView) -> ResearchJudgmentView:
        self.saved.append(judgment)
        return judgment


def _request() -> RecordResearchJudgmentRequest:
    return RecordResearchJudgmentRequest(
        run_ids=("sys-fx-nav-001", "sys-fx-nav-002"),
        judgment="同口径可比; 001 回撤更浅, 次日观察放量修复是否延续",
    )


def test_record_stamps_the_server_clock_and_persists_the_view() -> None:
    factory, recorder = _Factory(), _Recorder()
    process = RecordResearchJudgment(
        factory=factory, recorder=recorder, clock=lambda: _CREATED
    )

    view = process.record(_request())

    assert view.run_ids == ("sys-fx-nav-001", "sys-fx-nav-002")
    assert view.judgment == "同口径可比; 001 回撤更浅, 次日观察放量修复是否延续"
    assert view.strategy_id is None
    assert view.strategy_version is None
    assert view.created_at == _CREATED
    assert recorder.saved == [view]
    assert factory.materials[0].created_at == _CREATED


def test_record_carries_the_optional_follow_up_strategy_reference() -> None:
    factory, recorder = _Factory(), _Recorder()
    process = RecordResearchJudgment(
        factory=factory, recorder=recorder, clock=lambda: _CREATED
    )

    view = process.record(
        RecordResearchJudgmentRequest(
            run_ids=("sys-fx-nav-001",),
            judgment="单 run 结论成立, 转入策略版本验证",
            strategy_id="sys-fx-etf-rotation",
            strategy_version=2,
        )
    )

    assert view.strategy_id == "sys-fx-etf-rotation"
    assert view.strategy_version == 2
    assert recorder.saved == [view]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: replace(r, run_ids=()),
        lambda r: replace(r, run_ids=("sys-fx-nav-001", "sys-fx-nav-001")),
        lambda r: replace(r, run_ids=(" ",)),
        lambda r: replace(r, run_ids=(" padded ",)),
        lambda r: replace(r, judgment=" "),
        lambda r: replace(r, judgment=" padded "),
        lambda r: replace(r, strategy_id="sys-fx-etf-rotation"),
        lambda r: replace(r, strategy_version=2),
        lambda r: replace(r, strategy_id=" ", strategy_version=2),
        lambda r: replace(r, strategy_id="sys-fx-etf-rotation", strategy_version=0),
    ],
)
def test_record_rejects_invalid_user_input(
    mutation: Callable[[RecordResearchJudgmentRequest], RecordResearchJudgmentRequest],
) -> None:
    process = RecordResearchJudgment(
        factory=_Factory(), recorder=_Recorder(), clock=lambda: _CREATED
    )

    with pytest.raises(AppCommandError):
        process.record(mutation(_request()))
