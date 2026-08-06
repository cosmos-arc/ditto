"""Unit tests for the constrained, explicitly registered baseline registry."""

from __future__ import annotations

import operator
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError


def _request(
    *,
    baseline_key: str,
    strategy: object | None = None,
) -> object:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselinePlanRequest,
        BaselineRef,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ExactResearchSnapshot,
        ExactUniverseIdentity,
    )

    return BaselinePlanRequest(
        baseline_ref=BaselineRef(baseline_key, 1),
        snapshot=ExactResearchSnapshot("snapshot-1", "a" * 64),
        universe=ExactUniverseIdentity("pit-universe-1", "b" * 64),
        exact_strategy=strategy,
    )


def test_builtin_registry_has_stable_sorted_execution_manifest() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        default_baseline_registry,
    )

    first = default_baseline_registry()
    second = default_baseline_registry()

    assert [item.ref.identity for item in first.descriptors] == [
        "etf_current_active.v1",
        "stock_universe_equal_weight.v1",
    ]
    assert first.manifest_hash == second.manifest_hash
    assert len(first.manifest_hash) == 64
    assert all(item.deterministic for item in first.descriptors)


def test_stock_equal_weight_builds_frozen_pit_plan_without_strategy_lookup() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselinePlanKind,
        default_baseline_registry,
    )

    plan = default_baseline_registry().plan(
        _request(baseline_key="stock_universe_equal_weight"),
    )

    assert plan.baseline_ref.identity == "stock_universe_equal_weight.v1"
    assert plan.kind is BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT
    assert plan.exact_strategy is None
    assert plan.semantics == (
        ("allocation", "equal_weight"),
        ("membership", "point_in_time"),
        ("rebalance", "fold_schedule"),
    )
    assert plan.execution_policy.identity == "a_share_stock_daily.v1"
    assert plan.snapshot.snapshot_id == "snapshot-1"
    assert plan.universe.universe_id == "pit-universe-1"
    assert len(plan.canonical_hash) == 64


def test_etf_current_active_requires_and_preserves_frozen_exact_identity() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselinePlanKind,
        default_baseline_registry,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ExactStrategyIdentity,
    )

    exact = ExactStrategyIdentity("r1_etf_rotation", 9, "c" * 64)
    plan = default_baseline_registry().plan(
        _request(baseline_key="etf_current_active", strategy=exact),
    )

    assert plan.kind is BaselinePlanKind.ETF_CURRENT_ACTIVE
    assert plan.exact_strategy is exact
    assert plan.exact_strategy.identity == "r1_etf_rotation@9"
    assert plan.semantics == (("strategy_resolution", "frozen_exact_version"),)
    assert plan.execution_policy.identity == "a_share_etf_daily.v1"


def test_etf_current_active_never_resolves_missing_identity_at_runtime() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        default_baseline_registry,
    )

    with pytest.raises(AppProcessError) as exc_info:
        default_baseline_registry().plan(
            _request(baseline_key="etf_current_active"),
        )

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "exact_baseline_strategy_identity_required",
        "baseline_identity": "etf_current_active.v1",
    }


@pytest.mark.parametrize(
    ("key", "version"),
    [
        ("unknown", 1),
        ("stock_universe_equal_weight", 2),
    ],
)
def test_unknown_baseline_key_or_version_fails_closed(key: str, version: int) -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineRef,
        default_baseline_registry,
    )

    source = _request(baseline_key="stock_universe_equal_weight")
    request = replace(source, baseline_ref=BaselineRef(key, version))

    with pytest.raises(AppProcessError) as exc_info:
        default_baseline_registry().plan(request)

    assert exc_info.value.details == {
        "code": "EXECUTOR_UNAVAILABLE",
        "reason": "unknown_baseline_runner",
        "baseline_identity": f"{key}.v{version}",
    }


class _CustomBuilder:
    def build(self, request: object, descriptor: object, policy: object) -> object:
        from ditto_application.processes.experiments.baseline_registry import (
            BaselineExecutionPlan,
        )

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
            semantics=(("rule", "custom"),),
        )


def _custom_registration(*, builder: object | None = None) -> object:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineDescriptor,
        BaselinePlanKind,
        BaselineRef,
        BaselineRegistration,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ResearchAssetLane,
        default_stock_execution_policy,
    )

    return BaselineRegistration(
        descriptor=BaselineDescriptor(
            ref=BaselineRef("custom_quality_equal_weight", 1),
            kind=BaselinePlanKind.CODE_REGISTERED_EXTENSION,
            lane=ResearchAssetLane.STOCK,
            implementation_key="research.baseline.custom_quality_equal_weight.v1",
            executor_contract_version=1,
            requires_exact_strategy=False,
            execution_policy_hash=default_stock_execution_policy().canonical_hash,
        ),
        execution_policy=default_stock_execution_policy(),
        builder=builder or _CustomBuilder(),
    )


def test_explicit_code_registration_supports_constrained_extension() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineRegistry,
    )

    registry = BaselineRegistry((_custom_registration(),))
    plan = registry.plan(_request(baseline_key="custom_quality_equal_weight"))

    assert plan.baseline_ref.identity == "custom_quality_equal_weight.v1"
    assert plan.semantics == (("rule", "custom"),)


