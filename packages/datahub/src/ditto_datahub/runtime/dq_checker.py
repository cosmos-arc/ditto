"""Data quality checker."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ..types import DQResult, DQSeverity
from .dq_rules import DQ_RULES


@dataclass
class DQCheckResult:
    """DQ check result summary."""

    passed: bool
    results: list[DQResult]

    @property
    def fail_count(self) -> int:
        """Number of failed rules with FAIL severity."""
        return sum(
            1 for r in self.results if not r.passed and r.severity == DQSeverity.FAIL
        )

    @property
    def warn_count(self) -> int:
        """Number of failed rules with WARN severity."""
        return sum(
            1 for r in self.results if not r.passed and r.severity == DQSeverity.WARN
        )


class DQChecker:
    """Data quality checker using Python configuration."""

    def __init__(self) -> None:
        """Initialize DQ checker."""
        self.rules = DQ_RULES

    def check(self, df: pl.DataFrame, dataset_id: str) -> DQCheckResult:
        """Execute DQ checks."""
        rules = self.rules.get(dataset_id, [])

        results = []
        all_passed = True

        for rule in rules:
            passed, affected_rows, message = rule.check_fn(df, rule.params or {})

            result = DQResult(
                passed=passed,
                severity=rule.severity,
                rule_name=rule.name,
                message=message,
                affected_rows=affected_rows,
            )
            results.append(result)

            if not passed and rule.severity == DQSeverity.FAIL:
                all_passed = False

        return DQCheckResult(passed=all_passed, results=results)
