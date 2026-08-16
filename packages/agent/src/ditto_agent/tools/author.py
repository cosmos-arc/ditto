"""Read-only Author Copilot draft, compile, validate, and diff tools."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_application.queries.authoring_preview_contracts import (
    AuthoringPreviewKind,
    AuthoringPreviewPort,
)

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.tools._common import (
    Arguments,
    function_spec,
    seal_authoring_preview,
)

_TEXT = {"type": "string", "minLength": 1}
_POSITIVE_INTEGER = {"type": "integer", "minimum": 1}
_SPEC_JSON = {"type": "object"}


class AuthorDraftStrategyTool:
    """Validate one detached structured StrategySpec draft."""

    spec = function_spec(
        name="author_draft_strategy",
        description="Create a non-persisted canonical StrategySpec draft preview.",
        properties={"spec_json": _SPEC_JSON},
        required=("spec_json",),
    )

    def __init__(self, *, facade: AuthoringPreviewPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Delegate structured draft validation and seal its evidence."""
        parsed = Arguments(arguments, required=("spec_json",))
        result = self._facade.create_draft(spec_json=parsed.mapping("spec_json"))
        return seal_authoring_preview(
            tool_name=self.spec.name,
            expected_kind=AuthoringPreviewKind.DRAFT.value,
            read_model=result,
            context=context,
        )


class AuthorCompileExpressionTool:
    """Compile one detached Ditto expression and return diagnostics."""

    spec = function_spec(
        name="author_compile_expression",
        description="Compile a detached Ditto DSL expression without saving it.",
        properties={
            "derived_id": _TEXT,
            "version": _POSITIVE_INTEGER,
            "expression": _TEXT,
        },
        required=("derived_id", "version", "expression"),
    )

    def __init__(self, *, facade: AuthoringPreviewPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Delegate to Ditto's compiler without parsing DSL inside Agent."""
        parsed = Arguments(
            arguments,
            required=("derived_id", "version", "expression"),
        )
        result = self._facade.compile_expression(
            derived_id=parsed.text("derived_id"),
            version=parsed.positive_integer("version"),
            expression=parsed.text("expression"),
        )
        return seal_authoring_preview(
            tool_name=self.spec.name,
            expected_kind=AuthoringPreviewKind.COMPILE.value,
            read_model=result,
            context=context,
        )


class AuthorValidateStrategyTool:
    """Validate a candidate against one exact immutable strategy version."""

    spec = function_spec(
        name="author_validate_strategy",
        description="Validate a StrategySpec candidate against an exact base version.",
        properties={
            "strategy_id": _TEXT,
            "base_version": _POSITIVE_INTEGER,
            "spec_json": _SPEC_JSON,
        },
        required=("strategy_id", "base_version", "spec_json"),
    )

    def __init__(self, *, facade: AuthoringPreviewPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Delegate exact-base validation and seal its evidence."""
        parsed = Arguments(
            arguments,
            required=("strategy_id", "base_version", "spec_json"),
        )
        result = self._facade.validate_strategy(
            strategy_id=parsed.text("strategy_id"),
            base_version=parsed.positive_integer("base_version"),
            spec_json=parsed.mapping("spec_json"),
        )
        return seal_authoring_preview(
            tool_name=self.spec.name,
            expected_kind=AuthoringPreviewKind.VALIDATE.value,
            read_model=result,
            context=context,
        )


class AuthorDiffStrategyTool:
    """Diff a candidate against one exact immutable strategy version."""

    spec = function_spec(
        name="author_diff_strategy",
        description="Diff a StrategySpec candidate against an exact base version.",
        properties={
            "strategy_id": _TEXT,
            "base_version": _POSITIVE_INTEGER,
            "spec_json": _SPEC_JSON,
        },
        required=("strategy_id", "base_version", "spec_json"),
    )

    def __init__(self, *, facade: AuthoringPreviewPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Delegate canonical diff generation and seal its evidence."""
        parsed = Arguments(
            arguments,
            required=("strategy_id", "base_version", "spec_json"),
        )
        result = self._facade.diff_strategy(
            strategy_id=parsed.text("strategy_id"),
            base_version=parsed.positive_integer("base_version"),
            spec_json=parsed.mapping("spec_json"),
        )
        return seal_authoring_preview(
            tool_name=self.spec.name,
            expected_kind=AuthoringPreviewKind.DIFF.value,
            read_model=result,
            context=context,
        )


__all__ = [
    "AuthorCompileExpressionTool",
    "AuthorDiffStrategyTool",
    "AuthorDraftStrategyTool",
    "AuthorValidateStrategyTool",
]
