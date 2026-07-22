"""Constrained baseline registry with explicit code-only extension points."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import NoReturn, Protocol, cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ExactUniverseIdentity,
    ResearchAssetLane,
    ResearchExecutionPolicy,
    default_etf_execution_policy,
    default_stock_execution_policy,
)

__all__ = [
    "BaselineDescriptor",
    "BaselineExecutionPlan",
    "BaselinePlanBuilder",
    "BaselinePlanKind",
    "BaselinePlanRequest",
    "BaselineRef",
    "BaselineRegistration",
    "BaselineRegistry",
    "default_baseline_registry",
]

_SHA256_HEX_LENGTH = 64
_SEMANTIC_PAIR_LENGTH = 2


def _raise_registry_error(
    message: str,
    *,
    reason: str,
    code: str = "SPEC_INVALID",
    **details: object,
) -> NoReturn:
    payload: dict[str, object] = {"code": code, "reason": reason}
    payload.update(details)
    raise AppProcessError(message, details=payload)


def _canonical_string(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _raise_registry_error(
            f"{field_name} must be a canonical non-empty string",
            reason="invalid_baseline_identity",
            field=field_name,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _raise_registry_error(
            f"{field_name} must have a canonical UTF-8 identity",
            reason="invalid_baseline_identity",
            field=field_name,
        )
    return value


def _positive_version(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        _raise_registry_error(
            f"{field_name} must be a positive integer",
            reason="invalid_baseline_version",
            field=field_name,
        )
    return value


def _canonical_hash(payload: object) -> str:
    try:
        encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppProcessError(
            "baseline contract has no canonical JSON identity",
            details={
                "code": "SPEC_INVALID",
                "reason": "invalid_baseline_contract_identity",
                "codec_error": type(exc).__name__,
            },
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _is_canonical_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class BaselineRef:
    """Stable baseline key and exact integer version."""

    key: str
    version: int

    def __post_init__(self) -> None:
        """Validate the stable key and positive exact version."""
        _canonical_string(self.key, field_name="baseline_key")
        _positive_version(self.version, field_name="baseline_version")

    @property
    def identity(self) -> str:
        """Return the exact ``key.vN`` execution identity."""
        return f"{self.key}.v{self.version}"

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete baseline reference payload."""
        return {"key": self.key, "version": self.version}


class BaselinePlanKind(StrEnum):
    """Constrained execution-plan families understood by the worker."""

    STOCK_UNIVERSE_EQUAL_WEIGHT = "stock_universe_equal_weight"
    ETF_CURRENT_ACTIVE = "etf_current_active"
    CODE_REGISTERED_EXTENSION = "code_registered_extension"


def _validate_descriptor_namespace(descriptor: BaselineDescriptor) -> None:
    expected_by_identity = {
        "stock_universe_equal_weight.v1": (
            BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
            ResearchAssetLane.STOCK,
            "research.baseline.stock_universe_equal_weight.v1",
            1,
            False,
            default_stock_execution_policy().canonical_hash,
        ),
        "etf_current_active.v1": (
            BaselinePlanKind.ETF_CURRENT_ACTIVE,
            ResearchAssetLane.ETF,
            "research.baseline.etf_current_active.v1",
            1,
            True,
            default_etf_execution_policy().canonical_hash,
        ),
    }
    reserved_keys = frozenset(
        {"stock_universe_equal_weight", "etf_current_active"},
    )
    identity = descriptor.ref.identity
    expected = expected_by_identity.get(identity)
    if expected is not None:
        actual = (
            descriptor.kind,
            descriptor.lane,
            descriptor.implementation_key,
            descriptor.executor_contract_version,
            descriptor.requires_exact_strategy,
            descriptor.execution_policy_hash,
        )
        if actual != expected:
            _raise_registry_error(
                "reserved baseline execution identity cannot be redefined",
                code="REPRODUCIBILITY_FAILED",
                reason="reserved_baseline_identity_drift",
                baseline_identity=identity,
            )
        return
    if descriptor.ref.key in reserved_keys:
        _raise_registry_error(
            "reserved baseline key has no registered version",
            code="EXECUTOR_UNAVAILABLE",
            reason="reserved_baseline_identity_drift",
            baseline_identity=identity,
        )
    if descriptor.kind is not BaselinePlanKind.CODE_REGISTERED_EXTENSION:
        _raise_registry_error(
            "builtin baseline plan kinds are reserved",
            reason="builtin_baseline_kind_reserved",
            baseline_identity=identity,
        )


