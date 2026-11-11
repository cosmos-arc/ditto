"""Exact Research Case reads for the research handoff journey."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_analysis.research.cases import ResearchCase
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.research_cases import ResearchCaseQueryService
from ditto_application.research_case_contracts import (
    ResearchCaseMaterial,
    ResearchCaseView,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.selection.contracts import SelectionRun

_AS_OF = datetime(2026, 11, 10, 7, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _material(**overrides: object) -> ResearchCaseMaterial:
    baseline = ResearchCaseMaterial(
        selection_run_id=f"selection-run:sha256:{_HASH_A}",
        selection_run_hash=_HASH_A,
        selection_input_hash=_HASH_B,
        selection_spec_hash="c" * 64,
        objective="验证筛选候选的持续性",
        asset_kind="stock",
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=("source-a", "source-b"),
        candidate_instrument_ids=(InstrumentId(600001), InstrumentId(600002)),
        selection_status="ready",
        missing_inputs=(),
    )
    return type(baseline)(**{**asdict(baseline), **overrides})


class _Reader:
    """In-memory structural double for the analysis-owned store."""

    def __init__(self) -> None:
        self.cases: dict[str, ResearchCaseView] = {}

    def save(self, case: ResearchCaseView) -> None:
        self.cases[case.case_id] = case

    def get(self, case_id: str) -> ResearchCaseView | None:
        return self.cases.get(case_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchCaseView, ...]:
        ordered = sorted(
            self.cases.values(),
            key=lambda item: (item.as_of, item.case_id),
            reverse=True,
        )
        return tuple(ordered[:limit])

    def list_by_run(
        self, selection_run_id: str, *, limit: int = 20
    ) -> tuple[ResearchCaseView, ...]:
        matched = [
            item
            for item in self.list_recent(limit=len(self.cases))
            if item.selection_run_id == selection_run_id
        ]
        return tuple(matched[:limit])


class _Runs:
    """Existence-only run reader double (the query never reads run fields)."""

    def __init__(self, *run_ids: str) -> None:
        self.known = frozenset(run_ids)

    def get(self, run_id: str) -> SelectionRun | None:
        if run_id not in self.known:
            return None
        return cast(SelectionRun, object())

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        return []


def _case(reader: _Reader, **overrides: object) -> ResearchCaseView:
    case: ResearchCaseView = ResearchCase(**asdict(_material(**overrides)))
    reader.save(case)
    return case


def test_get_returns_the_exact_case_by_content_identity() -> None:
    reader = _Reader()
    case = _case(reader)
    service = ResearchCaseQueryService(reader, _Runs(case.selection_run_id))

    assert service.get(case.case_id) is case


def test_get_fails_closed_for_an_unknown_case() -> None:
    service = ResearchCaseQueryService(_Reader(), _Runs())

    with pytest.raises(AppQueryError) as error:
        service.get("research-case:sha256:" + "f" * 64)
    assert error.value.details["reason"] == "research_case_not_found"


def test_get_rejects_blank_identities() -> None:
    service = ResearchCaseQueryService(_Reader(), _Runs())

    with pytest.raises(AppQueryError) as error:
        service.get("   ")
    assert error.value.details["reason"] == "invalid_research_case_id"


def test_list_recent_projects_handoff_summaries_newest_first() -> None:
    reader = _Reader()
    older = _case(reader, as_of=datetime(2026, 11, 9, 7, 0, tzinfo=UTC))
    newer = _case(
        reader,
        as_of=datetime(2026, 11, 10, 7, 0, tzinfo=UTC),
        selection_run_id=f"selection-run:sha256:{_HASH_B}",
        selection_run_hash=_HASH_B,
        objective="更新一天的假设",
    )
    service = ResearchCaseQueryService(reader, _Runs())

    listed = service.list_recent(limit=10)

    assert [item.case_id for item in listed] == [newer.case_id, older.case_id]
    assert listed[0].objective == "更新一天的假设"
    assert listed[0].selection_run_id == newer.selection_run_id
    assert listed[0].candidate_count == 2
    assert listed[0].selection_status == "ready"


def test_list_recent_rejects_non_positive_limits() -> None:
    service = ResearchCaseQueryService(_Reader(), _Runs())

    with pytest.raises(AppQueryError) as error:
        service.list_recent(limit=0)
    assert error.value.details["reason"] == "invalid_research_case_limit"


def test_list_by_run_filters_to_one_selection_run() -> None:
    reader = _Reader()
    run_a_case = _case(reader)
    _case(
        reader,
        selection_run_id=f"selection-run:sha256:{_HASH_B}",
        selection_run_hash=_HASH_B,
        objective="另一个运行的用例",
    )
    service = ResearchCaseQueryService(
        reader,
        _Runs(run_a_case.selection_run_id, f"selection-run:sha256:{_HASH_B}"),
    )

    listed = service.list_by_run(run_a_case.selection_run_id, limit=10)

    assert [item.case_id for item in listed] == [run_a_case.case_id]


def test_list_by_run_fails_closed_for_an_unknown_run() -> None:
    reader = _Reader()
    service = ResearchCaseQueryService(reader, _Runs())

    with pytest.raises(AppQueryError) as error:
        service.list_by_run(f"selection-run:sha256:{_HASH_A}")
    assert error.value.details["reason"] == "selection_run_not_found"
