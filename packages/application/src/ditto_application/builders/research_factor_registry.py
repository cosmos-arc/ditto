"""Immutable code-only factor identities for research execution."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType
from typing import cast

import orjson
import polars as pl
from ditto_features.expression.contracts import (
    Analysis,
    AnalysisWarning,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorContext, FactorSpec

from ditto_application.exceptions import AppBuilderError

__all__ = [
    "ResearchFactorBinding",
    "ResearchFactorRegistration",
    "ResearchFactorRegistry",
    "ResearchFactorRegistryManifest",
    "analysis_execution_hash",
]

_MANIFEST_SCHEMA = "ditto.research-factor-registry.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _registry_error(
    message: str,
    *,
    reason: str,
    code: str = "SPEC_INVALID",
    **details: object,
) -> AppBuilderError:
    payload: dict[str, object] = {"code": code, "reason": reason}
    payload.update(details)
    return AppBuilderError(message, details=payload)


def _require_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _registry_error(
            f"{field_name} must be a non-empty canonical string",
            reason="invalid_research_factor_registration",
            field_name=field_name,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _registry_error(
            f"{field_name} must be valid UTF-8",
            reason="invalid_research_factor_registration",
            field_name=field_name,
        ) from None
    return value


def _validate_computation(
    expression: object,
    computation_type: object,
    *,
    factor_id: str,
) -> None:
    if not isinstance(expression, str):
        raise _registry_error(
            "factor expression must be a string",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.expression",
        )
    try:
        expression.encode("utf-8")
    except UnicodeEncodeError:
        raise _registry_error(
            "factor expression must be valid UTF-8",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.expression",
        ) from None
    if computation_type not in {"expression", "python"}:
        raise _registry_error(
            "factor computation type is invalid",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.computation_type",
        )
    if computation_type == "expression" and not expression.strip():
        raise _registry_error(
            "expression factors require a non-empty expression",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.expression",
        )
    if computation_type == "python" and expression:
        raise _registry_error(
            "python factors cannot carry an expression",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.expression",
        )


def _validate_dependencies(value: object, *, factor_id: str) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item
        for item in cast(tuple[object, ...], value)
    ):
        raise _registry_error(
            "factor dependencies must be a tuple of non-empty strings",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.dependencies",
        )


def _validate_calendar(value: object, *, factor_id: str) -> None:
    if value is None:
        return
    if not isinstance(value, FactorContext):
        raise _registry_error(
            "factor calendar context is invalid",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.calendar_context",
        )
    raw_special = cast(object, value.is_special)
    raw_half_day = cast(object, value.is_half_day)
    raw_exchange = cast(object, value.exchange)
    if (
        type(raw_special) is not bool
        or type(raw_half_day) is not bool
        or (raw_exchange is not None and not isinstance(raw_exchange, str))
    ):
        raise _registry_error(
            "factor calendar context is invalid",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.calendar_context",
        )


def _validate_spec(spec: object, *, factor_id: str) -> FactorSpec:
    if not isinstance(spec, FactorSpec):
        raise _registry_error(
            "research factor registration requires FactorSpec",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
        )
    raw_id = cast(object, spec.id)
    if raw_id != factor_id:
        raise _registry_error(
            "research factor registration and FactorSpec identities differ",
            reason="research_factor_identity_mismatch",
            factor_id=factor_id,
            spec_id=raw_id,
        )
    _require_text(raw_id, field_name="spec.id")
    raw_expression = cast(object, spec.expression)
    raw_computation_type = cast(object, spec.computation_type)
    _validate_computation(raw_expression, raw_computation_type, factor_id=factor_id)
    raw_dependencies = cast(object, spec.dependencies)
    _validate_dependencies(raw_dependencies, factor_id=factor_id)
    raw_description = cast(object, spec.description)
    if not isinstance(raw_description, str):
        raise _registry_error(
            "factor description must be a string",
            reason="invalid_research_factor_registration",
            factor_id=factor_id,
            field_name="spec.description",
        )
    _validate_calendar(cast(object, spec.calendar_context), factor_id=factor_id)
    return spec


def _factor_spec_payload(spec: FactorSpec) -> dict[str, object]:
    calendar = spec.calendar_context
    return {
        "calendar_context": (
            None
            if calendar is None
            else {
                "exchange": calendar.exchange,
                "is_half_day": calendar.is_half_day,
                "is_special": calendar.is_special,
            }
        ),
        "computation_type": spec.computation_type,
        "dependencies": list(spec.dependencies),
        "description": spec.description,
        "expression": spec.expression,
        "id": spec.id,
    }


def _canonical_hash(payload: object) -> str:
    return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _compiled_expression_hash(expression: object) -> str:
    """Hash the executable Polars expression bytes, not compiler claims."""
    if type(expression) is not pl.Expr:
        raise _registry_error(
            "compiled research factor must contain an exact Polars expression",
            reason="invalid_compiled_research_factor_expression",
        )
    try:
        serialized = expression.meta.serialize()
    except (OSError, ValueError, pl.exceptions.PolarsError):
        raise _registry_error(
            "compiled research factor expression cannot be serialized",
            reason="invalid_compiled_research_factor_expression",
        ) from None
    if type(serialized) is not bytes or not serialized:
        raise _registry_error(
            "compiled research factor serialization is invalid",
            reason="invalid_compiled_research_factor_expression",
        )
    return sha256(serialized).hexdigest()


def _analysis_text(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _registry_error(
            "compiled factor analysis contains invalid text",
            reason="invalid_compiled_research_factor_analysis",
            field_name=field_name,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _registry_error(
            "compiled factor analysis contains invalid text",
            reason="invalid_compiled_research_factor_analysis",
            field_name=field_name,
        ) from None
    return value


def _analysis_texts(value: object, *, field_name: str) -> list[str]:
    if type(value) is not tuple:
        raise _registry_error(
            "compiled factor analysis contains an invalid sequence",
            reason="invalid_compiled_research_factor_analysis",
            field_name=field_name,
        )
    return [
        _analysis_text(item, field_name=f"{field_name}[{index}]")
        for index, item in enumerate(cast("tuple[object, ...]", value))
    ]


def analysis_execution_hash(value: object) -> str:
    """Hash every exact Analysis field consumed by planning or execution."""
    if type(value) is not Analysis:
        raise _registry_error(
            "compiled factor analysis must use the exact contract",
            reason="invalid_compiled_research_factor_analysis",
        )
    analysis = value
    if type(analysis.lookback) is not int or analysis.lookback < 0:
        raise _registry_error(
            "compiled factor lookback must be a non-negative exact integer",
            reason="invalid_compiled_research_factor_analysis",
            field_name="analysis.lookback",
        )
    if type(analysis.requires_full_day) is not bool:
        raise _registry_error(
            "compiled factor full-day flag must be an exact boolean",
            reason="invalid_compiled_research_factor_analysis",
            field_name="analysis.requires_full_day",
        )
    if type(analysis.warnings) is not tuple or any(
        type(item) is not AnalysisWarning
        for item in cast("tuple[object, ...]", analysis.warnings)
    ):
        raise _registry_error(
            "compiled factor warnings must use exact contracts",
            reason="invalid_compiled_research_factor_analysis",
            field_name="analysis.warnings",
        )
    warnings = analysis.warnings
    return _canonical_hash(
        {
            "dependencies": _analysis_texts(
                analysis.dependencies,
                field_name="analysis.dependencies",
            ),
            "operator_names": _analysis_texts(
                analysis.operator_names,
                field_name="analysis.operator_names",
            ),
            "lookback": analysis.lookback,
            "requires_full_day": analysis.requires_full_day,
            "scope": _analysis_text(analysis.scope, field_name="analysis.scope"),
            "output_schema": _analysis_texts(
                analysis.output_schema,
                field_name="analysis.output_schema",
            ),
            "warnings": [
                {
                    "message": _analysis_text(
                        warning.message,
                        field_name=f"analysis.warnings[{index}].message",
                    ),
                    "error_code": _analysis_text(
                        warning.error_code,
                        field_name=f"analysis.warnings[{index}].error_code",
                    ),
                }
                for index, warning in enumerate(warnings)
            ],
        }
    )


def _compile_identity_payload(identity: CompileIdentity) -> dict[str, object]:
    return {
        "analysis_version": identity.analysis_version,
        "cache_key": identity.cache_key,
        "compile_input_hash": identity.compile_input_hash,
        "compiler_fingerprint": identity.compiler_fingerprint,
        "engine_codegen_version": identity.engine_codegen_version,
        "expr_serialization_format": identity.expr_serialization_format,
        "global_compile_flags": list(identity.global_compile_flags),
        "operator_fingerprint": identity.operator_fingerprint,
        "operator_versions": [list(item) for item in identity.operator_versions],
        "polars_version": identity.polars_version,
    }


def _copy_spec(spec: FactorSpec) -> FactorSpec:
    calendar = spec.calendar_context
    calendar_copy = (
        None
        if calendar is None
        else FactorContext(
            is_special=calendar.is_special,
            is_half_day=calendar.is_half_day,
            exchange=calendar.exchange,
        )
    )
    return FactorSpec(
        id=spec.id,
        expression=spec.expression,
        dependencies=tuple(spec.dependencies),
        description=spec.description,
        calendar_context=calendar_copy,
        computation_type=spec.computation_type,
    )


@dataclass(frozen=True, slots=True)
class ResearchFactorRegistration:
    """One exact versioned code registration and its canonical spec identity."""

    factor_id: str
    version: int
    spec: FactorSpec
    spec_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate and defensively copy the declared FactorSpec."""
        factor_id = _require_text(self.factor_id, field_name="factor_id")
        if type(self.version) is not int or self.version <= 0:
            raise _registry_error(
                "research factor version must be a positive integer",
                reason="invalid_research_factor_registration",
                factor_id=factor_id,
                version=self.version,
            )
        spec = _copy_spec(_validate_spec(self.spec, factor_id=factor_id))
        object.__setattr__(self, "spec", spec)
        object.__setattr__(
            self,
            "spec_hash",
            _canonical_hash(_factor_spec_payload(spec)),
        )

    def manifest_payload(self) -> dict[str, object]:
        """Return the complete canonical code-registration payload."""
        return {
            "factor_id": self.factor_id,
            "version": self.version,
            "spec_hash": self.spec_hash,
            "spec": _factor_spec_payload(self.spec),
        }


