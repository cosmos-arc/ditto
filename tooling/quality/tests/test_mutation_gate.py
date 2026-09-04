"""Tests for the deterministic critical-core mutation gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tooling.quality.mutation_gate import (
    MutationGateError,
    MutationStats,
    evaluate_stats,
    load_stats,
)


def test_mutation_score_uses_every_non_skipped_terminal_mutant() -> None:
    stats = MutationStats(
        killed=78,
        survived=12,
        no_tests=5,
        suspicious=2,
        timeout=2,
        interrupted=0,
        segfault=1,
        skipped=4,
        total=104,
    )

    result = evaluate_stats(stats, threshold=80.0)

    assert result.score == 80.0
    assert result.denominator == 100


def test_mutation_gate_rejects_incomplete_results() -> None:
    stats = MutationStats(
        killed=9,
        survived=1,
        no_tests=0,
        suspicious=0,
        timeout=0,
        interrupted=0,
        segfault=0,
        skipped=0,
        total=11,
    )

    with pytest.raises(MutationGateError, match="incomplete"):
        evaluate_stats(stats, threshold=80.0)


def test_mutation_gate_rejects_score_below_threshold() -> None:
    stats = MutationStats(
        killed=6,
        survived=3,
        no_tests=0,
        suspicious=0,
        timeout=1,
        interrupted=0,
        segfault=0,
        skipped=0,
        total=10,
    )

    with pytest.raises(MutationGateError, match=r"70.00%.*80.00%"):
        evaluate_stats(stats, threshold=80.0)


def test_load_stats_rejects_missing_or_boolean_fields(tmp_path: Path) -> None:
    report = tmp_path / "stats.json"
    report.write_text(json.dumps({"killed": True}), encoding="utf-8")

    with pytest.raises(MutationGateError, match="missing integer field"):
        load_stats(report)
