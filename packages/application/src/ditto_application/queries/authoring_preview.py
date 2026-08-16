"""Side-effect-free StrategySpec and expression authoring previews."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import cast

from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.expression.diagnostics import ExpressionCompileError
from ditto_kernel.exceptions import DittoError
from ditto_strategy.alpha.node_registry import NodeRegistry, default_node_registry
from ditto_strategy.alpha.spec_codec import (
    adapt_legacy_strategy_spec,
    canonical_spec_hash,
    canonical_spec_payload,
)
from ditto_strategy.alpha.specs import StrategySpecV2
from ditto_strategy.alpha.validation import validate_spec_params
from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppBuilderError, AppQueryError
from ditto_application.queries.authoring_preview_contracts import (
    AuthoringPreviewKind,
    AuthoringPreviewReadModel,
)
from ditto_application.queries.evidence_contracts import EvidencePayloadReadModel
from ditto_application.strategy_spec_deserialization import (
    deserialize_strategy_spec,
    deserialize_strategy_spec_v2,
    diff_canonical_payloads,
)

__all__ = ["AuthoringPreviewFacade"]

_LEGACY_FIELDS = frozenset(
    {
        "asset_class",
        "benchmark",
        "constraints",
        "execution",
        "name",
        "param_constraints",
        "params",
        "required_datasets",
        "scorer",
        "selector",
        "signal_expressions",
        "signal_weights",
        "strategy_id",
        "tags",
        "template",
        "universe",
    }
)
_FORBIDDEN_DRAFT_FIELDS = frozenset(
    {
        "code",
        "explanation",
        "python_code",
        "source_code",
    }
)


@dataclass(frozen=True, slots=True)
class _CanonicalDraft:
    subject_id: str
    source_contract: str
    canonical_spec: dict[str, object]
    canonical_hash: str


def _diagnostic(
    *,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "details": dict(details or {}),
    }


def _error_diagnostic(exc: Exception) -> dict[str, object]:
    details = exc.details if isinstance(exc, DittoError) else {}
    return _diagnostic(
        code="AUTHORING_STRATEGY_INVALID",
        message=str(exc),
        details=details,
    )


def _compile_diagnostic(exc: ExpressionCompileError) -> dict[str, object]:
    diagnostic = exc.diagnostic
    return {
        "code": diagnostic.error_code,
        "message": diagnostic.message,
        "source_line": diagnostic.source_line,
        "span": asdict(diagnostic.span),
        "suggestions": diagnostic.suggestions,
    }


def _find_forbidden_field(value: object, *, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, item in cast("Mapping[object, object]", value).items():
            key_text = str(key)
            item_path = f"{path}.{key_text}" if path else key_text
            if key_text.casefold() in _FORBIDDEN_DRAFT_FIELDS:
                return item_path
            nested = _find_forbidden_field(item, path=item_path)
            if nested is not None:
                return nested
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(cast("Sequence[object]", value)):
            nested = _find_forbidden_field(item, path=f"{path}[{index}]")
            if nested is not None:
                return nested
    return None


def _subject_hint(spec_json: Mapping[str, object]) -> str:
    for key in ("strategy_family_id", "strategy_id"):
        value = spec_json.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "unresolved-strategy"


def _is_v2(spec_json: Mapping[str, object]) -> bool:
    return "schema_version" in spec_json


def _validate_v2_nodes(spec: StrategySpecV2, registry: NodeRegistry) -> None:
    for node in spec.pipeline.nodes:
        descriptor = registry.lookup(node.ref)
        if descriptor.category is not node.category:
            raise AppBuilderError(
                "strategy node category does not match its descriptor",
                details={
                    "reason": "node_category_mismatch",
                    "node_identity": node.ref.identity,
                    "expected_category": descriptor.category.value,
                    "actual_category": node.category.value,
                },
            )
        if spec.strategy_kind not in descriptor.supported_strategy_kinds:
            raise AppBuilderError(
                "strategy node does not support the requested strategy kind",
                details={
                    "reason": "unsupported_node_strategy_kind",
                    "node_identity": node.ref.identity,
                    "strategy_kind": spec.strategy_kind.value,
                },
            )
        descriptor.resolve_config(node.config)


def _canonicalize(
    *,
    spec_json: Mapping[str, object],
    registry: NodeRegistry,
) -> _CanonicalDraft:
    record = StrategySpecRecord(
        strategy_id=_subject_hint(spec_json),
        name=str(spec_json.get("name", "")),
        spec_json=dict(spec_json),
    )
    if _is_v2(spec_json):
        spec = deserialize_strategy_spec_v2(record)
        _validate_v2_nodes(spec, registry)
        source_contract = "strategy_spec_v2"
    else:
        unknown = tuple(sorted(set(spec_json) - _LEGACY_FIELDS))
        if unknown:
            raise AppBuilderError(
                "legacy strategy draft contains unknown fields",
                details={
                    "reason": "unknown_legacy_strategy_field",
                    "unknown_fields": unknown,
                },
            )
        legacy = deserialize_strategy_spec(record)
        validate_spec_params(legacy)
        spec = adapt_legacy_strategy_spec(legacy)
        _validate_v2_nodes(spec, registry)
        source_contract = "strategy_spec_legacy"
    return _CanonicalDraft(
        subject_id=spec.strategy_family_id,
        source_contract=source_contract,
        canonical_spec=canonical_spec_payload(spec),
        canonical_hash=canonical_spec_hash(spec),
    )


def _seal_result(
    *,
    kind: AuthoringPreviewKind,
    subject_id: str,
    subject_version: str,
    valid: bool,
    changed: bool,
    value: Mapping[str, object],
    lineage: tuple[str, ...],
) -> AuthoringPreviewReadModel:
    payload = EvidencePayloadReadModel.seal(schema_version=1, value=value)
    return AuthoringPreviewReadModel(
        kind=kind,
        subject_id=subject_id,
        subject_version=subject_version,
        valid=valid,
        changed=changed,
        payload=payload,
        lineage=(*lineage, f"author-preview:sha256:{payload.payload_hash}"),
    )


def _invalid_strategy_result(
    *,
    kind: AuthoringPreviewKind,
    subject_id: str,
    subject_version: str,
    diagnostic: Mapping[str, object],
    lineage: tuple[str, ...],
) -> AuthoringPreviewReadModel:
    return _seal_result(
        kind=kind,
        subject_id=subject_id,
        subject_version=subject_version,
        valid=False,
        changed=False,
        value={
            "operation": kind.value,
            "valid": False,
            "changed": False,
            "publishable": False,
            "diagnostics": (dict(diagnostic),),
        },
        lineage=lineage,
    )


class AuthoringPreviewFacade:
    """Compile and compare detached authoring payloads without mutation authority."""

    def __init__(
        self,
        *,
        catalog: StrategyCatalogReader,
        expression_compiler: ExpressionCompiler | None = None,
        node_registry: NodeRegistry | None = None,
    ) -> None:
        self._catalog = catalog
        self._expression_compiler = expression_compiler or ExpressionCompiler()
        self._node_registry = node_registry or default_node_registry()

    def create_draft(
        self,
        *,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        """Validate a detached structured draft and return canonical evidence."""
        subject_id = _subject_hint(spec_json)
        forbidden = _find_forbidden_field(spec_json)
        if forbidden is not None:
            return _invalid_strategy_result(
                kind=AuthoringPreviewKind.DRAFT,
                subject_id=subject_id,
                subject_version="draft",
                diagnostic=_diagnostic(
                    code="AUTHORING_FORBIDDEN_FIELD",
                    message="strategy drafts cannot contain code or explanations",
                    details={"field": forbidden},
                ),
                lineage=(f"strategy-draft:{subject_id}",),
            )
        try:
            draft = _canonicalize(
                spec_json=spec_json,
                registry=self._node_registry,
            )
        except (DittoError, TypeError, ValueError) as exc:
            return _invalid_strategy_result(
                kind=AuthoringPreviewKind.DRAFT,
                subject_id=subject_id,
                subject_version="draft",
                diagnostic=_error_diagnostic(exc),
                lineage=(f"strategy-draft:{subject_id}",),
            )
        return _seal_result(
            kind=AuthoringPreviewKind.DRAFT,
            subject_id=draft.subject_id,
            subject_version="draft",
            valid=True,
            changed=False,
            value={
                "operation": "draft",
                "valid": True,
                "changed": False,
                "publishable": False,
                "source_contract": draft.source_contract,
                "canonical_hash": draft.canonical_hash,
                "canonical_spec": draft.canonical_spec,
                "diagnostics": (),
            },
            lineage=(f"strategy-draft:{draft.subject_id}",),
        )

    def compile_expression(
        self,
        *,
        derived_id: str,
        version: int,
        expression: str,
    ) -> AuthoringPreviewReadModel:
        """Compile one DSL expression through the Ditto expression compiler."""
        lineage = (f"derived-draft:{derived_id}:v{version}",)
        try:
            compiled = self._expression_compiler.compile(
                DerivedSpec(
                    id=derived_id,
                    version=version,
                    role=DerivedRole.FACTOR,
                    materialization_profile=MaterializationProfile.DERIVE,
                    expression=expression,
                )
            )
        except ExpressionCompileError as exc:
            return _invalid_strategy_result(
                kind=AuthoringPreviewKind.COMPILE,
                subject_id=derived_id,
                subject_version=str(version),
                diagnostic=_compile_diagnostic(exc),
                lineage=lineage,
            )
        except (DittoError, TypeError, ValueError) as exc:
            return _invalid_strategy_result(
                kind=AuthoringPreviewKind.COMPILE,
                subject_id=derived_id,
                subject_version=str(version),
                diagnostic=_error_diagnostic(exc),
                lineage=lineage,
            )
        return _seal_result(
            kind=AuthoringPreviewKind.COMPILE,
            subject_id=derived_id,
            subject_version=str(version),
            valid=True,
            changed=False,
            value={
                "operation": "compile",
                "valid": True,
                "changed": False,
                "publishable": False,
                "derived_id": compiled.derived_id,
                "version": compiled.version,
                "analysis": asdict(compiled.analysis),
                "compile_identity": asdict(compiled.compile_identity),
                "diagnostics": (),
            },
            lineage=lineage,
        )

    def validate_strategy(
        self,
        *,
        strategy_id: str,
        base_version: int,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        """Validate a candidate against one exact immutable base version."""
        return self._compare(
            kind=AuthoringPreviewKind.VALIDATE,
            strategy_id=strategy_id,
            base_version=base_version,
            spec_json=spec_json,
        )

    def diff_strategy(
        self,
        *,
        strategy_id: str,
        base_version: int,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        """Return a replayable canonical diff against one exact base version."""
        return self._compare(
            kind=AuthoringPreviewKind.DIFF,
            strategy_id=strategy_id,
            base_version=base_version,
            spec_json=spec_json,
        )

    def _compare(
        self,
        *,
        kind: AuthoringPreviewKind,
        strategy_id: str,
        base_version: int,
        spec_json: Mapping[str, object],
    ) -> AuthoringPreviewReadModel:
        base_record = self._exact_base(strategy_id, base_version)
        base = _canonicalize(
            spec_json=base_record.spec_json,
            registry=self._node_registry,
        )
        if (
            base.subject_id != strategy_id
            or base.canonical_hash != base_record.spec_hash
        ):
            raise AppQueryError(
                "base strategy hash mismatch",
                details={
                    "code": "AUTHORING_BASE_HASH_MISMATCH",
                    "strategy_id": strategy_id,
                    "base_version": base_version,
                },
            )
        lineage = (
            f"strategy:{strategy_id}:v{base_version}",
            f"strategy:sha256:{base.canonical_hash}",
        )
        forbidden = _find_forbidden_field(spec_json)
        if forbidden is not None:
            return _invalid_strategy_result(
                kind=kind,
                subject_id=strategy_id,
                subject_version=str(base_version),
                diagnostic=_diagnostic(
                    code="AUTHORING_FORBIDDEN_FIELD",
                    message="strategy drafts cannot contain code or explanations",
                    details={"field": forbidden},
                ),
                lineage=lineage,
            )
        try:
            candidate = _canonicalize(
                spec_json=spec_json,
                registry=self._node_registry,
            )
        except (DittoError, TypeError, ValueError) as exc:
            return _invalid_strategy_result(
                kind=kind,
                subject_id=strategy_id,
                subject_version=str(base_version),
                diagnostic=_error_diagnostic(exc),
                lineage=lineage,
            )
        if candidate.subject_id != strategy_id:
            return _invalid_strategy_result(
                kind=kind,
                subject_id=strategy_id,
                subject_version=str(base_version),
                diagnostic=_diagnostic(
                    code="AUTHORING_IDENTITY_MISMATCH",
                    message="candidate strategy identity differs from exact base",
                    details={
                        "expected_strategy_id": strategy_id,
                        "candidate_strategy_id": candidate.subject_id,
                    },
                ),
                lineage=lineage,
            )
        changes = diff_canonical_payloads(
            base.canonical_spec,
            candidate.canonical_spec,
        )
        changed = bool(changes)
        value: dict[str, object] = {
            "operation": kind.value,
            "valid": True,
            "changed": changed,
            "publishable": False,
            "strategy_id": strategy_id,
            "base_version": base_version,
            "base_spec_hash": base.canonical_hash,
            "source_contract": candidate.source_contract,
            "canonical_hash": candidate.canonical_hash,
            "canonical_spec": candidate.canonical_spec,
            "diagnostics": (),
        }
        if kind is AuthoringPreviewKind.DIFF:
            value["changes"] = tuple(asdict(change) for change in changes)
        return _seal_result(
            kind=kind,
            subject_id=strategy_id,
            subject_version=str(base_version),
            valid=True,
            changed=changed,
            value=value,
            lineage=lineage,
        )

    def _exact_base(
        self,
        strategy_id: str,
        base_version: int,
    ) -> StrategySpecRecord:
        record = self._catalog.get_spec(strategy_id, base_version)
        if record is None or record.version != base_version:
            raise AppQueryError(
                "exact base strategy version not found",
                details={
                    "code": "AUTHORING_BASE_NOT_FOUND",
                    "strategy_id": strategy_id,
                    "base_version": base_version,
                },
            )
        return record