@dataclass(frozen=True, slots=True)
class ResearchFactorBinding:
    """One used factor bound to exact code and compiler/cache identities."""

    factor_id: str
    version: int
    spec_hash: str
    compile_identity: CompileIdentity
    compiled_expression_hash: str
    analysis_execution_hash: str
    binding_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute the content address for the exact used binding."""
        if _SHA256.fullmatch(self.compiled_expression_hash) is None:
            raise _registry_error(
                "compiled expression hash must be an exact SHA-256 digest",
                reason="invalid_compiled_research_factor_expression_hash",
                factor_id=self.factor_id,
            )
        if _SHA256.fullmatch(self.analysis_execution_hash) is None:
            raise _registry_error(
                "analysis execution hash must be an exact SHA-256 digest",
                reason="invalid_compiled_research_factor_analysis_hash",
                factor_id=self.factor_id,
            )
        payload = {
            "analysis_execution_hash": self.analysis_execution_hash,
            "compile_identity": _compile_identity_payload(self.compile_identity),
            "compiled_expression_hash": self.compiled_expression_hash,
            "factor_id": self.factor_id,
            "spec_hash": self.spec_hash,
            "version": self.version,
        }
        object.__setattr__(self, "binding_hash", _canonical_hash(payload))


@dataclass(frozen=True, slots=True)
class ResearchFactorRegistryManifest:
    """Full immutable registry manifest and its content address."""

    registrations: tuple[ResearchFactorRegistration, ...]
    schema_id: str = _MANIFEST_SCHEMA
    manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Freeze entries and compute the full registry content address."""
        registrations = tuple(self.registrations)
        object.__setattr__(self, "registrations", registrations)
        payload = {
            "schema_id": self.schema_id,
            "registrations": [item.manifest_payload() for item in registrations],
        }
        object.__setattr__(self, "manifest_hash", _canonical_hash(payload))


