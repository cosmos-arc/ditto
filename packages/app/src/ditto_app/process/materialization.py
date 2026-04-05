"""
Re-export shim for materialization sub-modules.

The original monolithic module has been split into focused files:

- ``materialization_types.py``     — InputContext, protocols, errors, spec hydration
- ``materialization_helpers.py``   — DQ summary, manifest building, dependency refs
- ``publication_facade.py``        — DerivedPublicationFacade, certification rules
- ``cascade_orchestrator.py``      — InvalidationCascadeOrchestrator, CascadeStatus
- ``materialization_orchestrator.py`` — DerivedMaterializationOrchestrator,
  runtime input, factor service

All public names are re-exported here so that existing import paths remain valid.
"""

from ditto_app.process.cascade_orchestrator import (
    CASCADE_MAX_RETRY_COUNT,
    REALTIME_CASCADE_MAX_DEPTH,
    CascadeDepthExceededError,
    CascadeStatus,
    InvalidationCascadeOrchestrator,
    RepairBatchResult,
)
from ditto_app.process.materialization_helpers import (
    build_manifest_record,
    build_minimal_dq_record,
    dependency_refs,
    resolve_shadow_baseline,
)
from ditto_app.process.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
    FactorOrthogonalizationService,
    RuntimeDerivedInputProvider,
    UniverseProvider,
    apply_cs_amplification,
)
from ditto_app.process.materialization_types import (
    DerivedInputProvider,
    InMemoryDerivedInputProvider,
    InputContext,
    MissingDependencyError,
    UnavailableDerivedInputProvider,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
)
from ditto_app.process.publication_facade import (
    DerivedPublicationFacade,
    build_certification_checks,
)

__all__ = [
    # -- cascade_protocol --
    "CASCADE_MAX_RETRY_COUNT",
    "REALTIME_CASCADE_MAX_DEPTH",
    "CascadeDepthExceededError",
    "CascadeStatus",
    # -- input_preparation --
    "DerivedInputProvider",
    # -- materialization_orchestrator --
    "DerivedMaterializationOrchestrator",
    # -- publication --
    "DerivedPublicationFacade",
    # -- factor_orthogonalization_service --
    "FactorOrthogonalizationService",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "InvalidationCascadeOrchestrator",
    "MissingDependencyError",
    "RepairBatchResult",
    # -- runtime_input --
    "RuntimeDerivedInputProvider",
    "UnavailableDerivedInputProvider",
    "UniverseProvider",
    "apply_cs_amplification",
    # -- publication_rules --
    "build_certification_checks",
    # -- manifest_builder --
    "build_manifest_record",
    # -- dq_summary --
    "build_minimal_dq_record",
    "dependency_refs",
    "earliest_pending_start",
    "hydrate_spec",
    "prepare_input_frame",
    "resolve_shadow_baseline",
]
