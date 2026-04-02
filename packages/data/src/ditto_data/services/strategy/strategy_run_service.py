"""StrategyRunService — 策略运行生命周期管理."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from ditto_data.models.strategy_run import (
    RunStatus,
    StrategyRunRecord,
)

__all__ = [
    "StrategyRunReaderProtocol",
    "StrategyRunService",
    "StrategyRunWriterProtocol",
]


@runtime_checkable
class StrategyRunReaderProtocol(Protocol):
    """策略运行读取协议."""

    def get(self, run_id: str) -> StrategyRunRecord | None:
        """获取运行记录."""
        ...

    def list_by_strategy(self, strategy_id: str) -> list[StrategyRunRecord]:
        """按策略 ID 列出运行记录."""
        ...


@runtime_checkable
class StrategyRunWriterProtocol(Protocol):
    """策略运行写入协议."""

    def save(self, record: StrategyRunRecord) -> None:
        """保存运行记录."""
        ...

    def update_status(
        self,
        run_id: str,
        status: str,
        error_message: str = "",
    ) -> bool:
        """更新运行状态，成功返回 True."""
        ...


class StrategyRunService:
    """策略运行服务 — 生命周期管理 (pending → running → completed/failed)."""

    def __init__(
        self,
        reader: StrategyRunReaderProtocol,
        writer: StrategyRunWriterProtocol,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def create_run(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = "",
        mode: str = "backtest",
    ) -> None:
        """创建运行记录 (初始状态 pending)."""
        record = StrategyRunRecord(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            mode=mode,
            status=RunStatus.PENDING,
            started_at=_utc_now(),
        )
        self._writer.save(record)

    def mark_running(self, run_id: str) -> bool:
        """标记为运行中."""
        return self._writer.update_status(run_id, RunStatus.RUNNING)

    def mark_completed(self, run_id: str) -> bool:
        """标记为已完成."""
        return self._writer.update_status(run_id, RunStatus.COMPLETED)

    def mark_failed(self, run_id: str, error_message: str = "") -> bool:
        """标记为失败."""
        return self._writer.update_status(run_id, RunStatus.FAILED, error_message)

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """获取运行记录."""
        return self._reader.get(run_id)

    def list_by_strategy(self, strategy_id: str) -> list[StrategyRunRecord]:
        """按策略 ID 列出运行记录."""
        return self._reader.list_by_strategy(strategy_id)


def _utc_now() -> str:
    """返回 RFC3339 UTC 时间戳。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
