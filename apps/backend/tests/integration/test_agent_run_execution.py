"""Persisted Apps composition for one bounded read-only Agent execution."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.fake import ScriptedFailure, ScriptedOutcome
from ditto_agent.models.port import (
    AgentModelPort,
    ModelFailureKind,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelToolCall,
    ModelToolInvoker,
    ModelUsage,
    ResumeModelRequest,
)
from ditto_agent.presentation import AgentPresentationError
from ditto_agent.runtime.service import (
    AgentProjectionState,
    AgentRequestConflict,
    AgentRunCreateCommand,
    AgentRunExecuteCommand,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
)
from ditto_agent.tools._common import application_context, seal_research_evidence
from ditto_agent.tools.registry import EvidenceToolRegistry
from ditto_agent.tools.research import ExperimentEvidenceTool
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    ResearchEvidenceKind,
    ResearchEvidenceQueryPort,
    ResearchEvidenceReadModel,
)
from ditto_apps.registry.agent.database_provider import (
    AgentDatabaseBundle,
    build_agent_database,
)
from ditto_apps.registry.agent.model_provider import (
    AgentModelProviderSettings,
    build_agent_model,
)
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)

NOW = datetime(2026, 8, 30, 8, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
TOOL_NAME = "research_experiment_evidence"


class _Facade:
    def __init__(self, result: ResearchEvidenceReadModel) -> None:
        self._result = result
        self.contexts: list[EvidenceTemporalContext] = []

    def get_experiment_evidence(
        self,
        *,
        experiment_id: str,
        context: EvidenceTemporalContext,
        candidate_id: str | None = None,
        fold_id: str | None = None,
    ) -> ResearchEvidenceReadModel:
        del experiment_id, candidate_id, fold_id
        self.contexts.append(context)
        return self._result


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=NOW,
            knowledge_cutoff=datetime(2026, 8, 30, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 30, 6, tzinfo=UTC),
            source_snapshot_id="snapshot-certified-2026-08-29",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _read_model(context: TemporalToolContext) -> ResearchEvidenceReadModel:
    return ResearchEvidenceReadModel(
        kind=ResearchEvidenceKind.EXPERIMENT,
        subject_id="experiment-beta",
        subject_version="1",
        strategy_id="strategy-beta",
        strategy_version="1",
        dataset_id="etf-daily-certified",
        temporal_context=application_context(context),
        payload=EvidencePayloadReadModel.seal(
            schema_version=1,
            value={"status": "completed", "visible_metric": 0.73},
        ),
        artifact_refs=(
            EvidenceArtifactReference(
                artifact_id="artifact-beta",
                artifact_kind="experiment_report",
                content_hash=HASH_A,
                schema_hash=HASH_B,
            ),
        ),
        lineage=(
            "experiment:experiment-beta",
            "snapshot:snapshot-certified-2026-08-29",
        ),
    )


def _schema_hash(registry: EvidenceToolRegistry) -> str:
    return canonical_sha256(
        tuple(
            {
                "kind": spec.kind,
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "requires_approval": spec.requires_approval,
            }
            for spec in registry.specs
        )
    )


def _runtime_with_model(
    tmp_path: Path,
    model_factory: Callable[[ModelToolInvoker], AgentModelPort],
    *,
    approved_license_classes: tuple[str, ...] = ("approved-research",),
) -> tuple[PersistedAgentRuntime, AgentDatabaseBundle]:
    context = _context()
    facade = _Facade(_read_model(context))
    registry = EvidenceToolRegistry(
        tools=(
            ExperimentEvidenceTool(
                facade=cast(ResearchEvidenceQueryPort, facade),
            ),
        )
    )
    manifest = AgentManifest(
        manifest_id="beta-recovery",
        agent_version="r5.1",
        prompt_version="evidence-v1",
        prompt_hash=HASH_B,
        tool_schema_version="read-only-v1",
        tool_schema_hash=_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="recovery-test-v1",
    )
    bundle = build_agent_database(tmp_path)
    bundle.writer.put_manifest(manifest)
    return (
        PersistedAgentRuntime(
            reader=bundle.reader,
            writer=bundle.writer,
            manifest=manifest,
            clock=lambda: NOW,
            options=PersistedAgentRuntimeOptions(
                presentation_reader=bundle.presentation_reader,
                presentation_writer=bundle.presentation_writer,
                presentation_projector=bundle.presentation_projector,
                episode_writer=bundle.episode_writer,
                tool_registry=registry,
                model_factory=model_factory,
                approved_license_classes=approved_license_classes,
            ),
        ),
        bundle,
    )


@pytest.mark.asyncio
async def test_unapproved_license_fails_closed_before_evidence_reaches_model(
    tmp_path: Path,
) -> None:
    context = _context()
    expected = seal_research_evidence(
        tool_name=TOOL_NAME,
        expected_kind=ResearchEvidenceKind.EXPERIMENT.value,
        read_model=_read_model(context),
        context=context,
    )
    result = ModelResult(
        final_output={
            "claims": [
                {
                    "claim": "The publication-visible metric is 0.73.",
                    "evidence_refs": [expected.evidence_id],
                }
            ],
            "uncertainty": "Bound to the certified snapshot.",
        },
        tool_calls=(
            ModelToolCall(
                call_id="call-unapproved-license",
                tool_name=TOOL_NAME,
                arguments={
                    "experiment_id": "experiment-beta",
                    "candidate_id": None,
                    "fold_id": None,
                },
            ),
        ),
        usage=ModelUsage(requests=2, input_tokens=120, output_tokens=40),
        interruptions=(),
        continuation=None,
    )
    runtime, bundle = _runtime_with_model(
        tmp_path,
        lambda invoker: build_agent_model(
            AgentModelProviderSettings(),
            script=(ScriptedOutcome(result=result),),
            tool_invoker=invoker,
        ),
        approved_license_classes=(),
    )
    queued = _queue_run(runtime, key="unapproved-license")

    failed = await runtime.execute_run(
        AgentRunExecuteCommand(
            run_id=queued.run_id,
            expected_revision=queued.revision,
        )
    )

    assert failed.status is RunStatus.FAILED
    assert failed.failure_code == "evidence_license_not_approved"
    assert failed.evidence_refs == ()
    bundle.close()


def _queue_run(runtime: PersistedAgentRuntime, *, key: str) -> AgentRunView:
    session = runtime.create_session(
        AgentSessionCreateCommand(
            retention_class=RetentionClass.AUDIT,
            idempotency_key=f"{key}-session",
        )
    )
    plan = AgentRunExecutionPlan(
        temporal_context=_context(),
        allowed_tools=(TOOL_NAME,),
        max_output_tokens=256,
    )
    return runtime.create_run(
        AgentRunCreateCommand(
            session_id=session.session_id,
            objective="Explain experiment-beta without future publications.",
            authority_hash=plan.authority_hash,
            max_model_tokens=1_000,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key=f"{key}-run",
            execution_plan=plan,
        )
    )


class _CancelledModel:
    async def run(self, request: ModelRequest) -> ModelResult:
        del request
        raise asyncio.CancelledError

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        del request
        if False:
            yield cast(ModelStreamEvent, None)  # pragma: no cover
        raise AssertionError("cancelled execution must not stream")

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        del request
        raise AssertionError("cancelled execution must not resume")


class _BlockingFailureModel:
    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, request: ModelRequest) -> ModelResult:
        del request
        self.calls += 1
        self.started.set()
        await self.release.wait()
        raise ModelProviderError("provider unavailable")

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        del request
        if False:
            yield cast(ModelStreamEvent, None)  # pragma: no cover
        raise AssertionError("blocking execution must not stream")

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        del request
        raise AssertionError("blocking execution must not resume")


@pytest.mark.asyncio
@pytest.mark.pit
async def test_execute_queued_run_persists_grounded_projection_and_episode(
    tmp_path: Path,
) -> None:
    context = _context()
    read_model = _read_model(context)
    facade = _Facade(read_model)
    registry = EvidenceToolRegistry(
        tools=(
            ExperimentEvidenceTool(
                facade=cast(ResearchEvidenceQueryPort, facade),
            ),
        )
    )
    manifest = AgentManifest(
        manifest_id="beta-execution",
        agent_version="r5.1",
        prompt_version="evidence-v1",
        prompt_hash=HASH_B,
        tool_schema_version="read-only-v1",
        tool_schema_hash=_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-v1",
    )
    expected = seal_research_evidence(
        tool_name=TOOL_NAME,
        expected_kind=ResearchEvidenceKind.EXPERIMENT.value,
        read_model=read_model,
        context=context,
    )
    result = ModelResult(
        final_output={
            "claims": [
                {
                    "claim": "The publication-visible metric is 0.73.",
                    "evidence_refs": [expected.evidence_id],
                }
            ],
            "uncertainty": "Bound to the certified snapshot.",
        },
        tool_calls=(
            ModelToolCall(
                call_id="call-beta",
                tool_name=TOOL_NAME,
                arguments={
                    "experiment_id": "experiment-beta",
                    "candidate_id": None,
                    "fold_id": None,
                },
            ),
        ),
        usage=ModelUsage(requests=2, input_tokens=120, output_tokens=40),
        interruptions=(),
        continuation=None,
    )
    bundle = build_agent_database(tmp_path)
    bundle.writer.put_manifest(manifest)
    runtime = PersistedAgentRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        manifest=manifest,
        clock=lambda: NOW,
        options=PersistedAgentRuntimeOptions(
            presentation_reader=bundle.presentation_reader,
            presentation_writer=bundle.presentation_writer,
            presentation_projector=bundle.presentation_projector,
            episode_writer=bundle.episode_writer,
            tool_registry=registry,
            model_factory=lambda invoker: build_agent_model(
                AgentModelProviderSettings(),
                script=(ScriptedOutcome(result=result),),
                tool_invoker=invoker,
            ),
            approved_license_classes=("approved-research",),
        ),
    )
    session = runtime.create_session(
        AgentSessionCreateCommand(
            retention_class=RetentionClass.AUDIT,
            idempotency_key="beta-session",
        )
    )
    plan = AgentRunExecutionPlan(
        temporal_context=context,
        allowed_tools=(TOOL_NAME,),
        max_output_tokens=256,
    )
    queued = runtime.create_run(
        AgentRunCreateCommand(
            session_id=session.session_id,
            objective="Explain experiment-beta without future publications.",
            authority_hash=plan.authority_hash,
            max_model_tokens=1_000,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key="beta-run",
            execution_plan=plan,
        )
    )

    completed = await runtime.execute_run(
        AgentRunExecuteCommand(
            run_id=queued.run_id,
            expected_revision=queued.revision,
        )
    )

    assert completed.status is RunStatus.COMPLETED
    assert completed.revision == 2
    assert completed.output_summary == "The publication-visible metric is 0.73."
    assert completed.evidence_refs == (expected.evidence_id,)
    assert completed.execution_plan == plan
    assert facade.contexts == [application_context(context)]
    events = bundle.reader.list_run_events(completed.run_id)
    assert tuple(item.event_type for item in events) == (
        "run_queued",
        "run_started",
        "provider_attempt",
        "tool_call",
        "tool_result",
        "run_completed",
    )
    episode = bundle.episode_reader.get(f"episode-{completed.run_id}")
    assert episode is not None
    assert episode.final_status is RunStatus.COMPLETED
    assert tuple(item.event_hash for item in episode.events) == tuple(
        item.event_hash for item in events
    )
    assert "future_sentinel" not in cast(
        Mapping[str, object],
        read_model.payload.value,
    )
    bundle.close()


@pytest.mark.asyncio
async def test_provider_failure_seals_failed_run_for_operator_recovery(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime_with_model(
        tmp_path,
        lambda invoker: build_agent_model(
            AgentModelProviderSettings(),
            script=(
                ScriptedFailure(
                    kind=ModelFailureKind.PROVIDER,
                    message="provider unavailable",
                ),
            ),
            tool_invoker=invoker,
        ),
    )
    queued = _queue_run(runtime, key="provider-failure")

    failed = await runtime.execute_run(
        AgentRunExecuteCommand(
            run_id=queued.run_id,
            expected_revision=queued.revision,
        )
    )

    assert failed.status is RunStatus.FAILED
    assert failed.failure_code == "model_provider_failed"
    assert tuple(
        event.event_type for event in bundle.reader.list_run_events(failed.run_id)
    ) == ("run_queued", "run_started", "provider_attempt", "run_failed")
    episode = bundle.episode_reader.get(f"episode-{failed.run_id}")
    assert episode is not None
    assert episode.final_status is RunStatus.FAILED
    bundle.close()


@pytest.mark.asyncio
async def test_process_interruption_before_commit_leaves_run_queued_and_retryable(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime_with_model(
        tmp_path,
        lambda _invoker: _CancelledModel(),
    )
    queued = _queue_run(runtime, key="interrupted")

    with pytest.raises(asyncio.CancelledError):
        await runtime.execute_run(
            AgentRunExecuteCommand(
                run_id=queued.run_id,
                expected_revision=queued.revision,
            )
        )

    recovered = runtime.get_run(queued.run_id)
    assert recovered.status is RunStatus.QUEUED
    assert recovered.revision == queued.revision
    assert tuple(
        event.event_type for event in bundle.reader.list_run_events(queued.run_id)
    ) == ("run_queued",)
    assert bundle.episode_reader.get(f"episode-{queued.run_id}") is None
    bundle.close()


@pytest.mark.asyncio
async def test_episode_write_failure_rolls_back_terminal_run_and_events(
    tmp_path: Path,
) -> None:
    runtime, bundle = _runtime_with_model(
        tmp_path,
        lambda invoker: build_agent_model(
            AgentModelProviderSettings(),
            script=(
                ScriptedFailure(
                    kind=ModelFailureKind.PROVIDER,
                    message="provider unavailable",
                ),
            ),
            tool_invoker=invoker,
        ),
    )
    queued = _queue_run(runtime, key="episode-write-failure")
    bundle.database.get_connection().execute(
        """
        CREATE TEMP TRIGGER reject_episode_insert
        BEFORE INSERT ON agent_episode_manifests
        BEGIN
            SELECT RAISE(ABORT, 'injected episode failure');
        END
        """
    )

    with pytest.raises(AgentRuntimeUnavailable):
        await runtime.execute_run(
            AgentRunExecuteCommand(
                run_id=queued.run_id,
                expected_revision=queued.revision,
            )
        )

    recovered = bundle.reader.get_run(queued.run_id)
    assert recovered is not None
    assert recovered.status is RunStatus.QUEUED
    assert recovered.revision == queued.revision
    assert tuple(
        event.event_type for event in bundle.reader.list_run_events(queued.run_id)
    ) == ("run_queued",)
    bundle.database.get_connection().execute("DROP TRIGGER reject_episode_insert")
    retried = await runtime.execute_run(
        AgentRunExecuteCommand(
            run_id=queued.run_id,
            expected_revision=queued.revision,
        )
    )
    assert retried.status is RunStatus.FAILED
    assert bundle.episode_reader.get(f"episode-{queued.run_id}") is not None
    bundle.close()


@pytest.mark.asyncio
async def test_projection_write_failure_leaves_run_queued_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, bundle = _runtime_with_model(
        tmp_path,
        lambda invoker: build_agent_model(
            AgentModelProviderSettings(),
            script=(
                ScriptedFailure(
                    kind=ModelFailureKind.PROVIDER,
                    message="provider unavailable",
                ),
            ),
            tool_invoker=invoker,
        ),
    )
    queued = _queue_run(runtime, key="projection-write-failure")

    def fail_projection(_update: object) -> None:
        raise AgentPresentationError(
            "injected presentation failure",
            reason_code="agent_presentation_write_failed",
        )

    monkeypatch.setattr(bundle.presentation_projector, "publish", fail_projection)

    with pytest.raises(AgentRuntimeUnavailable) as error:
        await runtime.execute_run(
            AgentRunExecuteCommand(
                run_id=queued.run_id,
                expected_revision=queued.revision,
            )
        )

    assert error.value.reason_code == "agent_presentation_write_failed"
    recovered = bundle.reader.get_run(queued.run_id)
    assert recovered is not None
    assert recovered.status is RunStatus.QUEUED
    assert recovered.revision == queued.revision
    assert tuple(
        event.event_type for event in bundle.reader.list_run_events(queued.run_id)
    ) == ("run_queued",)
    monkeypatch.undo()
    retried = await runtime.execute_run(
        AgentRunExecuteCommand(
            run_id=queued.run_id,
            expected_revision=queued.revision,
        )
    )
    assert retried.status is RunStatus.FAILED
    assert retried.failure_code == "model_provider_failed"
    bundle.close()


@pytest.mark.asyncio
async def test_projection_cursor_failure_uses_authoritative_event_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, bundle = _runtime_with_model(
        tmp_path,
        lambda invoker: build_agent_model(
            AgentModelProviderSettings(),
            script=(
                ScriptedFailure(
                    kind=ModelFailureKind.PROVIDER,
                    message="provider unavailable",
                ),
            ),
            tool_invoker=invoker,
        ),
    )
    queued = _queue_run(runtime, key="projection-cursor-failure")

    def fail_cursor(_run: object, *, updated_at: datetime) -> None:
        del updated_at
        raise AgentRuntimeUnavailable("agent_presentation_write_failed")

    monkeypatch.setattr(runtime, "_advance_projection_status", fail_cursor)

    failed = await runtime.execute_run(
        AgentRunExecuteCommand(
            run_id=queued.run_id,
            expected_revision=queued.revision,
        )
    )

    events = bundle.reader.list_run_events(queued.run_id)
    assert failed.status is RunStatus.FAILED
    assert failed.failure_code == "model_provider_failed"
    assert failed.projection_state is AgentProjectionState.COMPLETE
    assert failed.event_cursor == events[-1].event_id
    bundle.close()


@pytest.mark.asyncio
async def test_concurrent_execute_requests_invoke_model_once_per_run(
    tmp_path: Path,
) -> None:
    model = _BlockingFailureModel()
    runtime, bundle = _runtime_with_model(tmp_path, lambda _invoker: model)
    queued = _queue_run(runtime, key="concurrent-execute")
    command = AgentRunExecuteCommand(
        run_id=queued.run_id,
        expected_revision=queued.revision,
    )

    first = asyncio.create_task(runtime.execute_run(command))
    await model.started.wait()
    second = asyncio.create_task(runtime.execute_run(command))
    await asyncio.sleep(0)
    model.release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert model.calls == 1
    assert (
        sum(
            isinstance(result, AgentRunView) and result.status is RunStatus.FAILED
            for result in results
        )
        == 1
    )
    assert sum(isinstance(result, AgentRequestConflict) for result in results) == 1
    bundle.close()
