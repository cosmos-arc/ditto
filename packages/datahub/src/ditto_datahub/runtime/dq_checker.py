"""Data quality checker."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_foundation import logger, span

from ..types import DQResult, DQSeverity
from .dq_rules import DQ_RULES


@dataclass
class DQCheckResult:
    """DQ check result summary."""

    passed: bool
    results: list[DQResult]

    @property
    def fail_count(self) -> int:
        """Number of failed rules with ERROR severity (B.5: renamed from FAIL)."""
        return sum(
            1 for r in self.results if not r.passed and r.severity == DQSeverity.ERROR
        )

    @property
    def warn_count(self) -> int:
        """Number of failed rules with WARNING severity (B.5: renamed from WARN)."""
        return sum(
            1 for r in self.results if not r.passed and r.severity == DQSeverity.WARNING
        )


class DQChecker:
    """Data quality checker using Python configuration."""

    def __init__(self) -> None:
        """Initialize DQ checker."""
        self.rules = DQ_RULES

    def check(self, df: pl.DataFrame, dataset_id: str) -> DQCheckResult:
        """Execute DQ checks."""
        with span("dq_checker.check", dataset_id=dataset_id):
            return self._check_impl(df, dataset_id)

    def _check_impl(self, df: pl.DataFrame, dataset_id: str) -> DQCheckResult:
        """Internal implementation of DQ checks."""
        rules = self.rules.get(dataset_id, [])

        logger.info(
            "dq_check_start",
            event="dq_check",
            dataset_id=dataset_id,
            rules_count=len(rules),
            row_count=len(df),
        )

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

            if not passed and rule.severity == DQSeverity.ERROR:
                all_passed = False

        fail_count = sum(
            1 for r in results if not r.passed and r.severity == DQSeverity.ERROR
        )
        warn_count = sum(
            1 for r in results if not r.passed and r.severity == DQSeverity.WARNING
        )

        logger.info(
            "dq_check_complete",
            event="dq_check",
            dataset_id=dataset_id,
            passed=all_passed,
            fail_count=fail_count,
            warn_count=warn_count,
        )

        return DQCheckResult(passed=all_passed, results=results)