def test_manifest_excludes_runtime_builder_object_identity() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineRegistry,
    )

    first = BaselineRegistry((_custom_registration(builder=_CustomBuilder()),))
    second = BaselineRegistry((_custom_registration(builder=_CustomBuilder()),))

    assert first.manifest_hash == second.manifest_hash


def test_duplicate_explicit_registration_fails_closed() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineRegistry,
    )

    registration = _custom_registration()
    with pytest.raises(AppProcessError) as exc_info:
        BaselineRegistry((registration, registration))

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "duplicate_baseline_runner"


def test_reserved_etf_identity_cannot_disable_exact_strategy_requirement() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineDescriptor,
        BaselinePlanKind,
        BaselineRef,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ResearchAssetLane,
        default_etf_execution_policy,
    )

    policy = default_etf_execution_policy()
    with pytest.raises(AppProcessError) as exc_info:
        BaselineDescriptor(
            ref=BaselineRef("etf_current_active", 1),
            kind=BaselinePlanKind.ETF_CURRENT_ACTIVE,
            lane=ResearchAssetLane.ETF,
            implementation_key="research.baseline.etf_current_active.v1",
            executor_contract_version=1,
            requires_exact_strategy=False,
            execution_policy_hash=policy.canonical_hash,
        )

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "reserved_baseline_identity_drift",
        "baseline_identity": "etf_current_active.v1",
    }


def test_code_extension_cannot_impersonate_a_builtin_plan_kind() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineDescriptor,
        BaselinePlanKind,
        BaselineRef,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ResearchAssetLane,
        default_stock_execution_policy,
    )

    policy = default_stock_execution_policy()
    with pytest.raises(AppProcessError) as exc_info:
        BaselineDescriptor(
            ref=BaselineRef("custom_equal_weight", 1),
            kind=BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
            lane=ResearchAssetLane.STOCK,
            implementation_key="research.baseline.custom_equal_weight.v1",
            executor_contract_version=1,
            requires_exact_strategy=False,
            execution_policy_hash=policy.canonical_hash,
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "builtin_baseline_kind_reserved",
        "baseline_identity": "custom_equal_weight.v1",
    }


def test_reserved_identity_cannot_register_a_custom_builder() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineDescriptor,
        BaselinePlanKind,
        BaselineRef,
        BaselineRegistration,
        BaselineRegistry,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ResearchAssetLane,
        default_etf_execution_policy,
    )

    policy = default_etf_execution_policy()
    registration = BaselineRegistration(
        descriptor=BaselineDescriptor(
            ref=BaselineRef("etf_current_active", 1),
            kind=BaselinePlanKind.ETF_CURRENT_ACTIVE,
            lane=ResearchAssetLane.ETF,
            implementation_key="research.baseline.etf_current_active.v1",
            executor_contract_version=1,
            requires_exact_strategy=True,
            execution_policy_hash=policy.canonical_hash,
        ),
        execution_policy=policy,
        builder=_CustomBuilder(),
    )

    with pytest.raises(AppProcessError) as exc_info:
        BaselineRegistry((registration,))

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "reserved_baseline_builder_drift",
        "baseline_identity": "etf_current_active.v1",
    }


def test_reserved_identity_hash_includes_executor_contract_version() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineDescriptor,
        BaselinePlanKind,
        BaselineRef,
    )
    from ditto_application.processes.experiments.execution_contracts import (
        ResearchAssetLane,
        default_stock_execution_policy,
    )

    policy = default_stock_execution_policy()
    with pytest.raises(AppProcessError) as exc_info:
        BaselineDescriptor(
            ref=BaselineRef("stock_universe_equal_weight", 1),
            kind=BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
            lane=ResearchAssetLane.STOCK,
            implementation_key="research.baseline.stock_universe_equal_weight.v1",
            executor_contract_version=2,
            requires_exact_strategy=False,
            execution_policy_hash=policy.canonical_hash,
        )

    assert exc_info.value.details["reason"] == "reserved_baseline_identity_drift"


def test_registry_state_and_lookup_mapping_are_immutable_after_manifest() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        default_baseline_registry,
    )

    registry = default_baseline_registry()
    lookup_field = "_by_identity"
    manifest_field = "_manifest_hash"
    lookup = cast("Mapping[str, object]", getattr(registry, lookup_field))

    with pytest.raises(FrozenInstanceError):
        setattr(registry, manifest_field, "0" * 64)
    with pytest.raises(TypeError):
        operator.setitem(lookup, "forged.v1", object())


def test_registry_rejects_builder_output_that_drifts_from_descriptor() -> None:
    from ditto_application.processes.experiments.baseline_registry import (
        BaselineRegistry,
    )

    class _DriftingBuilder(_CustomBuilder):
        def build(
            self,
            request: object,
            descriptor: object,
            policy: object,
        ) -> object:
            result = super().build(request, descriptor, policy)
            return replace(result, implementation_key="x")

    registry = BaselineRegistry(
        (_custom_registration(builder=_DriftingBuilder()),),
    )
    with pytest.raises(AppProcessError) as exc_info:
        registry.plan(_request(baseline_key="custom_quality_equal_weight"))

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "baseline_plan_identity_drift",
        "baseline_identity": "custom_quality_equal_weight.v1",
    }
