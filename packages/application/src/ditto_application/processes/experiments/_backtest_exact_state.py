"""Exact-value predicates for the frozen research backtest object graph."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import fields, is_dataclass
from typing import Protocol, cast


class _OrderJournal(Protocol):
    def all_events(self) -> tuple[object, ...]: ...


def all_references_identical(
    pairs: tuple[tuple[object, object], ...],
) -> bool:
    """Return whether each actual object is its required exact reference."""
    return all(actual is expected for actual, expected in pairs)


def has_exact_runtime_value(actual: object, expected: object) -> bool:
    """Compare canonical runtime values without subclass or loose-equality gaps."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is float:
        matches = cast("float", actual).hex() == expected.hex()
    elif type(expected) is tuple:
        actual_items = cast("tuple[object, ...]", actual)
        expected_items = cast("tuple[object, ...]", expected)
        matches = len(actual_items) == len(expected_items) and all(
            has_exact_runtime_value(actual_item, expected_item)
            for actual_item, expected_item in zip(
                actual_items,
                expected_items,
                strict=True,
            )
        )
    elif type(expected) is list:
        actual_items = cast("list[object]", actual)
        expected_items = cast("list[object]", expected)
        matches = len(actual_items) == len(expected_items) and all(
            has_exact_runtime_value(actual_item, expected_item)
            for actual_item, expected_item in zip(
                actual_items,
                expected_items,
                strict=True,
            )
        )
    elif type(expected) is dict:
        actual_items = tuple(cast("dict[object, object]", actual).items())
        expected_items = tuple(cast("dict[object, object]", expected).items())
        matches = len(actual_items) == len(expected_items) and all(
            has_exact_runtime_value(actual_key, expected_key)
            and has_exact_runtime_value(actual_value, expected_value)
            for (actual_key, actual_value), (expected_key, expected_value) in zip(
                actual_items,
                expected_items,
                strict=True,
            )
        )
    elif is_dataclass(expected) and not isinstance(expected, type):
        matches = all(
            has_exact_runtime_value(
                getattr(actual, item.name),
                getattr(expected, item.name),
            )
            for item in fields(expected)
        )
    else:
        matches = actual == expected
    return matches


def _is_pristine_list_defaultdict(value: object) -> bool:
    """Return whether journal storage is exactly an empty defaultdict(list)."""
    if type(value) is not defaultdict:
        return False
    events = cast("defaultdict[object, object]", value)
    return events.default_factory is list and not events


def pristine_order_state_drift_reason(
    order_journal: _OrderJournal,
    order_book: object,
) -> str | None:
    """Return the stable drift reason for non-pristine order state, if any."""
    if not _is_pristine_list_defaultdict(vars(order_journal).get("_events")):
        return "constructed_order_journal_state_drift"
    order_book_state = vars(order_book)
    if not has_exact_runtime_value(order_book_state.get("_tickets"), {}):
        return "constructed_order_book_state_drift"
    if (
        order_book_state.get("_journal") is not order_journal
        or order_journal.all_events() != ()
    ):
        return "constructed_order_book_state_drift"
    return None
