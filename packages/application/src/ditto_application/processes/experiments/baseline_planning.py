"""Strict adapter from persisted planning envelopes to baseline registrations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, cast

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselinePlanRequest,
    BaselineRef,
    BaselineRegistration,
    BaselineRegistry,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor as PlanningBaselineDescriptor,
)

__all__ = [
    "BaselinePlanningResolution",
    "build_frozen_baseline_plan",
    "resolve_planning_baseline",
]

_DESCRIPTOR_SCHEMA_VERSION = 1
_DESCRIPTOR_REFS = {
    "stock-universe-equal-weight": BaselineRef("stock_universe_equal_weight", 1),
    "etf-current-active": BaselineRef("etf_current_active", 1),
}
_ETF_PAYLOAD_KEYS = frozenset({"strategy_id", "version", "spec_hash"})


def _fail(
    message: str,
    *,
    reason: str,
    code: str = "SPEC_INVALID",
    **details: object,
) -> NoReturn:
    raise AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


@dataclass(frozen=True, slots=True)
class BaselinePlanningResolution:
    """Registered runner identity frozen before authority and data reads."""

    ref: BaselineRef
    registration: BaselineRegistration
    exact_strategy: ExactStrategyIdentity | None
    registry_manifest_hash: str

    def __post_init__(self) -> None:
        """Reject constructed resolutions that bypassed the strict adapter."""
        if (
            type(self.ref) is not BaselineRef
            or type(self.registration) is not BaselineRegistration
            or self.registration.descriptor.ref != self.ref
            or (
                self.exact_strategy is not None
                and type(self.exact_strategy) is not ExactStrategyIdentity
            )
        ):
            _fail(
                "baseline planning resolution is invalid",
                reason="invalid_baseline_planning_resolution",
            )


def _exact_etf_strategy(
    payload: Mapping[str, object],
) -> ExactStrategyIdentity:
    if set(payload) != set(_ETF_PAYLOAD_KEYS):
        _fail(
            "ETF baseline must freeze strategy_id, version, and spec_hash",
            reason="invalid_etf_baseline_payload",
        )
    strategy_id = payload.get("strategy_id")
    version = payload.get("version")
    spec_hash = payload.get("spec_hash")
    if (
        type(strategy_id) is not str
        or type(version) is not int
        or type(spec_hash) is not str
    ):
        _fail(
            "ETF baseline exact strategy fields have invalid types",
            reason="invalid_etf_baseline_payload",
        )
    return ExactStrategyIdentity(strategy_id, version, spec_hash)


def resolve_planning_baseline(
    descriptor: PlanningBaselineDescriptor,
    registry: BaselineRegistry,
) -> BaselinePlanningResolution:
    """Resolve only approved v1 planning names into exact code registrations."""
    if type(descriptor) is not PlanningBaselineDescriptor:
        _fail(
            "planning baseline must use the exact descriptor DTO",
            reason="invalid_planning_baseline_descriptor",
        )
    if type(registry) is not BaselineRegistry:
        _fail(
            "baseline registry has the wrong type", reason="invalid_baseline_registry"
        )
    if descriptor.schema_version != _DESCRIPTOR_SCHEMA_VERSION:
        _fail(
            "planning baseline schema version is unsupported",
            code="EXECUTOR_UNAVAILABLE",
            reason="unknown_planning_baseline_descriptor",
            descriptor_type=descriptor.descriptor_type,
            schema_version=descriptor.schema_version,
        )
    ref = _DESCRIPTOR_REFS.get(descriptor.descriptor_type)
    if ref is None:
        _fail(
            "planning baseline descriptor has no registered executor",
            code="EXECUTOR_UNAVAILABLE",
            reason="unknown_planning_baseline_descriptor",
            descriptor_type=descriptor.descriptor_type,
            schema_version=descriptor.schema_version,
        )
    payload = cast("Mapping[str, object]", descriptor.payload)
    exact_strategy: ExactStrategyIdentity | None
    if ref.key == "etf_current_active":
        exact_strategy = _exact_etf_strategy(payload)
    else:
        if payload:
            _fail(
                "stock equal-weight baseline does not accept moving inputs",
                reason="invalid_stock_baseline_payload",
            )
        exact_strategy = None
    registration = registry.lookup(ref)
    return BaselinePlanningResolution(
        ref=ref,
        registration=registration,
        exact_strategy=exact_strategy,
        registry_manifest_hash=registry.manifest_hash,
    )


def build_frozen_baseline_plan(
    resolution: BaselinePlanningResolution,
    *,
    registry: BaselineRegistry,
    snapshot: ExactResearchSnapshot,
    universe: ExactUniverseIdentity,
) -> BaselineExecutionPlan:
    """Bind the preflight registration to exact snapshot and PIT membership."""
    if type(resolution) is not BaselinePlanningResolution:
        _fail(
            "baseline resolution has the wrong type",
            reason="invalid_baseline_planning_resolution",
        )
    if type(registry) is not BaselineRegistry:
        _fail(
            "baseline registry has the wrong type", reason="invalid_baseline_registry"
        )
    if registry.manifest_hash != resolution.registry_manifest_hash:
        _fail(
            "baseline registry changed after preflight",
            code="REPRODUCIBILITY_FAILED",
            reason="baseline_registry_manifest_drift",
        )
    registration = registry.lookup(resolution.ref)
    if (
        registration.descriptor != resolution.registration.descriptor
        or registration.execution_policy != resolution.registration.execution_policy
    ):
        _fail(
            "baseline registration changed after preflight",
            code="REPRODUCIBILITY_FAILED",
            reason="baseline_registration_drift",
        )
    return registry.plan(
        BaselinePlanRequest(
            baseline_ref=resolution.ref,
            snapshot=snapshot,
            universe=universe,
            exact_strategy=resolution.exact_strategy,
        )
    )
