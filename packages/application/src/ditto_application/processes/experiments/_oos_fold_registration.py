"""Exact out-of-sample fold registration for R3 comparisons."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_analysis.experiments import DateWindow, FoldId

from ditto_application.processes.experiments._evidence_values import (
    comparison_error,
)


@dataclass(frozen=True, slots=True)
class OOSFoldRegistration:
    """One pre-registered exact walk-forward OOS fold."""

    fold_id: FoldId
    fold_ordinal: int
    test_window: DateWindow

    def __post_init__(self) -> None:
        """Require nominal IDs, positive order, and an exact date window."""
        if type(self.fold_id) is not FoldId or type(self.test_window) is not DateWindow:
            comparison_error("invalid_oos_fold_registration")
        if type(self.fold_ordinal) is not int or self.fold_ordinal <= 0:
            comparison_error(
                "invalid_comparison_ordinal",
                field="fold_ordinal",
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return a deterministic fold identity payload."""
        return {
            "fold_id": str(self.fold_id),
            "fold_ordinal": self.fold_ordinal,
            "test_window": {
                "end": self.test_window.end.isoformat(),
                "start": self.test_window.start.isoformat(),
            },
        }
