"""
Public facade for materialization helper functions split across leaf modules.

- ``minimal_dq``       → ``build_minimal_dq_record``
- ``manifest_builder`` → ``build_manifest_record``, ``resolve_shadow_baseline``
- ``dependency_refs``  → ``dependency_refs``
"""

from ditto_application.processes.materialization.dependency_refs import dependency_refs
from ditto_application.processes.materialization.manifest_builder import (
    build_manifest_record,
    resolve_shadow_baseline,
)
from ditto_application.processes.materialization.minimal_dq import (
    build_minimal_dq_record,
)

__all__ = [
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "resolve_shadow_baseline",
]
