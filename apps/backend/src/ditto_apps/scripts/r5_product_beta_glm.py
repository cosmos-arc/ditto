"""Run one persisted, PIT-bound GLM product-beta validation."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from ditto_agent._canonical import canonical_bytes, canonical_sha256
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
from ditto_agent.runtime.service import (
    AgentRunCreateCommand,
    AgentRunExecuteCommand,
    AgentSessionCreateCommand,
)
from ditto_agent.tools._common import application_context, function_spec
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

from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.model_provider import (
    AgentModelCredentialKind,
    AgentModelProviderKind,
    AgentModelProviderSettings,
    build_agent_model,
)
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)
from ditto_apps.scripts.r2_data_acceptance import run_fixture_acceptance

_API_KEY_ENV = "DITTO_AGENT_GLM_VALIDATION_API_KEY"
_CREDENTIAL_KIND = AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
_DATASET_ID = "etf_daily"
_EXPERIMENT_ID = "product-beta-certified-etf"
_TOOL_NAME = "research_experiment_evidence"
_MAX_MODEL_TOKENS = 4_096
_MAX_OUTPUT_TOKENS = 1_024
_CHECKED_AT = datetime(2026, 8, 30, 8, tzinfo=UTC)


class ProductBetaValidationError(RuntimeError):
    """The persisted model run did not satisfy the product-beta contract."""


class _CertifiedExperimentFacade:
    """Expose one exact R2-certified experiment-shaped evidence record."""

    def __init__(self, result: ResearchEvidenceReadModel) -> None:
        self._result = result

    def get_experiment_evidence(
        self,
        *,
        experiment_id: str,
        context: EvidenceTemporalContext,
        candidate_id: str | None = None,
        fold_id: str | None = None,
    ) -> ResearchEvidenceReadModel:
        if experiment_id != _EXPERIMENT_ID:
            raise ProductBetaValidationError(
                "certified experiment identity differs from its exact scope"
            )
        if candidate_id is not None or fold_id is not None:
            raise ProductBetaValidationError(
                "certified experiment sub-scope must remain absent"
            )
        if context != self._result.temporal_context:
            raise ProductBetaValidationError(
                "certified experiment query differs from its exact PIT context"
            )
        return self._result


class _CertifiedExperimentEvidenceTool(ExperimentEvidenceTool):
    """Narrow the product-beta tool schema to its sole exact identity."""

    spec = function_spec(
        name=_TOOL_NAME,
        description="Read the exact R2-certified ETF product-beta experiment.",
        properties={
            "experiment_id": {"type": "string", "minLength": 1},
        },
        required=("experiment_id",),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run persisted GLM product-beta validation"
    )
    parser.add_argument("--model", choices=("glm-5.3", "glm-5-turbo"), required=True)
    parser.add_argument("--approval-a4", action="store_true")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _write(output: Path, payload: Mapping[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_bytes(payload))


def _not_run_payload(*, model_id: str, reason_code: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "not_run",
        "reason_code": reason_code,
        "provider": "glm",
        "model_id": model_id,
        "credential_kind": _CREDENTIAL_KIND,
        "production_eligible": False,
        "api_key_read": reason_code != "a4_approval_required",
        "live_endpoint_called": False,
    }


def _tool_schema_hash(registry: EvidenceToolRegistry) -> str:
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


def _certified_evidence(
    *,
    context: TemporalToolContext,
) -> tuple[ResearchEvidenceReadModel, str, str, str]:
    acceptance = run_fixture_acceptance(checked_at=_CHECKED_AT)
    product = next(
        item for item in acceptance.preflight.products if item.dataset_id == _DATASET_ID
    )
    report_id = product.certification_report_id
    content_hash = product.certification_content_hash
    if acceptance.status != "ready" or not product.ready:
        raise ProductBetaValidationError("R2 certified ETF acceptance is not ready")
    if report_id is None or content_hash is None:
        raise ProductBetaValidationError("R2 certification identity is incomplete")
    source_snapshot_id = f"{report_id}:2026-08-28:{content_hash}"
    if context.source_snapshot_id != source_snapshot_id:
        raise ProductBetaValidationError("source snapshot identity drifted")
    artifact_schema_hash = canonical_sha256(
        {
            "schema": "ditto.product-beta.certified-experiment",
            "version": 1,
        }
    )
    return (
        ResearchEvidenceReadModel(
            kind=ResearchEvidenceKind.EXPERIMENT,
            subject_id=_EXPERIMENT_ID,
            subject_version="1",
            strategy_id="seed_etf_industry_rotation",
            strategy_version="1",
            dataset_id=_DATASET_ID,
            temporal_context=application_context(context),
            payload=EvidencePayloadReadModel.seal(
                schema_version=1,
                value={
                    "status": "ready",
                    "dataset_id": _DATASET_ID,
                    "certification_report_id": report_id,
                    "certification_content_hash": content_hash,
                    "certified_from": (
                        product.certified_from.isoformat()
                        if product.certified_from is not None
                        else None
                    ),
                    "certified_through": (
                        product.certified_through.isoformat()
                        if product.certified_through is not None
                        else None
                    ),
                },
            ),
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=report_id,
                    artifact_kind="data_product_certification",
                    content_hash=content_hash,
                    schema_hash=artifact_schema_hash,
                ),
            ),
            lineage=(
                f"certification:{report_id}",
                f"snapshot:{source_snapshot_id}",
            ),
        ),
        report_id,
        content_hash,
        source_snapshot_id,
    )


def _context(source_snapshot_id: str) -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=_CHECKED_AT,
            knowledge_cutoff=datetime(2026, 8, 30, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 30, 6, tzinfo=UTC),
            source_snapshot_id=source_snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _certification_identity() -> tuple[str, str, str]:
    acceptance = run_fixture_acceptance(checked_at=_CHECKED_AT)
    product = next(
        item for item in acceptance.preflight.products if item.dataset_id == _DATASET_ID
    )
    if (
        acceptance.status != "ready"
        or not product.ready
        or product.certification_report_id is None
        or product.certification_content_hash is None
    ):
        raise ProductBetaValidationError("R2 certification identity is unavailable")
    snapshot_id = (
        f"{product.certification_report_id}:2026-08-28:"
        f"{product.certification_content_hash}"
    )
    return (
        product.certification_report_id,
        product.certification_content_hash,
        snapshot_id,
    )


async def _execute(
    *,
    data_root: Path,
    model_id: str,
    api_key: str,
) -> dict[str, object]:
    report_id, content_hash, source_snapshot_id = _certification_identity()
    context = _context(source_snapshot_id)
    read_model, verified_report_id, verified_content_hash, verified_snapshot_id = (
        _certified_evidence(context=context)
    )
    if (report_id, content_hash, source_snapshot_id) != (
        verified_report_id,
        verified_content_hash,
        verified_snapshot_id,
    ):
        raise ProductBetaValidationError("R2 certification changed during validation")
    registry = EvidenceToolRegistry(
        tools=(
            _CertifiedExperimentEvidenceTool(
                facade=cast(
                    ResearchEvidenceQueryPort,
                    _CertifiedExperimentFacade(read_model),
                )
            ),
        )
    )
    prompt_identity = canonical_sha256(
        {
            "prompt": "product-beta-certified-evidence",
            "version": 1,
        }
    )
    manifest = AgentManifest(
        manifest_id="product-beta-glm",
        agent_version="r5.1",
        prompt_version="certified-evidence-v1",
        prompt_hash=prompt_identity,
        tool_schema_version="read-only-v1",
        tool_schema_hash=_tool_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot=model_id,
    )
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.GLM,
        model_calls_enabled=True,
        a4_approved=True,
        model_id=model_id,
        api_key=api_key,
        credential_kind=_CREDENTIAL_KIND,
        production_mode=False,
    )
    plan = AgentRunExecutionPlan(
        temporal_context=context,
        allowed_tools=(_TOOL_NAME,),
        max_output_tokens=_MAX_OUTPUT_TOKENS,
    )
    bundle = build_agent_database(data_root)
    try:
        bundle.writer.put_manifest(manifest)
        runtime = PersistedAgentRuntime(
            reader=bundle.reader,
            writer=bundle.writer,
            manifest=manifest,
            clock=lambda: _CHECKED_AT,
            options=PersistedAgentRuntimeOptions(
                provider_name=AgentModelProviderKind.GLM.value,
                presentation_reader=bundle.presentation_reader,
                presentation_writer=bundle.presentation_writer,
                presentation_projector=bundle.presentation_projector,
                episode_writer=bundle.episode_writer,
                tool_registry=registry,
                model_factory=lambda invoker: build_agent_model(
                    settings,
                    tool_invoker=invoker,
                ),
            ),
        )
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.AUDIT,
                idempotency_key="product-beta-glm-session-v1",
            )
        )
        objective = (
            "Call research_experiment_evidence exactly once with experiment_id "
            "product-beta-certified-etf and no candidate_id or fold_id. Then return "
            "one claim stating that the host result is ready, cite the exact "
            "evidence_id from the host result, and state that the conclusion is "
            "limited to the certified snapshot."
        )
        queued = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective=objective,
                authority_hash=plan.authority_hash,
                max_model_tokens=_MAX_MODEL_TOKENS,
                max_model_spend_usd=Decimal("0"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="product-beta-glm-run-v1",
                execution_plan=plan,
            )
        )
        started_ns = time.monotonic_ns()
        completed = await runtime.execute_run(
            AgentRunExecuteCommand(
                run_id=queued.run_id,
                expected_revision=queued.revision,
            )
        )
        latency_ms = (time.monotonic_ns() - started_ns) // 1_000_000
        events = runtime.list_run_events(completed.run_id)
        episode = bundle.episode_reader.get(f"episode-{completed.run_id}")
        if (
            completed.status is not RunStatus.COMPLETED
            or completed.output_summary is None
            or completed.output_summary.startswith("Refused:")
            or len(completed.tool_records) != 1
            or len(completed.evidence_refs) != 1
            or completed.guardrail is None
            or completed.guardrail.status != "passed"
            or completed.usage is None
            or completed.usage.tool_calls != 1
            or episode is None
            or episode.final_status is not RunStatus.COMPLETED
            or not episode.verify_manifest_hash()
            or not episode.verify_replay_identity()
        ):
            raise ProductBetaValidationError(
                "persisted GLM run did not satisfy the governed completion contract"
            )
        return {
            "schema_version": 1,
            "status": "passed",
            "provider": "glm",
            "model_id": model_id,
            "credential_kind": _CREDENTIAL_KIND,
            "production_eligible": False,
            "release_gate_passed": True,
            "dataset_mode": "certified_fixture",
            "dataset_id": _DATASET_ID,
            "certification_report_id": report_id,
            "certification_content_hash": content_hash,
            "source_snapshot_id": source_snapshot_id,
            "authority_hash": plan.authority_hash,
            "temporal_context_hash": canonical_sha256(context.canonical_payload()),
            "run_id": completed.run_id,
            "run_status": completed.status,
            "run_revision": completed.revision,
            "event_types": tuple(event.event_type for event in events),
            "event_count": len(events),
            "evidence_refs": completed.evidence_refs,
            "output_summary_hash": canonical_sha256(
                {"output_summary": completed.output_summary}
            ),
            "guardrail_status": completed.guardrail.status,
            "usage": {
                "model_attempts": completed.usage.model_attempts,
                "model_turns": completed.usage.model_turns,
                "tool_calls": completed.usage.tool_calls,
                "retries": completed.usage.retries,
                "total_tokens": completed.usage.total_tokens,
            },
            "latency_ms": latency_ms,
            "episode_manifest_hash": episode.manifest_hash,
            "episode_replay_identity": episode.replay_identity,
            "episode_verified": True,
        }
    finally:
        bundle.close()


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Run the explicit A4 lane and persist only safe product-beta evidence."""
    arguments = _parser().parse_args(argv)
    model_id = str(arguments.model)
    output = Path(arguments.output)
    if not bool(arguments.approval_a4):
        _write(
            output,
            _not_run_payload(
                model_id=model_id,
                reason_code="a4_approval_required",
            ),
        )
        return 5
    api_key = environment.get(_API_KEY_ENV)
    if api_key is None or not api_key.strip() or api_key != api_key.strip():
        _write(
            output,
            _not_run_payload(
                model_id=model_id,
                reason_code="glm_validation_credential_missing",
            ),
        )
        return 5
    data_root = Path(arguments.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    try:
        payload = asyncio.run(
            _execute(
                data_root=data_root,
                model_id=model_id,
                api_key=api_key,
            )
        )
    except Exception as exc:
        _write(
            output,
            {
                "schema_version": 1,
                "status": "failed",
                "reason_code": "product_beta_glm_validation_failed",
                "failure_type": type(exc).__name__,
                "provider": "glm",
                "model_id": model_id,
                "credential_kind": _CREDENTIAL_KIND,
                "production_eligible": False,
                "release_gate_passed": False,
            },
        )
        return 1
    report_hash = canonical_sha256(payload)
    _write(output, {**payload, "report_hash": report_hash})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ProductBetaValidationError", "main"]
