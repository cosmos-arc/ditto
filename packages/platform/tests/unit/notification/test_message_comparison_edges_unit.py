"""Total-order boundary tests for notification severity levels."""

from __future__ import annotations

import operator
from collections.abc import Callable

import pytest
from ditto_platform.services.notification.message import NotificationLevel


@pytest.mark.parametrize(
    "comparison",
    [operator.lt, operator.le, operator.gt, operator.ge],
)
def test_level_comparison_rejects_unrelated_types(
    comparison: Callable[[object, object], object],
) -> None:
    with pytest.raises(TypeError):
        comparison(NotificationLevel.INFO, object())


def test_greater_than_uses_severity_order_for_distinct_levels() -> None:
    assert NotificationLevel.CRITICAL > NotificationLevel.ERROR
