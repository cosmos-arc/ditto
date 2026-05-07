"""Signal domain models — 信号领域数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SignalRecord"]


@dataclass(frozen=True)
class SignalRecord:
    """Strategy-owned signal record for downstream storage contracts."""

    signal_id: str
    strategy_id: str
    run_id: str
    trade_date: str
    instrument_id: int
    direction: str
    strength: float
    score: float
    metadata: dict[str, object] = field(default_factory=dict)
