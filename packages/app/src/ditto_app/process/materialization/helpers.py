"""
Backward-compatible shim — re-exports from the split leaf modules.

Consumers should import from the specific leaf modules directly:

- ``minimal_dq``       → ``build_minimal_dq_record``
- ``manifest_builder`` → ``build_manifest_record``, ``resolve_shadow_baseline``
- ``dependency_refs``  → ``dependency_refs``
"""

from ditto_app.process.materialization.dependency_refs import dependency_refs
from ditto_app.process.materialization.manifest_builder import (
    build_manifest_record,
    resolve_shadow_baseline,
)
from ditto_app.process.materialization.minimal_dq import build_minimal_dq_record

__all__ = [
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "resolve_shadow_baseline",
]
