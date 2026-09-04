"""Canonical SHA-256 identities for selection specifications and runs."""

from __future__ import annotations

from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionInputBundle,
    SelectionRun,
    StockSelectionSpec,
    canonical_input_hash,
    canonical_run_hash,
    canonical_spec_hash,
)

__all__ = [
    "canonical_selection_input_hash",
    "canonical_selection_run_hash",
    "canonical_selection_spec_hash",
]


def canonical_selection_spec_hash(value: StockSelectionSpec | EtfSelectionSpec) -> str:
    """Hash the exact stock- or ETF-specific selection policy."""
    return canonical_spec_hash(value)


def canonical_selection_input_hash(value: SelectionInputBundle) -> str:
    """Hash PIT, source, spec, seed, universe, and normalized instrument facts."""
    return canonical_input_hash(value)


def canonical_selection_run_hash(value: SelectionRun) -> str:
    """Hash the complete ordered candidates and exclusions of a saved run."""
    return canonical_run_hash(value)
