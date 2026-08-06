"""Public facade for the frozen R3 daily factor catalog contracts."""

from __future__ import annotations

from ditto_features.factors.core_daily_availability import (
    AvailabilityContext,
    CertifiedBenchmarkEvidence,
    CoreFactorInputAvailability,
    assess_core_factor_input_availability,
)
from ditto_features.factors.core_daily_catalog import R3_CORE_FACTOR_CATALOG
from ditto_features.factors.core_daily_contracts import (
    AssetLane,
    AvailabilityReason,
    CertifiedHistoryCoverage,
    CoreFactorCatalog,
    CoreFactorDescriptor,
    CoreFactorSpecContract,
    DatasetInputRequirement,
    LaneDatasetRequirement,
    Lookback,
    LookbackUnit,
    MaterializedIntermediate,
    MissingValuePolicy,
    PitRequirement,
    PreprocessingContract,
    PreprocessingStep,
    StandardizationMethod,
    WinsorizationMethod,
)

__all__ = [
    "R3_CORE_FACTOR_CATALOG",
    "AssetLane",
    "AvailabilityContext",
    "AvailabilityReason",
    "CertifiedBenchmarkEvidence",
    "CertifiedHistoryCoverage",
    "CoreFactorCatalog",
    "CoreFactorDescriptor",
    "CoreFactorInputAvailability",
    "CoreFactorSpecContract",
    "DatasetInputRequirement",
    "LaneDatasetRequirement",
    "Lookback",
    "LookbackUnit",
    "MaterializedIntermediate",
    "MissingValuePolicy",
    "PitRequirement",
    "PreprocessingContract",
    "PreprocessingStep",
    "StandardizationMethod",
    "WinsorizationMethod",
    "assess_core_factor_input_availability",
]
