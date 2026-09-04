"""Small runtime metadata projections used by backtest orchestration."""

from __future__ import annotations

from typing import Protocol

__all__ = ["model_name", "resume_provenance"]


class _ResumeConfig(Protocol):
    @property
    def resume_from_run_id(self) -> str | None: ...

    @property
    def resume_checkpoint_trade_date(self) -> str | None: ...

    @property
    def resume_checkpoint_completed_days(self) -> int: ...

    @property
    def resume_checkpoint_total_days(self) -> int: ...

    @property
    def resume_checkpoint_nav(self) -> float | None: ...

    @property
    def resume_checkpoint_order_count(self) -> int: ...

    @property
    def resume_checkpoint_fill_count(self) -> int: ...

    @property
    def resume_account_state_hash(self) -> str | None: ...

    @property
    def resume_settlement_state_hash(self) -> str | None: ...

    @property
    def resume_runtime_state_hash(self) -> str | None: ...


def resume_provenance(config: _ResumeConfig) -> dict[str, object] | None:
    """Build normalized checkpoint provenance for restored child-run artifacts."""
    if not config.resume_from_run_id:
        return None
    return {
        "from_run_id": config.resume_from_run_id,
        "checkpoint_trade_date": config.resume_checkpoint_trade_date,
        "checkpoint_completed_days": config.resume_checkpoint_completed_days,
        "checkpoint_total_days": config.resume_checkpoint_total_days,
        "checkpoint_nav": config.resume_checkpoint_nav,
        "checkpoint_order_count": config.resume_checkpoint_order_count,
        "checkpoint_fill_count": config.resume_checkpoint_fill_count,
        "account_state_hash": config.resume_account_state_hash,
        "settlement_state_hash": config.resume_settlement_state_hash,
        "runtime_state_hash": config.resume_runtime_state_hash,
    }


def model_name(model: object | None) -> str:
    """Return a stable model class name for artifact metadata."""
    if model is None:
        return ""
    return type(model).__name__
