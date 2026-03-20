"""
Port-side unified derived materialization helpers and input providers.

This module serves as the public entry point for materialization helpers.
Implementation lives in focused submodules:

* :mod:`input_preparation` -- ``InputContext``, ``DerivedInputProvider``,
  ``prepare_input_frame``, ``hydrate_spec``, etc.
* :mod:`dq_summary` -- ``build_minimal_dq_record`` and DQ computation helpers.
* :mod:`manifest_builder` -- ``build_manifest_record``,
  ``resolve_shadow_baseline``, ``dependency_refs``.
"""

from ditto_port.services.derived.dq_summary import build_minimal_dq_record
from ditto_port.services.derived.input_preparation import (
    DerivedInputProvider,
    InMemoryDerivedInputProvider,
    InputContext,
    MissingDependencyError,
    UnavailableDerivedInputProvider,
    earliest_pending_start,
    hydrate_spec,
    prepare_input_frame,
)
from ditto_port.services.derived.manifest_builder import (
    build_manifest_record,
    dependency_refs,
    resolve_shadow_baseline,
)

from ._utils import now_iso

__all__ = [
    "DerivedInputProvider",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "MissingDependencyError",
    "UnavailableDerivedInputProvider",
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "earliest_pending_start",
    "hydrate_spec",
    "now_iso",
    "prepare_input_frame",
    "resolve_shadow_baseline",
]
