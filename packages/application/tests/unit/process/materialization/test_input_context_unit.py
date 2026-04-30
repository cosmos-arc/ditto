"""Tests for InputContext parameter object and refactored InputProvider protocol."""

from __future__ import annotations

import dataclasses
import inspect

import polars as pl
import pytest
from ditto_analytics.materialization import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
    DerivedRunMode,
    DerivedRunTrigger,
)
from ditto_application.process.materialization.types import (
    DerivedInputProvider,
    InMemoryDerivedInputProvider,
    InputContext,
    UnavailableDerivedInputProvider,
)
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(**overrides: object) -> DerivedSpec:
    defaults: dict[str, object] = {
        "id": "test.derived",
        "version": 1,
        "role": DerivedRole.FEATURE,
        "materialization_profile": MaterializationProfile.DERIVE,
        "expression": "close",
    }
    defaults.update(overrides)
    return DerivedSpec(**defaults)  # type: ignore[arg-type]


def _make_request(**overrides: object) -> DerivedMaterializationRequest:
    defaults: dict[str, object] = {
        "derived_id": "test.derived",
        "version": 1,
        "mode": DerivedRunMode.FULL,
        "request_start": "2024-01-01",
        "request_end": "2024-01-31",
        "trigger": DerivedRunTrigger.MANUAL,
        "source_snapshot_id": None,
    }
    defaults.update(overrides)
    return DerivedMaterializationRequest(**defaults)  # type: ignore[arg-type]


def _make_plan(**overrides: object) -> DerivedExecutionPlan:
    defaults: dict[str, object] = {
        "derived_id": "test.derived",
        "version": 1,
        "profile": MaterializationProfile.DERIVE,
        "mode": DerivedRunMode.FULL,
        "request_start": "2024-01-01",
        "request_end": "2024-01-31",
        "compute_start": "2024-01-01",
        "compute_end": "2024-01-31",
        "partitions": ("2024",),
        "lookback": 0,
        "requires_full_day": False,
    }
    defaults.update(overrides)
    return DerivedExecutionPlan(**defaults)  # type: ignore[arg-type]


def _make_context(**overrides: object) -> InputContext:
    defaults: dict[str, object] = {
        "spec": _make_spec(),
        "request": _make_request(),
        "plan": _make_plan(),
        "dependencies": ("close",),
    }
    defaults.update(overrides)
    return InputContext(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# InputContext
# ---------------------------------------------------------------------------


class TestInputContext:
    def test_is_frozen_dataclass(self) -> None:
        """InputContext should be a frozen dataclass, rejecting attribute mutation."""
        ctx = _make_context()
        assert dataclasses.is_dataclass(ctx)
        assert dataclasses.is_dataclass(type(ctx))
        # Frozen dataclasses raise AttributeError on assignment
        with pytest.raises(AttributeError):
            ctx.spec = _make_spec()  # type: ignore[misc]

    def test_stores_all_fields(self) -> None:
        """InputContext should store spec, request, plan, and dependencies."""
        spec = _make_spec(id="my.derived")
        request = _make_request(derived_id="my.derived")
        plan = _make_plan(derived_id="my.derived")
        dependencies = ("close", "volume")
        ctx = InputContext(
            spec=spec,
            request=request,
            plan=plan,
            dependencies=dependencies,
        )
        assert ctx.spec is spec
        assert ctx.request is request
        assert ctx.plan is plan
        assert ctx.dependencies is dependencies

    def test_equality(self) -> None:
        """Two InputContexts with identical fields should be equal."""
        ctx_a = _make_context()
        ctx_b = _make_context()
        assert ctx_a == ctx_b


# ---------------------------------------------------------------------------
# Protocol signature
# ---------------------------------------------------------------------------


class TestDerivedInputProviderProtocol:
    def test_protocol_accepts_input_context(self) -> None:
        """Protocol should accept InputContext instead of 4 separate params."""
        sig = inspect.signature(DerivedInputProvider.load_input)
        params = list(sig.parameters.keys())
        assert params == ["self", "context"]


# ---------------------------------------------------------------------------
# InMemoryDerivedInputProvider
# ---------------------------------------------------------------------------


class TestInMemoryDerivedInputProvider:
    def test_loads_frame_based_on_context_spec_id(self) -> None:
        """InMemoryDerivedInputProvider should load frame based on context.spec.id."""
        frame = pl.DataFrame({"instrument_id": ["000001.SZ"], "close": [10.0]})
        provider = InMemoryDerivedInputProvider(
            frames={"test.derived": frame},
        )
        ctx = _make_context(spec=_make_spec(id="test.derived"))
        result = provider.load_input(ctx)
        assert result.equals(frame)

    def test_raises_key_error_for_missing_spec_id(self) -> None:
        """InMemoryDerivedInputProvider should raise KeyError when spec.id not found."""
        provider = InMemoryDerivedInputProvider(frames={})
        ctx = _make_context(spec=_make_spec(id="unknown.derived"))
        with pytest.raises(KeyError, match=r"unknown\.derived"):
            provider.load_input(ctx)

    def test_signature_accepts_input_context(self) -> None:
        """InMemoryDerivedInputProvider.load_input should accept InputContext."""
        provider = InMemoryDerivedInputProvider(frames={})
        # Verify the method exists and has correct signature
        assert hasattr(provider, "load_input")


# ---------------------------------------------------------------------------
# UnavailableDerivedInputProvider
# ---------------------------------------------------------------------------


class TestUnavailableDerivedInputProvider:
    def test_raises_not_implemented(self) -> None:
        """UnavailableDerivedInputProvider should raise NotImplementedError."""
        provider = UnavailableDerivedInputProvider()
        ctx = _make_context(spec=_make_spec(id="test.derived"))
        with pytest.raises(NotImplementedError, match=r"test\.derived"):
            provider.load_input(ctx)

    def test_signature_accepts_input_context(self) -> None:
        """UnavailableDerivedInputProvider.load_input should accept InputContext."""
        provider = UnavailableDerivedInputProvider()
        assert hasattr(provider, "load_input")
