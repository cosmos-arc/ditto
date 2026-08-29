"""Campaign HTTP, SSE, idempotency, and crash-recovery integration contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never, cast

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_analysis.errors import ExperimentPersistenceError
from ditto_analysis.experiments.campaign_persistence import CampaignReaderProtocol
from ditto_analysis.experiments.models import ExperimentId
from ditto_analysis.experiments.persistence import LeaseFence
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteCampaignReader,
    SQLiteCampaignWriter,
)
from ditto_application.agent_campaign_contracts import (
    CampaignCandidateProposalCommand,
)
from ditto_application.agent_campaign_runtime import (
    CampaignApproveCommand,
    CampaignCreateCommand,
    CampaignInvalidRequest,
    CampaignRuntimePort,
    CampaignRuntimeUnavailable,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    decode_campaign_detail,
)
from ditto_application.processes.experiments.autonomous_campaign import (
    AutonomousCampaignCoordinator,
    CampaignScheduledTrial,
    CampaignTrialRetryRequest,
    CampaignTrialScheduleRequest,
    CampaignTrialSchedulerPort,
)
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.agent_routes import router
from ditto_apps.middleware import api_error_handler
from ditto_apps.registry.agent.campaign_runtime import PersistedCampaignRuntime
from ditto_apps.registry.agent.database_provider import (
    AgentDatabaseBundle,
    build_agent_database,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

NOW = datetime(2026, 8, 16, 6, tzinfo=UTC)


def _manifest_document(
    *,
    objective: str = "Improve an ETF timing signal.",
    candidate_limit: int = 8,
) -> dict[str, object]:
    return {
        "campaign_id": "campaign-api",
        "objective": objective,
        "primary_metric_id": "sharpe_ratio",
        "hypothesis": {
            "statement": "Short-term reversal persists after costs.",
            "mechanism": "Liquidity provision earns a reversal premium.",
            "universe_hash": "c" * 64,
            "expected_signal": "Validation Sharpe improves.",
            "failure_condition": "Validation Sharpe does not improve.",
        },
        "baseline_candidate": {
            "candidate_id": "candidate-baseline",
            "ordinal": 1,
            "parameters": {"lookback": 20},
            "factor_code_hash": "a" * 64,
            "model_code_hash": None,
            "data_requirement_hashes": ["b" * 64],
        },
        "experiment_plan": {
            "fold_protocol_id": "walk-forward-v1",
            "fold_protocol_version": 1,
            "fold_protocol_hash": "d" * 64,
            "snapshot_id": "snapshot-2026-08-12",
            "validation_objective_hash": "e" * 64,
            "cost_model_hash": "f" * 64,
            "seed": 42,
            "purge_sessions": 5,
            "embargo_sessions": 2,
        },
        "budget": {
            "candidate_limit": candidate_limit,
            "fold_run_limit": 16,
            "generation_limit": 6,
            "concurrent_sandbox_limit": 2,
            "wall_time_limit_seconds": 14_400,
            "temporary_storage_limit_bytes": 20 * 1024**3,
            "model_spend_limit_usd_micros": 8_000_000,
            "sandbox_resource_limits": {
                "cpu_count": 2,
                "memory_bytes": 4 * 1024**3,
                "process_limit": 64,
                "temporary_storage_bytes": 1024**3,
                "wall_time_seconds": 600,
                "output_bytes": 10 * 1024**2,
            },
        },
        "search_axis": "factor_code",
        "search_space_hash": "1" * 64,
        "lineage_root": "2" * 64,
        "stopping_rule": "Stop after two completed generations without improvement.",
        "allowed_tools": ["campaign_propose_candidate"],
        "prohibited_actions": [
            "holdout.evaluate",
            "strategy.publish",
            "broker.submit_order",
        ],
    }


def _assert_initial_campaign_projection(
    data: dict[str, object], objective: object
) -> None:
    assert data["objective"] == objective
    assert data["event_cursor"] == 1
    assert data["projection_version"] == 1
    assert data["projection_state"] == "partial"
    assert data["projection_reason"] == "campaign_result_projection_unavailable"
    assert data["tool_records"] == []
    assert data["evidence_refs"] == []
    assert data["artifact_refs"] == []


def _validation_requests(document: dict[str, object]) -> tuple[dict[str, object], ...]:
    return (
        {
            "step": "hypothesis",
            "campaign_id": document["campaign_id"],
            "objective": document["objective"],
            "primary_metric_id": document["primary_metric_id"],
            "hypothesis": document["hypothesis"],
        },
        {
            "step": "experiment_plan",
            "search_axis": document["search_axis"],
            "baseline_candidate": document["baseline_candidate"],
            "experiment_plan": document["experiment_plan"],
        },
        {
            "step": "governance",
            "budget": document["budget"],
            "search_space_hash": document["search_space_hash"],
            "lineage_root": document["lineage_root"],
            "stopping_rule": document["stopping_rule"],
            "allowed_tools": document["allowed_tools"],
            "prohibited_actions": document["prohibited_actions"],
        },
        {"step": "manifest", "manifest": document},
    )


class _Scheduler(CampaignTrialSchedulerPort):
    def __init__(self) -> None:
        self.cancel_calls = 0
        self.schedule_calls = 0
        self.lost = False

    @staticmethod
    def _lease(campaign_id: ExperimentId, now_epoch_us: int) -> LeaseFence:
        return LeaseFence(
            experiment_id=campaign_id,
            owner_token="campaign-api-test",
            revision=1,
            lease_until_epoch_us=now_epoch_us + 60_000_000,
        )

    def required_fold_run_count(self, campaign_id: ExperimentId) -> int:
        return 2

    def schedule_trial(
        self,
        request: CampaignTrialScheduleRequest,
        *,
        now_epoch_us: int,
    ) -> CampaignScheduledTrial:
        self.schedule_calls += 1
        if self.lost:
            raise AppProcessError(
                "Campaign lease was lost",
                details={"code": "LEASE_LOST", "reason": "campaign_lease_lost"},
            )
        return CampaignScheduledTrial(
            lease=self._lease(request.campaign_id, now_epoch_us),
            fold_run_count=2,
        )

    def schedule_retry(
        self,
        request: CampaignTrialRetryRequest,
        *,
        now_epoch_us: int,
    ) -> LeaseFence:
        return self._lease(request.campaign_id, now_epoch_us)

    def cancel_campaign(
        self,
        campaign_id: ExperimentId,
        *,
        now_epoch_us: int,
    ) -> None:
        self.cancel_calls += 1


class _CrashOnFirstCompletion:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._crashed = False

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def complete_idempotency(self, **kwargs: object) -> object:
        if not self._crashed:
            self._crashed = True
            raise AgentPersistenceError(
                "simulated completion crash",
                reason_code="simulated_completion_crash",
            )
        return self._delegate.complete_idempotency(**kwargs)


class _FailingCampaignReader:
    @staticmethod
    def _fail() -> Never:
        raise ExperimentPersistenceError(
            "simulated Campaign read failure",
            details={"reason_code": "campaign_test_read_failed"},
        )

    def get_campaign(self, campaign_id: ExperimentId) -> Never:
        self._fail()

    def list_campaign_events(self, campaign_id: ExperimentId) -> Never:
        self._fail()


def _runtime(
    tmp_path: Path,
    *,
    idempotency_writer: object | None = None,
) -> tuple[
    PersistedCampaignRuntime,
    AutonomousCampaignCoordinator,
    _Scheduler,
    AgentDatabaseBundle,
    ResearchExperimentDatabase,
]:
    agent_bundle = build_agent_database(tmp_path)
    research_database = ResearchExperimentDatabase(tmp_path)
    research_database.initialize()
    reader = SQLiteCampaignReader(research_database)
    scheduler = _Scheduler()
    coordinator = AutonomousCampaignCoordinator(
        reader=reader,
        writer=SQLiteCampaignWriter(research_database),
        scheduler=scheduler,
    )
    runtime = PersistedCampaignRuntime(
        coordinator=coordinator,
        reader=reader,
        idempotency_reader=agent_bundle.reader,
        idempotency_writer=idempotency_writer or agent_bundle.writer,
        clock=lambda: NOW,
    )
    return runtime, coordinator, scheduler, agent_bundle, research_database


def _http_app(runtime: CampaignRuntimePort) -> tuple[FastAPI, AsyncContainer]:
    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def campaign_runtime(self) -> CampaignRuntimePort:
            return runtime

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(APIError, api_error_handler)
    return app, container


@pytest.mark.asyncio
async def test_campaign_validation_is_stepwise_canonical_and_has_no_write_side_effect(
    tmp_path: Path,
) -> None:
    runtime, _coordinator, _scheduler, agent_bundle, _research_database = _runtime(
        tmp_path
    )
    app, container = _http_app(runtime)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            document = _manifest_document()
            responses = [
                await client.post(
                    "/api/v1/agent/campaigns/validation",
                    json=request,
                )
                for request in _validation_requests(document)
            ]

            assert [response.status_code for response in responses] == [
                200,
                200,
                200,
                200,
            ]
            assert [response.json()["data"]["step"] for response in responses] == [
                "hypothesis",
                "experiment_plan",
                "governance",
                "manifest",
            ]
            assert all(response.json()["data"]["valid"] for response in responses)
            assert all(
                response.json()["data"]["canonical_manifest"] is None
                for response in responses[:3]
            )
            final = responses[-1].json()["data"]
            assert final["canonical_manifest"]["schema_id"] == (
                "r5-research-campaign-manifest"
            )
            assert len(final["manifest_hash"]) == 64

            history = await client.get("/api/v1/agent/campaigns")
            assert history.status_code == 200
            assert history.json()["data"] == []
            assert history.json()["pagination"]["total"] == 0

            invalid = _validation_requests(document)[2] | {
                "allowed_tools": [
                    "campaign_propose_candidate",
                    "campaign_propose_candidate",
                ]
            }
            rejected = await client.post(
                "/api/v1/agent/campaigns/validation",
                json=invalid,
            )
            assert rejected.status_code == 422
            assert rejected.json()["error_code"] == "CAMPAIGN_MANIFEST_INVALID"
    finally:
        await container.close()
        agent_bundle.close()


@pytest.mark.asyncio
async def test_campaign_lifecycle_is_idempotent_and_sse_resumes_from_store(
    tmp_path: Path,
) -> None:
    runtime, _coordinator, scheduler, agent_bundle, research_database = _runtime(
        tmp_path
    )
    app, container = _http_app(runtime)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            document = _manifest_document()
            created = await client.post(
                "/api/v1/agent/campaigns",
                json={"manifest": document},
                headers={"Idempotency-Key": "campaign-create-1"},
            )
            replay = await client.post(
                "/api/v1/agent/campaigns",
                json={"manifest": document},
                headers={"Idempotency-Key": "campaign-create-1"},
            )
            drift = await client.post(
                "/api/v1/agent/campaigns",
                json={"manifest": _manifest_document(objective="Drifted objective")},
                headers={"Idempotency-Key": "campaign-create-1"},
            )

            assert created.status_code == replay.status_code == 201
            assert created.json() == replay.json()
            assert created.json()["data"]["status"] == "draft"
            _assert_initial_campaign_projection(
                created.json()["data"], document["objective"]
            )
            assert drift.status_code == 409

            draft = created.json()["data"]
            assert draft["canonical_manifest"]["campaign_id"] == document["campaign_id"]
            assert draft["canonical_manifest"]["objective"] == document["objective"]
            assert (
                draft["canonical_manifest"]["schema_id"]
                == "r5-research-campaign-manifest"
            )
            approved = await client.post(
                "/api/v1/agent/campaigns/campaign-api/approve",
                json={
                    "expected_manifest_hash": draft["manifest_hash"],
                    "operator_id": "operator-api",
                    "expires_at": (NOW + timedelta(hours=4)).isoformat(),
                },
                headers={"Idempotency-Key": "campaign-approve-1"},
            )
            assert approved.status_code == 200, approved.text
            authority = approved.json()["data"]
            assert authority["status"] == "authorized"
            assert authority["manifest_hash"] == draft["manifest_hash"]
            assert authority["authorization_hash"] is not None
            assert authority["budget"]["candidate_limit"] == 8
            assert authority["budget"]["fold_run_limit"] == 16
            assert authority["event_cursor"] == 2
            assert authority["projection_version"] == 2
            assert authority["projection_updated_at"] is not None

            resumed = await client.get(
                "/api/v1/agent/campaigns/campaign-api/events",
                headers={"Last-Event-ID": "1"},
            )
            assert resumed.status_code == 200
            assert resumed.headers["content-type"].startswith("text/event-stream")
            assert resumed.content.count(b"event: campaign_authorized\n") == 1
            assert b"event: campaign_created\n" not in resumed.content

            shown = await client.get("/api/v1/agent/campaigns/campaign-api")
            assert shown.json()["data"] == authority

            cancel_body = {
                "expected_authorization_hash": authority["authorization_hash"]
            }
            cancelled = await client.post(
                "/api/v1/agent/campaigns/campaign-api/cancel",
                json=cancel_body,
                headers={"Idempotency-Key": "campaign-cancel-1"},
            )
            cancel_replay = await client.post(
                "/api/v1/agent/campaigns/campaign-api/cancel",
                json=cancel_body,
                headers={"Idempotency-Key": "campaign-cancel-1"},
            )
            assert cancelled.status_code == cancel_replay.status_code == 200
            assert cancelled.json() == cancel_replay.json()
            assert cancelled.json()["data"]["status"] == "cancelled"
            assert scheduler.cancel_calls == 1
    finally:
        await container.close()
        agent_bundle.close()
        research_database.close_all()


def test_pending_create_recovers_after_completion_crash_without_duplicate_event(
    tmp_path: Path,
) -> None:
    agent_bundle = build_agent_database(tmp_path)
    crashing_writer = _CrashOnFirstCompletion(agent_bundle.writer)
    research_database = ResearchExperimentDatabase(tmp_path)
    research_database.initialize()
    reader = SQLiteCampaignReader(research_database)
    scheduler = _Scheduler()
    coordinator = AutonomousCampaignCoordinator(
        reader=reader,
        writer=SQLiteCampaignWriter(research_database),
        scheduler=scheduler,
    )
    crashing = PersistedCampaignRuntime(
        coordinator=coordinator,
        reader=reader,
        idempotency_reader=agent_bundle.reader,
        idempotency_writer=crashing_writer,
        clock=lambda: NOW,
    )
    command = CampaignCreateCommand(
        manifest_document=_manifest_document(),
        idempotency_key="campaign-create-crash",
    )
    try:
        with pytest.raises(CampaignRuntimeUnavailable) as failure:
            crashing.create_campaign(command)
        assert failure.value.reason_code == "simulated_completion_crash"

        restarted = PersistedCampaignRuntime(
            coordinator=coordinator,
            reader=reader,
            idempotency_reader=agent_bundle.reader,
            idempotency_writer=agent_bundle.writer,
            clock=lambda: NOW + timedelta(seconds=1),
        )
        recovered = restarted.create_campaign(command)

        assert recovered.status == "draft"
        assert tuple(
            event.event_type
            for event in reader.list_campaign_events(ExperimentId("campaign-api"))
        ) == ("campaign_created",)
    finally:
        agent_bundle.close()
        research_database.close_all()


def test_public_runtime_translates_approval_and_event_read_failures(
    tmp_path: Path,
) -> None:
    _persisted, coordinator, _scheduler, agent_bundle, research_database = _runtime(
        tmp_path
    )
    failing = PersistedCampaignRuntime(
        coordinator=coordinator,
        reader=cast(CampaignReaderProtocol, _FailingCampaignReader()),
        idempotency_reader=agent_bundle.reader,
        idempotency_writer=agent_bundle.writer,
        clock=lambda: NOW,
    )
    try:
        with pytest.raises(CampaignRuntimeUnavailable) as approval_failure:
            failing.approve_campaign(
                CampaignApproveCommand(
                    campaign_id="campaign-api",
                    expected_manifest_hash="a" * 64,
                    operator_id="operator-runtime",
                    expires_at=NOW + timedelta(hours=1),
                    idempotency_key="campaign-failing-approval",
                )
            )
        assert approval_failure.value.reason_code == "campaign_test_read_failed"

        with pytest.raises(CampaignRuntimeUnavailable) as event_failure:
            failing.list_campaign_events("campaign-api")
        assert event_failure.value.reason_code == "campaign_test_read_failed"
    finally:
        agent_bundle.close()
        research_database.close_all()


def test_expired_pending_approval_cannot_create_new_authority_after_restart(
    tmp_path: Path,
) -> None:
    runtime, _coordinator, _scheduler, agent_bundle, research_database = _runtime(
        tmp_path
    )
    command = CampaignApproveCommand(
        campaign_id="campaign-api",
        expected_manifest_hash=runtime.create_campaign(
            CampaignCreateCommand(
                manifest_document=_manifest_document(),
                idempotency_key="campaign-create-expiry",
            )
        ).manifest_hash,
        operator_id="operator-expiry",
        expires_at=NOW + timedelta(seconds=1),
        idempotency_key="campaign-approve-expiry",
    )
    agent_bundle.writer.reserve_idempotency(
        scope="agent.campaign.approve",
        idempotency_key=command.idempotency_key,
        request_hash=command.request_hash,
        occurred_at=NOW,
    )
    restarted = PersistedCampaignRuntime(
        coordinator=_coordinator,
        reader=SQLiteCampaignReader(research_database),
        idempotency_reader=agent_bundle.reader,
        idempotency_writer=agent_bundle.writer,
        clock=lambda: NOW + timedelta(seconds=2),
    )
    try:
        with pytest.raises(CampaignInvalidRequest) as expired:
            restarted.approve_campaign(command)
        assert expired.value.reason_code == "campaign_approval_expired"
        assert restarted.get_campaign("campaign-api").status == "draft"
    finally:
        agent_bundle.close()
        research_database.close_all()


def test_persisted_approval_event_recovers_completion_after_expiry(
    tmp_path: Path,
) -> None:
    runtime, coordinator, _scheduler, agent_bundle, research_database = _runtime(
        tmp_path
    )
    draft = runtime.create_campaign(
        CampaignCreateCommand(
            manifest_document=_manifest_document(),
            idempotency_key="campaign-create-approval-crash",
        )
    )
    command = CampaignApproveCommand(
        campaign_id=draft.campaign_id,
        expected_manifest_hash=draft.manifest_hash,
        operator_id="operator-approval-crash",
        expires_at=NOW + timedelta(seconds=1),
        idempotency_key="campaign-approve-crash",
    )
    crashing = PersistedCampaignRuntime(
        coordinator=coordinator,
        reader=SQLiteCampaignReader(research_database),
        idempotency_reader=agent_bundle.reader,
        idempotency_writer=_CrashOnFirstCompletion(agent_bundle.writer),
        clock=lambda: NOW,
    )
    try:
        with pytest.raises(CampaignRuntimeUnavailable):
            crashing.approve_campaign(command)

        restarted = PersistedCampaignRuntime(
            coordinator=coordinator,
            reader=SQLiteCampaignReader(research_database),
            idempotency_reader=agent_bundle.reader,
            idempotency_writer=agent_bundle.writer,
            clock=lambda: NOW + timedelta(seconds=2),
        )
        recovered = restarted.approve_campaign(command)

        assert recovered.status == "authorized"
        assert tuple(
            event.event_type
            for event in SQLiteCampaignReader(research_database).list_campaign_events(
                ExperimentId("campaign-api")
            )
            if event.event_type == "campaign_authorized"
        ) == ("campaign_authorized",)
    finally:
        agent_bundle.close()
        research_database.close_all()


def _authorize_runtime(
    runtime: PersistedCampaignRuntime,
    document: dict[str, object],
) -> tuple[str, str, str]:
    draft = runtime.create_campaign(
        CampaignCreateCommand(
            manifest_document=document,
            idempotency_key="campaign-create-runtime",
        )
    )
    approved = runtime.approve_campaign(
        CampaignApproveCommand(
            campaign_id=draft.campaign_id,
            expected_manifest_hash=draft.manifest_hash,
            operator_id="operator-runtime",
            expires_at=NOW + timedelta(hours=4),
            idempotency_key="campaign-approve-runtime",
        )
    )
    assert approved.authorization_hash is not None
    return approved.campaign_id, approved.authorization_hash, draft.manifest_hash


def _proposal(
    reader: SQLiteCampaignReader,
    *,
    lookback: int,
) -> CampaignCandidateProposalCommand:
    authorization = next(
        event
        for event in reader.list_campaign_events(ExperimentId("campaign-api"))
        if event.event_type == "campaign_authorized"
    )
    detail = decode_campaign_detail(authorization.detail_payload)
    proof = detail["proof"]
    assert isinstance(proof, dict)
    return CampaignCandidateProposalCommand(
        campaign_id="campaign-api",
        authorization_id=str(proof["authorization_id"]),
        authorization_hash=str(proof["authorization_hash"]),
        authority_hash=str(proof["authority_hash"]),
        run_id="run-campaign-api",
        episode_id="episode-run-campaign-api",
        call_id=f"call-campaign-api-{lookback}",
        parent_candidate_id="candidate-baseline",
        parameters={"lookback": lookback},
        factor_code_hash="5" * 64,
        model_code_hash=None,
        data_requirement_hashes=("6" * 64,),
    )


def test_lease_recovery_and_budget_pause_are_visible_without_double_trial(
    tmp_path: Path,
) -> None:
    runtime, coordinator, scheduler, agent_bundle, research_database = _runtime(
        tmp_path
    )
    reader = SQLiteCampaignReader(research_database)
    try:
        _authorize_runtime(runtime, _manifest_document(candidate_limit=2))
        proposal = _proposal(reader, lookback=10)
        scheduler.lost = True
        with pytest.raises(AppProcessError) as lost:
            coordinator.propose_candidate(
                proposal,
                occurred_at=NOW + timedelta(seconds=1),
            )
        assert lost.value.details["reason"] == "campaign_lease_lost"
        assert runtime.get_campaign("campaign-api").status == "paused"

        scheduler.lost = False
        coordinator.propose_candidate(
            proposal,
            occurred_at=NOW + timedelta(seconds=2),
        )
        recovered = runtime.get_campaign("campaign-api")
        assert recovered.status == "running"
        assert recovered.statistical_trial_count == 1
        assert recovered.operational_attempt_count == 1

        coordinator.propose_candidate(
            proposal,
            occurred_at=NOW + timedelta(seconds=3),
        )
        assert runtime.get_campaign("campaign-api").statistical_trial_count == 1
        with pytest.raises(AppProcessError) as exhausted:
            coordinator.propose_candidate(
                _proposal(reader, lookback=11),
                occurred_at=NOW + timedelta(seconds=4),
            )
        assert exhausted.value.details["reason"] == (
            "campaign_candidate_budget_exhausted"
        )
        paused = runtime.get_campaign("campaign-api")
        assert paused.status == "paused_budget"
        assert paused.statistical_trial_count == 1
        assert scheduler.schedule_calls == 2
        assert any(
            event.event_type == "campaign_paused_budget"
            for event in runtime.list_campaign_events("campaign-api")
        )
    finally:
        agent_bundle.close()
        research_database.close_all()
