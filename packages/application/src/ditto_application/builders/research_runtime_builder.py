"""Explicit-version research runtime assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, cast

from ditto_strategy.alpha.node_registry import NodeRegistry, default_node_registry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec, StrategySpecV2
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders._typed_runtime import build_typed_legacy_runtime
from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.factor_bridge import CompiledExpressions

__all__ = [
    "ResearchRuntimeBuilder",
    "ResearchSnapshotIdentity",
    "ResearchStrategyRuntime",
    "ResearchVersionGuard",
]


def _builder_error(
    message: str,
    *,
    reason: str,
    **details: object,
) -> AppBuilderError:
    payload: dict[str, object] = {
        "code": "SPEC_INVALID",
        "reason": reason,
    }
    payload.update(details)
    return AppBuilderError(message, details=payload)


def _require_snapshot_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _builder_error(
            "research snapshot identity must be a non-empty canonical string",
            reason="invalid_research_snapshot_identity",
            path="snapshot_identity.snapshot_id",
            actual_type=type(value).__name__,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _builder_error(
            "research snapshot identity must have a canonical UTF-8 identity",
            reason="invalid_research_snapshot_identity",
            path="snapshot_identity.snapshot_id",
            actual_type="str",
        ) from None
    return value


def _require_snapshot_manifest_hash(value: object, *, snapshot_id: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise _builder_error(
            "research snapshot manifest hash must be canonical SHA-256",
            reason="invalid_research_snapshot_identity",
            snapshot_id=snapshot_id,
            path="snapshot_identity.manifest_hash",
            actual_type=type(value).__name__,
        )
    return value


def _require_research_record(value: object) -> StrategySpecRecord:
    if not isinstance(value, StrategySpecRecord):
        raise _builder_error(
            "research runtime requires an explicit StrategySpecRecord",
            reason="invalid_research_version_record",
            path="record",
            actual_type=type(value).__name__,
        )
    if type(value.version) is not int or value.version <= 0:
        raise _builder_error(
            "research runtime requires a positive exact integer version",
            reason="invalid_research_version_record",
            path="record.version",
            actual_value=value.version,
        )
    raw_strategy_id = cast(object, value.strategy_id)
    if (
        not isinstance(raw_strategy_id, str)
        or not raw_strategy_id
        or raw_strategy_id != raw_strategy_id.strip()
    ):
        raise _builder_error(
            "research record strategy identity must be non-empty and canonical",
            reason="invalid_research_strategy_identity",
            path="record.strategy_id",
            actual_value=raw_strategy_id,
        )
    raw_spec_json = cast(object, value.spec_json)
    if not isinstance(raw_spec_json, dict):
        raise _builder_error(
            "research record spec_json must be an object",
            reason="invalid_research_version_record",
            path="record.spec_json",
            actual_type=type(raw_spec_json).__name__,
        )
    return value


def _ensure_payload_strategy_identity(
    record: StrategySpecRecord,
) -> bool:
    """Validate record/payload family agreement and return native-V2 status."""
    is_native_v2 = record.spec_json.get("schema_version") is not None
    identity_field = "strategy_family_id" if is_native_v2 else "strategy_id"
    payload_identity = record.spec_json.get(identity_field)
    path = f"spec_json.{identity_field}"
    if (
        not isinstance(payload_identity, str)
        or not payload_identity
        or payload_identity != payload_identity.strip()
    ):
        raise _builder_error(
            "research payload strategy identity must be non-empty and canonical",
            reason="invalid_research_strategy_identity",
            path=path,
            actual_value=payload_identity,
        )
    if payload_identity != record.strategy_id:
        raise _builder_error(
            "research record and payload strategy identities do not match",
            reason="research_strategy_identity_mismatch",
            path=path,
            record_strategy_id=record.strategy_id,
            payload_strategy_family_id=payload_identity,
        )
    return is_native_v2


def _ensure_resolved_strategy_identity(
    record: StrategySpecRecord,
    *,
    legacy_strategy_id: str,
    base_family_id: str,
    resolved_family_id: str,
) -> None:
    identities = (
        ("legacy_spec.strategy_id", legacy_strategy_id),
        ("base_spec.strategy_family_id", base_family_id),
        ("resolved_spec.strategy_family_id", resolved_family_id),
    )
    for path, identity in identities:
        if identity != record.strategy_id:
            raise _builder_error(
                "resolved research strategy identity does not match its record",
                reason="research_strategy_identity_mismatch",
                path=path,
                record_strategy_id=record.strategy_id,
                payload_strategy_family_id=identity,
            )


def _require_snapshot_identity(value: object) -> ResearchSnapshotIdentity:
    if not isinstance(value, ResearchSnapshotIdentity):
        raise _builder_error(
            "research runtime requires ResearchSnapshotIdentity",
            reason="invalid_research_snapshot_identity",
            actual_type=type(value).__name__,
        )
    snapshot_id = _require_snapshot_id(cast(object, value.snapshot_id))
    manifest_hash = _require_snapshot_manifest_hash(
        cast(object, value.manifest_hash),
        snapshot_id=snapshot_id,
    )
    return ResearchSnapshotIdentity(
        snapshot_id=snapshot_id,
        manifest_hash=manifest_hash,
    )


@dataclass(frozen=True)
class ResearchSnapshotIdentity:
    """Opaque identity of a certified research dataset snapshot."""

    snapshot_id: str
    manifest_hash: str

    def __post_init__(self) -> None:
        """Reject identities that cannot be reproduced byte-for-byte."""
        snapshot_id = _require_snapshot_id(self.snapshot_id)
        _require_snapshot_manifest_hash(self.manifest_hash, snapshot_id=snapshot_id)


class ResearchVersionGuard(Protocol):
    """Task15 extension seam for deciding whether an explicit version is buildable."""

    def ensure_buildable(self, record: StrategySpecRecord) -> None:
        """Raise a typed builder error when the exact version is not researchable."""
        ...


class _DraftReviewResearchVersionGuard:
    """Pre-governance policy for explicit draft/review records only."""

    _ALLOWED_STATUSES = frozenset({"draft", "review"})

    def ensure_buildable(self, record: StrategySpecRecord) -> None:
        if record.status not in self._ALLOWED_STATUSES:
            raise _builder_error(
                "strategy version is not buildable by the research runtime",
                reason="research_version_not_buildable",
                path="record.status",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
                version_status=record.status,
                allowed_statuses=tuple(sorted(self._ALLOWED_STATUSES)),
            )


@dataclass(frozen=True)
class ResearchStrategyRuntime:
    """Resolved runtime and immutable identities for one research candidate."""

    strategy_id: str
    strategy_version: int
    version_status: str
    legacy_spec: StrategySpec
    base_spec: StrategySpecV2
    resolved_spec: StrategySpecV2
    pipeline: StrategyPipeline
    snapshot_identity: ResearchSnapshotIdentity
    base_spec_hash: str
    resolved_spec_hash: str
    parameter_hash: str
    effective_parameters: tuple[EffectiveParameter, ...]
    node_registry_manifest_hash: str
    compiled_expressions: CompiledExpressions | None = None


class ResearchRuntimeBuilder:
    """Build from one explicit legacy record without catalog or active-pointer I/O."""

    def __init__(
        self,
        *,
        node_registry: NodeRegistry | None = None,
        node_pipeline_builder: NodePipelineBuilder | None = None,
        version_guard: ResearchVersionGuard | None = None,
    ) -> None:
        registry = node_registry or default_node_registry()
        self._node_registry = registry
        self._node_pipeline_builder = node_pipeline_builder or NodePipelineBuilder(
            registry=registry,
        )
        self._status_guard = _DraftReviewResearchVersionGuard()
        self._version_guard = version_guard

    def build(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
    ) -> ResearchStrategyRuntime:
        """Resolve an exact legacy version and candidate into the existing runner."""
        record = _require_research_record(record)
        snapshot_identity = _require_snapshot_identity(snapshot_identity)
        self._status_guard.ensure_buildable(record)
        if self._version_guard is not None:
            self._version_guard.ensure_buildable(record)
        is_native_v2 = _ensure_payload_strategy_identity(record)
        if is_native_v2:
            raise _builder_error(
                "native StrategySpec v2 execution is not available in Task3",
                reason="native_v2_executor_unavailable",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
            )

        resolved = build_typed_legacy_runtime(
            record=record,
            candidate_parameters=candidate_parameters,
            registry=self._node_registry,
            node_pipeline_builder=self._node_pipeline_builder,
        )
        _ensure_resolved_strategy_identity(
            record,
            legacy_strategy_id=resolved.legacy_spec.strategy_id,
            base_family_id=resolved.base_spec.strategy_family_id,
            resolved_family_id=resolved.resolved_spec.strategy_family_id,
        )
        return ResearchStrategyRuntime(
            strategy_id=record.strategy_id,
            strategy_version=record.version,
            version_status=record.status,
            legacy_spec=resolved.legacy_spec,
            base_spec=resolved.base_spec,
            resolved_spec=resolved.resolved_spec,
            pipeline=resolved.pipeline,
            snapshot_identity=snapshot_identity,
            base_spec_hash=resolved.base_spec_hash,
            resolved_spec_hash=resolved.resolved_spec_hash,
            parameter_hash=resolved.parameter_hash,
            effective_parameters=resolved.effective_parameters,
            node_registry_manifest_hash=resolved.node_registry_manifest_hash,
            compiled_expressions=resolved.compiled_expressions,
        )
