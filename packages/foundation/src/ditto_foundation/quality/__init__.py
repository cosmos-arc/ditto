"""
Foundation layer quality types.

This module contains basic quality-related type definitions that are
used across multiple layers (datahub, core, apps).

These types are infrastructure-level primitives and should have no
dependencies on higher-level packages.
"""

from ditto_foundation.quality.spec import DQSeverity

__all__ = ["DQSeverity"]
