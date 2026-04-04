"""Re-export research records from ditto_kernel (migration shim)."""

from ditto_kernel.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)

__all__ = [
    "ResearchDatasetSnapshotRecord",
    "ResearchDatasetSpecRecord",
    "ResearchSpineSnapshotRecord",
    "ResearchSpineSpecRecord",
]