class ResearchFactorRegistry:
    """Process-local immutable snapshot of the built-in factor declarations."""

    def __init__(
        self,
        *,
        extensions: Sequence[ResearchFactorRegistration] = (),
    ) -> None:
        builtins = tuple(
            ResearchFactorRegistration(
                factor_id=factor_id,
                version=1,
                spec=spec,
            )
            for factor_id, spec in sorted(ALL_FACTOR_SPECS.items())
        )
        extension_copies: list[ResearchFactorRegistration] = []
        for item in cast(tuple[object, ...], tuple(extensions)):
            if not isinstance(item, ResearchFactorRegistration):
                raise _registry_error(
                    "research factor extensions must be code registrations",
                    reason="invalid_research_factor_registration",
                )
            extension_copies.append(
                ResearchFactorRegistration(
                    factor_id=item.factor_id,
                    version=item.version,
                    spec=item.spec,
                )
            )
        resolved = (*builtins, *extension_copies)
        factor_ids = tuple(item.factor_id for item in resolved)
        if len(factor_ids) != len(set(factor_ids)):
            raise _registry_error(
                "research factor IDs must be unique",
                reason="duplicate_research_factor_registration",
                factor_ids=factor_ids,
            )
        ordered = tuple(sorted(resolved, key=lambda item: item.factor_id))
        self._registrations: Mapping[str, ResearchFactorRegistration] = (
            MappingProxyType({item.factor_id: item for item in ordered})
        )
        self._factor_specs: Mapping[str, FactorSpec] = MappingProxyType(
            {item.factor_id: item.spec for item in ordered}
        )
        self._factor_versions: Mapping[str, int] = MappingProxyType(
            {item.factor_id: item.version for item in ordered}
        )
        self._manifest = ResearchFactorRegistryManifest(ordered)

    @property
    def registrations(self) -> Mapping[str, ResearchFactorRegistration]:
        """Return the immutable factor-id keyed registration snapshot."""
        return self._registrations

    @property
    def factor_specs(self) -> Mapping[str, FactorSpec]:
        """Return the immutable FactorBridge lookup surface."""
        return self._factor_specs

    @property
    def factor_versions(self) -> Mapping[str, int]:
        """Return immutable exact versions keyed by factor ID."""
        return self._factor_versions

    @property
    def manifest(self) -> ResearchFactorRegistryManifest:
        """Return the complete immutable registry manifest."""
        return self._manifest

    @property
    def manifest_hash(self) -> str:
        """Return the canonical full-registry identity."""
        return self._manifest.manifest_hash

    def resolve_used(
        self,
        factor_ids: tuple[str, ...],
    ) -> tuple[ResearchFactorRegistration, ...]:
        """Resolve the exact ordered used set; unknown and duplicate IDs fail closed."""
        if len(factor_ids) != len(set(factor_ids)):
            raise _registry_error(
                "research strategy cannot use a factor more than once",
                reason="duplicate_research_factor_use",
                factor_ids=factor_ids,
            )
        resolved: list[ResearchFactorRegistration] = []
        for factor_id in factor_ids:
            registration = self._registrations.get(factor_id)
            if registration is None:
                raise _registry_error(
                    f"unknown research factor: {factor_id}",
                    reason="unknown_research_factor",
                    factor_id=factor_id,
                )
            if registration.spec.computation_type != "expression":
                raise _registry_error(
                    f"research factor executor is unavailable: {factor_id}",
                    code="EXECUTOR_UNAVAILABLE",
                    reason="research_factor_executor_unavailable",
                    factor_id=factor_id,
                    computation_type=registration.spec.computation_type,
                )
            resolved.append(registration)
        return tuple(resolved)

    def bind_compiled(
        self,
        factor_ids: tuple[str, ...],
        compiled: tuple[CompiledDerivedExpression, ...],
    ) -> tuple[ResearchFactorBinding, ...]:
        """Bind source factor order to the exact compile identities actually used."""
        registrations = self.resolve_used(factor_ids)
        if len(registrations) != len(compiled):
            raise _registry_error(
                "compiled factor count does not match the resolved used set",
                reason="research_factor_compile_count_mismatch",
                factor_count=len(registrations),
                compiled_count=len(compiled),
            )
        bindings: list[ResearchFactorBinding] = []
        for registration, expression in zip(
            registrations,
            compiled,
            strict=True,
        ):
            if type(expression) is not CompiledDerivedExpression:
                raise _registry_error(
                    "compiled factor must use the exact expression contract",
                    reason="research_factor_compile_identity_mismatch",
                    factor_id=registration.factor_id,
                )
            if (
                expression.derived_id != registration.factor_id
                or expression.version != registration.version
            ):
                raise _registry_error(
                    "compiled factor identity does not match its registration",
                    reason="research_factor_compile_identity_mismatch",
                    factor_id=registration.factor_id,
                    factor_version=registration.version,
                    compiled_id=expression.derived_id,
                    compiled_version=expression.version,
                )
            bindings.append(
                ResearchFactorBinding(
                    factor_id=registration.factor_id,
                    version=registration.version,
                    spec_hash=registration.spec_hash,
                    compile_identity=expression.compile_identity,
                    compiled_expression_hash=_compiled_expression_hash(expression.expr),
                    analysis_execution_hash=analysis_execution_hash(
                        expression.analysis
                    ),
                )
            )
        return tuple(bindings)