@dataclass(frozen=True, slots=True)
class BaselineDescriptor:
    """Stable baseline execution identity; contains no Python import path."""

    ref: BaselineRef
    kind: BaselinePlanKind
    lane: ResearchAssetLane
    implementation_key: str
    executor_contract_version: int
    requires_exact_strategy: bool
    execution_policy_hash: str
    deterministic: bool = True
    canonical_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate and hash the descriptor execution identity."""
        typed_fields = (
            (self.ref, BaselineRef, "ref"),
            (self.kind, BaselinePlanKind, "kind"),
            (self.lane, ResearchAssetLane, "lane"),
        )
        for value, expected, field_name in typed_fields:
            if type(value) is not expected:
                _raise_registry_error(
                    f"baseline descriptor {field_name} has the wrong type",
                    reason="invalid_baseline_descriptor_field",
                    field=field_name,
                )
        _canonical_string(
            self.implementation_key,
            field_name="baseline_implementation_key",
        )
        _positive_version(
            self.executor_contract_version,
            field_name="baseline_executor_contract_version",
        )
        if type(self.requires_exact_strategy) is not bool:
            _raise_registry_error(
                "requires_exact_strategy must be bool",
                reason="invalid_baseline_descriptor_field",
                field="requires_exact_strategy",
            )
        if type(self.deterministic) is not bool or not self.deterministic:
            _raise_registry_error(
                "research baseline runners must be deterministic",
                code="REPRODUCIBILITY_FAILED",
                reason="nondeterministic_baseline_runner_forbidden",
            )
        if not _is_canonical_hash(self.execution_policy_hash):
            _raise_registry_error(
                "execution_policy_hash must be a lowercase SHA-256 digest",
                reason="invalid_baseline_policy_hash",
            )
        _validate_descriptor_namespace(self)
        object.__setattr__(
            self,
            "canonical_hash",
            _canonical_hash(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return execution identity fields only; UI metadata is absent."""
        return {
            "deterministic": self.deterministic,
            "execution_policy_hash": self.execution_policy_hash,
            "executor_contract_version": self.executor_contract_version,
            "implementation_key": self.implementation_key,
            "kind": self.kind.value,
            "lane": self.lane.value,
            "ref": self.ref.canonical_payload(),
            "requires_exact_strategy": self.requires_exact_strategy,
        }


@dataclass(frozen=True, slots=True)
class BaselinePlanRequest:
    """Exact frozen inputs from which one baseline plan may be built."""

    baseline_ref: BaselineRef
    snapshot: ExactResearchSnapshot
    universe: ExactUniverseIdentity
    exact_strategy: ExactStrategyIdentity | None = None

    def __post_init__(self) -> None:
        """Require exact typed snapshot, universe, and optional strategy inputs."""
        typed_fields = (
            (self.baseline_ref, BaselineRef, "baseline_ref"),
            (self.snapshot, ExactResearchSnapshot, "snapshot"),
            (self.universe, ExactUniverseIdentity, "universe"),
        )
        for value, expected, field_name in typed_fields:
            if type(value) is not expected:
                _raise_registry_error(
                    f"baseline request {field_name} has the wrong type",
                    reason="invalid_baseline_plan_request",
                    field=field_name,
                )
        if (
            self.exact_strategy is not None
            and type(self.exact_strategy) is not ExactStrategyIdentity
        ):
            _raise_registry_error(
                "exact_strategy must be ExactStrategyIdentity or None",
                reason="invalid_baseline_plan_request",
                field="exact_strategy",
            )


