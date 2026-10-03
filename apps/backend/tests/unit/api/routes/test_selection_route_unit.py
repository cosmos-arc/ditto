"""Selection create/get/compare route contract tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.assemble_facts import (
    AssembleSelectionFacts,
    AssembleSelectionFactsRequest,
)
from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
)
from ditto_application.processes.selection.facade import (
    CreateSelectionRunRequest,
    IndustryRotationObservationDraft,
    SelectionFactorValueDraft,
    SelectionFactorWeightDraft,
    SelectionInstrumentDraft,
    SelectionWorkspaceFacade,
    StockSelectionSpecDraft,
)
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.selection_runs import SelectionRunQueryService
from ditto_apps.api.errors import UnprocessableEntityError
from ditto_apps.api.routes.selection import (
    _assembly_request,
    assemble_selection_run,
    compare_selection_runs,
    create_research_case,
    create_selection_run,
    get_industry_rotation,
    get_selection_run,
)
from ditto_apps.models.selection import (
    AssembleSelectionRunBody,
    CreateResearchCaseBody,
    SelectionFactorWeightRequest,
)
from ditto_apps.registry.research_case import AnalysisResearchCaseFactory
from ditto_kernel.identity import InstrumentId
from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.contracts import SelectionRun
from ditto_strategy.selection.pipeline import SelectionPipeline
from packages.application.tests.integration.snapshot_readiness_support import (
    ready_selection,
)

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


def _original[T](
    function: Callable[..., Awaitable[T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    return cast(
        Callable[..., Coroutine[Any, Any, T]],
        function.__dict__["__dishka_orig_func__"],
    )


def _assembly_body(*, seed: int = 17) -> AssembleSelectionRunBody:
    return AssembleSelectionRunBody(
        universe_id="a-share-main",
        as_of=_AS_OF,
        spec_id="stock-core",
        spec_version="1",
        top_k=1,
        min_average_turnover=20_000_000.0,
        min_listing_days=120,
        factor_weights=(SelectionFactorWeightRequest(name="momentum", weight=1.0),),
        seed=seed,
    )


def _history_request(*, seed: int = 17) -> CreateSelectionRunRequest:
    """One ETF-flavoured request the synthetic history pool can resolve."""
    return CreateSelectionRunRequest(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        rotation_source_snapshot_ids=("market-a",),
        market_context_feature_set_id=None,
        membership_version="sw-l1:2026-08-31",
        rotation_algorithm_version="industry-rotation-v1",
        industries=(
            IndustryRotationObservationDraft(
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
        selection_source_snapshot_ids=("market-a",),
        selection_spec=StockSelectionSpecDraft(
            spec_id="stock-core",
            spec_version="1",
            top_k=1,
            min_average_turnover=20_000_000.0,
            min_listing_days=120,
            factor_weights=(SelectionFactorWeightDraft("momentum", 1.0),),
        ),
        seed=seed,
        instruments=(
            SelectionInstrumentDraft(
                instrument_id=InstrumentId(600000),
                instrument_name="Pudong Bank",
                industry_id=None,
                factor_values=(SelectionFactorValueDraft("momentum", 0.7),),
                average_turnover=100_000_000.0,
                is_st=False,
                is_suspended=False,
                listing_days=5000,
                limit_state="normal",
                tracking_error=None,
            ),
        ),
    )


def _facade(store: _Store, readiness, history) -> SelectionWorkspaceFacade:
    return SelectionWorkspaceFacade(
        RunIndustryAndSecuritySelection(
            rotation_service=IndustryRotationService(),
            selection_pipeline=SelectionPipeline(),
            rotation_writer=store,
            run_writer=store,
        ),
        readiness=readiness,
        historical_universe=history,
    )


class _FakeAssembleProcess(AssembleSelectionFacts):
    """Record lifted requests and serve a fixed assembly result."""

    def __init__(
        self,
        assembler: Callable[[AssembleSelectionFactsRequest], CreateSelectionRunRequest],
    ) -> None:
        self._assembler = assembler
        self.requests: list[AssembleSelectionFactsRequest] = []

    def assemble(self, request: AssembleSelectionFactsRequest):
        self.requests.append(request)
        return self._assembler(request)


@pytest.fixture
def gate():
    with ready_selection(_history_request()) as (readiness, bound, history):
        yield readiness, bound, history


def test_create_handler_is_content_idempotent_and_preserves_evidence(gate) -> None:
    readiness, bound, history = gate
    store = _Store()
    handler = _original(create_selection_run)

    def assembler(request: AssembleSelectionFactsRequest):
        return bound

    process = _FakeAssembleProcess(assembler)

    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        first = asyncio.run(
            handler(
                body=_assembly_body(),
                process=process,
                facade=_facade(store, readiness, history),
            )
        )
        second = asyncio.run(
            handler(
                body=_assembly_body(),
                process=process,
                facade=_facade(store, readiness, history),
            )
        )

    assert first.data.selection_run.run_id == second.data.selection_run.run_id
    assert len(store.saved) == 1
    assert first.data.industry_rotation.rankings[0].industry_id == "801010"
    assert first.data.selection_run.candidates[0].instrument_id == InstrumentId(600000)


def test_client_fact_package_is_not_a_create_input(gate) -> None:
    """Only policy bodies reach create; fact packages are transport responses."""
    body_type = _assembly_body()
    fields = body_type.model_fields
    assert "instruments" not in fields
    assert "data_fields" not in fields
    assert "selection_source_snapshot_ids" not in fields


def test_get_and_compare_handlers_read_exact_saved_runs(gate) -> None:
    readiness, bound, history = gate
    store = _Store()
    facade = _facade(store, readiness, history)
    create_handler = _original(create_selection_run)

    def assembler(request: AssembleSelectionFactsRequest):
        return bound

    process = _FakeAssembleProcess(assembler)
    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        first_response = asyncio.run(
            create_handler(body=_assembly_body(), process=process, facade=facade)
        )
        from dataclasses import replace as _replace

        second_response = asyncio.run(
            create_handler(
                body=_assembly_body(seed=18),
                process=_FakeAssembleProcess(lambda request: _replace(bound, seed=18)),
                facade=facade,
            )
        )
        query = SelectionRunQueryService(store)
        get_handler = _original(get_selection_run)
        exact = asyncio.run(
            get_handler(
                query=query,
                run_id=first_response.data.selection_run.run_id,
            )
        )
        rotation_handler = _original(get_industry_rotation)
        exact_rotation = asyncio.run(
            rotation_handler(
                query=IndustryRotationQueryService(store),
                snapshot_id=first_response.data.industry_rotation.snapshot_id,
            )
        )
        compare_handler = _original(compare_selection_runs)
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


def test_create_research_case_handler_returns_exact_selection_lineage(
    gate,
) -> None:
    readiness, bound, history = gate
    store = _Store()
    facade = _facade(store, readiness, history)
    create_run_handler = _original(create_selection_run)
    create_case_handler = _original(create_research_case)
    process = _FakeAssembleProcess(lambda request: bound)

    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        run_response = asyncio.run(
            create_run_handler(body=_assembly_body(), process=process, facade=facade)
        )
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


def test_assembly_request_lifts_policy_fields() -> None:
    lifted = _assembly_request(_assembly_body())

    assert lifted.universe_id == "a-share-main"
    assert lifted.asset_kind == "stock"
    assert lifted.as_of == _AS_OF
    assert lifted.knowledge_cutoff is None
    assert lifted.publication_cutoff is None
    assert lifted.seed == 17
    assert lifted.lookback_days == 400
    assert lifted.factor_weights[0].name == "momentum"
    assert lifted.excluded_limit_states == ("limit_up", "limit_down")


def test_assemble_handler_round_trips_request_without_client_facts(gate) -> None:
    readiness, bound, history = gate
    assembled = bound

    process = _FakeAssembleProcess(lambda request: assembled)
    facade = _facade(_Store(), readiness, history)
    handler = _original(assemble_selection_run)

    with patch(
        "ditto_apps.api.routes.selection.asyncio.to_thread",
        side_effect=_inline_to_thread,
    ):
        response = asyncio.run(handler(body=_assembly_body(), process=process))
        receipt = asyncio.run(
            _original(create_selection_run)(
                body=_assembly_body(),
                process=_FakeAssembleProcess(lambda request: assembled),
                facade=facade,
            )
        )

    assert process.requests[0].universe_id == "a-share-main"
    assert response.data.request.universe_snapshot_id == assembled.universe_snapshot_id
    assert response.data.request.instruments[0].instrument_id == InstrumentId(600000)
    assert receipt.data.selection_run.candidates[0].instrument_id == InstrumentId(
        600000
    )


def test_assemble_handler_maps_process_errors(gate) -> None:
    def refuse(request: AssembleSelectionFactsRequest):
        raise AppProcessError(
            "backdated cutoffs cannot use the live read model",
            details={"reason": "ASSEMBLY_CUTOFF_BACKDATED"},
        )

    process = _FakeAssembleProcess(refuse)
    handler = _original(assemble_selection_run)

    with (
        patch(
            "ditto_apps.api.routes.selection.asyncio.to_thread",
            side_effect=_inline_to_thread,
        ),
        pytest.raises(UnprocessableEntityError) as error,
    ):
        asyncio.run(handler(body=_assembly_body(), process=process))

    assert error.value.error_code == "ASSEMBLY_CUTOFF_BACKDATED"
