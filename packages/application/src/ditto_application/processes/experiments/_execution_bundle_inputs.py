"""Frozen input and component bindings used by research execution bundles."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanKind,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
)

__all__ = [
    "BaselineExecutorBinding",
    "CodeEnvironmentLock",
    "ContentAddressedResearchInput",
    "ExecutionEvidenceSource",
    "PolicyModelEvidenceBinding",
    "ResearchFillMode",
    "ResearchSnapshotBinding",
    "VersionedExecutionComponent",
    "research_data_feed_manifest_hash",
]

_SHA256 = re.compile(r"[0-9a-f]{64}")
_FOLD_ROLES = frozenset({"exploration", "walk_forward", "holdout"})
_FACTOR_IDENTITY_PART_COUNT = 2
_POLICY_MODEL_ROLES = frozenset({"fees", "rules", "settlement", "slippage"})
_PARTS_PER_MILLION = 1_000_000
_RESEARCH_FEED_ARTIFACT_KINDS = (
    "bars",
    "calendar",
    "membership",
    "fundamental",
    "classification",
)
_REQUIRED_RESEARCH_FEED_ARTIFACT_KINDS = (
    "bars",
    "calendar",
    "membership",
)

EXECUTABLE_FOLD_ROLES = _FOLD_ROLES
PARTS_PER_MILLION = _PARTS_PER_MILLION
POLICY_MODEL_ROLES = _POLICY_MODEL_ROLES


def _error(message: str, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        message,
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def _identity(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise _error(
            f"{field_name} must be a canonical non-empty string",
            "invalid_execution_identity",
            field=field_name,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _error(
            f"{field_name} must have a canonical UTF-8 identity",
            "invalid_execution_identity",
            field=field_name,
        ) from None
    return value


def _hash(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise _error(
            f"{field_name} must be a canonical SHA-256 digest",
            "invalid_content_hash",
            field=field_name,
        )
    return value


def _nonnegative_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(
            f"{field_name} must be a non-negative integer",
            "invalid_execution_control",
            field=field_name,
        )
    return value


def _positive_integer(value: object, field_name: str) -> int:
    result = _nonnegative_integer(value, field_name)
    if result == 0:
        raise _error(
            f"{field_name} must be a positive integer",
            "invalid_execution_control",
            field=field_name,
        )
    return result


def _date_value(value: object, field_name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise _error(
            f"{field_name} must be a date",
            "invalid_execution_window",
            field=field_name,
        )
    return value


def execution_bundle_error(
    message: str,
    reason: str,
    **details: object,
) -> AppProcessError:
    """Build one reproducibility failure for sibling bundle modules."""
    return _error(message, reason, **details)


def require_execution_identity(value: object, field_name: str) -> str:
    """Validate one canonical execution identity for sibling bundle modules."""
    return _identity(value, field_name)


def require_content_hash(value: object, field_name: str) -> str:
    """Validate one SHA-256 digest for sibling bundle modules."""
    return _hash(value, field_name)


def require_nonnegative_integer(value: object, field_name: str) -> int:
    """Validate one non-negative execution control for sibling modules."""
    return _nonnegative_integer(value, field_name)


def require_positive_integer(value: object, field_name: str) -> int:
    """Validate one positive execution control for sibling bundle modules."""
    return _positive_integer(value, field_name)


def require_date(value: object, field_name: str) -> date:
    """Validate one date-only execution boundary for sibling bundle modules."""
    return _date_value(value, field_name)


class ResearchFillMode(StrEnum):
    """Exact partial-fill behavior used by one frozen research run."""

    PARTIAL = "partial"
    ALL_OR_NOTHING = "all_or_nothing"


class ExecutionEvidenceSource(StrEnum):
    """Permitted immutable sources for executable policy/model evidence."""

    FROZEN_SNAPSHOT_PIT = "frozen_snapshot_pit"
    VERSIONED_CODE_REGISTRY = "versioned_code_registry"


@dataclass(frozen=True, slots=True)
class VersionedExecutionComponent:
    """One exact implementation key and contract version used at runtime."""

    implementation_key: str
    contract_version: int

    def __post_init__(self) -> None:
        """Reject implicit defaults and unversioned runtime components."""
        _identity(self.implementation_key, "implementation_key")
        _positive_integer(self.contract_version, "contract_version")

    def as_payload(self) -> Mapping[str, object]:
        """Return the canonical component identity."""
        return {
            "implementation_key": self.implementation_key,
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True, slots=True)
class ContentAddressedResearchInput:
    """One exact immutable input artifact required by a frozen snapshot."""

    input_id: str
    artifact_kind: str
    content_hash: str
    schema_hash: str

    def __post_init__(self) -> None:
        """Reject path-only or weakly identified research inputs."""
        _identity(self.input_id, "input_id")
        _identity(self.artifact_kind, "artifact_kind")
        _hash(self.content_hash, "content_hash")
        _hash(self.schema_hash, "schema_hash")

    def as_payload(self) -> Mapping[str, object]:
        """Return the deterministic input identity payload."""
        return {
            "input_id": self.input_id,
            "artifact_kind": self.artifact_kind,
            "content_hash": self.content_hash,
            "schema_hash": self.schema_hash,
        }


@dataclass(frozen=True, slots=True)
class PolicyModelEvidenceBinding:
    """Executable model implementation plus its immutable evidence source."""

    role: str
    implementation: VersionedExecutionComponent
    evidence_source: ExecutionEvidenceSource
    inputs: tuple[ContentAddressedResearchInput, ...]

    def __post_init__(self) -> None:
        """Require PIT inputs for moving rules and code identity for fixed models."""
        if self.role not in _POLICY_MODEL_ROLES:
            raise _error(
                "policy model role is unsupported",
                "invalid_policy_model_role",
                role=self.role,
            )
        if type(self.implementation) is not VersionedExecutionComponent:
            raise _error(
                "policy model implementation is not exact",
                "invalid_policy_model_binding",
                role=self.role,
            )
        if type(self.evidence_source) is not ExecutionEvidenceSource:
            raise _error(
                "policy model evidence source is not typed",
                "invalid_policy_model_binding",
                role=self.role,
            )
        raw_inputs_value: object = self.inputs
        if type(raw_inputs_value) is not tuple:
            raise _error(
                "policy model inputs must be an explicit tuple",
                "invalid_policy_model_binding",
                role=self.role,
            )
        raw_inputs = cast("tuple[object, ...]", raw_inputs_value)
        if any(type(item) is not ContentAddressedResearchInput for item in raw_inputs):
            raise _error(
                "policy model inputs must be content addressed",
                "invalid_policy_model_binding",
                role=self.role,
            )
        inputs = tuple(
            sorted(
                cast("tuple[ContentAddressedResearchInput, ...]", raw_inputs),
                key=lambda item: item.input_id.encode(),
            )
        )
        if len({item.input_id for item in inputs}) != len(inputs):
            raise _error(
                "policy model input identities must be unique",
                "invalid_policy_model_binding",
                role=self.role,
            )
        if (
            self.evidence_source is ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT
            and not inputs
        ):
            raise _error(
                "PIT policy models require frozen input evidence",
                "missing_policy_model_evidence",
                role=self.role,
            )
        if (
            self.evidence_source is ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY
            and inputs
        ):
            raise _error(
                "code-only policy models cannot imply mutable input evidence",
                "invalid_policy_model_binding",
                role=self.role,
            )
        object.__setattr__(self, "inputs", inputs)

    def as_payload(self) -> Mapping[str, object]:
        """Return complete model and evidence identity."""
        return {
            "role": self.role,
            "implementation": self.implementation.as_payload(),
            "evidence_source": self.evidence_source.value,
            "inputs": [item.as_payload() for item in self.inputs],
        }


@dataclass(frozen=True, slots=True)
class ResearchSnapshotBinding:
    """Exact snapshot and every content-addressed artifact used at execution."""

    exact_snapshot: ExactResearchSnapshot
    dataset_id: str
    source_snapshot_ids: tuple[str, ...]
    known_at_policy: str
    builder_version: str
    inputs: tuple[ContentAddressedResearchInput, ...]

    def __post_init__(self) -> None:
        """Canonicalize ordered evidence and fail closed on missing provenance."""
        if type(self.exact_snapshot) is not ExactResearchSnapshot:
            raise _error(
                "snapshot binding requires an exact snapshot identity",
                "invalid_snapshot_binding",
            )
        _identity(self.dataset_id, "dataset_id")
        _identity(self.known_at_policy, "known_at_policy")
        if self.known_at_policy != "sample_time":
            raise _error(
                "known-at policy lacks an executable timestamp contract",
                "unsupported_known_at_policy",
                known_at_policy=self.known_at_policy,
            )
        _identity(self.builder_version, "builder_version")
        raw_sources_value: object = self.source_snapshot_ids
        if type(raw_sources_value) is not tuple or not raw_sources_value:
            raise _error(
                "research snapshot must bind source snapshot identities",
                "missing_source_snapshot_identity",
            )
        raw_sources = cast("tuple[object, ...]", raw_sources_value)
        sources = tuple(
            sorted(_identity(item, "source_snapshot_id") for item in raw_sources)
        )
        if len(set(sources)) != len(sources):
            raise _error(
                "research snapshot source identities must be unique",
                "duplicate_source_snapshot_identity",
            )
        raw_inputs_value: object = self.inputs
        if type(raw_inputs_value) is not tuple or not raw_inputs_value:
            raise _error(
                "research snapshot must bind content-addressed inputs",
                "missing_research_input",
            )
        raw_inputs = cast("tuple[object, ...]", raw_inputs_value)
        if any(type(item) is not ContentAddressedResearchInput for item in raw_inputs):
            raise _error(
                "research snapshot inputs must use the exact input DTO",
                "invalid_research_input",
            )
        typed_inputs = cast("tuple[ContentAddressedResearchInput, ...]", raw_inputs)
        inputs = tuple(sorted(typed_inputs, key=lambda item: item.input_id.encode()))
        if len({item.input_id for item in inputs}) != len(inputs):
            raise _error(
                "research snapshot input identities must be unique",
                "duplicate_research_input",
            )
        object.__setattr__(self, "source_snapshot_ids", sources)
        object.__setattr__(self, "inputs", inputs)

    def as_payload(self) -> Mapping[str, object]:
        """Return the complete frozen snapshot identity."""
        return {
            "snapshot_id": self.exact_snapshot.snapshot_id,
            "dataset_id": self.dataset_id,
            "manifest_hash": self.exact_snapshot.manifest_hash,
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "known_at_policy": self.known_at_policy,
            "builder_version": self.builder_version,
            "inputs": [item.as_payload() for item in self.inputs],
        }


def research_data_feed_manifest_hash(snapshot: ResearchSnapshotBinding) -> str:
    """Hash the complete declared feed identity without trusting loaded frames."""
    if type(snapshot) is not ResearchSnapshotBinding:
        raise _error(
            "research feed manifest requires an exact snapshot binding",
            "invalid_research_snapshot_binding",
        )
    by_kind: dict[str, ContentAddressedResearchInput] = {}
    for evidence in snapshot.inputs:
        if evidence.artifact_kind not in _RESEARCH_FEED_ARTIFACT_KINDS:
            continue
        if evidence.artifact_kind in by_kind:
            raise _error(
                f"snapshot declares {evidence.artifact_kind} more than once",
                "duplicate_feed_artifact_kind",
                frame_kind=evidence.artifact_kind,
            )
        by_kind[evidence.artifact_kind] = evidence
    missing = tuple(
        kind for kind in _REQUIRED_RESEARCH_FEED_ARTIFACT_KINDS if kind not in by_kind
    )
    if missing:
        raise _error(
            "snapshot is missing required research feed artifacts",
            "missing_required_research_frame",
            frame_kinds=missing,
        )
    payload = {
        "schema_version": 1,
        "snapshot": {
            "snapshot_id": snapshot.exact_snapshot.snapshot_id,
            "manifest_hash": snapshot.exact_snapshot.manifest_hash,
            "dataset_id": snapshot.dataset_id,
            "source_snapshot_ids": list(snapshot.source_snapshot_ids),
            "known_at_policy": snapshot.known_at_policy,
            "builder_version": snapshot.builder_version,
        },
        "frames": [
            {
                "frame_kind": kind,
                **by_kind[kind].as_payload(),
            }
            for kind in _RESEARCH_FEED_ARTIFACT_KINDS
            if kind in by_kind
        ],
    }
    return hashlib.sha256(
        orjson.dumps(payload, option=orjson.OPT_SORT_KEYS),
    ).hexdigest()


def _canonical_factor_versions(
    raw_factors_value: object,
) -> tuple[tuple[str, int], ...]:
    """Canonicalize exact factor identity/version pairs."""
    if type(raw_factors_value) is not tuple:
        raise _error(
            "factor_versions must be an explicit tuple",
            "invalid_factor_identity",
        )
    raw_factors = cast("tuple[object, ...]", raw_factors_value)
    factors: list[tuple[str, int]] = []
    for raw_item in raw_factors:
        if type(raw_item) is not tuple:
            raise _error(
                "factor_versions must contain exact identity/version pairs",
                "invalid_factor_identity",
            )
        raw_pair = cast("tuple[object, ...]", raw_item)
        if len(raw_pair) != _FACTOR_IDENTITY_PART_COUNT:
            raise _error(
                "factor_versions must contain exact identity/version pairs",
                "invalid_factor_identity",
            )
        factor_id, version = raw_pair
        factors.append(
            (
                _identity(factor_id, "factor_id"),
                _positive_integer(version, "factor_version"),
            )
        )
    factors.sort(key=lambda item: item[0].encode())
    if len({factor_id for factor_id, _ in factors}) != len(factors):
        raise _error(
            "factor identities must be unique",
            "duplicate_factor_identity",
        )
    return tuple(factors)


@dataclass(frozen=True, slots=True)
class BaselineExecutorBinding:
    """Synthetic baseline executor identity without a fake catalog strategy."""

    baseline_ref: str
    kind: BaselinePlanKind
    descriptor_hash: str
    implementation_key: str
    executor_contract_version: int
    registry_manifest_hash: str
    factor_versions: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        """Freeze the registered deterministic baseline implementation."""
        _identity(self.baseline_ref, "baseline_ref")
        if type(self.kind) is not BaselinePlanKind:
            raise _error(
                "baseline kind must be exact and registered",
                "invalid_baseline_executor_binding",
            )
        _hash(self.descriptor_hash, "baseline_descriptor_hash")
        _identity(self.implementation_key, "baseline_implementation_key")
        _positive_integer(
            self.executor_contract_version,
            "baseline_executor_contract_version",
        )
        _hash(self.registry_manifest_hash, "baseline_registry_manifest_hash")
        factors = _canonical_factor_versions(self.factor_versions)
        if self.kind is BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT and factors:
            raise _error(
                "stock equal-weight baseline cannot depend on factor artifacts",
                "unexpected_baseline_factor_binding",
            )
        object.__setattr__(self, "factor_versions", factors)

    def as_payload(self) -> Mapping[str, object]:
        """Return exact synthetic baseline runner evidence."""
        return {
            "baseline_ref": self.baseline_ref,
            "kind": self.kind.value,
            "descriptor_hash": self.descriptor_hash,
            "implementation_key": self.implementation_key,
            "executor_contract_version": self.executor_contract_version,
            "registry_manifest_hash": self.registry_manifest_hash,
            "factor_versions": [
                {"factor_id": factor_id, "version": version}
                for factor_id, version in self.factor_versions
            ],
        }


@dataclass(frozen=True, slots=True)
class CodeEnvironmentLock:
    """Exact code revision and dependency/environment lock evidence."""

    code_version: str
    environment_lock_hash: str

    def __post_init__(self) -> None:
        """Reject unversioned execution environments."""
        _identity(self.code_version, "code_version")
        _hash(self.environment_lock_hash, "environment_lock_hash")

    def as_payload(self) -> Mapping[str, object]:
        """Return the code and environment lock payload."""
        return {
            "code_version": self.code_version,
            "environment_lock_hash": self.environment_lock_hash,
        }
