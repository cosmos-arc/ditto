"""Tests for analytics spec validation helpers."""

import pytest
from ditto_data.errors import DerivedNotImplementedError
from ditto_features.validation import validate_derived_spec
from ditto_kernel.strategy import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)


class TestValidateDerivedSpec:
    """Tests for validate_derived_spec."""

    def test_passes_valid_spec(self) -> None:
        """Valid spec should not raise."""
        spec = DerivedSpec(
            id="factor.simple",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
        )
        validate_derived_spec(spec)

    def test_rejects_composite_entity_keys(self) -> None:
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
            validate_derived_spec(spec)

    def test_rejects_intraday_grain(self) -> None:
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
            DerivedNotImplementedError, match=r"grain='1m' 已预留、暂未实现"
        ):
            validate_derived_spec(spec)
