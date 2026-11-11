"""SelectionRun to Research Case lineage orchestration."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest
from ditto_analysis.research.cases import ResearchCase
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
    CreateResearchCaseRequest,
)
from ditto_application.research_case_contracts import (
    ResearchCaseMaterial,
    ResearchCaseView,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.selection.contracts import (
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRun,
    SelectionRunStatus,
    StockSelectionSpec,
)
from ditto_strategy.selection.pipeline import SelectionPipeline


class _Reader:
    def __init__(self, run: SelectionRun | None) -> None:
        self._run = run

    def get(self, run_id: str) -> SelectionRun | None:
        if self._run is not None and self._run.run_id == run_id:
            return self._run
        return None

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        del spec_id, limit
        return []


class _Factory:
    def create(self, material: ResearchCaseMaterial) -> ResearchCaseView:
        return ResearchCase(**asdict(material))


class _Recorder:
    def __init__(self) -> None:
        self.saved: list[ResearchCaseView] = []

    def save(self, case: ResearchCaseView) -> None:
        self.saved.append(case)


def _run() -> SelectionRun:
    from datetime import UTC, datetime

    as_of = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)
    return SelectionPipeline().run(
        SelectionInputBundle(
            as_of=as_of,
            knowledge_cutoff=as_of,
            publication_cutoff=as_of,
            universe_snapshot_id="universe:sha256:abc",
            industry_rotation_snapshot_id="industry-rotation:sha256:def",
            source_snapshot_ids=("market-a", "fundamental-a"),
            spec=StockSelectionSpec(
                spec_id="stock-core",
                spec_version="1",
                top_k=2,
                min_average_turnover=20_000_000.0,
                min_listing_days=120,
                factor_weights=(SelectionFactorWeight("momentum", 1.0),),
            ),
            seed=17,
            instruments=tuple(
                SelectionInstrumentInput(
                    instrument_id=instrument_id,
                    instrument_name=f"Instrument {instrument_id}",
                    industry_id="801010",
                    factor_values=(SelectionFactorValue("momentum", score),),
                    average_turnover=100_000_000.0,
                    is_st=False,
                    is_suspended=False,
                    listing_days=500,
                    limit_state=SelectionLimitState.NORMAL,
                    tracking_error=None,
                )
                for instrument_id, score in (
                    (InstrumentId(600001), 1.0),
                    (InstrumentId(600002), 0.5),
                    (InstrumentId(600003), 0.1),
                )
            ),
        )
    )


def test_create_research_case_preserves_exact_selection_lineage() -> None:
    run = _run()
    process = CreateResearchCaseFromSelection(_Reader(run), _Factory(), _Recorder())

    case = process.create(
        CreateResearchCaseRequest(
            selection_run_id=run.run_id,
            objective="Validate the selected leaders with walk-forward evidence.",
            candidate_instrument_ids=tuple(
                reversed(tuple(item.instrument_id for item in run.candidates))
            ),
        )
    )

    assert case.selection_run_id == run.run_id
    assert case.selection_input_hash == run.input_hash
    assert case.selection_spec_hash == run.spec_hash
    assert case.candidate_instrument_ids == tuple(
        item.instrument_id for item in run.candidates
    )
    assert case.source_snapshot_ids == run.source_snapshot_ids
    assert case.knowledge_cutoff == run.knowledge_cutoff


def test_create_research_case_persists_the_handed_off_case() -> None:
    run = _run()
    recorder = _Recorder()
    process = CreateResearchCaseFromSelection(_Reader(run), _Factory(), recorder)

    case = process.create(
        CreateResearchCaseRequest(run.run_id, "Persist the hypothesis for research.")
    )

    # 交接是持久的：创建即在 append-only 存储落一条内容寻址用例，
    # 之后的读取不依赖创建时所在的页面或会话。
    assert [item.case_id for item in recorder.saved] == [case.case_id]


def test_create_research_case_replay_re_saves_the_same_identity() -> None:
    run = _run()
    recorder = _Recorder()
    process = CreateResearchCaseFromSelection(_Reader(run), _Factory(), recorder)

    first = process.create(
        CreateResearchCaseRequest(run.run_id, "One replayable case.")
    )
    second = process.create(
        CreateResearchCaseRequest(run.run_id, "One replayable case.")
    )

    assert first.case_id == second.case_id
    assert [item.case_id for item in recorder.saved] == [first.case_id, second.case_id]


def test_create_research_case_allows_live_lane_knowledge_after_as_of() -> None:
    # #583：活体日频车道 knowledge 晚于 as_of 的已保存运行可建 ResearchCase——
    # 因果序只保留 publication ≤ knowledge，重放车道由上游钉死。
    from datetime import timedelta

    run = replace(_run(), knowledge_cutoff=_run().as_of + timedelta(days=1))
    process = CreateResearchCaseFromSelection(_Reader(run), _Factory(), _Recorder())

    case = process.create(
        CreateResearchCaseRequest(run.run_id, "Live-lane case with current knowledge.")
    )

    assert case.knowledge_cutoff > case.as_of


def test_create_research_case_fails_closed_for_missing_blocked_or_excluded_input() -> (
    None
):
    run = _run()
    recorder = _Recorder()
    process = CreateResearchCaseFromSelection(_Reader(run), _Factory(), recorder)
    missing = CreateResearchCaseFromSelection(_Reader(None), _Factory(), _Recorder())

    with pytest.raises(AppProcessError) as missing_error:
        missing.create(CreateResearchCaseRequest(run.run_id, "Test one hypothesis."))
    assert missing_error.value.details["reason"] == "selection_run_not_found"

    blocked_run = replace(
        run,
        status=SelectionRunStatus.BLOCKED,
        candidates=(),
        missing_inputs=("bars",),
    )
    with pytest.raises(AppProcessError) as blocked_error:
        CreateResearchCaseFromSelection(
            _Reader(blocked_run), _Factory(), _Recorder()
        ).create(CreateResearchCaseRequest(blocked_run.run_id, "Test one hypothesis."))
    assert blocked_error.value.details["reason"] == "selection_run_blocked"

    with pytest.raises(AppProcessError) as candidate_error:
        process.create(
            CreateResearchCaseRequest(
                run.run_id,
                "Test one hypothesis.",
                (InstrumentId(999999),),
            )
        )
    assert candidate_error.value.details["reason"] == "research_case_candidate_invalid"
    # 失败路径不落任何持久化用例：读取面不会看到失败的交接。
    assert recorder.saved == []
