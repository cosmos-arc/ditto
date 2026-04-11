"""Tests for LineageQueryFacade — 运行血统查询."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.query.lineage import LineageQueryFacade
from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_kernel.enums import RunStatus


def _make_record(
    run_id: str = "run-001",
    strategy_id: str = "strat-a",
    parent_run_id: str = "",
    **overrides: object,
) -> StrategyRunRecord:
    """构造测试用 StrategyRunRecord."""
    defaults: dict[str, object] = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": "1.0",
        "mode": "backtest",
        "status": RunStatus.COMPLETED,
        "started_at": "2024-01-15T08:00:00Z",
        "completed_at": "2024-01-15T09:30:00Z",
        "error_message": "",
        "parent_run_id": parent_run_id,
    }
    defaults.update(overrides)
    return StrategyRunRecord(**defaults)  # type: ignore[arg-type]


def _make_service() -> MagicMock:
    """构造 MagicMock 模拟 StrategyRunService."""
    return MagicMock(
        spec=["get_lineage", "list_replays", "get_run", "list_runs"],
    )


# ========== get_lineage ==========


class TestGetLineage:
    """LineageQueryFacade.get_lineage — 运行血统链查询."""

    def test_single_run_no_parent(self) -> None:
        """原始运行（无 parent_run_id）返回 depth=0."""
        service = _make_service()
        record = _make_record(run_id="run-001")
        service.get_lineage.return_value = [record]
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("run-001")

        assert result is not None
        assert result.depth == 0
        assert len(result.runs) == 1
        assert result.runs[0].run_id == "run-001"
        service.get_lineage.assert_called_once_with("run-001")

    def test_replay_chain_depth_1(self) -> None:
        """一级重放 — 原始 → 重放1."""
        service = _make_service()
        original = _make_record(run_id="run-001")
        replay = _make_record(run_id="run-002", parent_run_id="run-001")
        service.get_lineage.return_value = [original, replay]
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("run-002")

        assert result is not None
        assert result.depth == 1
        assert len(result.runs) == 2
        assert result.runs[0].run_id == "run-001"
        assert result.runs[1].run_id == "run-002"

    def test_replay_chain_depth_2(self) -> None:
        """二级重放 — 原始 → 重放1 → 重放2."""
        service = _make_service()
        original = _make_record(run_id="run-001")
        replay1 = _make_record(run_id="run-002", parent_run_id="run-001")
        replay2 = _make_record(run_id="run-003", parent_run_id="run-002")
        service.get_lineage.return_value = [original, replay1, replay2]
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("run-003")

        assert result is not None
        assert result.depth == 2
        assert len(result.runs) == 3

    def test_run_not_found_returns_none(self) -> None:
        """运行不存在时返回 None."""
        service = _make_service()
        service.get_lineage.return_value = []
        facade = LineageQueryFacade(run_service=service)

        result = facade.get_lineage("nonexistent")

        assert result is None


# ========== list_replays ==========


class TestListReplays:
    """LineageQueryFacade.list_replays — 列出直接重放记录."""

    def test_list_replays(self) -> None:
        """列出原始运行的所有直接重放."""
        service = _make_service()
        replays = [
            _make_record(run_id="run-002", parent_run_id="run-001"),
            _make_record(run_id="run-003", parent_run_id="run-001"),
        ]
        service.list_replays.return_value = replays
        facade = LineageQueryFacade(run_service=service)

        result = facade.list_replays("run-001")

        assert len(result) == 2
        assert all(r.parent_run_id == "run-001" for r in result)
        service.list_replays.assert_called_once_with("run-001")

    def test_list_replays_empty(self) -> None:
        """无重放记录时返回空列表."""
        service = _make_service()
        service.list_replays.return_value = []
        facade = LineageQueryFacade(run_service=service)

        result = facade.list_replays("run-001")

        assert result == []
