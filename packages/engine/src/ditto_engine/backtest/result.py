"""
build_run_manifest — 回测 RunManifest 构建.

从 EngineLoop.run() 末尾提取的纯函数，无副作用，降低 engine.py 复杂度。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ditto_kernel.identity import InstrumentId

from ditto_engine.backtest.manifest import (
    InputRef,
    RuleRef,
    RunManifest,
    RunMode,
    hash_config,
    hash_spec,
    hash_universe,
)

if TYPE_CHECKING:
    from ditto_engine.backtest.engine import EngineConfig

__all__ = ["build_run_manifest"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_run_manifest(
    *,
    run_id: str,
    config: EngineConfig,
    input_instruments: set[InstrumentId],
    bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]],
    rule_refs: tuple[RuleRef, ...],
    random_seed: int,
) -> RunManifest:
    """构建 RunManifest — 记录运行配置、规则引用、输入依赖等治理字段."""
    input_refs = tuple(sorted(input_instruments))
    config_hash = hash_config(
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        strategy_id=config.strategy_id,
        rebalance_freq=config.rebalance_freq,
        engine_version=config.engine_version,
    )
    spec_hash = hash_spec(
        strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        rebalance_freq=config.rebalance_freq,
    )
    return RunManifest(
        run_id=run_id,
        strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        mode=RunMode.BACKTEST,
        input_refs=input_refs,
        input_ref_details=_build_input_ref_details(bar_fingerprints),
        parameter_overrides=config.parameter_overrides,
        rule_refs=rule_refs,
        config_hash=config_hash,
        engine_version=config.engine_version,
        spec_hash=spec_hash,
        universe_hash=hash_universe(input_instruments),
        dependency_versions=_collect_dependency_versions(),
        random_seed=random_seed,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_input_ref_details(
    bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]],
) -> tuple[InputRef, ...]:
    """
    从 bar_fingerprints 构建 InputRef 列表.

    对每个 instrument 的 sorted (date, close) 元组列表计算 SHA-256 哈希,
    生成 InputRef(instrument_id, data_hash, date_range, source).
    """
    refs: list[InputRef] = []
    for iid in sorted(bar_fingerprints.keys()):
        entries = bar_fingerprints[iid]
        sorted_entries = sorted(entries, key=lambda t: t[0])
        payload = ",".join(f"{d}:{c}" for d, c in sorted_entries)
        data_hash = (
            "sha256:"
            + hashlib.sha256(
                payload.encode("utf-8"),
            ).hexdigest()[:16]
        )
        dates = [d for d, _ in sorted_entries]
        date_range = (dates[0], dates[-1]) if dates else ("", "")
        refs.append(
            InputRef(
                instrument_id=iid,
                data_hash=data_hash,
                date_range=date_range,
                source="backtest:data_feed",
            ),
        )
    return tuple(refs)


def _collect_dependency_versions() -> tuple[str, ...]:
    """收集当前运行环境的依赖版本（用于可复现性审计）."""
    packages = ("polars", "ditto-engine")
    versions: list[str] = []
    for pkg in sorted(packages):
        try:
            ver = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            ver = "unknown"
        versions.append(f"{pkg}=={ver}")
    return tuple(versions)
