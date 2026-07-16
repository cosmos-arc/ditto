"""StrategyRunLifecycleStore 单元测试 — 策略运行生命周期管理。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_kernel.strategy import RunStatus
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
    StrategyRunReaderProtocol,
    StrategyRunWriterProtocol,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    run_id: str = "run-001",
    strategy_id: str = "momentum-etf",
    strategy_version: str = "1.0",
    mode: str = "backtest",
    status: str = "pending",
    **overrides: object,
) -> StrategyRunRecord:
    """创建 StrategyRunRecord 测试辅助函数。"""
    return StrategyRunRecord(
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        mode=mode,
        status=status,
        **overrides,
    )


def _make_service(
    reader: MagicMock | None = None,
    writer: MagicMock | None = None,
) -> StrategyRunLifecycleStore:
    """创建 StrategyRunLifecycleStore 实例。"""
    resolved_reader = reader or MagicMock(spec=StrategyRunReaderProtocol)
    if reader is None:
        resolved_reader.get.return_value = None
    return StrategyRunLifecycleStore(
        reader=resolved_reader,
        writer=writer or MagicMock(spec=StrategyRunWriterProtocol),
    )


# ---------------------------------------------------------------------------
# Tests: StrategyRunRecord
# ---------------------------------------------------------------------------


class TestStrategyRunRecord:
    """测试 StrategyRunRecord frozen dataclass。"""

    def test_default_values(self) -> None:
        """默认值正确。"""
        record = StrategyRunRecord(
            run_id="run-001",
            strategy_id="test",
        )
        assert record.run_id == "run-001"
        assert record.strategy_id == "test"
        assert record.strategy_version == ""
        assert record.mode == "backtest"
        assert record.status == "pending"
        assert record.started_at == ""
        assert record.completed_at == ""
        assert record.error_message == ""

    def test_frozen(self) -> None:
        """StrategyRunRecord 是 frozen，不可变。"""
        record = _make_record()
        with pytest.raises(AttributeError):
            record.status = "running"  # type: ignore[misc]

    def test_custom_values(self) -> None:
        """自定义值正确。"""
        record = _make_record(
            strategy_version="2.0",
            mode="research",
            status="running",
            error_message="test error",
        )
        assert record.strategy_version == "2.0"
        assert record.mode == "research"
        assert record.status == "running"
        assert record.error_message == "test error"


# ---------------------------------------------------------------------------
# Tests: RunStatus
# ---------------------------------------------------------------------------


class TestRunStatus:
    """测试 RunStatus StrEnum。"""

    def test_values(self) -> None:
        """枚举值完整。"""
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# Tests: StrategyRunService — 生命周期
# ---------------------------------------------------------------------------


class TestStrategyRunServiceLifecycle:
    """测试 StrategyRunService 运行生命周期。"""

    def test_create_run(self) -> None:
        """create_run() 写入 pending 记录。"""
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        service = _make_service(writer=mock_writer)

        service.create_run(
            run_id="run-new",
            strategy_id="test-strat",
            strategy_version="1.0",
            mode="backtest",
        )

        mock_writer.save.assert_called_once()
        record = mock_writer.save.call_args[0][0]
        assert record.run_id == "run-new"
        assert record.strategy_id == "test-strat"
        assert record.status == RunStatus.PENDING

    def test_create_run_sets_started_at(self) -> None:
        """create_run() 生成 started_at 时间戳。"""
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        service = _make_service(writer=mock_writer)

        service.create_run(
            run_id="run-ts",
            strategy_id="test-strat",
        )

        record = mock_writer.save.call_args[0][0]
        assert record.started_at != ""
        assert record.started_at.endswith("Z")

    def test_create_run_does_not_overwrite_completed_evidence(self) -> None:
        """Deterministic retries must preserve an existing terminal run fact."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        mock_reader.get.return_value = _make_record(
            run_id="eod-2026-07-16-stock-1",
            strategy_id="stock",
            strategy_version="1",
            mode="recommendation",
            status="completed",
        )
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        service = _make_service(reader=mock_reader, writer=mock_writer)

        service.create_run(
            run_id="eod-2026-07-16-stock-1",
            strategy_id="stock",
            strategy_version="1",
            mode="recommendation",
        )

        mock_writer.save.assert_not_called()

    def test_create_run_accepts_same_identity_after_losing_insert_race(self) -> None:
        """A concurrent identical creator owns the durable row without conflict."""
        concurrent = _make_record(
            run_id="eod-2026-07-16-stock-1",
            strategy_id="stock",
            strategy_version="1",
            mode="recommendation",
        )
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        mock_reader.get.side_effect = [None, concurrent]
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.save.return_value = False
        service = _make_service(reader=mock_reader, writer=mock_writer)

        service.create_run(
            run_id="eod-2026-07-16-stock-1",
            strategy_id="stock",
            strategy_version="1",
            mode="recommendation",
        )

        mock_writer.save.assert_called_once()
        assert mock_reader.get.call_count == 2

    def test_create_run_rejects_different_identity_after_losing_insert_race(
        self,
    ) -> None:
        """A concurrent hash collision must never be claimed as this run."""
        concurrent = _make_record(
            run_id="eod-collision",
            strategy_id="other",
            strategy_version="9",
            mode="recommendation",
        )
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        mock_reader.get.side_effect = [None, concurrent]
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.save.return_value = False
        service = _make_service(reader=mock_reader, writer=mock_writer)

        with pytest.raises(ValueError, match="different run identity"):
            service.create_run(
                run_id="eod-collision",
                strategy_id="stock",
                strategy_version="1",
                mode="recommendation",
            )

    def test_mark_running(self) -> None:
        """mark_running() 更新状态为 running。"""
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.update_status.return_value = True
        service = _make_service(writer=mock_writer)

        result = service.mark_running("run-001")

        assert result is True
        mock_writer.update_status.assert_called_once_with("run-001", RunStatus.RUNNING)

    def test_retry_failed_delegates_to_guarded_writer_transition(self) -> None:
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.retry_failed.return_value = True
        service = _make_service(writer=mock_writer)

        result = service.retry_failed("run-001", config_json='{"attempt":2}')

        assert result is True
        mock_writer.retry_failed.assert_called_once_with(
            "run-001",
            config_json='{"attempt":2}',
        )

    def test_mark_completed(self) -> None:
        """mark_completed() 更新状态为 completed。"""
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.update_status.return_value = True
        service = _make_service(writer=mock_writer)

        result = service.mark_completed("run-001")

        assert result is True
        mock_writer.update_status.assert_called_once_with(
            "run-001", RunStatus.COMPLETED
        )

    def test_mark_failed(self) -> None:
        """mark_failed() 更新状态为 failed 并记录错误信息。"""
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.update_status.return_value = True
        service = _make_service(writer=mock_writer)

        result = service.mark_failed("run-001", "OOM error")

        assert result is True
        mock_writer.update_status.assert_called_once_with(
            "run-001", RunStatus.FAILED, "OOM error"
        )

    def test_mark_pending_failed_delegates_to_guarded_writer_transition(self) -> None:
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.mark_pending_failed.return_value = True
        service = _make_service(writer=mock_writer)

        result = service.mark_pending_failed("run-001", "blocked:NOT_READY")

        assert result is True
        mock_writer.mark_pending_failed.assert_called_once_with(
            "run-001",
            "blocked:NOT_READY",
        )

    def test_refresh_blocked_evidence_delegates_to_guarded_writer_update(
        self,
    ) -> None:
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        mock_writer.refresh_blocked_evidence.return_value = True
        service = _make_service(writer=mock_writer)

        result = service.refresh_blocked_evidence(
            "run-001",
            config_json='{"state":"B"}',
        )

        assert result is True
        mock_writer.refresh_blocked_evidence.assert_called_once_with(
            "run-001",
            config_json='{"state":"B"}',
        )

    def test_get_run(self) -> None:
        """get_run() 返回运行记录。"""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        expected = _make_record()
        mock_reader.get.return_value = expected
        service = _make_service(reader=mock_reader)

        result = service.get_run("run-001")

        assert result is expected
        mock_reader.get.assert_called_once_with("run-001")

    def test_get_run_not_found(self) -> None:
        """get_run() 找不到时返回 None。"""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        mock_reader.get.return_value = None
        service = _make_service(reader=mock_reader)

        result = service.get_run("nonexistent")

        assert result is None

    def test_list_by_strategy(self) -> None:
        """list_by_strategy() 返回指定策略的运行记录。"""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        records = [_make_record(), _make_record(run_id="run-002")]
        mock_reader.list_by_strategy.return_value = records
        service = _make_service(reader=mock_reader)

        result = service.list_by_strategy("momentum-etf")

        assert len(result) == 2
        mock_reader.list_by_strategy.assert_called_once_with("momentum-etf")


