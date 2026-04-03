"""Tests for FactorContext and calendar context integration (P2-D)."""

from __future__ import annotations

import pytest
from ditto_analytics.factors.spec import FactorContext, FactorSpec


class TestFactorContext:
    """Tests for the FactorContext dataclass."""

    def test_default_context_is_empty(self) -> None:
        """FactorContext() should have all calendar flags default to False/None."""
        ctx = FactorContext()
        assert ctx.is_special is False
        assert ctx.is_half_day is False
        assert ctx.exchange is None

    def test_context_with_is_special(self) -> None:
        """FactorContext can carry is_special=True."""
        ctx = FactorContext(is_special=True)
        assert ctx.is_special is True

    def test_context_with_all_fields(self) -> None:
        """FactorContext can carry all calendar metadata."""
        ctx = FactorContext(is_special=True, is_half_day=True, exchange="SSE")
        assert ctx.is_special is True
        assert ctx.is_half_day is True
        assert ctx.exchange == "SSE"

    def test_context_is_frozen(self) -> None:
        """FactorContext should be immutable."""
        ctx = FactorContext()
        with pytest.raises(AttributeError):
            ctx.is_special = True  # type: ignore[misc]

    def test_context_equality(self) -> None:
        """Two FactorContexts with same values should be equal."""
        ctx1 = FactorContext(is_special=True)
        ctx2 = FactorContext(is_special=True)
        assert ctx1 == ctx2

    def test_context_inequality(self) -> None:
        """Two FactorContexts with different values should not be equal."""
        ctx1 = FactorContext(is_special=False)
        ctx2 = FactorContext(is_special=True)
        assert ctx1 != ctx2


class TestFactorSpecWithContext:
    """Tests for FactorSpec calendar_context field."""

    def test_default_context_is_none(self) -> None:
        """FactorSpec without context should have calendar_context=None."""
        spec = FactorSpec(id="test", expression="close")
        assert spec.calendar_context is None

    def test_spec_with_context(self) -> None:
        """FactorSpec can carry a FactorContext."""
        ctx = FactorContext(is_special=True)
        spec = FactorSpec(
            id="test",
            expression="close",
            calendar_context=ctx,
        )
        assert spec.calendar_context is not None
        assert spec.calendar_context.is_special is True

    def test_spec_context_preserves_exchange(self) -> None:
        """FactorSpec context can carry exchange info."""
        ctx = FactorContext(is_special=False, is_half_day=True, exchange="SZSE")
        spec = FactorSpec(
            id="test",
            expression="close",
            calendar_context=ctx,
        )
        assert spec.calendar_context.exchange == "SZSE"
        assert spec.calendar_context.is_half_day is True

    def test_backward_compatible(self) -> None:
        """Existing FactorSpec creation without context still works."""
        spec = FactorSpec(
            id="rsi_14",
            expression="ts_rsi(market.close, 14)",
            dependencies=("market.close",),
            description="RSI-14",
        )
        assert spec.id == "rsi_14"
        assert spec.calendar_context is None

    def test_spec_is_frozen_with_context(self) -> None:
        """FactorSpec should remain immutable even with context."""
        ctx = FactorContext(is_special=True)
        spec = FactorSpec(id="test", expression="close", calendar_context=ctx)
        with pytest.raises(AttributeError):
            spec.calendar_context = FactorContext()  # type: ignore[misc]


class TestFactorContextInRegistry:
    """Integration: verify existing factor definitions still work."""

    def test_all_existing_specs_have_no_context(self) -> None:
        """All pre-existing specs should have calendar_context=None."""
        from ditto_analytics.factors import ALL_FACTOR_SPECS

        for spec_id, spec in ALL_FACTOR_SPECS.items():
            assert spec.calendar_context is None, (
                f"{spec_id} unexpectedly has calendar_context"
            )

    def test_context_field_exported(self) -> None:
        """FactorContext should be importable from factors package."""
        from ditto_analytics.factors import FactorContext  # noqa: F401
