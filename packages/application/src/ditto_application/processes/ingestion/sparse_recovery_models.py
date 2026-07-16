"""DTOs for sparse PIT full-history re-attestation."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SparsePITComponentRecoveryResult",
    "SparsePITReattestationRequest",
    "SparsePITReattestationResult",
]


@dataclass(frozen=True, slots=True)
class SparsePITReattestationRequest:
    """Request a full component replay up to one PIT cutoff."""

    dataset: str
    source: str
    signal_date: str


@dataclass(frozen=True, slots=True)
class SparsePITComponentRecoveryResult:
    """Outcome of re-ingesting and verifying one catalog component."""

    trade_date: str
    passed: bool
    checksum: str | None = None
    row_count: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize one component recovery outcome."""
        result: dict[str, object] = {
            "trade_date": self.trade_date,
            "passed": self.passed,
        }
        if self.checksum is not None:
            result["checksum"] = self.checksum
        if self.row_count is not None:
            result["row_count"] = self.row_count
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass(frozen=True, slots=True)
class SparsePITReattestationResult:
    """Verified cumulative result of one full-history recovery run."""

    dataset: str
    source: str
    signal_date: str
    passed: bool
    component_dates: tuple[str, ...]
    components: tuple[SparsePITComponentRecoveryResult, ...]
    source_snapshot_id: str | None = None
    source_snapshot_ids: tuple[str, ...] = ()
    row_count: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the stable CLI/Prefect recovery evidence shape."""
        result: dict[str, object] = {
            "dataset": self.dataset,
            "source": self.source,
            "signal_date": self.signal_date,
            "passed": self.passed,
            "component_dates": list(self.component_dates),
            "components": [component.to_dict() for component in self.components],
        }
        if self.source_snapshot_id is not None:
            result["source_snapshot_id"] = self.source_snapshot_id
        if self.source_snapshot_ids:
            result["source_snapshot_ids"] = list(self.source_snapshot_ids)
        if self.row_count is not None:
            result["row_count"] = self.row_count
        if self.error is not None:
            result["error"] = self.error
        return result
