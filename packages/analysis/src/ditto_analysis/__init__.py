"""
Ditto Analysis public API.

Exports analysis errors, research dataset/spine domain models, and
research catalog contracts.  The reports, diagnostics, experiments,
and screeners namespaces are reserved for future analysis product work
and export no public runtime API today.
"""

from ditto_analysis.errors import AnalysisError, ResearchDatasetError
from ditto_analysis.research import (
    DatasetSnapshot,
    ResearchDatasetSpec,
    SpineSnapshot,
    SpineSpec,
)

__all__ = [
    "AnalysisError",
    "DatasetSnapshot",
    "ResearchDatasetError",
    "ResearchDatasetSpec",
    "SpineSnapshot",
    "SpineSpec",
]
