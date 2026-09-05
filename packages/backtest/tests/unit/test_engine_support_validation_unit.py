"""Compatibility fence tests for ``EngineLoop`` dependency assembly."""

from __future__ import annotations

import pytest
from ditto_backtest.engine_support import EngineLoopDeps, normalize_engine_loop_deps

_NAMES = (
    "pipeline",
    "planner",
    "brokerage",
    "pre_trade_check",
    "data_feed",
    "synchronizer",
    "options",
)


def _ports() -> dict[str, object]:
    return {name: object() for name in _NAMES}


def test_explicit_dependency_bundle_cannot_mix_with_legacy_ports() -> None:
    ports = _ports()
    bundle = normalize_engine_loop_deps(None, (), ports)
    assert isinstance(bundle, EngineLoopDeps)
    assert normalize_engine_loop_deps(bundle, (), {}) is bundle

    for args, keyword_ports in (((object(),), {}), ((), {"pipeline": object()})):
        with pytest.raises(TypeError, match="cannot be combined"):
            normalize_engine_loop_deps(bundle, args, keyword_ports)


def test_legacy_dependency_normalization_rejects_ambiguous_shapes() -> None:
    with pytest.raises(TypeError, match="too many positional"):
        normalize_engine_loop_deps(None, (object(),) * 8, {})
    with pytest.raises(TypeError, match="duplicate dependency"):
        normalize_engine_loop_deps(None, (object(),), {"pipeline": object()})
    with pytest.raises(TypeError, match="unexpected dependencies"):
        normalize_engine_loop_deps(None, (), {**_ports(), "future": object()})
    with pytest.raises(TypeError, match="missing dependencies"):
        normalize_engine_loop_deps(None, (), {})


def test_first_legacy_positional_dependency_is_not_mistaken_for_bundle() -> None:
    sentinel = object()
    remaining = _ports()
    remaining.pop("pipeline")

    bundle = normalize_engine_loop_deps(sentinel, (), remaining)

    assert bundle.pipeline is sentinel
