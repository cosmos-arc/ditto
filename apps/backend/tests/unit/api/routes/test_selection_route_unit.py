"""Selection create/get/compare route contract tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch

from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
)
from ditto_application.processes.selection.facade import SelectionWorkspaceFacade
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.selection_runs import SelectionRunQueryService
from ditto_apps.api.routes.selection import (
    compare_selection_runs,
    create_research_case,
    create_selection_run,
    get_industry_rotation,
    get_selection_run,
)
from ditto_apps.models.selection import (
    CreateResearchCaseBody,
    CreateSelectionRunBody,
    IndustryRotationObservationRequest,
    SelectionFactorValueRequest,
    SelectionFactorWeightRequest,
    SelectionInstrumentRequest,
    StockSelectionSpecRequest,
)
from ditto_apps.registry.research_case import AnalysisResearchCaseFactory
from ditto_kernel.identity import InstrumentId
from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.contracts import SelectionRun
from ditto_strategy.selection.pipeline import SelectionPipeline

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


class _Store:
    def __init__(self) -> None:
        self.saved: dict[str, SelectionRun] = {}
        self.saved_rotations: dict[str, IndustryRotationSnapshot] = {}

    def save(self, value: SelectionRun) -> None:
        self.saved.setdefault(value.run_id, value)

    def save_rotation(self, value: IndustryRotationSnapshot) -> None:
        self.saved_rotations.setdefault(value.snapshot_id, value)

    def get(self, run_id: str) -> SelectionRun | None:
        return self.saved.get(run_id)

    def get_rotation(self, snapshot_id: str) -> IndustryRotationSnapshot | None:
        return self.saved_rotations.get(snapshot_id)

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        return [item for item in self.saved.values() if item.spec_id == spec_id][:limit]


async def _inline_to_thread(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def _body(*, seed: int = 17) -> CreateSelectionRunBody:
    return CreateSelectionRunBody(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        rotation_source_snapshot_ids=("market-a",),
        market_context_feature_set_id="market-context:sha256:abc",
        membership_version="sw-l1:2026-08-31",
        rotation_algorithm_version="industry-rotation-v1",
        industries=(
            IndustryRotationObservationRequest(
                industry_id="801010",
                industry_name="Agriculture",
                relative_strength_5d=0.5,
                relative_strength_20d=0.5,
                relative_strength_60d=0.5,
                advancing_count=6,
                declining_count=4,
                member_count=10,
                trend_score=0.5,
                fundamental_score=0.5,
                regime_alignment_score=0.5,
            ),
        ),
        universe_snapshot_id="universe:sha256:abc",
        selection_source_snapshot_ids=("market-a", "fundamental-a"),
        selection_spec=StockSelectionSpecRequest(
            asset_kind="stock",
            spec_id="stock-core",
            spec_version="1",
            top_k=1,
            min_average_turnover=20_000_000.0,
            min_listing_days=120,
            factor_weights=(SelectionFactorWeightRequest(name="momentum", weight=1.0),),
        ),
        seed=seed,
        instruments=(
            SelectionInstrumentRequest(
                instrument_id=InstrumentId(600000),
                instrument_name="Pudong Bank",
                industry_id="801780",
                factor_values=(
                    SelectionFactorValueRequest(name="momentum", value=0.7),
                ),
                average_turnover=100_000_000.0,
                is_st=False,
                is_suspended=False,
                listing_days=5000,
                limit_state="normal",
            ),
        ),
    )


def _facade(store: _Store) -> SelectionWorkspaceFacade:
    return SelectionWorkspaceFacade(
        RunIndustryAndSecuritySelection(
            rotation_service=IndustryRotationService(),
            selection_pipeline=SelectionPipeline(),
            rotation_writer=store,
            run_writer=store,
        )
    )


def test_create_handler_is_content_idempotent_and_preserves_evidence() -> None:
    store = _Store()
    handler = cast(
        Callable[..., object], create_selection_run.__dict__["__dishka_orig_func__"]
    )

    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        first = asyncio.run(handler(body=_body(), facade=_facade(store)))
        second = asyncio.run(handler(body=_body(), facade=_facade(store)))

    assert first.data.selection_run.run_id == second.data.selection_run.run_id
    assert len(store.saved) == 1
    assert first.data.industry_rotation.rankings[0].industry_id == "801010"
    assert first.data.selection_run.candidates[0].instrument_id == InstrumentId(600000)


def test_get_and_compare_handlers_read_exact_saved_runs() -> None:
    store = _Store()
    facade = _facade(store)
    create_handler = cast(
        Callable[..., object],
        create_selection_run.__dict__["__dishka_orig_func__"],
    )
    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        first_response = asyncio.run(create_handler(body=_body(), facade=facade))
        second_response = asyncio.run(
            create_handler(body=_body(seed=18), facade=facade)
        )
        query = SelectionRunQueryService(store)
        get_handler = cast(
            Callable[..., object],
            get_selection_run.__dict__["__dishka_orig_func__"],
        )
        exact = asyncio.run(
            get_handler(
                query=query,
                run_id=first_response.data.selection_run.run_id,
            )
        )
        rotation_handler = cast(
            Callable[..., object],
            get_industry_rotation.__dict__["__dishka_orig_func__"],
        )
        exact_rotation = asyncio.run(
            rotation_handler(
                query=IndustryRotationQueryService(store),
                snapshot_id=first_response.data.industry_rotation.snapshot_id,
            )
        )
        compare_handler = cast(
            Callable[..., object],
            compare_selection_runs.__dict__["__dishka_orig_func__"],
        )
        compared = asyncio.run(
            compare_handler(
                query=query,
                before_run_id=first_response.data.selection_run.run_id,
                after_run_id=second_response.data.selection_run.run_id,
            )
        )

    assert exact.data == first_response.data.selection_run
    assert exact_rotation.data == first_response.data.industry_rotation
    assert compared.data.seed_changed is True


def test_create_research_case_handler_returns_exact_selection_lineage() -> None:
    store = _Store()
    facade = _facade(store)
    create_run_handler = cast(
        Callable[..., object],
        create_selection_run.__dict__["__dishka_orig_func__"],
    )
    create_case_handler = cast(
        Callable[..., object],
        create_research_case.__dict__["__dishka_orig_func__"],
    )

    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        run_response = asyncio.run(create_run_handler(body=_body(), facade=facade))
        case_response = asyncio.run(
            create_case_handler(
                run_id=run_response.data.selection_run.run_id,
                body=CreateResearchCaseBody(
                    objective="Validate this selection with walk-forward evidence.",
                    candidate_instrument_ids=(InstrumentId(600000),),
                ),
                process=CreateResearchCaseFromSelection(
                    store,
                    AnalysisResearchCaseFactory(),
                ),
            )
        )

    assert case_response.data.selection_run_id == run_response.data.selection_run.run_id
    assert case_response.data.case_id.startswith("research-case:sha256:")
    assert case_response.data.candidate_instrument_ids == (InstrumentId(600000),)


def test_research_case_request_accepts_json_candidate_array() -> None:
    """OpenAPI JSON arrays must validate under the strict HTTP contract."""
    body = CreateResearchCaseBody.model_validate(
        {
            "objective": "Evaluate the exact selected candidate.",
            "candidate_instrument_ids": [1_002_506],
        }
    )

    assert body.candidate_instrument_ids == (InstrumentId(1_002_506),)
