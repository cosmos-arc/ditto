"""StrategyContext — 策略运行时上下文."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["StrategyContext"]


@dataclass
class StrategyContext:
    """
    策略运行时上下文 — EngineLoop 持有，跨交易日持久化.

    Attributes:
        risk_locked_instruments: 被风控锁定的标的
            {instrument_id: (reason, cooldown_until_date | None)}.
            cooldown_until_date 为 None 表示当日锁定（次日自动清除），
            非 None 表示跨日锁定（到期日前保留）。
        positions: 持仓成本数据 {instrument_id: avg_cost}，
            跨交易日持久化，不受 ``clear_locks()`` 影响。

    """

    risk_locked_instruments: dict[str, tuple[str, str | None]] = field(
        default_factory=dict,
    )
    positions: dict[str, float] = field(default_factory=dict)

    def lock_instrument(
        self,
        instrument_id: str,
        reason: str,
        cooldown_until: str | None = None,
    ) -> None:
        """锁定标的。cooldown_until 为 None 时当日有效，否则跨日有效。"""
        self.risk_locked_instruments[instrument_id] = (reason, cooldown_until)

    def is_locked(self, instrument_id: str) -> bool:
        """检查标的是否被锁定。"""
        return instrument_id in self.risk_locked_instruments

    def get_locked_instruments(self) -> set[str]:
        """返回所有被锁定标的 ID 集合。"""
        return set(self.risk_locked_instruments.keys())

    def clear_locks(self, today: str) -> None:
        """
        清除已到期锁定，不影响 positions。

        cooldown_until 为 None（当日锁定）→ 始终清除。
        cooldown_until < today（已过期）→ 清除。
        cooldown_until >= today（未过期）→ 保留（含当天）。
        """
        self.risk_locked_instruments = {
            iid: info
            for iid, info in self.risk_locked_instruments.items()
            if info[1] is not None and info[1] >= today
        }
