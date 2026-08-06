"""Canonical identity primitives used by persisted R3 preflight authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import DateWindow, canonical_payload


def invalid_preflight_authority(message: str) -> ExperimentIntegrityError:
    """Return the stable integrity error for malformed preflight authority."""
    return ExperimentIntegrityError(
        message,
        details={"reason_code": "holdout_preflight_authority_invalid"},
    )


def canonical_string(value: object, name: str) -> str:
    """Validate a non-empty, whitespace-stable identity string."""
    if type(value) is not str or not value or value != value.strip():
        raise invalid_preflight_authority(f"{name} must be a canonical string")
    return value


@dataclass(frozen=True, slots=True)
class HoldoutConsumptionAuthority:
    """Reset-resistant authority; caller labels and parameter values are excluded."""

    strategy_family_id: str
    certified_data_cutoff: date
    oos_window: DateWindow

    @property
    def content_hash(self) -> ContentHash:
        """Return the canonical Task 7 research-cycle consumption identity."""
        return canonical_research_cycle_hash(
            strategy_family_id=self.strategy_family_id,
            certified_data_cutoff=self.certified_data_cutoff,
            oos_window=self.oos_window,
        )


def canonical_research_cycle_hash(
    *,
    strategy_family_id: str,
    certified_data_cutoff: date,
    oos_window: DateWindow,
) -> ContentHash:
    """Derive cycle identity only from family, certified cutoff, and OOS semantics."""
    family = canonical_string(strategy_family_id, "strategy_family_id")
    if type(certified_data_cutoff) is not date or type(oos_window) is not DateWindow:
        raise invalid_preflight_authority("research cycle authority types are invalid")
    return canonical_payload(
        {
            "schema_version": 1,
            "authority": "r3_holdout_consumption",
            "strategy_family_id": family,
            "certified_data_cutoff": certified_data_cutoff.isoformat(),
            "oos": {
                "start": oos_window.start.isoformat(),
                "end": oos_window.end.isoformat(),
            },
        }
    ).content_hash
