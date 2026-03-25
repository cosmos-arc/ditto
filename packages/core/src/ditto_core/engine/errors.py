"""
Derived engine error hierarchy.

Canonical definitions live in ditto_datahub.errors (DataHub owns these
because DataHub services raise them).  This module re-exports so that
existing Core consumers continue to work.
"""

from __future__ import annotations

from ditto_datahub.errors import (
    DerivedDependencyError,
    DerivedError,
    DerivedMaterializationError,
    DerivedNotFoundError,
    DerivedNotImplementedError,
    DerivedValidationError,
    DerivedVersionError,
)

__all__ = [
    "DerivedDependencyError",
    "DerivedError",
    "DerivedMaterializationError",
    "DerivedNotFoundError",
    "DerivedNotImplementedError",
    "DerivedValidationError",
    "DerivedVersionError",
]
