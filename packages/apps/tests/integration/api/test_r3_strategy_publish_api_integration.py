"""HTTP acceptance for evidence-gated R3 strategy publication.

The fixture owns both SQLite databases and the indexed artifact root under
``tmp_path``.  It deliberately leaves the R2 live gate unevaluated, proving
that the public HTTP route drives the real reader, command handler, promotion
process, and governance state without mutating production-facing state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Never

import httpx
import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_analysis.experiments import (
    ContentHash,
    ExperimentId,
    encode_launch_spec,
)
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SCHEMA_VERSION_V1,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_analysis.experiments.gates import (
    HARD_GATE_RULE_IDS,
    GateEvaluation,
    GateFact,
    GateLayer,
    GateOutcome,
    HardGateEvidence,
    evaluate_hard_gates,
)
from ditto_analysis.experiments.persistence import LeaseFence
from ditto_analysis.research._indexed_artifacts import IndexedArtifactIO
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_application.commands.strategy_governance import (
    PublishStrategyVersionHandler,
    SubmitReviewHandler,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.strategy.promotion import StrategyPromotionProcess
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.strategy import router
from ditto_apps.middleware import api_error_handler
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
    StrategyGovernanceCasConflict,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)
from fastapi import FastAPI
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_NOW = datetime(2026, 7, 28, 4, 0, tzinfo=UTC)
_NOW_US = int(_NOW.timestamp() * 1_000_000)


@pytest.fixture(autouse=True)
def _inline_strategy_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the HTTP boundary real while avoiding the test runner's thread portal."""

    async def run_inline(
        func: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(func)
        return func(*args, **kwargs)

    monkeypatch.setattr("ditto_apps.api.routes.strategy.run_blocking", run_inline)


@dataclass(slots=True)
class _PublishHarness:
    client: httpx.AsyncClient
    container: AsyncContainer
    research_database: ResearchExperimentDatabase
    governance_pool: SQLitePool
    governance_store: SQLiteStrategyGovernanceStore
    catalog: StrategyCatalogService
    publish_handler: PublishStrategyVersionHandler
    submit_handler: SubmitReviewHandler
    packet: ReviewPacket
    strategy_id: str
    candidate_version: int

    async def close(self) -> None:
        """Release every test-owned connection and DI scope."""
        await self.client.aclose()
        await self.container.close()
        self.research_database.close_all()
        self.governance_pool.close_all()


def _strategy_record(
    *,
    strategy_id: str,
    version: int,
    parent_version: int | None,
    created_at: str,
) -> StrategySpecRecord:
    seed = SEED_STRATEGY_SPECS[strategy_id]
    base = StrategySpecRecord(
        strategy_id=strategy_id,
        name=seed.name,
        spec_json=asdict(seed),
        version=version,
        parent_version=parent_version,
        created_at=created_at,
        tags=seed.tags,
    )
    return replace(base, spec_hash=canonical_spec_hash_for_record(base))


def _deterministic_packet(
    *,
    experiment_id: ExperimentId,
    candidate_id: str,
    launch_spec_hash: ContentHash,
    r2_live_gate: bool | None = None,
    soft_failure: bool = False,
) -> ReviewPacket:
    hard_gates = evaluate_hard_gates(
        HardGateEvidence(
            certified_snapshot=GateFact(True, {"fixture": "tmp_path"}),
            ninety_six_month=GateFact(True, {"months": 96}),
            pit_known_at=GateFact(True, {"verified": True}),
            split_purge_embargo=GateFact(True, {"verified": True}),
            reproduction=GateFact(True, {"verified": True}),
            cost_assumptions=GateFact(True, {"verified": True}),
            baseline_declared=GateFact(True, {"verified": True}),
            trial_declaration=GateFact(True, {"verified": True}),
            holdout_claim=GateFact(True, {"verified": True}),
            artifact_completeness=GateFact(True, {"verified": True}),
            r2_live_gate=GateFact(r2_live_gate, {"source": "deterministic_fixture"}),
        )
    )
    assert tuple(gate.rule_id for gate in hard_gates) == HARD_GATE_RULE_IDS
    expected_r2_outcome = {
        True: GateOutcome.PASS,
        False: GateOutcome.FAIL,
        None: GateOutcome.NOT_EVALUATED,
    }[r2_live_gate]
    assert hard_gates[-1].outcome is expected_r2_outcome
    evaluations = hard_gates
    if soft_failure:
        evaluations += (
            GateEvaluation(
                rule_id="preferred_sharpe",
                layer=GateLayer.EVIDENCE,
                outcome=GateOutcome.FAIL,
                observed=0.8,
                policy={"preferred_minimum": 1.0},
            ),
        )
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id=str(experiment_id),
            candidate_id=candidate_id,
            fold_ids=("wf-fold-1",),
            attempt_ids=("wf-attempt-1",),
        ),
        spec_hash=launch_spec_hash,
        resolved_spec_hash=ContentHash("1" * 64),
        parameter_hash=ContentHash("2" * 64),
        snapshot_hash=ContentHash("3" * 64),
        registry_hash=ContentHash("4" * 64),
        objective_payload_hash=ContentHash("5" * 64),
        gate_evaluations=evaluations,
        comparison_payload_hash=ContentHash("6" * 64),
        r1_impact_payload_hash=ContentHash("7" * 64),
        selection_evidence_artifact_id="selection-evidence-http-acceptance",
        holdout_claim_id="holdout-claim-http-acceptance",
        candidate_rationale="Deterministic HTTP acceptance candidate.",
    )


