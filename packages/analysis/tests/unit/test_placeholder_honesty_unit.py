"""Tests for reserved analysis placeholder namespaces."""

from __future__ import annotations

import importlib
from types import ModuleType

import pytest

PLACEHOLDER_MODULE_NAMES = (
    "ditto_analysis.reports",
    "ditto_analysis.diagnostics",
    "ditto_analysis.experiments",
    "ditto_analysis.screeners",
)

MISLEADING_AVAILABILITY_PHRASES = (
    "提供",
    "支持",
    "available",
    "provides",
    "supports",
)


@pytest.fixture(params=PLACEHOLDER_MODULE_NAMES)
def placeholder_module(request: pytest.FixtureRequest) -> ModuleType:
    """Import one reserved analysis placeholder module."""
    return importlib.import_module(str(request.param))


def test_reserved_placeholder_exports_no_public_runtime_api(
    placeholder_module: ModuleType,
) -> None:
    """Reserved placeholders must expose no public runtime contract."""
    assert placeholder_module.__all__ == []


def test_reserved_placeholder_docstring_is_honest(
    placeholder_module: ModuleType,
) -> None:
    """Reserved placeholders must not read like available product capability."""
    docstring = placeholder_module.__doc__

    assert docstring is not None
    assert "Reserved namespace" in docstring
    assert "future analysis product work" in docstring
    assert "No public runtime API is exported yet" in docstring
    assert "Production code must not import this namespace for behavior" in docstring
    assert not any(
        phrase in docstring.casefold() for phrase in MISLEADING_AVAILABILITY_PHRASES
    )
