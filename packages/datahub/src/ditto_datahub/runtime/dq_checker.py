r"""
Data quality checker.

.. deprecated::
    This module is DEPRECATED. Use ``ditto_datahub.dq.engine.DQEngine`` instead.

    The legacy ``DQChecker`` class returns ``DQCheckResult`` which wraps the old
    ``types.DQResult`` format. The new ``DQEngine`` returns ``dq.models.DQResult``
    with ``issues: list[DQIssue]`` which provides better structure and flexibility.

    Migration guide:
    - Old: dq_checker = DQChecker(); result = dq_checker.check(df, dataset_id)
    - New: dq_engine = DQEngine(config_path=\"...\"); result = dq_engine.check(df)

    This module is kept for backward compatibility and will be removed in a future
    release.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import polars as pl
from ditto_foundation import logger, span

from ..types import DQResult, DQSeverity
from .dq_rules import DQ_RULES

# Emit deprecation warning when module is imported
warnings.warn(
    "DQChecker is deprecated. Use ditto_datahub.dq.engine.DQEngine instead. "
    "The DQEngine returns dq.models.DQResult with issues list instead of "
    "the legacy DQCheckResult format.",
    DeprecationWarning,
    stacklevel=2,
)


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

    @property
    def has_errors(self) -> bool:
        """Has ERROR severity issues."""
        return self.fail_count > 0

    @property
    def has_warnings(self) -> bool:
        """Has WARNING severity issues."""
        return self.warn_count > 0

    @property
    def error_count(self) -> int:
        """Count of ERROR issues."""
        return self.fail_count

    @property
    def issues(self) -> list[DQResult]:
        """All failed issues."""
        return [r for r in self.results if not r.passed]


class DQChecker:
    """
    Data quality checker using Python configuration.

    .. deprecated::
        Use ``ditto_datahub.dq.engine.DQEngine`` instead.
    """

    def __init__(self) -> None:
        """
        Initialize DQ checker.

        .. deprecated::
            Use ``DQEngine`` instead.
        """
        warnings.warn(
            "DQChecker is deprecated. Use ditto_datahub.dq.engine.DQEngine instead. "
            "Initialize with DQEngine(config_path='path/to/dq/rules') and use "
            "the check() method which returns dq.models.DQResult with issues list.",
            DeprecationWarning,
            stacklevel=2,
        )
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