def _build_harness(
    tmp_path: Path,
    *,
    drift_launch_identity: bool = False,
    legacy_packet: bool = False,
    r2_live_gate: bool | None = None,
    soft_failure: bool = False,
    prepare_candidate_review: bool = True,
) -> _PublishHarness:
    lane = golden_support.ETF_GOLDEN_LANE
    research_database = ResearchExperimentDatabase(tmp_path / "research-data")
    research_database.initialize()
    research_reader = SQLiteExperimentReader(research_database)
    research_writer = SQLiteExperimentWriter(research_database)
    planning = ExperimentPlanningProcess(
        reader=research_reader,
        writer=research_writer,
        certification_probe=golden_support.PlanningCertificationProbe(lane),
        executor_probe=golden_support.PlanningExecutorProbe(lane),
        authority_probe=golden_support.PlanningAuthorityProbe(lane),
    )
    planning_request = golden_support.build_planning_request(lane)
    preflight = planning.preflight(planning_request)
    assert preflight.plan_hash is not None
    planning.launch(planning_request, confirmed_plan_hash=preflight.plan_hash)
    launch = research_reader.get_launch_spec(ExperimentId(lane.experiment_id))
    assert launch is not None
    candidate = next(item for item in launch.candidates if not item.is_baseline)
    launch_spec_hash = (
        ContentHash("0" * 64)
        if drift_launch_identity
        else encode_launch_spec(launch).content_hash
    )
    packet = _deterministic_packet(
        experiment_id=launch.experiment_id,
        candidate_id=str(candidate.candidate_id),
        launch_spec_hash=launch_spec_hash,
        r2_live_gate=r2_live_gate,
        soft_failure=soft_failure,
    )
    if legacy_packet:
        packet = replace(
            packet,
            schema_version=REVIEW_PACKET_SCHEMA_VERSION_V1,
        )
    fence = LeaseFence(
        experiment_id=launch.experiment_id,
        owner_token="http-acceptance",
        revision=0,
        lease_until_epoch_us=_NOW_US - 1,
    )
    if legacy_packet:
        bundle_hash = packet.bundle_hash
        IndexedArtifactIO(
            artifact_root=research_database.artifact_root,
            reader=research_reader,
            writer=research_writer,
        ).publish_json(
            ArtifactPublicationSpec(
                artifact_id=f"review-packet-{bundle_hash}",
                experiment_id=launch.experiment_id,
                candidate_id=None,
                fold_id=None,
                attempt_id=None,
                artifact_kind="review_packet",
                relative_path=(
                    f"experiments/{launch.experiment_id}/review-packet.json"
                ),
                reproduction_fingerprint=bundle_hash,
                audit={"created_at": _NOW.isoformat()},
                created_at=_NOW,
            ),
            packet.canonical_payload(),
            lease_fence=fence,
            now_epoch_us=_NOW_US,
        )
    else:
        research_writer.publish_review_packet(
            packet,
            lease_fence=fence,
            now_epoch_us=_NOW_US,
            created_at=_NOW,
        )
    assert research_reader.get_review_packet(str(packet.bundle_hash)) == packet

    governance_pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    spec_writer = SQLiteStrategySpecWriter(governance_pool)
    spec_writer.init_schema()
    governance_store = SQLiteStrategyGovernanceStore(governance_pool)
    governance_store.init_schema()
    governance = GovernanceService(governance_store)
    active_record = _strategy_record(
        strategy_id=lane.strategy_id,
        version=1,
        parent_version=None,
        created_at="2026-07-28T00:00:00Z",
    )
    candidate_record = _strategy_record(
        strategy_id=lane.strategy_id,
        version=lane.strategy_version,
        parent_version=1,
        created_at="2026-07-28T00:00:10Z",
    )
    assert launch.strategy_spec_hash == ContentHash(candidate_record.spec_hash)
    governance.create_draft(
        strategy_id=lane.strategy_id,
        version=1,
        spec_record=active_record,
        created_at=active_record.created_at,
    )
    governance.publish_and_activate(
        strategy_id=lane.strategy_id,
        version=1,
        actor="http-acceptance-bootstrap",
        reason="existing R1 active strategy",
        decided_at="2026-07-28T00:00:01Z",
    )
    governance.create_draft(
        strategy_id=lane.strategy_id,
        version=lane.strategy_version,
        spec_record=candidate_record,
        created_at=candidate_record.created_at,
    )
    if prepare_candidate_review:
        governance.submit_review(
            lane.strategy_id,
            lane.strategy_version,
            event_id="http-acceptance:candidate:submit",
            actor="http-acceptance-reviewer",
            reason="submit deterministic candidate",
            decided_at="2026-07-28T00:00:11Z",
        )
        governance.approve(
            lane.strategy_id,
            lane.strategy_version,
            event_id="http-acceptance:candidate:approve",
            actor="http-acceptance-reviewer",
            reason="approved except live gate",
            decided_at="2026-07-28T00:00:12Z",
        )

    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(governance_pool),
        writer=spec_writer,
        active_pointer_reader=governance_store,
    )
    publish_handler = PublishStrategyVersionHandler(
        process=StrategyPromotionProcess(governance),
        reader=research_reader,
    )
    submit_handler = SubmitReviewHandler(governance, research_reader)

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def publish_strategy_version_handler(self) -> PublishStrategyVersionHandler:
            return publish_handler

        @provide
        def submit_review_handler(self) -> SubmitReviewHandler:
            return submit_handler

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(APIError, api_error_handler)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    return _PublishHarness(
        client=client,
        container=container,
        research_database=research_database,
        governance_pool=governance_pool,
        governance_store=governance_store,
        catalog=catalog,
        publish_handler=publish_handler,
        submit_handler=submit_handler,
        packet=packet,
        strategy_id=lane.strategy_id,
        candidate_version=lane.strategy_version,
    )


