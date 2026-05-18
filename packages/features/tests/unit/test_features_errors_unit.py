"""Features error hierarchy unit tests."""

import pytest
from ditto_features.errors import (
    DerivedError,
    EvaluationError,
    FactorValidationError,
    FeaturesError,
    FeatureStorageError,
    MaterializationError,
)


def test_features_error_hierarchy() -> None:
    """All features domain errors inherit from FeaturesError."""
    assert issubclass(MaterializationError, FeaturesError)
    assert issubclass(EvaluationError, FeaturesError)
    assert issubclass(FactorValidationError, FeaturesError)
    assert issubclass(FeatureStorageError, FeaturesError)
    assert issubclass(DerivedError, FeaturesError)
    assert not issubclass(FactorValidationError, ValueError)
    assert not issubclass(FeatureStorageError, ValueError)


def test_features_error_is_ditto_error() -> None:
    """FeaturesError inherits from DittoError (kernel root)."""
    from ditto_kernel.exceptions import DittoError

    assert issubclass(FeaturesError, DittoError)


def test_materialization_error_carries_details() -> None:
    """MaterializationError carries factor context."""
    err = MaterializationError("materialization failed", factor_id="alpha_001")
    assert err.details["factor_id"] == "alpha_001"


def test_evaluation_error_carries_details() -> None:
    """EvaluationError carries evaluation context."""
    err = EvaluationError("IC computation failed", metric="ic")
    assert err.details["metric"] == "ic"


def test_factor_validation_error_carries_details() -> None:
    """FactorValidationError carries factor context."""
    err = FactorValidationError("invalid factor", factor_name="momentum_20")
    assert err.details["factor_name"] == "momentum_20"


def test_feature_storage_error_carries_details() -> None:
    """FeatureStorageError carries storage context."""
    err = FeatureStorageError("write failed", path="/data/factors/alpha.parquet")
    assert err.details["path"] == "/data/factors/alpha.parquet"


def test_derived_error_catchable_via_features_error() -> None:
    """DerivedError and subclasses are catchable via FeaturesError."""
    from ditto_features.errors import (
        DerivedNotFoundError,
        DerivedVersionError,
    )

    with pytest.raises(FeaturesError):
        raise DerivedNotFoundError(derived_id="test")

    with pytest.raises(FeaturesError):
        raise DerivedVersionError(derived_id="test", reason="test")
