"""Snapshot readiness against real immutable SQLite evidence ledgers."""

from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.selection.facade import SelectionWorkspaceFacade
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.snapshot_readiness import FieldRequirement
from ditto_platform.foundation import SQLitePool
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.storage.sqlite.industry_rotation_store import (
    SQLiteIndustryRotationStore,
)
from ditto_strategy.storage.sqlite.selection_run_store import SQLiteSelectionRunStore
from packages.application.tests.integration.snapshot_readiness_support import (
    completed_evidence,
    ready_selection,
)

_DAY = date(2026, 9, 18)
_VISIBLE = datetime(2026, 9, 18, 9, tzinfo=UTC)


@pytest.mark.integration
def test_completed_snapshot_with_retained_payload_is_ready():
    with completed_evidence() as (query, request, _):
        result = query.assess(request)
        assert result.ready
        assert result.fields[0].reason_codes == ()
        assert query.assess(request) == result


@pytest.mark.integration
@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"complete": False}, "SNAPSHOT_INCOMPLETE"),
        ({"payload_retained": False}, "SNAPSHOT_PAYLOAD_MISSING"),
        (
            {"request_start": date(2026, 9, 17), "request_end": date(2026, 9, 17)},
            "SNAPSHOT_COVERAGE_MISSING",
        ),
    ],
)
def test_incomplete_evidence_blocks_consumption(kwargs, reason):
    with completed_evidence(**kwargs) as (query, request, _):
        result = query.assess(request)
        assert not result.ready
        assert result.fields[0].reason_codes == (reason,)


@pytest.mark.integration
def test_dataset_mismatch_and_missing_snapshot_fail_closed():
    with completed_evidence() as (query, request, _):
        mismatched = replace(
            request,
            fields=(replace(request.fields[0], dataset_id="stock_status"),),
        )
        assert query.assess(mismatched).fields[0].reason_codes == ("SNAPSHOT_CONFLICT",)
        absent = replace(
            request,
            fields=(replace(request.fields[0], snapshot_id="snapshot:none"),),
        )
        assert query.assess(absent).fields[0].reason_codes == ("SNAPSHOT_MISSING",)


def _gate_facade(query, history=None):
    """Real readiness gate over isolated in-memory run stores."""
    pool = SQLitePool(":memory:")
    runs = SQLiteSelectionRunStore(pool)
    rotations = SQLiteIndustryRotationStore(pool)
    runs.init_schema()
    rotations.init_schema()
    facade = SelectionWorkspaceFacade(
        RunIndustryAndSecuritySelection(
            rotation_service=IndustryRotationService(),
            selection_pipeline=SelectionPipeline(),
            rotation_writer=rotations,
            run_writer=runs,
        ),
        readiness=query,
        historical_universe=history,
    )
    return facade, runs, pool


def test_selection_cannot_save_a_run_without_complete_consumed_field_bindings():
    with completed_evidence() as (query, _, _):
        facade, runs, pool = _gate_facade(query)
        gated = replace(selection_request(), data_from=_DAY, data_to=_DAY)
        with pytest.raises(AppProcessError, match="数据不完整"):
            facade.create(gated)
        assert runs.list_by_spec("admission-test") == []
        pool.close()


def test_request_without_data_binding_is_rejected():
    """Requests without server-side bindings must not bypass the gate."""
    with completed_evidence() as (query, _, _):
        facade, runs, pool = _gate_facade(query)
        with pytest.raises(AppProcessError, match="数据不完整"):
            facade.create(selection_request())
        assert runs.list_by_spec("admission-test") == []
        pool.close()


def test_readiness_binds_each_stage_to_its_own_declared_sources():
    """A snapshot declared only for rotation cannot serve selection inputs."""
    with ready_selection(selection_request()) as (query, request, history):
        facade, _, pool = _gate_facade(query, history)
        report = facade.assess_data_readiness(
            replace(request, selection_source_snapshot_ids=("unbound",))
        )
        pool.close()
    assert not report.ready
    selection_field = next(
        item for item in report.fields if item.consumer_field.startswith("instruments.")
    )
    assert "SNAPSHOT_CONFLICT" in selection_field.reason_codes
    rotation_field = next(
        item for item in report.fields if item.consumer_field == "membership_version"
    )
    assert "SNAPSHOT_CONFLICT" not in rotation_field.reason_codes