def _validated_semantics(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        _raise_registry_error(
            "baseline semantics must be tuple[tuple[str, str], ...]",
            reason="invalid_baseline_plan_semantics",
        )
    raw_items = cast("tuple[object, ...]", value)
    items: list[tuple[str, str]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, tuple):
            _raise_registry_error(
                "baseline semantics entries must be string pairs",
                reason="invalid_baseline_plan_semantics",
            )
        pair = cast("tuple[object, ...]", raw_item)
        if len(pair) != _SEMANTIC_PAIR_LENGTH:
            _raise_registry_error(
                "baseline semantics entries must be string pairs",
                reason="invalid_baseline_plan_semantics",
            )
        key, item = pair
        items.append(
            (
                _canonical_string(key, field_name="baseline_semantic_key"),
                _canonical_string(item, field_name="baseline_semantic_value"),
            )
        )
    if tuple(items) != tuple(sorted(items)) or len(
        {key for key, _ in items},
    ) != len(items):
        _raise_registry_error(
            "baseline semantics must have unique keys in canonical order",
            reason="invalid_baseline_plan_semantics",
        )
    return tuple(items)


@dataclass(frozen=True, slots=True)
class BaselineExecutionPlan:
    """Worker-facing frozen plan; building it performs no data or catalog I/O."""

    baseline_ref: BaselineRef
    kind: BaselinePlanKind
    implementation_key: str
    executor_contract_version: int
    descriptor_hash: str
    snapshot: ExactResearchSnapshot
    universe: ExactUniverseIdentity
    execution_policy: ResearchExecutionPolicy
    exact_strategy: ExactStrategyIdentity | None
    semantics: tuple[tuple[str, str], ...]
    canonical_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate and hash every worker-facing plan semantic."""
        typed_fields = (
            (self.baseline_ref, BaselineRef, "baseline_ref"),
            (self.kind, BaselinePlanKind, "kind"),
            (self.snapshot, ExactResearchSnapshot, "snapshot"),
            (self.universe, ExactUniverseIdentity, "universe"),
            (self.execution_policy, ResearchExecutionPolicy, "execution_policy"),
        )
        for value, expected, field_name in typed_fields:
            if type(value) is not expected:
                _raise_registry_error(
                    f"baseline plan {field_name} has the wrong type",
                    reason="invalid_baseline_execution_plan",
                    field=field_name,
                )
        _canonical_string(self.implementation_key, field_name="implementation_key")
        _positive_version(
            self.executor_contract_version,
            field_name="executor_contract_version",
        )
        if not _is_canonical_hash(self.descriptor_hash):
            _raise_registry_error(
                "descriptor_hash must be a lowercase SHA-256 digest",
                reason="invalid_baseline_execution_plan",
                field="descriptor_hash",
            )
        if (
            self.exact_strategy is not None
            and type(self.exact_strategy) is not ExactStrategyIdentity
        ):
            _raise_registry_error(
                "exact_strategy must be ExactStrategyIdentity or None",
                reason="invalid_baseline_execution_plan",
                field="exact_strategy",
            )
        object.__setattr__(self, "semantics", _validated_semantics(self.semantics))
        object.__setattr__(
            self,
            "canonical_hash",
            _canonical_hash(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return all fields that affect this baseline execution."""
        strategy_payload = (
            None
            if self.exact_strategy is None
            else self.exact_strategy.canonical_payload()
        )
        return {
            "baseline_ref": self.baseline_ref.canonical_payload(),
            "descriptor_hash": self.descriptor_hash,
            "exact_strategy": strategy_payload,
            "execution_policy": self.execution_policy.canonical_payload(),
            "executor_contract_version": self.executor_contract_version,
            "implementation_key": self.implementation_key,
            "kind": self.kind.value,
            "semantics": [list(item) for item in self.semantics],
            "snapshot": self.snapshot.canonical_payload(),
            "universe": self.universe.canonical_payload(),
        }


class BaselinePlanBuilder(Protocol):
    """Explicit code seam for deterministic baseline plan construction."""

    def build(
        self,
        request: BaselinePlanRequest,
        descriptor: BaselineDescriptor,
        policy: ResearchExecutionPolicy,
    ) -> BaselineExecutionPlan:
        """Build a frozen plan without resolving active/latest state."""
        ...


@dataclass(frozen=True, slots=True)
class BaselineRegistration:
    """One explicitly supplied descriptor, policy, and Python builder object."""

    descriptor: BaselineDescriptor
    execution_policy: ResearchExecutionPolicy
    builder: BaselinePlanBuilder

    def __post_init__(self) -> None:
        """Bind one descriptor to an exact policy and explicit builder object."""
        if type(self.descriptor) is not BaselineDescriptor:
            _raise_registry_error(
                "registration descriptor must be BaselineDescriptor",
                reason="invalid_baseline_registration",
            )
        if type(self.execution_policy) is not ResearchExecutionPolicy:
            _raise_registry_error(
                "registration policy must be ResearchExecutionPolicy",
                reason="invalid_baseline_registration",
            )
        if not callable(getattr(self.builder, "build", None)):
            _raise_registry_error(
                "registration builder must implement BaselinePlanBuilder",
                reason="invalid_baseline_registration",
            )
        if (
            self.descriptor.execution_policy_hash
            != self.execution_policy.canonical_hash
            or self.descriptor.lane is not self.execution_policy.lane
        ):
            _raise_registry_error(
                "baseline descriptor and execution policy identities do not match",
                reason="baseline_policy_identity_mismatch",
                baseline_identity=self.descriptor.ref.identity,
            )


class _StockEqualWeightBuilder:
    def build(
        self,
        request: BaselinePlanRequest,
        descriptor: BaselineDescriptor,
        policy: ResearchExecutionPolicy,
    ) -> BaselineExecutionPlan:
        return _plan(
            request,
            descriptor,
            policy,
            semantics=(
                ("allocation", "equal_weight"),
                ("membership", "point_in_time"),
                ("rebalance", "fold_schedule"),
            ),
        )


class _ETFCurrentActiveBuilder:
    def build(
        self,
        request: BaselinePlanRequest,
        descriptor: BaselineDescriptor,
        policy: ResearchExecutionPolicy,
    ) -> BaselineExecutionPlan:
        return _plan(
            request,
            descriptor,
            policy,
            semantics=(("strategy_resolution", "frozen_exact_version"),),
        )


def _plan(
    request: BaselinePlanRequest,
    descriptor: BaselineDescriptor,
    policy: ResearchExecutionPolicy,
    *,
    semantics: tuple[tuple[str, str], ...],
) -> BaselineExecutionPlan:
    return BaselineExecutionPlan(
        baseline_ref=descriptor.ref,
        kind=descriptor.kind,
        implementation_key=descriptor.implementation_key,
        executor_contract_version=descriptor.executor_contract_version,
        descriptor_hash=descriptor.canonical_hash,
        snapshot=request.snapshot,
        universe=request.universe,
        execution_policy=policy,
        exact_strategy=request.exact_strategy,
        semantics=semantics,
    )


def _validate_reserved_builder(registration: BaselineRegistration) -> None:
    expected_types: dict[str, type[object]] = {
        "stock_universe_equal_weight.v1": _StockEqualWeightBuilder,
        "etf_current_active.v1": _ETFCurrentActiveBuilder,
    }
    identity = registration.descriptor.ref.identity
    expected_type = expected_types.get(identity)
    if expected_type is not None and type(registration.builder) is not expected_type:
        _raise_registry_error(
            "reserved baseline identity requires its builtin builder",
            code="REPRODUCIBILITY_FAILED",
            reason="reserved_baseline_builder_drift",
            baseline_identity=identity,
        )


@dataclass(frozen=True, slots=True, init=False)
class BaselineRegistry:
    """Immutable exact-version registry; it performs no discovery or imports."""

    _registrations: tuple[BaselineRegistration, ...]
    _by_identity: Mapping[str, BaselineRegistration]
    _manifest_hash: str

    def __init__(self, registrations: Sequence[object]) -> None:
        raw = tuple(registrations)
        if not raw or any(type(item) is not BaselineRegistration for item in raw):
            _raise_registry_error(
                "registry accepts an explicit non-empty registration sequence",
                reason="invalid_baseline_registration",
            )
        resolved = cast("tuple[BaselineRegistration, ...]", raw)
        for registration in resolved:
            _validate_reserved_builder(registration)
        identities = tuple(item.descriptor.ref.identity for item in resolved)
        if len(set(identities)) != len(identities):
            _raise_registry_error(
                "baseline registration identities must be unique",
                reason="duplicate_baseline_runner",
                baseline_identities=identities,
            )
        ordered = tuple(sorted(resolved, key=lambda item: item.descriptor.ref.identity))
        object.__setattr__(self, "_registrations", ordered)
        object.__setattr__(
            self,
            "_by_identity",
            MappingProxyType(
                {item.descriptor.ref.identity: item for item in ordered},
            ),
        )
        object.__setattr__(
            self,
            "_manifest_hash",
            _canonical_hash(
                [item.descriptor.canonical_payload() for item in ordered],
            ),
        )

    @property
    def descriptors(self) -> tuple[BaselineDescriptor, ...]:
        """Return descriptors in stable identity order."""
        return tuple(item.descriptor for item in self._registrations)

    @property
    def manifest_hash(self) -> str:
        """Return a hash that excludes Python builder object identity."""
        return self._manifest_hash

    def lookup(self, ref: BaselineRef) -> BaselineRegistration:
        """Resolve one exact key/version or fail closed."""
        if type(ref) is not BaselineRef:
            _raise_registry_error(
                "baseline lookup requires BaselineRef",
                reason="invalid_baseline_identity",
            )
        registration = self._by_identity.get(ref.identity)
        if registration is None or registration.descriptor.ref.identity != ref.identity:
            _raise_registry_error(
                f"unknown baseline runner: {ref.identity}",
                code="EXECUTOR_UNAVAILABLE",
                reason="unknown_baseline_runner",
                baseline_identity=ref.identity,
            )
        return registration

    def plan(self, request: BaselinePlanRequest) -> BaselineExecutionPlan:
        """Build and fence one plan against its registered execution identity."""
        if type(request) is not BaselinePlanRequest:
            _raise_registry_error(
                "baseline plan requires BaselinePlanRequest",
                reason="invalid_baseline_plan_request",
            )
        registration = self.lookup(request.baseline_ref)
        descriptor = registration.descriptor
        self._validate_exact_strategy(request, descriptor)
        plan = registration.builder.build(
            request,
            descriptor,
            registration.execution_policy,
        )
        if type(plan) is not BaselineExecutionPlan or not self._matches_registration(
            plan,
            request,
            registration,
        ):
            _raise_registry_error(
                "baseline builder output drifted from its registration",
                code="REPRODUCIBILITY_FAILED",
                reason="baseline_plan_identity_drift",
                baseline_identity=descriptor.ref.identity,
            )
        return plan

    @staticmethod
    def _validate_exact_strategy(
        request: BaselinePlanRequest,
        descriptor: BaselineDescriptor,
    ) -> None:
        if descriptor.requires_exact_strategy and request.exact_strategy is None:
            _raise_registry_error(
                "ETF current-active baseline requires a frozen exact version",
                code="REPRODUCIBILITY_FAILED",
                reason="exact_baseline_strategy_identity_required",
                baseline_identity=descriptor.ref.identity,
            )
        if (
            not descriptor.requires_exact_strategy
            and request.exact_strategy is not None
        ):
            _raise_registry_error(
                "baseline does not accept a strategy identity",
                code="REPRODUCIBILITY_FAILED",
                reason="unexpected_baseline_strategy_identity",
                baseline_identity=descriptor.ref.identity,
            )

    @staticmethod
    def _matches_registration(
        plan: BaselineExecutionPlan,
        request: BaselinePlanRequest,
        registration: BaselineRegistration,
    ) -> bool:
        descriptor = registration.descriptor
        policy = registration.execution_policy
        return (
            plan.baseline_ref == descriptor.ref
            and plan.kind is descriptor.kind
            and plan.implementation_key == descriptor.implementation_key
            and plan.executor_contract_version == descriptor.executor_contract_version
            and plan.descriptor_hash == descriptor.canonical_hash
            and plan.snapshot == request.snapshot
            and plan.universe == request.universe
            and plan.exact_strategy == request.exact_strategy
            and plan.execution_policy == policy
            and plan.execution_policy.canonical_hash == descriptor.execution_policy_hash
        )


def _builtin_registration(
    *,
    ref: BaselineRef,
    kind: BaselinePlanKind,
    policy: ResearchExecutionPolicy,
    implementation_key: str,
    requires_exact_strategy: bool,
    builder: BaselinePlanBuilder,
) -> BaselineRegistration:
    return BaselineRegistration(
        descriptor=BaselineDescriptor(
            ref=ref,
            kind=kind,
            lane=policy.lane,
            implementation_key=implementation_key,
            executor_contract_version=1,
            requires_exact_strategy=requires_exact_strategy,
            execution_policy_hash=policy.canonical_hash,
        ),
        execution_policy=policy,
        builder=builder,
    )


def _builtin_registrations() -> tuple[BaselineRegistration, ...]:
    stock_policy = default_stock_execution_policy()
    etf_policy = default_etf_execution_policy()
    return (
        _builtin_registration(
            ref=BaselineRef("stock_universe_equal_weight", 1),
            kind=BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
            policy=stock_policy,
            implementation_key="research.baseline.stock_universe_equal_weight.v1",
            requires_exact_strategy=False,
            builder=_StockEqualWeightBuilder(),
        ),
        _builtin_registration(
            ref=BaselineRef("etf_current_active", 1),
            kind=BaselinePlanKind.ETF_CURRENT_ACTIVE,
            policy=etf_policy,
            implementation_key="research.baseline.etf_current_active.v1",
            requires_exact_strategy=True,
            builder=_ETFCurrentActiveBuilder(),
        ),
    )


def default_baseline_registry(
    extra_registrations: Sequence[BaselineRegistration] = (),
) -> BaselineRegistry:
    """Build the v1 registry plus explicit, code-supplied extension registrations."""
    return BaselineRegistry((*_builtin_registrations(), *extra_registrations))
