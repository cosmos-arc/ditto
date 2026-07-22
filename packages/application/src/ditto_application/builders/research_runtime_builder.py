"""Explicit-version research runtime assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, cast

from ditto_features.expression.compiler import ExpressionCompiler
from ditto_strategy.alpha.node_registry import NodeRegistry, default_node_registry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.alpha.specs import StrategySpec, StrategySpecV2
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders._typed_runtime import build_typed_legacy_runtime
from ditto_application.builders.node_pipeline_builder import (
    AttestedNodePipeline,
    NodePipelineBuilder,
)
from ditto_application.builders.research_factor_registry import (
    ResearchFactorBinding,
    ResearchFactorRegistry,
    ResearchFactorRegistryManifest,
)
from ditto_application.exceptions import AppBuilderError, AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
)

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
    attested_pipeline: AttestedNodePipeline
    snapshot_identity: ResearchSnapshotIdentity
    base_spec_hash: str
    resolved_spec_hash: str
    parameter_hash: str
    effective_parameters: tuple[EffectiveParameter, ...]
    node_registry_manifest_hash: str
    factor_registry_manifest: ResearchFactorRegistryManifest
    used_factor_bindings: tuple[ResearchFactorBinding, ...]
    compiled_expressions: CompiledExpressions | None = None

    @property
    def pipeline(self) -> StrategyPipeline:
        """Return the sole runner carried by the sealed attestation."""
        return self.attested_pipeline.pipeline

    @property
    def pipeline_execution_hash(self) -> str:
        """Return the execution identity derived by the sealed attestation."""
        return self.attested_pipeline.execution_hash

    def require_verified_pipeline(
        self, *, expected_execution_hash: str
    ) -> StrategyPipeline:
        """Verify and return the exact runner that a service will consume."""
        if type(self.attested_pipeline) is not AttestedNodePipeline:
            raise _builder_error(
                "research pipeline attestation is invalid",
                reason="invalid_research_pipeline_attestation",
            )
        return self.attested_pipeline.require_verified_pipeline(
            expected_execution_hash=expected_execution_hash,
        )

    @property
    def factor_registry_manifest_hash(self) -> str:
        """Return the full code-only factor registry identity."""
        return self.factor_registry_manifest.manifest_hash

    @property
    def factor_versions(self) -> tuple[tuple[str, int], ...]:
        """Return exact used factor versions in source signal order."""
        return tuple(
            (binding.factor_id, binding.version)
            for binding in self.used_factor_bindings
        )


class _ConstrainedResearchRuntimeCompiler:
    """Compile one already-governed exact record through the sealed R3 graph."""

    def __init__(
        self,
        *,
        node_registry: NodeRegistry | None = None,
        node_pipeline_builder: NodePipelineBuilder | None = None,
        factor_registry: ResearchFactorRegistry | None = None,
        factor_compiler: ExpressionCompiler | None = None,
    ) -> None:
        if (
            node_pipeline_builder is not None
            and type(node_pipeline_builder) is not NodePipelineBuilder
        ):
            raise _builder_error(
                "research runtime requires the constrained node pipeline builder",
                reason="invalid_research_pipeline_builder",
                actual_type=type(node_pipeline_builder).__name__,
            )
        registry = (
            node_registry
            if node_registry is not None
            else node_pipeline_builder.registry
            if node_pipeline_builder is not None
            else default_node_registry()
        )
        if type(registry) is not NodeRegistry:
            raise _builder_error(
                "research runtime requires the exact builtin node registry",
                reason="invalid_research_node_registry",
                actual_type=type(registry).__name__,
            )
        if (
            node_pipeline_builder is not None
            and node_pipeline_builder.registry is not registry
        ):
            raise _builder_error(
                "research runtime requires the constrained node pipeline builder",
                reason="invalid_research_pipeline_builder",
                actual_type=type(node_pipeline_builder).__name__,
            )
        self._node_registry = registry
        self._node_pipeline_builder = node_pipeline_builder or NodePipelineBuilder(
            registry=registry,
        )
        self._factor_registry = (
            factor_registry if factor_registry is not None else ResearchFactorRegistry()
        )
        self._factor_bridge = FactorBridge(
            compiler=factor_compiler,
            factor_registry=self._factor_registry.factor_specs,
            factor_versions=self._factor_registry.factor_versions,
            require_registered_factor_ids=True,
        )

    def compile(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> ResearchStrategyRuntime:
        """Compile a validated exact record without choosing its lifecycle lane."""
        is_native_v2 = _ensure_payload_strategy_identity(record)
        if is_native_v2:
            raise _builder_error(
                "native StrategySpec v2 execution is not available in Task3",
                reason="native_v2_executor_unavailable",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
            )

        try:
            resolved = build_typed_legacy_runtime(
                record=record,
                candidate_parameters=candidate_parameters,
                registry=self._node_registry,
                node_pipeline_builder=self._node_pipeline_builder,
                evidence_sink=evidence_sink,
                factor_bridge=self._factor_bridge,
                require_pipeline_attestation=True,
            )
        except AppProcessError as exc:
            raise AppBuilderError(str(exc), details=exc.details) from exc
        _ensure_resolved_strategy_identity(
            record,
            legacy_strategy_id=resolved.legacy_spec.strategy_id,
            base_family_id=resolved.base_spec.strategy_family_id,
            resolved_family_id=resolved.resolved_spec.strategy_family_id,
        )
        if resolved.pipeline_execution_hash is None:
            raise _builder_error(
                "research pipeline execution identity is unavailable",
                reason="research_pipeline_attestation_unavailable",
            )
        if resolved.attested_pipeline is None:
            raise _builder_error(
                "research pipeline attestation is unavailable",
                reason="research_pipeline_attestation_unavailable",
            )
        return ResearchStrategyRuntime(
            strategy_id=record.strategy_id,
            strategy_version=record.version,
            version_status=record.status,
            legacy_spec=resolved.legacy_spec,
            base_spec=resolved.base_spec,
            resolved_spec=resolved.resolved_spec,
            attested_pipeline=resolved.attested_pipeline,
            snapshot_identity=snapshot_identity,
            base_spec_hash=resolved.base_spec_hash,
            resolved_spec_hash=resolved.resolved_spec_hash,
            parameter_hash=resolved.parameter_hash,
            effective_parameters=resolved.effective_parameters,
            node_registry_manifest_hash=resolved.node_registry_manifest_hash,
            factor_registry_manifest=self._factor_registry.manifest,
            used_factor_bindings=self._factor_registry.bind_compiled(
                resolved.legacy_spec.signal_expressions,
                (
                    ()
                    if resolved.compiled_expressions is None
                    else resolved.compiled_expressions.expressions
                ),
            ),
            compiled_expressions=resolved.compiled_expressions,
        )


# Package-internal public names shared by the two lifecycle-specific adapters.
ConstrainedResearchRuntimeCompiler = _ConstrainedResearchRuntimeCompiler
research_runtime_error = _builder_error
require_exact_research_record = _require_research_record
require_research_snapshot_identity = _require_snapshot_identity


class ResearchRuntimeBuilder:
    """Build draft/review candidates without catalog or active-pointer I/O."""

    def __init__(
        self,
        *,
        node_registry: NodeRegistry | None = None,
        node_pipeline_builder: NodePipelineBuilder | None = None,
        version_guard: ResearchVersionGuard | None = None,
        factor_registry: ResearchFactorRegistry | None = None,
        factor_compiler: ExpressionCompiler | None = None,
    ) -> None:
        self._status_guard = _DraftReviewResearchVersionGuard()
        self._version_guard = version_guard
        self._compiler = _ConstrainedResearchRuntimeCompiler(
            node_registry=node_registry,
            node_pipeline_builder=node_pipeline_builder,
            factor_registry=factor_registry,
            factor_compiler=factor_compiler,
        )

    def build(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> ResearchStrategyRuntime:
        """Resolve one explicit draft/review record through the constrained compiler."""
        record = _require_research_record(record)
        snapshot_identity = _require_snapshot_identity(snapshot_identity)
        self._status_guard.ensure_buildable(record)
        if self._version_guard is not None:
            self._version_guard.ensure_buildable(record)
        return self._compiler.compile(
            record=record,
            candidate_parameters=candidate_parameters,
            snapshot_identity=snapshot_identity,
            evidence_sink=evidence_sink,
        )
