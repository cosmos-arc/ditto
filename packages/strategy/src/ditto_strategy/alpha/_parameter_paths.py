"""Internal canonical parameter path helpers."""

from __future__ import annotations

_LEGACY_FACTOR_PARAMETER_PREFIX = "/pipeline/nodes/legacy_factor_set/config/params"


def escape_parameter_path_segment(value: str) -> str:
    """Escape one path segment using RFC 6901 ``~0``/``~1`` rules."""
    return value.replace("~", "~0").replace("/", "~1")


def legacy_parameter_path(name: str) -> str:
    """Map one legacy ``spec.params`` key to its stable StrategySpec v2 path."""
    return f"{_LEGACY_FACTOR_PARAMETER_PREFIX}/{escape_parameter_path_segment(name)}"
