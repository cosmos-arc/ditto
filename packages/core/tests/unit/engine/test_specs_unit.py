"""Tests for derived spec models."""

from typing import get_args

import pytest
from ditto_core.engine.specs import (
    CalendarId,
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    GrainId,
    MaterializationProfile,
    TimeSpec,
)
from ditto_datahub.errors import DerivedNotImplementedError


class TestLiteralTypeAliases:
    """Tests for CalendarId and GrainId Literal type aliases."""

    def test_calendar_id_literal_values(self) -> None:
        """CalendarId should be Literal['cn_stock'] per ADR-032 D-2."""
        args = get_args(CalendarId.__value__)
        assert args == ("cn_stock",)

    def test_grain_id_literal_values(self) -> None:
        """GrainId should be Literal['1d', '1m'] per ADR-032 D-3."""
        args = get_args(GrainId.__value__)
        assert args == ("1d", "1m")

    def test_derived_spec_accepts_calendar_cn_stock(self) -> None:
        """DerivedSpec should accept calendar='cn_stock'."""
        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
            calendar="cn_stock",
        )
        assert spec.calendar == "cn_stock"

    def test_derived_spec_accepts_grain_1d(self) -> None:
        """DerivedSpec should accept grain='1d'."""
        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
            grain="1d",
        )
        assert spec.grain == "1d"

    def test_derived_spec_accepts_grain_1m(self) -> None:
        """DerivedSpec should accept grain='1m' (reserved, in Literal type)."""
        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
            grain="1m",
        )
        assert spec.grain == "1m"


class TestTimeSpec:
    """Tests for TimeSpec dataclass."""

    def test_construct_with_required_fields(self) -> None:
        """TimeSpec requires event_time_key; availability_time_key is optional."""
        ts = TimeSpec(event_time_key="trade_date")
        assert ts.event_time_key == "trade_date"
        assert ts.availability_time_key is None

    def test_construct_with_all_fields(self) -> None:
        """TimeSpec accepts explicit availability_time_key."""
        ts = TimeSpec(
            event_time_key="trade_date",
            availability_time_key="data_arrival_time",
        )
        assert ts.event_time_key == "trade_date"
        assert ts.availability_time_key == "data_arrival_time"

    def test_frozen_immutable(self) -> None:
        """TimeSpec should be frozen (immutable)."""
        ts = TimeSpec(event_time_key="trade_date")
        with pytest.raises(AttributeError):
            ts.event_time_key = "bar_time"  # type: ignore[misc]

    def test_event_time_key_required(self) -> None:
        """event_time_key is a required positional argument."""
        with pytest.raises(TypeError):
            TimeSpec()  # type: ignore[call-arg]


class TestExecutionPolicy:
    """Tests for ExecutionPolicy dataclass."""

    def test_default_values(self) -> None:
        """ExecutionPolicy has sensible defaults."""
        policy = ExecutionPolicy()
        assert policy.pit_required is True
        assert policy.normalization_preset == "default"
        assert policy.adj_type == "none"

    def test_explicit_adj_type(self) -> None:
        """ExecutionPolicy accepts explicit adj_type for ETF adjustment control."""
        policy = ExecutionPolicy(adj_type="qfq")
        assert policy.adj_type == "qfq"

    def test_explicit_values(self) -> None:
        """ExecutionPolicy accepts explicit values."""
        policy = ExecutionPolicy(
            pit_required=False,
            normalization_preset="none",
        )
        assert policy.pit_required is False
        assert policy.normalization_preset == "none"

    def test_frozen_immutable(self) -> None:
        """ExecutionPolicy should be frozen (immutable)."""
        policy = ExecutionPolicy()
        with pytest.raises(AttributeError):
            policy.pit_required = False  # type: ignore[misc]

    def test_no_arg_required(self) -> None:
        """ExecutionPolicy can be constructed without arguments."""
        policy = ExecutionPolicy()
        assert isinstance(policy, ExecutionPolicy)


class TestDerivedSpec:
    """Tests for DerivedSpec."""

    def test_effective_time_keys_use_grain_default(self) -> None:
        """Default time keys should be derived from grain."""
        spec = DerivedSpec(
            id="factor.momentum_20d",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(close, 20)",
        )

        assert spec.effective_time_keys == ("trade_date",)
        assert spec.timezone == "Asia/Shanghai"

    def test_effective_time_keys_allow_explicit_override(self) -> None:
        """Explicit time keys should override the grain default."""
        spec = DerivedSpec(
            id="feature.orderbook_state",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.STATE,
            expression="last(price)",
            time_keys=("session_date", "snapshot_time"),
        )

        assert spec.effective_time_keys == ("session_date", "snapshot_time")

    def test_validate_spec_rejects_composite_entity_keys(self) -> None:
        """Composite keys are reserved but not yet supported."""
        spec = DerivedSpec(
            id="factor.multi_key",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
            entity_keys=("instrument_id", "exchange"),
        )

        with pytest.raises(DerivedNotImplementedError, match="复合键已预留、暂未实现"):
            spec.validate_spec()

    def test_validate_spec_rejects_intraday_grain(self) -> None:
        """Intraday grain is reserved but not yet implemented."""
        spec = DerivedSpec(
            id="factor.intraday_alpha",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
            grain="1m",
        )

        with pytest.raises(
            DerivedNotImplementedError, match="grain='1m' 已预留、暂未实现"
        ):
            spec.validate_spec()

    def test_no_pit_required_or_normalization_fields(self) -> None:
        """DerivedSpec should not have pit_required or normalization_preset."""
        spec = DerivedSpec(
            id="factor.momentum_20d",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(close, 20)",
        )
        assert not hasattr(spec, "pit_required")
        assert not hasattr(spec, "normalization_preset")

    def test_time_spec_optional_default_none(self) -> None:
        """time_spec defaults to None when not provided."""
        spec = DerivedSpec(
            id="factor.simple",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
        )
        assert spec.time_spec is None

    def test_time_spec_provided(self) -> None:
        """DerivedSpec accepts a TimeSpec instance."""
        ts = TimeSpec(event_time_key="trade_date")
        spec = DerivedSpec(
            id="factor.timed",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
            time_spec=ts,
        )
        assert spec.time_spec is ts
        assert spec.time_spec is not None
        assert spec.time_spec.event_time_key == "trade_date"

    def test_validate_spec_no_normalization_validation(self) -> None:
        """validate_spec should not check normalization_preset."""
        spec = DerivedSpec(
            id="factor.simple",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
        )
        # Should not raise
        spec.validate_spec()
