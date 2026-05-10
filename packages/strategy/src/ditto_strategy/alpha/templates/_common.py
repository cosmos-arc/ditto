"""Shared template utilities — NOT public API."""

from __future__ import annotations

from typing import NoReturn

from ditto_strategy.errors import StrategySpecError

__all__ = ["raise_config_error"]


def raise_config_error(
    message: str,
    *,
    template: str,
    field_name: str,
    reason: str,
    actual_value: object,
    **details: object,
) -> NoReturn:
    """Raise a template config error with consistent metadata."""
    payload: dict[str, object] = {
        "template": template,
        "field_name": field_name,
        "reason": reason,
        "actual_value": actual_value,
    }
    payload.update(details)
    raise StrategySpecError(message, details=payload)
