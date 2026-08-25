"""Readable Agent run projection integration contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
)
from ditto_agent.presentation import AgentContextPresentation
from ditto_agent.runtime.service import (
    AgentProjectionState,
    AgentRunCreateCommand,
    AgentSessionCreateCommand,
)
from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)

NOW = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
HASH = "c" * 64


def _manifest() -> AgentManifest:
    return AgentManifest(
        manifest_id="presentation-balanced",
        agent_version="r5.1",
        prompt_version="presentation-v1",
        prompt_hash="1" * 64,
        tool_schema_version="read-only-v1",
        tool_schema_hash="2" * 64,
        model_profile=ModelProfile.BALANCED,
        model_snapshot="fake-presentation",
    )


def test_created_projection_is_readable_and_recovers_after_restart(
    tmp_path: Path,
) -> None:
    bundle = build_agent_database(tmp_path)
    manifest = _manifest()
    bundle.writer.put_manifest(manifest)
    runtime = PersistedAgentRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        manifest=manifest,
        clock=lambda: NOW,
        options=PersistedAgentRuntimeOptions(
            presentation_reader=bundle.presentation_reader,
            presentation_writer=bundle.presentation_writer,
        ),
    )
    session = runtime.create_session(
        AgentSessionCreateCommand(
            retention_class=RetentionClass.STANDARD,
            idempotency_key="presentation-session",
        )
    )
    created = runtime.create_run(
        AgentRunCreateCommand(
            session_id=session.session_id,
            objective="Explain exact Daily Decision V3 evidence.",
            authority_hash=HASH,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key="presentation-run",
            context=AgentContextPresentation(
                context_type="daily_decision",
                context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
            ),
        )
    )

    assert created.objective == "Explain exact Daily Decision V3 evidence."
    assert created.context == AgentContextPresentation(
        context_type="daily_decision",
        context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
    )
    assert created.projection_state is AgentProjectionState.COMPLETE
    assert created.projection_reason is None
    assert created.projection_version == 1
    assert created.event_cursor > 0

    other = runtime.create_run(
        AgentRunCreateCommand(
            session_id=session.session_id,
            objective="Explain a different immutable experiment revision.",
            authority_hash="d" * 64,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            idempotency_key="presentation-run-other-context",
            context=AgentContextPresentation(
                context_type="experiment",
                context_id="experiment-22@revision-4",
            ),
        )
    )
    filtered = runtime.list_runs(
        status=None,
        session_id=None,
        context_type="daily_decision",
        context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
        limit=20,
        offset=0,
    )
    assert filtered.total == 1
    assert filtered.items == (created,)
    assert other.run_id != created.run_id
    run_id = created.run_id
    bundle.close()

    restarted = build_agent_database(tmp_path)
    try:
        recovered = PersistedAgentRuntime(
            reader=restarted.reader,
            writer=restarted.writer,
            manifest=manifest,
            clock=lambda: NOW,
            options=PersistedAgentRuntimeOptions(
                presentation_reader=restarted.presentation_reader,
                presentation_writer=restarted.presentation_writer,
            ),
        ).get_run(run_id)
        assert recovered == created
    finally:
        restarted.close()


def test_unconfigured_projection_is_explicitly_partial(tmp_path: Path) -> None:
    bundle = build_agent_database(tmp_path)
    manifest = _manifest()
    bundle.writer.put_manifest(manifest)
    runtime = PersistedAgentRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        manifest=manifest,
        clock=lambda: NOW,
    )
    try:
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="partial-session",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective="Never infer this from its hash.",
                authority_hash=HASH,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="partial-run",
            )
        )
        assert run.objective is None
        assert run.context is None
        assert run.projection_state is AgentProjectionState.PARTIAL
        assert run.projection_reason == "agent_presentation_unconfigured"
    finally:
        bundle.close()
