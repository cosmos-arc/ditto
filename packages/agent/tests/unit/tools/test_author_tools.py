"""Author Copilot tools stay no-write, exact, and evidence-sealed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelToolCall
from ditto_agent.tools.author import (
    AuthorCompileExpressionTool,
    AuthorDiffStrategyTool,
    AuthorDraftStrategyTool,
    AuthorValidateStrategyTool,
)
from ditto_agent.tools.registry import EvidenceToolRegistry, ToolNotAllowedError
from ditto_application.queries.authoring_preview_contracts import (
    AuthoringPreviewKind,
    AuthoringPreviewPort,
    AuthoringPreviewReadModel,
)
from ditto_application.queries.evidence_contracts import EvidencePayloadReadModel


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id="snapshot-20260812",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


class _Facade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def _result(
        self,
        kind: AuthoringPreviewKind,
        subject_id: str,
        subject_version: str,
    ) -> AuthoringPreviewReadModel:
        return AuthoringPreviewReadModel(
            kind=kind,
            subject_id=subject_id,
            subject_version=subject_version,
            valid=True,
            changed=kind is AuthoringPreviewKind.DIFF,
            payload=EvidencePayloadReadModel.seal(
                schema_version=1,
                value={
                    "operation": kind.value,
                    "valid": True,
                    "changed": kind is AuthoringPreviewKind.DIFF,
                    "publishable": False,
                },
            ),
            lineage=(f"author-preview:{kind.value}:{subject_id}:{subject_version}",),
        )

    def create_draft(self, *, spec_json: object) -> AuthoringPreviewReadModel:
        self.calls.append(("draft", spec_json))
        return self._result(AuthoringPreviewKind.DRAFT, "strategy-001", "draft")

    def compile_expression(
        self,
        *,
        derived_id: str,
        version: int,
        expression: str,
    ) -> AuthoringPreviewReadModel:
        self.calls.append(("compile", (derived_id, version, expression)))
        return self._result(AuthoringPreviewKind.COMPILE, derived_id, str(version))

    def validate_strategy(
        self,
        *,
        strategy_id: str,
        base_version: int,
        spec_json: object,
    ) -> AuthoringPreviewReadModel:
        self.calls.append(("validate", (strategy_id, base_version, spec_json)))
        return self._result(
            AuthoringPreviewKind.VALIDATE,
            strategy_id,
            str(base_version),
        )

    def diff_strategy(
        self,
        *,
        strategy_id: str,
        base_version: int,
        spec_json: object,
    ) -> AuthoringPreviewReadModel:
        self.calls.append(("diff", (strategy_id, base_version, spec_json)))
        return self._result(
            AuthoringPreviewKind.DIFF,
            strategy_id,
            str(base_version),
        )


def _tools(facade: _Facade) -> tuple[object, ...]:
    port = cast(AuthoringPreviewPort, facade)
    return (
        AuthorDraftStrategyTool(facade=port),
        AuthorCompileExpressionTool(facade=port),
        AuthorValidateStrategyTool(facade=port),
        AuthorDiffStrategyTool(facade=port),
    )


def test_author_tool_specs_are_closed_no_approval_and_expose_no_trusted_context() -> (
    None
):
    facade = _Facade()
    tools = _tools(facade)

    assert tuple(tool.spec.name for tool in tools) == (
        "author_draft_strategy",
        "author_compile_expression",
        "author_validate_strategy",
        "author_diff_strategy",
    )
    trusted = {
        "decision_time",
        "knowledge_cutoff",
        "publication_cutoff",
        "source_snapshot_id",
    }
    assert all(not tool.spec.requires_approval for tool in tools)
    assert all(
        tool.spec.input_schema["additionalProperties"] is False for tool in tools
    )
    assert all(
        trusted.isdisjoint(tool.spec.input_schema["properties"]) for tool in tools
    )


@pytest.mark.parametrize(
    ("index", "arguments", "expected_call"),
    [
        (0, {"spec_json": {"strategy_family_id": "strategy-001"}}, "draft"),
        (
            1,
            {
                "derived_id": "factor.momentum",
                "version": 1,
                "expression": "ts_mean(market.close, 20)",
            },
            "compile",
        ),
        (
            2,
            {
                "strategy_id": "strategy-001",
                "base_version": 3,
                "spec_json": {"strategy_family_id": "strategy-001"},
            },
            "validate",
        ),
        (
            3,
            {
                "strategy_id": "strategy-001",
                "base_version": 3,
                "spec_json": {"strategy_family_id": "strategy-001"},
            },
            "diff",
        ),
    ],
)
def test_author_tools_are_thin_facade_adapters_with_sealed_evidence(
    index: int,
    arguments: dict[str, object],
    expected_call: str,
) -> None:
    facade = _Facade()
    tool = _tools(facade)[index]
    context = _context()

    envelope = tool.invoke(arguments=arguments, context=context)

    assert facade.calls[0][0] == expected_call
    assert envelope.tool_name == tool.spec.name
    assert envelope.temporal_context == context
    assert envelope.result["kind"] == "authoring_preview"
    assert envelope.result["preview_kind"] == expected_call
    assert envelope.result["publishable"] is False
    assert envelope.artifact_refs[0].startswith("author-preview:sha256:")
    assert envelope.verify_integrity()


@pytest.mark.parametrize("field", ["code", "python_code", "explanation"])
def test_model_cannot_smuggle_code_or_explanation_as_tool_argument(field: str) -> None:
    facade = _Facade()
    tool = AuthorDraftStrategyTool(facade=cast(AuthoringPreviewPort, facade))

    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={"spec_json": {}, field: "generated text"},
            context=_context(),
        )
    assert facade.calls == []


def test_registry_accepts_preview_tools_but_still_rejects_publish() -> None:
    facade = _Facade()
    registry = EvidenceToolRegistry(tools=cast(tuple, _tools(facade)))

    assert tuple(registry.tools) == (
        "author_draft_strategy",
        "author_compile_expression",
        "author_validate_strategy",
        "author_diff_strategy",
    )
    with pytest.raises(ToolNotAllowedError, match="publish_strategy"):
        registry.execute(
            call=ModelToolCall(
                call_id="call-publish",
                tool_name="publish_strategy",
                arguments={"strategy_id": "strategy-001"},
            ),
            context=_context(),
        )


def test_tampered_application_payload_hash_is_rejected() -> None:
    class _TamperedFacade(_Facade):
        def create_draft(self, *, spec_json: object) -> AuthoringPreviewReadModel:
            result = super().create_draft(spec_json=spec_json)
            object.__setattr__(result.payload, "payload_hash", "f" * 64)
            return result

    tool = AuthorDraftStrategyTool(facade=cast(AuthoringPreviewPort, _TamperedFacade()))
    with pytest.raises(ValueError, match="payload hash mismatch"):
        tool.invoke(arguments={"spec_json": {}}, context=_context())
