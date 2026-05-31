"""Research dataset and spine models — re-export entry point."""

from __future__ import annotations

from .late_arrival import (
    _apply_late_arrival_policy,
    _detect_late_arrivals,
)
from .records import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from .specs import (
    DatasetSnapshot,
    KnownAtPolicy,
    LateArrivalError,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    SpineSnapshot,
    SpineSpec,
)

__all__ = [
    "DatasetSnapshot",
    "KnownAtPolicy",
    "LateArrivalError",
    "LateArrivalPolicy",
    "ResearchDatasetSnapshotRecord",
    "ResearchDatasetSpec",
    "ResearchDatasetSpecRecord",
    "ResearchSpineSnapshotRecord",
    "ResearchSpineSpecRecord",
    "SpineSnapshot",
    "SpineSpec",
    "_apply_late_arrival_policy",
    "_detect_late_arrivals",
]
