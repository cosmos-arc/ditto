"""StrategyRunLifecycleStore — 策略运行生命周期持久化存储."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_kernel.strategy import RunStatus

from ditto_strategy._internal import utc_now
from ditto_strategy.runs.models import StrategyRunCheckpointRecord, StrategyRunRecord

__all__ = [
    "StrategyRunCheckpointReaderProtocol",
    "StrategyRunCheckpointStore",
    "StrategyRunCheckpointWriterProtocol",
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

    def save(self, record: StrategyRunRecord) -> bool:
        """Insert a run if absent; return False without replacing evidence."""
        ...

    def update_status(
        self,
        run_id: str,
        status: str,
        error_message: str = "",
    ) -> bool:
        """更新运行状态，成功返回 True."""
        ...

    def retry_failed(self, run_id: str, *, config_json: str = "") -> bool:
        """CAS 恢复 failed run，成功返回 True."""
        ...

    def mark_pending_failed(self, run_id: str, error_message: str = "") -> bool:
        """Only fail a run that has not been claimed by a worker."""
        ...

    def refresh_blocked_evidence(self, run_id: str, *, config_json: str) -> bool:
        """Refresh required-data evidence on its exact failed state."""
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


@runtime_checkable
class StrategyRunCheckpointReaderProtocol(Protocol):
    """策略运行 checkpoint 读取协议."""

    def get_latest_checkpoint(self, run_id: str) -> StrategyRunCheckpointRecord | None:
        """获取运行最新 checkpoint."""
        ...

    def list_checkpoints_by_strategy(
        self,
        strategy_id: str,
    ) -> list[StrategyRunCheckpointRecord]:
        """按策略列出各运行最新 checkpoint."""
        ...


@runtime_checkable
class StrategyRunCheckpointWriterProtocol(Protocol):
    """策略运行 checkpoint 写入协议."""

    def save_checkpoint(self, record: StrategyRunCheckpointRecord) -> None:
        """保存运行最新 checkpoint."""
        ...


class StrategyRunCheckpointStore:
    """Persistent latest-checkpoint store for strategy runs."""

    def __init__(
        self,
        reader: StrategyRunCheckpointReaderProtocol,
        writer: StrategyRunCheckpointWriterProtocol,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def save_checkpoint(self, record: StrategyRunCheckpointRecord) -> None:
        """保存运行最新 checkpoint."""
        self._writer.save_checkpoint(record)

    def get_latest_checkpoint(self, run_id: str) -> StrategyRunCheckpointRecord | None:
        """获取运行最新 checkpoint."""
        return self._reader.get_latest_checkpoint(run_id)

    def list_checkpoints_by_strategy(
        self,
        strategy_id: str,
    ) -> list[StrategyRunCheckpointRecord]:
        """按策略列出各运行最新 checkpoint."""
        return self._reader.list_checkpoints_by_strategy(strategy_id)


def _validate_run_identity(
    existing: StrategyRunRecord,
    *,
    strategy_id: str,
    strategy_version: str,
    mode: str,
    parent_run_id: str,
) -> None:
    """Reject a deterministic run ID already owned by another identity."""
    identity = (
        existing.strategy_id,
        existing.strategy_version,
        existing.mode,
        existing.parent_run_id,
    )
    requested_identity = (
        strategy_id,
        strategy_version,
        mode,
        parent_run_id,
    )
    if identity != requested_identity:
        msg = f"run_id {existing.run_id} already belongs to a different run identity"
        raise ValueError(msg)


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
        existing = self._reader.get(run_id)
        if existing is not None:
            _validate_run_identity(
                existing,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                mode=mode,
                parent_run_id=parent_run_id,
            )
            return
        record = StrategyRunRecord(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            mode=mode,
            status=RunStatus.PENDING,
            started_at=utc_now(),
            parent_run_id=parent_run_id,
            config_json=config_json,
        )
        if self._writer.save(record):
            return
        concurrent = self._reader.get(run_id)
        if concurrent is None:
            msg = f"run_id {run_id} insert lost without a durable owner"
            raise RuntimeError(msg)
        _validate_run_identity(
            concurrent,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            mode=mode,
            parent_run_id=parent_run_id,
        )

    def mark_running(self, run_id: str) -> bool:
        """标记为运行中."""
        return self._writer.update_status(run_id, RunStatus.RUNNING)

    def retry_failed(self, run_id: str, *, config_json: str = "") -> bool:
        """只允许 failed run 以同一身份进入一次新的 pending 尝试。"""
        return self._writer.retry_failed(run_id, config_json=config_json)

    def mark_completed(self, run_id: str) -> bool:
        """标记为已完成."""
        return self._writer.update_status(run_id, RunStatus.COMPLETED)

    def mark_failed(self, run_id: str, error_message: str = "") -> bool:
        """标记为失败."""
        return self._writer.update_status(run_id, RunStatus.FAILED, error_message)

    def mark_pending_failed(self, run_id: str, error_message: str = "") -> bool:
        """Persist blocked evidence only while the run remains unclaimed."""
        return self._writer.mark_pending_failed(run_id, error_message)

    def refresh_blocked_evidence(self, run_id: str, *, config_json: str) -> bool:
        """Refresh required-data evidence without reopening failed ownership."""
        return self._writer.refresh_blocked_evidence(
            run_id,
            config_json=config_json,
        )

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