def test_readiness_rejects_stage_sources_no_binding_claims():
    """A declared source no consumed field claims cannot enter saved lineage."""
    with ready_selection(selection_request()) as (query, request, history):
        facade, _, pool = _gate_facade(query, history)
        report = facade.assess_data_readiness(
            replace(
                request,
                rotation_source_snapshot_ids=(
                    *request.rotation_source_snapshot_ids,
                    "extra-source",
                ),
            )
        )
        pool.close()
    assert not report.ready
    unclaimed = [
        item for item in report.fields if "SNAPSHOT_UNBOUND" in item.reason_codes
    ]
    assert [item.field for item in unclaimed] == ["extra-source"]


def test_readiness_tracks_stage_usage_by_identity_not_shared_contents():
    """Identical declared sets must not merge the two stages' usage."""
    with ready_selection(selection_request()) as (query, request, history):
        completed = request.rotation_source_snapshot_ids[0]
        shared = (completed, "extra")
        facade, _, pool = _gate_facade(query, history)
        report = facade.assess_data_readiness(
            replace(
                request,
                rotation_source_snapshot_ids=shared,
                selection_source_snapshot_ids=shared,
                data_fields=tuple(
                    replace(item, snapshot_id="extra")
                    if item.consumer_field.startswith("instruments.")
                    or item.consumer_field == "universe_snapshot_id"
                    else item
                    for item in request.data_fields
                ),
            )
        )
        pool.close()
    assert not report.ready
    unclaimed = {
        item.field for item in report.fields if "SNAPSHOT_UNBOUND" in item.reason_codes
    }
    assert unclaimed == {completed, "extra"}


def selection_request():
    from ditto_application.processes.selection.facade import (
        CreateSelectionRunRequest,
        IndustryRotationObservationDraft,
        SelectionFactorValueDraft,
        SelectionFactorWeightDraft,
        SelectionInstrumentDraft,
        StockSelectionSpecDraft,
    )
    from ditto_kernel.identity import InstrumentId

    return CreateSelectionRunRequest(
        as_of=_VISIBLE,
        knowledge_cutoff=_VISIBLE,
        publication_cutoff=_VISIBLE,
        rotation_source_snapshot_ids=("unverified",),
        market_context_feature_set_id=None,
        membership_version="test-v1",
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
        universe_snapshot_id="unverified",
        selection_source_snapshot_ids=("unverified",),
        selection_spec=StockSelectionSpecDraft(
            spec_id="admission-test",
            spec_version="1",
            top_k=1,
            min_average_turnover=0,
            min_listing_days=1,
            factor_weights=(SelectionFactorWeightDraft("liquidity", 1),),
        ),
        seed=1,
        instruments=(
            SelectionInstrumentDraft(
                instrument_id=InstrumentId(600000),
                instrument_name="Synthetic",
                industry_id=None,
                factor_values=(SelectionFactorValueDraft("liquidity", 1),),
                average_turnover=100,
                is_st=False,
                is_suspended=False,
                listing_days=100,
                limit_state="normal",
                tracking_error=None,
            ),
        ),
    )


@pytest.mark.integration
@pytest.mark.pit
def test_replay_gate_rejects_datasets_without_instrument_trade_date_identity():
    with completed_evidence() as (readiness, request, _):
        from ditto_application.queries.provider_snapshot import (
            ProviderSnapshotQuery,
            SnapshotReplayRequest,
        )
        from ditto_data.catalog.snapshot_reader import SnapshotReadService

        query = ProviderSnapshotQuery(
            cast(SnapshotReadService, SimpleNamespace()), readiness
        )
        mismatched = SnapshotReplayRequest(
            fields=(FieldRequirement("macro_indicators", "amount", "snapshot:any"),),
            instrument_ids=(1,),
            required_from=request.required_from,
            required_to=request.required_to,
            knowledge_cutoff=_VISIBLE,
        )

        with pytest.raises(AppQueryError, match="instrument- and trade-date-keyed"):
            query.replay(mismatched)

        assert readiness.assess(request).ready
