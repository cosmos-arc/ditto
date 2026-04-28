"""Tests for RunReadModel -- 跨策略运行记录查询与过滤."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.query.run import RunReadModel
from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_kernel.strategy import RunStatus


def _make_record(**overrides: object) -> StrategyRunRecord:
    """构造一个带默认值的 StrategyRunRecord."""
    defaults: dict[str, object] = {
        "run_id": "run-001",
        "strategy_id": "strat-a",
        "strategy_version": "1.0",
        "mode": "backtest",
        "status": RunStatus.COMPLETED,
        "started_at": "2024-01-15T08:00:00Z",
        "completed_at": "2024-01-15T09:30:00Z",
        "error_message": "",
    }
    defaults.update(overrides)
    return StrategyRunRecord(**defaults)  # type: ignore[arg-type]


def _make_service() -> MagicMock:
    """构造一个符合 StrategyRunService 接口的 MagicMock."""
    return MagicMock(
        spec=["get_run", "list_runs"],
    )


# ========== list_runs ==========


class TestRunReadModelListRuns:
    """RunReadModel.list_runs — 跨策略运行记录查询."""

    def test_list_runs_no_filter(self) -> None:
        """无过滤条件时返回全部运行记录."""
        service = _make_service()
        records = [
            _make_record(run_id="run-001"),
            _make_record(run_id="run-002", strategy_id="strat-b"),
        ]
        service.list_runs.return_value = records
        facade = RunReadModel(run_service=service)

        result = facade.list_runs()

        assert result == records
        assert len(result) == 2
        service.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=None,
            offset=None,
        )

    def test_list_runs_filter_by_status(self) -> None:
        """按状态过滤运行记录."""
        service = _make_service()
        records = [
            _make_record(run_id="run-001", status=RunStatus.FAILED),
        ]
        service.list_runs.return_value = records
        facade = RunReadModel(run_service=service)

        result = facade.list_runs(status=RunStatus.FAILED)

        assert result == records
        assert len(result) == 1
        assert result[0].status == RunStatus.FAILED
        service.list_runs.assert_called_once_with(
            strategy_id=None,
            status=RunStatus.FAILED,
            start_date=None,
            end_date=None,
            limit=None,
            offset=None,
        )

    def test_list_runs_filter_by_strategy_id(self) -> None:
        """按策略 ID 过滤运行记录."""
        service = _make_service()
        records = [
            _make_record(run_id="run-001", strategy_id="strat-a"),
            _make_record(run_id="run-003", strategy_id="strat-a"),
        ]
        service.list_runs.return_value = records
        facade = RunReadModel(run_service=service)

        result = facade.list_runs(strategy_id="strat-a")

        assert result == records
        assert all(r.strategy_id == "strat-a" for r in result)
        service.list_runs.assert_called_once_with(
            strategy_id="strat-a",
            status=None,
            start_date=None,
            end_date=None,
            limit=None,
            offset=None,
        )

    def test_list_runs_filter_by_date_range(self) -> None:
        """按时间范围过滤运行记录."""
        service = _make_service()
        records = [
            _make_record(
                run_id="run-001",
                started_at="2024-01-15T08:00:00Z",
            ),
        ]
        service.list_runs.return_value = records
        facade = RunReadModel(run_service=service)

        result = facade.list_runs(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result == records
        service.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date="2024-01-01",
            end_date="2024-01-31",
            limit=None,
            offset=None,
        )

    def test_list_runs_combined_filters(self) -> None:
        """多维度组合过滤."""
        service = _make_service()
        records = [
            _make_record(
                run_id="run-001",
                strategy_id="strat-a",
                status=RunStatus.COMPLETED,
                started_at="2024-01-15T08:00:00Z",
            ),
        ]
        service.list_runs.return_value = records
        facade = RunReadModel(run_service=service)

        result = facade.list_runs(
            strategy_id="strat-a",
            status=RunStatus.COMPLETED,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result == records
        assert len(result) == 1
        service.list_runs.assert_called_once_with(
            strategy_id="strat-a",
            status=RunStatus.COMPLETED,
            start_date="2024-01-01",
            end_date="2024-01-31",
            limit=None,
            offset=None,
        )

    def test_list_runs_empty_result(self) -> None:
        """无匹配记录时返回空列表."""
        service = _make_service()
        service.list_runs.return_value = []
        facade = RunReadModel(run_service=service)

        result = facade.list_runs(status=RunStatus.FAILED)

        assert result == []


# ========== get_run ==========


class TestRunReadModelGetRun:
    """RunReadModel.get_run — 单条运行记录查询."""

    def test_get_run_found(self) -> None:
        """找到记录时返回 StrategyRunRecord."""
        service = _make_service()
        record = _make_record(run_id="run-001")
        service.get_run.return_value = record
        facade = RunReadModel(run_service=service)

        result = facade.get_run("run-001")

        assert result is not None
        assert result.run_id == "run-001"
        assert result.strategy_id == "strat-a"
        service.get_run.assert_called_once_with("run-001")

    def test_get_run_not_found(self) -> None:
        """未找到记录时返回 None."""
        service = _make_service()
        service.get_run.return_value = None
        facade = RunReadModel(run_service=service)

        result = facade.get_run("nonexistent")

        assert result is None
        service.get_run.assert_called_once_with("nonexistent")
