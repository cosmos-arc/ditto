"""
Derived engine error hierarchy.

Canonical definitions live in ditto_data.errors (DataHub owns these
because Data services raise them).  This module re-exports so that
existing consumers continue to work.
"""

from __future__ import annotations

from ditto_data.errors import (
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
