"""Small support types and compatibility helpers for the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import orjson
from ditto_execution.brokerage import Brokerage
from ditto_execution.planner import ExecutionPlanner
from ditto_kernel.synchronizer import Synchronizer
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.pipeline import StrategyPipeline

from ditto_backtest.data_feed import DataFeed
from ditto_backtest.engine_steps import EngineOptions

__all__ = [
    "R4_CHECKPOINT_VERSION",
    "EngineLoopDeps",
    "canonical_json",
    "normalize_engine_loop_deps",
]

R4_CHECKPOINT_VERSION = 3


@dataclass(frozen=True)
class EngineLoopDeps:
    """Runtime collaborators required by EngineLoop."""

    pipeline: StrategyPipeline
    planner: ExecutionPlanner
    brokerage: Brokerage
    pre_trade_check: CompositePreTradeCheck
    data_feed: DataFeed
    synchronizer: Synchronizer
    options: EngineOptions


_LEGACY_DEPENDENCY_NAMES = (
    "pipeline",
    "planner",
    "brokerage",
    "pre_trade_check",
    "data_feed",
    "synchronizer",
    "options",
)
_LEGACY_DEPENDENCY_NAME_SET = frozenset(_LEGACY_DEPENDENCY_NAMES)


def canonical_json(value: object) -> str:
    """Encode checkpoint evidence deterministically, including integer IDs."""
    return orjson.dumps(
        value,
        option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SORT_KEYS,
    ).decode()


def normalize_engine_loop_deps(
    deps: object | None,
    legacy_args: tuple[object, ...],
    legacy_ports: dict[str, object],
) -> EngineLoopDeps:
    """Normalize the dependency bundle while preserving the legacy constructor."""
    if isinstance(deps, EngineLoopDeps):
        if legacy_args or legacy_ports:
            raise TypeError("EngineLoopDeps cannot be combined with legacy ports")
        return deps
    if deps is None:
        return _engine_loop_deps_from_legacy(legacy_args, legacy_ports)
    return _engine_loop_deps_from_legacy((deps, *legacy_args), legacy_ports)


def _engine_loop_deps_from_legacy(
    legacy_args: tuple[object, ...],
    legacy_ports: dict[str, object],
) -> EngineLoopDeps:
    if len(legacy_args) > len(_LEGACY_DEPENDENCY_NAMES):
        raise TypeError("EngineLoop received too many positional dependencies")

    ports = dict(legacy_ports)
    for name, value in zip(_LEGACY_DEPENDENCY_NAMES, legacy_args, strict=False):
        if name in ports:
            raise TypeError(f"EngineLoop got duplicate dependency: {name}")
        ports[name] = value

    unexpected = sorted(set(ports) - _LEGACY_DEPENDENCY_NAME_SET)
    if unexpected:
        names = ", ".join(unexpected)
        raise TypeError(f"EngineLoop got unexpected dependencies: {names}")
    missing = [name for name in _LEGACY_DEPENDENCY_NAMES if name not in ports]
    if missing:
        names = ", ".join(missing)
        raise TypeError(f"EngineLoop missing dependencies: {names}")

    return EngineLoopDeps(
        pipeline=cast(StrategyPipeline, ports["pipeline"]),
        planner=cast(ExecutionPlanner, ports["planner"]),
        brokerage=cast(Brokerage, ports["brokerage"]),
        pre_trade_check=cast(CompositePreTradeCheck, ports["pre_trade_check"]),
        data_feed=cast(DataFeed, ports["data_feed"]),
        synchronizer=cast(Synchronizer, ports["synchronizer"]),
        options=cast(EngineOptions, ports["options"]),
    )
