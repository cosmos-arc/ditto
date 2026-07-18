"""Certification command boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)


def test_review_delegates_without_mutating_machine_report() -> None:
    store = MagicMock()
    commands = DataProductCertificationCommands(store)
    reviewed_at = datetime(2026, 7, 18, tzinfo=UTC)

    commands.review(
        "certification:report:1",
        reviewer="human-reviewer",
        reviewed_at=reviewed_at,
    )

    store.approve_report.assert_called_once_with(
        "certification:report:1",
        reviewer="human-reviewer",
        reviewed_at=reviewed_at,
    )
