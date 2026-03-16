"""Tests for derived spec models."""

from typing import get_args

import pytest
from ditto_core.engine.specs import (
    CalendarId,
    DerivedRole,
    DerivedSpec,
    GrainId,
    MaterializationProfile,
)


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

        with pytest.raises(NotImplementedError, match="复合键已预留、暂未实现"):
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

        with pytest.raises(NotImplementedError, match="grain='1m' 已预留、暂未实现"):
            spec.validate_spec()

    def test_factor_role_defaults_to_pit_and_default_normalization(self) -> None:
        """Factor specs should default to PIT + default normalization preset."""
        spec = DerivedSpec(
            id="factor.momentum_20d",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(close, 20)",
        )

        assert spec.pit_required is True
        assert spec.normalization_preset == "default"
        assert spec.operator_versions == {}

    def test_non_factor_role_defaults_to_no_pit_and_no_normalization(self) -> None:
        """Non-factor roles should keep neutral execution defaults."""
        spec = DerivedSpec(
            id="feature.volume_ma_20d",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(volume, 20)",
        )

        assert spec.pit_required is False
        assert spec.normalization_preset == "none"
