"""Field admission against real immutable SQLite evidence ledgers."""

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.selection.facade import SelectionWorkspaceFacade
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldRequirement,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.storage.sqlite.industry_rotation_store import (
    SQLiteIndustryRotationStore,
)
from ditto_strategy.storage.sqlite.selection_run_store import SQLiteSelectionRunStore
from packages.application.tests.integration.field_admission_support import (
    certified_selection,
    field_evidence,
)

_DAY = date(2026, 9, 18)
_VISIBLE = datetime(2026, 9, 18, 9, tzinfo=UTC)


@pytest.fixture
def evidence():
    with field_evidence() as value:
        yield value


def test_requested_field_allows_then_revocation_blocks_without_deleting_history(
    evidence,
):
    query, request, reports, report = evidence
    before = reports.list_events(report.report_id)
    result = query.assess(request)
    assert result.allowed
    assert result.fields[0].license_record_id == report.evidence.license_record_ids[0]
    assert query.assess(request) == result
    assert reports.list_events(report.report_id) == before
    reports.revoke_report(
        report.report_id,
        revoked_by="human",
        revoked_at=_VISIBLE,
        reason="scope withdrawn",
    )
    assert not query.assess(request).allowed
    assert reports.get_report(report.report_id) == report


@pytest.mark.pit
def test_future_visibility_is_blocked_but_backfilled_creation_time_is_not_availability(
    evidence,
):
    query, request, _, _ = evidence
    early = replace(request, knowledge_cutoff=datetime(2026, 9, 18, 8, tzinfo=UTC))
    result = query.assess(early)
    assert not result.allowed
    assert "TIME_NOT_VISIBLE" in result.fields[0].reason_codes
    assert query.assess(request).allowed


def test_unused_unknown_field_does_not_block_and_scope_cannot_be_forged(evidence):
    query, request, _, _ = evidence
    unknown = FieldRequirement("stock_daily", "unknown", request.fields[0].snapshot_id)
    result = query.assess(replace(request, fields=(*request.fields, unknown)))
    assert not result.allowed
    assert result.fields[0].allowed_uses
    assert query.assess(request).allowed
    assert not query.assess(replace(request, instrument_ids=(600001,))).allowed
    assert not query.assess(
        replace(
            request,
            fields=(replace(request.fields[0], consumer_field="instruments.is_st"),),
        )
    ).allowed


def _gate_facade(query: FieldAdmissionQuery, history=None):
    """Real admission gate over isolated in-memory run stores."""
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
        admission=query,
        historical_universe=history,
    )
    return facade, runs, pool


def test_selection_cannot_save_a_run_without_complete_consumed_field_bindings(evidence):
    query, _, _, _ = evidence
    facade, runs, pool = _gate_facade(query)
    gated = replace(selection_request(), data_from=_DAY, data_to=_DAY)
    with pytest.raises(AppProcessError, match="准入"):
        facade.create(gated)
    assert runs.list_by_spec("admission-test") == []
    pool.close()


def test_request_without_data_binding_is_rejected(evidence):
    """Unreleased legacy requests must not bypass formal admission."""
    query, _, _, _ = evidence
    facade, runs, pool = _gate_facade(query)
    with pytest.raises(AppProcessError, match="准入"):
        facade.create(selection_request())
    assert runs.list_by_spec("admission-test") == []
    pool.close()


def test_admission_binds_each_stage_to_its_own_declared_sources():
    """A snapshot declared only for rotation cannot serve selection inputs."""
    with certified_selection(selection_request()) as (query, request, history):
        facade, _, pool = _gate_facade(query, history)
        report = facade.assess_admission(
            replace(request, selection_source_snapshot_ids=("unbound",))
        )
        pool.close()
    assert not report.allowed
    selection_field = next(
        item for item in report.fields if item.consumer_field.startswith("instruments.")
    )
    assert "SNAPSHOT_CONFLICT" in selection_field.reason_codes
    rotation_field = next(
        item for item in report.fields if item.consumer_field == "membership_version"
    )
    assert "SNAPSHOT_CONFLICT" not in rotation_field.reason_codes


def test_admission_rejects_stage_sources_no_binding_claims():
    """A declared source no consumed field claims cannot enter saved lineage."""
    with certified_selection(selection_request()) as (query, request, history):
        facade, _, pool = _gate_facade(query, history)
        report = facade.assess_admission(
            replace(
                request,
                rotation_source_snapshot_ids=(
                    *request.rotation_source_snapshot_ids,
                    "extra-source",
                ),
            )
        )
        pool.close()
    assert not report.allowed
    unclaimed = [
        item for item in report.fields if "SNAPSHOT_UNBOUND" in item.reason_codes
    ]
    assert [item.field for item in unclaimed] == ["extra-source"]


def test_admission_tracks_stage_usage_by_identity_not_shared_contents():
    """Identical declared sets must not merge the two stages' usage."""
    with certified_selection(selection_request()) as (query, request, history):
        certified = request.rotation_source_snapshot_ids[0]
        shared = (certified, "extra")
        facade, _, pool = _gate_facade(query, history)
        report = facade.assess_admission(
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
    assert not report.allowed
    unclaimed = {
        item.field for item in report.fields if "SNAPSHOT_UNBOUND" in item.reason_codes
    }
    assert unclaimed == {certified, "extra"}


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


@pytest.mark.parametrize(
    ("display", "compute", "purpose", "allowed"),
    [
        ("restricted", "allowed", "display", False),
        ("prohibited", "allowed", "exploration", False),
        ("allowed", "restricted", "display", True),
        ("allowed", "restricted", "formal_research", False),
    ],
)
def test_purposes_enforce_the_actual_license(display, compute, purpose, allowed):
    with field_evidence(display=display, compute=compute) as (query, request, _, _):
        result = query.assess(replace(request, purpose=purpose))
        assert result.allowed is allowed
        if not allowed:
            assert "LICENSE_RESTRICTED" in result.fields[0].reason_codes


def test_license_validity_is_use_time_not_historical_data_interval():
    historical = datetime(2015, 1, 5, 9, tzinfo=UTC)
    with field_evidence(day=historical.date(), visible=historical) as (
        query,
        request,
        _,
        _,
    ):
        assert query.assess(request).allowed
    with field_evidence(effective_to=_DAY) as (query, request, _, _):
        assert not query.assess(request).allowed
        assert (
            "LICENSE_INTERVAL_MISSING" in query.assess(request).fields[0].reason_codes
        )


@pytest.mark.integration
@pytest.mark.pit
def test_replay_gate_rejects_datasets_without_instrument_trade_date_identity():
    with field_evidence() as (admission, request, _, _):
        from types import SimpleNamespace

        from ditto_application.queries.provider_snapshot import (
            ProviderSnapshotQuery,
        )
        from ditto_data.catalog.snapshot_reader import SnapshotReadService

        query = ProviderSnapshotQuery(
            cast(SnapshotReadService, SimpleNamespace()), admission
        )
        mismatched = replace(
            request,
            fields=(FieldRequirement("macro_indicators", "amount", "snapshot:any"),),
        )

        with pytest.raises(AppQueryError, match="instrument- and trade-date-keyed"):
            query.replay(mismatched)

        assert admission.assess(request).allowed
