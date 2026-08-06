"""Shared runtime validation helpers for governed R3 factor contracts."""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["copy_sequence"]


def _require_ordered_sequence(value: object, field_name: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a non-text sequence")


def copy_sequence[T](value: Sequence[T], field_name: str) -> tuple[T, ...]:
    """Defensively copy an ordered sequence while rejecting text and iterables."""
    _require_ordered_sequence(value, field_name)
    return tuple(value)
