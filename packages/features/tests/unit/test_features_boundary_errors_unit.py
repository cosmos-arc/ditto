"""Features public-boundary error tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_features.errors import FactorValidationError, FeatureStorageError
from ditto_features.services.derived.queries import DerivedLatestQuery


def test_feature_storage_adapters_raise_feature_storage_error() -> None:
    """Feature storage adapters translate boundary validation into domain errors."""
    paths = [
        Path(
            "packages/features/src/ditto_features/storage/parquet/factors/"
            "factor_writer.py"
        ),
        Path(
            "packages/features/src/ditto_features/storage/parquet/features/"
            "technical/technical_indicator_writer.py"
        ),
        Path("packages/features/src/ditto_features/storage/sqlite/derived/writer.py"),
    ]

    offenders = [
        path.as_posix()
        for path in paths
        if FeatureStorageError.__name__ not in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_derived_query_validation_raises_factor_validation_error() -> None:
    """Derived query DTO validation failures use the factor domain error."""
    with pytest.raises(FactorValidationError) as exc_info:
        DerivedLatestQuery(derived_ids=(), instrument_ids=(1,))

    assert exc_info.value.details["field_name"] == "derived_ids"
    assert exc_info.value.details["reason"] == "empty"
