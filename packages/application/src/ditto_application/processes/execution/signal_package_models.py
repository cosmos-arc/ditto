"""Immutable read models emitted by the R1 signal package publisher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ditto_execution.targets import TargetPortfolioLike

from ditto_application.execution_dto import TradeIntent
from ditto_application.processes.execution.manual_sizing_context import (
    ManualSizingContext,
)

__all__ = ["SelectionReason", "SignalPackage", "SignalPackagePublishRequest"]


@dataclass(frozen=True)
class SignalPackagePublishRequest:
    """Explicit identity, sizing, and evidence inputs for one publication."""

    target: TargetPortfolioLike
    strategy_version: str
    account_id: str
    sleeve_id: str
    sizing_contexts: Mapping[int, ManualSizingContext]
    decision_date: str
    intended_trade_date: str
    required_datasets: tuple[str, ...]
    required_dataset_states: Sequence[Mapping[str, object]]
    dataset_snapshot_ids: Mapping[str, str] = field(default_factory=dict[str, str])
    factor_ids: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()
    factor_values: Mapping[int, Mapping[str, float]] = field(
        default_factory=dict[int, Mapping[str, float]]
    )
    industry_by_instrument: Mapping[int, str] = field(default_factory=dict[int, str])
    threshold: float = 0.01


@dataclass(frozen=True)
class SelectionReason:
    """Human-readable reason payload for one selected instrument."""

    instrument_id: int
    target_weight: float
    composite_score: float | None
    rank: int | None
    positive_contributors: tuple[str, ...]
    negative_contributors: tuple[str, ...]
    industry: str | None


@dataclass(frozen=True)
class SignalPackage:
    """Manual-trading signal package emitted from one target portfolio."""

    run_id: str
    strategy_id: str
    signal_date: str
    intents: tuple[TradeIntent, ...]
    dataset_snapshot_ids: dict[str, str]
    factor_ids: tuple[str, ...]
    risk_flags: tuple[str, ...]
    factor_values: dict[int, dict[str, float]]
    selection_reasons: dict[int, SelectionReason]
    checksum: str
    artifact_id: str = ""
    outcome: str = "completed"
    no_rebalance: bool = False
    artifact_status: str = ""