# ---------------------------------------------------------------------------
# Tests: StrategyRunService — Lineage
# ---------------------------------------------------------------------------


class TestStrategyRunServiceLineage:
    """测试 StrategyRunService 血统查询方法."""

    def test_list_lineage_single_run(self) -> None:
        """list_lineage() 原始运行返回长度 1 的链."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        record = _make_record(run_id="run-001", parent_run_id="")
        mock_reader.get.return_value = record
        service = _make_service(reader=mock_reader)

        result = service.list_lineage("run-001")

        assert len(result) == 1
        assert result[0].run_id == "run-001"

    def test_list_lineage_chain_depth_2(self) -> None:
        """list_lineage() 追溯两级 — run-002 → run-001."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        original = _make_record(run_id="run-001", parent_run_id="")
        replay = _make_record(run_id="run-002", parent_run_id="run-001")

        def _get(run_id: str) -> StrategyRunRecord | None:
            return {"run-001": original, "run-002": replay}.get(run_id)

        mock_reader.get.side_effect = _get
        service = _make_service(reader=mock_reader)

        result = service.list_lineage("run-002")

        assert len(result) == 2
        assert result[0].run_id == "run-001"
        assert result[1].run_id == "run-002"

    def test_list_lineage_not_found(self) -> None:
        """list_lineage() 运行不存在返回空列表."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        mock_reader.get.return_value = None
        service = _make_service(reader=mock_reader)

        result = service.list_lineage("nonexistent")

        assert result == []

    def test_list_lineage_breaks_cycle(self) -> None:
        """list_lineage() 检测循环并中断."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        record_a = _make_record(run_id="run-a", parent_run_id="run-b")
        record_b = _make_record(run_id="run-b", parent_run_id="run-a")

        def _get(run_id: str) -> StrategyRunRecord | None:
            return {"run-a": record_a, "run-b": record_b}.get(run_id)

        mock_reader.get.side_effect = _get
        service = _make_service(reader=mock_reader)

        result = service.list_lineage("run-a")

        assert len(result) == 2

    def test_list_replays(self) -> None:
        """list_replays() 返回指定运行的直接重放."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        replays = [
            _make_record(run_id="run-002", parent_run_id="run-001"),
        ]
        mock_reader.list_by_parent.return_value = replays
        service = _make_service(reader=mock_reader)

        result = service.list_replays("run-001")

        assert len(result) == 1
        mock_reader.list_by_parent.assert_called_once_with("run-001")

    def test_create_run_with_parent(self) -> None:
        """create_run() 带 parent_run_id 正确保存."""
        mock_writer = MagicMock(spec=StrategyRunWriterProtocol)
        service = _make_service(writer=mock_writer)

        service.create_run(
            run_id="run-002",
            strategy_id="strat-a",
            parent_run_id="run-001",
        )

        record = mock_writer.save.call_args[0][0]
        assert record.parent_run_id == "run-001"


# ---------------------------------------------------------------------------
# Tests: StrategyRunService — list_runs 分页
# ---------------------------------------------------------------------------


class TestStrategyRunServiceListRunsPagination:
    """测试 StrategyRunService.list_runs 分页参数透传."""

    def test_list_runs_with_limit(self) -> None:
        """list_runs(limit=2) 透传 limit 给 reader."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        records = [_make_record(run_id=f"run-{i:03d}") for i in range(5)]
        mock_reader.list_runs.return_value = records[:2]
        service = _make_service(reader=mock_reader)

        result = service.list_runs(limit=2)

        assert len(result) == 2
        mock_reader.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=2,
            offset=None,
        )

    def test_list_runs_with_offset(self) -> None:
        """list_runs(offset=3) 透传 offset 给 reader."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        records = [_make_record(run_id=f"run-{i:03d}") for i in range(5)]
        mock_reader.list_runs.return_value = records[3:]
        service = _make_service(reader=mock_reader)

        result = service.list_runs(offset=3)

        assert len(result) == 2
        mock_reader.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=None,
            offset=3,
        )

    def test_list_runs_with_limit_and_offset(self) -> None:
        """list_runs(limit=2, offset=1) 组合透传."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        records = [_make_record(run_id=f"run-{i:03d}") for i in range(5)]
        mock_reader.list_runs.return_value = records[1:3]
        service = _make_service(reader=mock_reader)

        result = service.list_runs(limit=2, offset=1)

        assert len(result) == 2
        mock_reader.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=2,
            offset=1,
        )

    def test_list_runs_default_no_pagination(self) -> None:
        """list_runs() 无分页参数时 limit/offset 均为 None."""
        mock_reader = MagicMock(spec=StrategyRunReaderProtocol)
        records = [_make_record(run_id=f"run-{i:03d}") for i in range(5)]
        mock_reader.list_runs.return_value = records
        service = _make_service(reader=mock_reader)

        result = service.list_runs()

        assert len(result) == 5
        mock_reader.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=None,
            offset=None,
        )
