"""Typed application error factory for experiment process contract failures."""

from __future__ import annotations

from ditto_application.exceptions import AppProcessError

__all__ = ["experiment_process_error"]


def experiment_process_error(reason: str) -> AppProcessError:
    """Return one typed fail-closed error for an invalid internal process graph."""
    return AppProcessError(
        "experiment process contract is invalid",
        details={"code": "SPEC_INVALID", "reason": reason},
    )
