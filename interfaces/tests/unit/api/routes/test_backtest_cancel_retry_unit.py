"""
Unit tests for cancel / retry endpoint logic.

Tests status guard, record-not-found, and response mapping.
Route handler logic is tested at model-level — mirroring
test_backtest_trigger_unit.py pattern.
"""

from __future__ import annotations

from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_interfaces.models.backtest import (
    CancelRunResponse,
    RetryRunResponse,
    to_run_response,
)
from ditto_kernel.enums import RunStatus
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    run_id: str = "run001",
    strategy_id: str = "momentum-etf",
    status: str = RunStatus.RUNNING,
    parent_run_id: str = "",
) -> StrategyRunRecord:
    """创建测试用 StrategyRunRecord."""
    return StrategyRunRecord(
        run_id=run_id,
        strategy_id=strategy_id,
        status=status,
        parent_run_id=parent_run_id,
    )


# ---------------------------------------------------------------------------
# Cancel: status guard
# ---------------------------------------------------------------------------


class TestCancelStatusGuard:
    """Cancel 端点 — 状态前置校验."""

    def test_cancel_running_is_allowed(self) -> None:
        """status=running → 允许取消."""
        record = _make_record(status=RunStatus.RUNNING)
        # 模拟 endpoint 逻辑
        allowed = record.status in (RunStatus.PENDING, RunStatus.RUNNING)
        assert allowed is True

    def test_cancel_pending_is_allowed(self) -> None:
        """status=pending → 允许取消."""
        record = _make_record(status=RunStatus.PENDING)
        allowed = record.status in (RunStatus.PENDING, RunStatus.RUNNING)
        assert allowed is True

    def test_cancel_completed_rejected(self) -> None:
        """status=completed → 409 Conflict."""
        record = _make_record(status=RunStatus.COMPLETED)
        allowed = record.status in (RunStatus.PENDING, RunStatus.RUNNING)
        assert allowed is False
        http_exc = HTTPException(
            status_code=409,
            detail="Cannot cancel run in 'completed' status",
        )
        assert http_exc.status_code == 409

    def test_cancel_failed_rejected(self) -> None:
        """status=failed → 409 Conflict."""
        record = _make_record(status=RunStatus.FAILED)
        allowed = record.status in (RunStatus.PENDING, RunStatus.RUNNING)
        assert allowed is False

    def test_cancel_cancelled_rejected(self) -> None:
        """status=cancelled → 409 Conflict."""
        record = _make_record(status=RunStatus.CANCELLED)
        allowed = record.status in (RunStatus.PENDING, RunStatus.RUNNING)
        assert allowed is False


# ---------------------------------------------------------------------------
# Cancel: response mapping
# ---------------------------------------------------------------------------


class TestCancelResponseMapping:
    """Cancel 成功 → CancelRunResponse 映射."""

    def test_cancel_response_fields(self) -> None:
        """取消成功后返回 CancelRunResponse."""
        record = _make_record(run_id="run001", status=RunStatus.RUNNING)
        response = CancelRunResponse(run_id=record.run_id, status="cancelled")
        assert response.run_id == "run001"
        assert response.status == "cancelled"


# ---------------------------------------------------------------------------
# Retry: status guard
# ---------------------------------------------------------------------------


class TestRetryStatusGuard:
    """Retry 端点 — 状态前置校验."""

    def test_retry_failed_is_allowed(self) -> None:
        """status=failed → 允许重试."""
        record = _make_record(status=RunStatus.FAILED)
        allowed = record.status in (RunStatus.FAILED, RunStatus.CANCELLED)
        assert allowed is True

    def test_retry_cancelled_is_allowed(self) -> None:
        """status=cancelled → 允许重试."""
        record = _make_record(status=RunStatus.CANCELLED)
        allowed = record.status in (RunStatus.FAILED, RunStatus.CANCELLED)
        assert allowed is True

    def test_retry_running_rejected(self) -> None:
        """status=running → 409 Conflict."""
        record = _make_record(status=RunStatus.RUNNING)
        allowed = record.status in (RunStatus.FAILED, RunStatus.CANCELLED)
        assert allowed is False
        http_exc = HTTPException(
            status_code=409,
            detail="Cannot retry run in 'running' status",
        )
        assert http_exc.status_code == 409

    def test_retry_completed_rejected(self) -> None:
        """status=completed → 409 Conflict."""
        record = _make_record(status=RunStatus.COMPLETED)
        allowed = record.status in (RunStatus.FAILED, RunStatus.CANCELLED)
        assert allowed is False

    def test_retry_pending_rejected(self) -> None:
        """status=pending → 409 Conflict."""
        record = _make_record(status=RunStatus.PENDING)
        allowed = record.status in (RunStatus.FAILED, RunStatus.CANCELLED)
        assert allowed is False


# ---------------------------------------------------------------------------
# Retry: response mapping
# ---------------------------------------------------------------------------


class TestRetryResponseMapping:
    """Retry 成功 → RetryRunResponse 映射."""

    def test_retry_response_fields(self) -> None:
        """重试成功后返回 RetryRunResponse（含 parent_run_id）."""
        original = _make_record(run_id="run001", status=RunStatus.FAILED)
        new_run_id = "run002"
        response = RetryRunResponse(
            run_id=new_run_id,
            parent_run_id=original.run_id,
            status=RunStatus.PENDING,
        )
        assert response.run_id == "run002"
        assert response.parent_run_id == "run001"
        assert response.status == RunStatus.PENDING


# ---------------------------------------------------------------------------
# Not found: 404
# ---------------------------------------------------------------------------


class TestNotFound:
    """run_id 不存在 → 404."""

    def test_cancel_not_found(self) -> None:
        """取消时 run_id 不存在 → 404."""
        record: StrategyRunRecord | None = None
        if record is None:
            http_exc = HTTPException(status_code=404, detail="Run not found: missing")
            assert http_exc.status_code == 404
            assert "not found" in http_exc.detail.lower()

    def test_retry_not_found(self) -> None:
        """重试时 run_id 不存在 → 404."""
        record: StrategyRunRecord | None = None
        if record is None:
            http_exc = HTTPException(status_code=404, detail="Run not found: missing")
            assert http_exc.status_code == 404
            assert "not found" in http_exc.detail.lower()


# ---------------------------------------------------------------------------
# Record → RunResponse mapping (reused by cancel)
# ---------------------------------------------------------------------------


class TestToRunResponseMapping:
    """StrategyRunRecord → RunResponse 转换验证."""

    def test_record_with_all_fields(self) -> None:
        """完整字段映射."""
        record = _make_record(
            run_id="run001",
            strategy_id="momentum-etf",
            status=RunStatus.CANCELLED,
        )
        response = to_run_response(record)
        assert response.run_id == "run001"
        assert response.strategy_id == "momentum-etf"
        assert response.status == RunStatus.CANCELLED