async def _submit_review(
    harness: _PublishHarness,
    *,
    bundle_hash: str,
    idempotency_key: str,
) -> httpx.Response:
    return await harness.client.post(
        (
            f"/api/v1/strategies/{harness.strategy_id}/versions/"
            f"{harness.candidate_version}/submit-review"
        ),
        headers={"Idempotency-Key": idempotency_key},
        json={
            "bundle_hash": bundle_hash,
            "actor": "http-acceptance-reviewer",
            "reason": "submit persisted candidate evidence",
        },
    )


@pytest.mark.parametrize("r2_live_gate", [False, None], ids=["fail", "not_evaluated"])
async def test_http_submit_review_blocks_nonpassing_hard_gate_without_writes(
    tmp_path: Path,
    r2_live_gate: bool | None,
) -> None:
    harness = _build_harness(
        tmp_path,
        r2_live_gate=r2_live_gate,
        prepare_candidate_review=False,
    )
    try:
        state_before = harness.governance_store.get_state(
            harness.strategy_id, harness.candidate_version
        )
        history_before = _governance_history(
            harness.governance_pool, harness.strategy_id
        )

        response = await _submit_review(
            harness,
            bundle_hash=str(harness.packet.bundle_hash),
            idempotency_key=f"submit-hard-{r2_live_gate}",
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "HARD_GATE_FAILED"
        assert (
            harness.governance_store.get_state(
                harness.strategy_id, harness.candidate_version
            )
            == state_before
        )
        assert (
            _governance_history(harness.governance_pool, harness.strategy_id)
            == history_before
        )
    finally:
        await harness.close()


@pytest.mark.parametrize(
    ("bundle_hash", "drift", "expected_code"),
    [
        ("f" * 64, False, "REVIEW_PACKET_NOT_FOUND"),
        (None, True, "EVIDENCE_STALE"),
    ],
    ids=["packet_missing", "target_drift"],
)
async def test_http_submit_review_rejects_missing_or_stale_evidence_zero_write(
    tmp_path: Path,
    bundle_hash: str | None,
    drift: bool,
    expected_code: str,
) -> None:
    harness = _build_harness(
        tmp_path,
        drift_launch_identity=drift,
        r2_live_gate=True,
        prepare_candidate_review=False,
    )
    try:
        state_before = harness.governance_store.get_state(
            harness.strategy_id, harness.candidate_version
        )
        history_before = _governance_history(
            harness.governance_pool, harness.strategy_id
        )
        response = await _submit_review(
            harness,
            bundle_hash=(
                str(harness.packet.bundle_hash) if bundle_hash is None else bundle_hash
            ),
            idempotency_key=f"submit-evidence-{expected_code}",
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == expected_code
        assert (
            harness.governance_store.get_state(
                harness.strategy_id, harness.candidate_version
            )
            == state_before
        )
        assert (
            _governance_history(harness.governance_pool, harness.strategy_id)
            == history_before
        )
    finally:
        await harness.close()


async def test_http_submit_review_allows_soft_metric_failure_and_replays_exactly(
    tmp_path: Path,
) -> None:
    harness = _build_harness(
        tmp_path,
        r2_live_gate=True,
        soft_failure=True,
        prepare_candidate_review=False,
    )
    try:
        bundle_hash = str(harness.packet.bundle_hash)
        first = await _submit_review(
            harness, bundle_hash=bundle_hash, idempotency_key="submit-pass"
        )
        history_after_first = _governance_history(
            harness.governance_pool, harness.strategy_id
        )
        replay = await _submit_review(
            harness, bundle_hash=bundle_hash, idempotency_key="submit-pass"
        )

        assert first.status_code == 200
        assert replay.status_code == first.status_code
        assert replay.json() == first.json()
        assert (
            _governance_history(harness.governance_pool, harness.strategy_id)
            == history_after_first
        )
        state = harness.governance_store.get_state(
            harness.strategy_id, harness.candidate_version
        )
        assert state is not None
        assert state.state.value == "review"

        reused = await _submit_review(
            harness, bundle_hash="e" * 64, idempotency_key="submit-pass"
        )
        assert reused.status_code == 409
        assert reused.json()["error_code"] == "IDEMPOTENCY_KEY_REUSED"
    finally:
        await harness.close()


def _governance_history(
    pool: SQLitePool,
    strategy_id: str,
) -> tuple[tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]:
    connection = pool.get_connection()
    decisions = connection.execute(
        "SELECT event_id, version, decision, actor, reason, decided_at "
        "FROM strategy_decision_event WHERE strategy_id = ? ORDER BY rowid",
        (strategy_id,),
    ).fetchall()
    activations = connection.execute(
        "SELECT event_id, target_version, activation_kind, actor, reason, "
        "activated_at FROM strategy_activation_event "
        "WHERE strategy_id = ? ORDER BY rowid",
        (strategy_id,),
    ).fetchall()
    return (
        tuple(tuple(row) for row in decisions),
        tuple(tuple(row) for row in activations),
    )


async def _assert_typed_zero_write_rejection(
    harness: _PublishHarness,
    *,
    expected_status: int,
    expected_error_code: str,
) -> None:
    pointer_before = harness.governance_store.get_active_pointer(harness.strategy_id)
    candidate_before = harness.governance_store.get_state(
        harness.strategy_id,
        harness.candidate_version,
    )
    active_before = harness.catalog.get_active_published(harness.strategy_id)
    history_before = _governance_history(
        harness.governance_pool,
        harness.strategy_id,
    )
    assert pointer_before is not None
    assert pointer_before.active_version == 1
    assert candidate_before is not None
    assert candidate_before.state.value == "review"
    assert candidate_before.review_outcome.value == "approved"
    assert active_before is not None
    assert active_before.version == 1

    response = await harness.client.post(
        (
            f"/api/v1/strategies/{harness.strategy_id}/versions/"
            f"{harness.candidate_version}/publish"
        ),
        headers={
            "Idempotency-Key": (
                f"publish-zero-write-{expected_status}-{expected_error_code}"
            )
        },
        json={
            "bundle_hash": str(harness.packet.bundle_hash),
            "actor": "http-acceptance-publisher",
            "reason": "attempt evidence-gated publication",
        },
    )

    assert response.status_code == expected_status
    payload = response.json()
    assert payload["status_code"] == expected_status
    assert payload["error_code"] == expected_error_code
    assert (
        harness.governance_store.get_active_pointer(harness.strategy_id)
        == pointer_before
    )
    assert (
        harness.governance_store.get_state(
            harness.strategy_id,
            harness.candidate_version,
        )
        == candidate_before
    )
    assert harness.catalog.get_active_published(harness.strategy_id) == active_before
    assert (
        _governance_history(harness.governance_pool, harness.strategy_id)
        == history_before
    )


async def test_http_publish_blocks_persisted_packet_when_r2_live_gate_is_unevaluated(
    tmp_path: Path,
) -> None:
    """A deterministic persisted packet reaches promotion and fails closed."""
    harness = _build_harness(tmp_path)
    try:
        await _assert_typed_zero_write_rejection(
            harness,
            expected_status=422,
            expected_error_code="hard_gate_blocked",
        )
    finally:
        await harness.close()


async def test_http_publish_rejects_packet_launch_identity_drift_without_writes(
    tmp_path: Path,
) -> None:
    """Packet/launch identity drift is typed 422 before governance mutation."""
    harness = _build_harness(tmp_path, drift_launch_identity=True)
    try:
        await _assert_typed_zero_write_rejection(
            harness,
            expected_status=422,
            expected_error_code="evidence_target_mismatch",
        )
    finally:
        await harness.close()


async def test_http_publish_rejects_legacy_v1_packet_without_writes(
    tmp_path: Path,
) -> None:
    """Persisted v1 remains readable but is ineligible for new promotion."""
    harness = _build_harness(tmp_path, legacy_packet=True)
    try:
        await _assert_typed_zero_write_rejection(
            harness,
            expected_status=422,
            expected_error_code="review_packet_schema_unsupported",
        )
    finally:
        await harness.close()


async def test_http_publish_maps_atomic_pointer_conflict_to_typed_409(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A promotion CAS miss is a stable 409 without forging live gate evidence."""
    harness = _build_harness(tmp_path)

    def raise_concurrent_conflict(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        raise StrategyGovernanceCasConflict("active pointer revision changed")

    monkeypatch.setattr(
        harness.publish_handler._process,
        "promote",
        raise_concurrent_conflict,
    )
    try:
        await _assert_typed_zero_write_rejection(
            harness,
            expected_status=409,
            expected_error_code="STRATEGY_REVISION_CONFLICT",
        )
    finally:
        await harness.close()
