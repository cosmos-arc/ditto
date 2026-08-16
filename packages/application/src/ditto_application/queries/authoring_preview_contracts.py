"""Pure application contracts for side-effect-free authoring previews."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ditto_application.queries.evidence_contracts import EvidencePayloadReadModel

__all__ = [
    "AuthoringPreviewKind",
    "AuthoringPreviewPort",
    "AuthoringPreviewReadModel",
]


class AuthoringPreviewKind(StrEnum):
    """Closed set of non-mutating Author Copilot operations."""

    DRAFT = "draft"
    COMPILE = "compile"
    VALIDATE = "validate"
    DIFF = "diff"


@dataclass(frozen=True, slots=True)
class AuthoringPreviewReadModel:
    """Content-addressed authoring result that can never be published directly."""

    kind: AuthoringPreviewKind
    subject_id: str
    subject_version: str
    valid: bool
    changed: bool
    payload: EvidencePayloadReadModel
    lineage: tuple[str, ...]


class AuthoringPreviewPort(Protocol):
    """Consumer-facing, read-only authoring boundary used by Agent tools."""

    def create_draft(
        self,
        *,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        """Validate and canonicalize a detached structured strategy draft."""
        ...

    def compile_expression(
        self,
        *,
        derived_id: str,
        version: int,
        expression: str,
    ) -> AuthoringPreviewReadModel:
        """Compile one detached DSL expression without materializing it."""
        ...

    def validate_strategy(
        self,
        *,
        strategy_id: str,
        base_version: int,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        """Validate a candidate against one exact immutable base version."""
        ...

    def diff_strategy(
        self,
        *,
        strategy_id: str,
        base_version: int,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        """Return the canonical candidate-vs-base field diff."""
        ...
