"""StrategyRunLifecycleStore — 策略运行生命周期持久化存储."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from ditto_kernel.strategy import RunStatus

from ditto_strategy.runs.models import StrategyRunRecord

__all__ = [
    "StrategyRunLifecycleStore",
    "StrategyRunReaderProtocol",
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

    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StrategyRunRecord]:
        """跨策略运行记录查询，支持多维度过滤."""
        ...

    def list_by_parent(self, parent_run_id: str) -> list[StrategyRunRecord]:
        """列出指定运行的所有重放记录."""
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

    def update_progress(
        self,
        run_id: str,
        *,
        progress_pct: float = 0.0,
        current_step: str = "",
        completed_days: int = 0,
        total_days: int = 0,
    ) -> bool:
        """更新运行进度，成功返回 True."""
        ...


class StrategyRunLifecycleStore:
    """
    Persistent strategy run lifecycle store.

    pending -> running -> completed/failed
    """

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
        parent_run_id: str = "",
        config_json: str = "",
    ) -> None:
        """创建运行记录 (初始状态 pending)."""
        record = StrategyRunRecord(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            mode=mode,
            status=RunStatus.PENDING,
            started_at=_utc_now(),
            parent_run_id=parent_run_id,
            config_json=config_json,
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

    def mark_cancelled(self, run_id: str) -> bool:
        """标记为已取消."""
        return self._writer.update_status(run_id, RunStatus.CANCELLED)

    def update_progress(
        self,
        run_id: str,
        *,
        progress_pct: float = 0.0,
        current_step: str = "",
        completed_days: int = 0,
        total_days: int = 0,
    ) -> bool:
        """更新运行进度."""
        return self._writer.update_progress(
            run_id,
            progress_pct=progress_pct,
            current_step=current_step,
            completed_days=completed_days,
            total_days=total_days,
        )

    def is_cancelled(self, run_id: str) -> bool:
        """检查运行是否已被取消."""
        record = self._reader.get(run_id)
        return record is not None and record.status == RunStatus.CANCELLED

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """获取运行记录."""
        return self._reader.get(run_id)

    def list_by_strategy(self, strategy_id: str) -> list[StrategyRunRecord]:
        """按策略 ID 列出运行记录."""
        return self._reader.list_by_strategy(strategy_id)

    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StrategyRunRecord]:
        """跨策略运行记录查询，支持多维度过滤."""
        return self._reader.list_runs(
            strategy_id=strategy_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    def list_lineage(self, run_id: str) -> list[StrategyRunRecord]:
        """获取运行血统链 — 从当前运行追溯到原始运行."""
        chain: list[StrategyRunRecord] = []
        visited: set[str] = set()
        current_id = run_id

        while current_id:
            if current_id in visited:
                break  # 防止循环
            visited.add(current_id)
            record = self._reader.get(current_id)
            if record is None:
                break
            chain.append(record)
            current_id = record.parent_run_id

        # 反转为正序（原始运行在前）
        chain.reverse()
        return chain

    def list_replays(self, run_id: str) -> list[StrategyRunRecord]:
        """列出指定运行的所有直接重放记录."""
        return self._reader.list_by_parent(run_id)


def _utc_now() -> str:
    """返回 RFC3339 UTC 时间戳。"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
