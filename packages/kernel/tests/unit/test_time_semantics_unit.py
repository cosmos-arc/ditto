"""Shared time-semantics constants."""

from ditto_kernel.time_semantics import (
    DEFAULT_PIT_TIME_COLUMN,
    PIT_POLICY_FAIL_CLOSED,
)


def test_pit_policy_constants_are_stable_manifest_values() -> None:
    """PIT manifest fields should use stable cross-package string values."""
    assert DEFAULT_PIT_TIME_COLUMN == "knowledge_date"
    assert PIT_POLICY_FAIL_CLOSED == "knowledge_date_fail_closed"
