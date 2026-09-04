from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_agent.contracts.runtime import AgentSession, RetentionClass, RunStatus
from ditto_agent.presentation import (
    AgentGuardrailPresentation,
    AgentRunPresentation,
)
from ditto_agent.runtime.service import AgentRuntimePort, AgentRuntimeState
from ditto_agent.storage.sqlite.episode_store import (
    AgentEpisodeReader,
    AgentEpisodeWriter,
)
from ditto_agent.storage.sqlite.errors import AgentDatabaseClosedError
from ditto_agent.storage.sqlite.presentation_store import (
    AgentPresentationReader,
    AgentPresentationWriter,
)
from ditto_application.agent_campaign_runtime import CampaignRuntimePort
from ditto_application.queries.decision_opinion import (
    DecisionOpinionQueryPort,
    DecisionOpinionQueryService,
)
from ditto_apps.registry.agent.campaign_runtime import PersistedCampaignRuntime
from ditto_apps.registry.agent.database_provider import (
    build_agent_database,
    restore_agent_database,
)
from ditto_apps.registry.container import make_app_container


def test_apps_owns_agent_database_lifecycle_without_exposing_pool(
    tmp_path: Path,
) -> None:
    bundle = build_agent_database(tmp_path)
    session = AgentSession(
        session_id="session-001",
        created_at=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
        retention_class=RetentionClass.STANDARD,
    )

    bundle.writer.create_session(session)

    assert bundle.reader.get_session(session.session_id) == session
    assert isinstance(bundle.episode_reader, AgentEpisodeReader)
    assert isinstance(bundle.episode_writer, AgentEpisodeWriter)
    assert isinstance(bundle.presentation_reader, AgentPresentationReader)
    assert isinstance(bundle.presentation_writer, AgentPresentationWriter)
    assert bundle.database.path == tmp_path / "agent" / "agent.sqlite"
    assert bundle.presentation_database.path == (
        tmp_path / "agent" / "agent-presentation.sqlite3"
    )
    assert not hasattr(bundle, "pool")

    bundle.close()
    with pytest.raises(AgentDatabaseClosedError):
        bundle.reader.get_session(session.session_id)


def test_production_container_enables_persisted_r5_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path))
    for name in (
        "DITTO_AGENT_ENABLED",
        "DITTO_AGENT_AUTHOR_ENABLED",
        "DITTO_AGENT_CAMPAIGN_ENABLED",
        "DITTO_AGENT_DECISION_SHADOW_ENABLED",
        "DITTO_AGENT_MODEL_CALLS_ENABLED",
    ):
        monkeypatch.setenv(name, "true")

    container = make_app_container()
    try:
        runtime = container.get(AgentRuntimePort)
        campaign_runtime = container.get(CampaignRuntimePort)
        decision_query = container.get(DecisionOpinionQueryPort)

        capability = runtime.get_capabilities()
        assert capability.enabled is True
        assert capability.runtime_state is AgentRuntimeState.AVAILABLE
        assert capability.provider == "fake"
        assert isinstance(campaign_runtime, PersistedCampaignRuntime)
        assert isinstance(decision_query, DecisionOpinionQueryService)
    finally:
        container.close()


def test_persisted_runtime_reports_model_execution_degraded_when_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("DITTO_AGENT_ENABLED", "true")
    monkeypatch.setenv("DITTO_AGENT_MODEL_CALLS_ENABLED", "false")

    container = make_app_container()
    try:
        capability = container.get(AgentRuntimePort).get_capabilities()

        assert capability.enabled is True
        assert capability.runtime_state is AgentRuntimeState.DEGRADED
        assert capability.provider is None
        assert capability.degradation_reason == "agent_model_execution_unconfigured"
    finally:
        container.close()


def test_agent_bundle_backup_and_restore_preserve_readable_projection(
    tmp_path: Path,
) -> None:
    source = build_agent_database(tmp_path / "source")
    presentation = AgentRunPresentation(
        run_id="run-backup",
        objective="Preserve this readable objective.",
        context=None,
        status=RunStatus.COMPLETED,
        output_summary="Recovered summary.",
        tool_records=(),
        evidence_refs=(),
        artifact_refs=(),
        guardrail=AgentGuardrailPresentation(status="passed", reason_code=None),
        usage=None,
        failure_code=None,
        projection_version=1,
        updated_at=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
    )
    source.presentation_writer.put(presentation)

    backup_root = tmp_path / "backup"
    source.backup_to(backup_root)
    source.close()
    restored = restore_agent_database(backup_root, tmp_path / "restored")
    try:
        recovered = restored.presentation_reader.get("run-backup")
        assert recovered is not None
        assert recovered.objective == "Preserve this readable objective."
        assert recovered.output_summary == "Recovered summary."
    finally:
        restored.close()
