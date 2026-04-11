"""Tests for BacktestQueryFacade — 回测查询编排 facade 统一入口."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import orjson
import polars as pl
import pytest
from ditto_data.models.strategy import ArtifactKind, StrategyArtifactRecord
from ditto_data.models.strategy_run import StrategyRunRecord


def _make_run_record(
    run_id: str = "run-001",
    strategy_id: str = "strat-001",
    status: str = "completed",
) -> StrategyRunRecord:
    """构造测试用 StrategyRunRecord."""
    return StrategyRunRecord(
        run_id=run_id,
        strategy_id=strategy_id,
        status=status,
    )


def _make_artifact_record(
    run_id: str = "run-001",
    file_path: str = "/data/artifacts/run-001",
) -> StrategyArtifactRecord:
    """构造测试用 StrategyArtifactRecord."""
    return StrategyArtifactRecord(
        artifact_id=f"art-{run_id}",
        strategy_id="strat-001",
        run_id=run_id,
        artifact_type=ArtifactKind.BACKTEST_REPORT,
        file_path=file_path,
    )


def _sample_report_json() -> dict[str, object]:
    """构造样例回测报告 JSON 内容."""
    return {
        "run_id": "run-001",
        "period": {"start": "2024-01-01", "end": "2024-03-31"},
        "initial_cash": 1_000_000.0,
        "final_nav": 1_050_000.0,
        "aggregated_trade_stats": {
            "total_trades": 42,
            "win_rate": 0.6,
        },
        "alpha_stats": {
            "sharpe": 1.8,
            "max_drawdown": -0.05,
        },
    }


def _make_facade(
    *,
    run_model: MagicMock | None = None,
    trade_facade: MagicMock | None = None,
    audit_service: MagicMock | None = None,
    artifact_service: MagicMock | None = None,
) -> object:
    """构造 BacktestQueryFacade 实例，注入 mock 依赖."""
    # 延迟导入确保测试在实现前可编写
    from ditto_app.query.backtest import BacktestQueryFacade

    return BacktestQueryFacade(
        trade_facade=trade_facade
        or MagicMock(
            spec=["query_trades"],
        ),
        run_model=run_model or MagicMock(spec=["list_runs", "get_run"]),
        audit_service=audit_service or MagicMock(spec=["query"]),
        artifact_service=artifact_service or MagicMock(spec=["list_artifacts"]),
    )


# =====================================================================
# list_runs — 委托给 RunReadModel
# =====================================================================


class TestBacktestQueryFacadeListRuns:
    """BacktestQueryFacade.list_runs — 委托给 RunReadModel."""

    def test_list_runs_no_filter(self) -> None:
        """无过滤条件时直接委托."""
        runs = [_make_run_record("run-001"), _make_run_record("run-002")]
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.list_runs.return_value = runs

        facade = _make_facade(run_model=run_model)
        result = facade.list_runs()

        assert result == runs
        run_model.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=None,
            offset=None,
        )

    def test_list_runs_with_filters(self) -> None:
        """传递过滤条件."""
        runs = [_make_run_record("run-001")]
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.list_runs.return_value = runs

        facade = _make_facade(run_model=run_model)
        result = facade.list_runs(
            strategy_id="strat-001",
            status="completed",
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        assert result == runs
        run_model.list_runs.assert_called_once_with(
            strategy_id="strat-001",
            status="completed",
            start_date="2024-01-01",
            end_date="2024-03-31",
            limit=None,
            offset=None,
        )


# =====================================================================
# get_run — 委托给 RunReadModel
# =====================================================================


class TestBacktestQueryFacadeGetRun:
    """BacktestQueryFacade.get_run — 委托给 RunReadModel."""

    def test_get_run_found(self) -> None:
        """找到运行记录时返回."""
        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        facade = _make_facade(run_model=run_model)
        result = facade.get_run("run-001")

        assert result == run
        run_model.get_run.assert_called_once_with("run-001")

    def test_get_run_not_found(self) -> None:
        """未找到运行记录时返回 None."""
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = None

        facade = _make_facade(run_model=run_model)
        result = facade.get_run("nonexistent")

        assert result is None
        run_model.get_run.assert_called_once_with("nonexistent")


# =====================================================================
# get_trades — 委托给 BacktestTradeQueryFacade
# =====================================================================


class TestBacktestQueryFacadeGetTrades:
    """BacktestQueryFacade.get_trades — 委托给 BacktestTradeQueryFacade."""

    def test_get_trades(self) -> None:
        """基础成交查询."""
        trade_df = pl.DataFrame({"trade_id": ["T001", "T002"]})
        trade_facade = MagicMock(spec=["query_trades"])
        trade_facade.query_trades.return_value = trade_df

        facade = _make_facade(trade_facade=trade_facade)
        result = facade.get_trades(run_id="run-001")

        assert result.equals(trade_df)
        trade_facade.query_trades.assert_called_once_with(
            run_id="run-001",
            start_date=None,
            end_date=None,
            limit=None,
            offset=0,
        )

    def test_get_trades_with_pagination(self) -> None:
        """带分页参数的成交查询."""
        trade_df = pl.DataFrame({"trade_id": ["T002"]})
        trade_facade = MagicMock(spec=["query_trades"])
        trade_facade.query_trades.return_value = trade_df

        facade = _make_facade(trade_facade=trade_facade)
        result = facade.get_trades(
            run_id="run-001",
            start_date="2024-01-10",
            end_date="2024-03-31",
            limit=10,
            offset=5,
        )

        assert result.equals(trade_df)
        trade_facade.query_trades.assert_called_once_with(
            run_id="run-001",
            start_date="2024-01-10",
            end_date="2024-03-31",
            limit=10,
            offset=5,
        )


# =====================================================================
# get_audit — 委托给 ExecutionAuditService
# =====================================================================


class TestBacktestQueryFacadeGetAudit:
    """BacktestQueryFacade.get_audit — 委托给 ExecutionAuditService."""

    def test_get_audit_all(self) -> None:
        """查询全部审计记录."""
        audit_records = [
            {"id": 1, "run_id": "run-001", "record_type": "risk_scan"},
            {"id": 2, "run_id": "run-001", "record_type": "pre_trade_decision"},
        ]
        audit_service = MagicMock(spec=["query"])
        audit_service.query.return_value = audit_records

        facade = _make_facade(audit_service=audit_service)
        result = facade.get_audit("run-001")

        assert result == audit_records
        audit_service.query.assert_called_once_with(
            "run-001",
            record_type=None,
            start_date=None,
            end_date=None,
        )

    def test_get_audit_by_type(self) -> None:
        """按记录类型过滤."""
        audit_records = [
            {"id": 1, "run_id": "run-001", "record_type": "risk_scan"},
        ]
        audit_service = MagicMock(spec=["query"])
        audit_service.query.return_value = audit_records

        facade = _make_facade(audit_service=audit_service)
        result = facade.get_audit("run-001", record_type="risk_scan")

        assert result == audit_records
        audit_service.query.assert_called_once_with(
            "run-001",
            record_type="risk_scan",
            start_date=None,
            end_date=None,
        )

    def test_get_audit_with_dates(self) -> None:
        """按日期范围过滤."""
        audit_service = MagicMock(spec=["query"])
        audit_service.query.return_value = []

        facade = _make_facade(audit_service=audit_service)
        result = facade.get_audit(
            "run-001",
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        assert result == []
        audit_service.query.assert_called_once_with(
            "run-001",
            record_type=None,
            start_date="2024-01-01",
            end_date="2024-03-31",
        )


# =====================================================================
# get_report — 从 backtest_report.json 读取报告元数据
# =====================================================================


class TestBacktestQueryFacadeGetReport:
    """BacktestQueryFacade.get_report — 从产物目录读取 backtest_report.json."""

    def test_get_report_found(self, tmp_path: Path) -> None:
        """运行记录存在且 report JSON 存在时返回内容."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()

        report_data = _sample_report_json()
        report_path = artifact_dir / "backtest_report.json"
        report_path.write_bytes(orjson.dumps(report_data))

        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        artifact_record = _make_artifact_record(
            run_id="run-001",
            file_path=str(artifact_dir),
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [artifact_record]

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
        )
        result = facade.get_report("run-001")

        assert result is not None
        assert result["run_id"] == "run-001"
        assert result["initial_cash"] == 1_000_000.0
        assert result["final_nav"] == 1_050_000.0

    def test_get_report_not_found(self) -> None:
        """run_id 不存在时返回 None."""
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = None

        facade = _make_facade(run_model=run_model)
        result = facade.get_report("nonexistent")

        assert result is None

    def test_get_report_missing_json_returns_none(self, tmp_path: Path) -> None:
        """运行记录存在但 backtest_report.json 不存在时返回 None."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        # 不创建 backtest_report.json

        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        artifact_record = _make_artifact_record(
            run_id="run-001",
            file_path=str(artifact_dir),
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [artifact_record]

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
        )
        result = facade.get_report("run-001")

        assert result is None

    def test_get_report_no_artifact_returns_none(self) -> None:
        """运行记录存在但没有对应产物记录时返回 None."""
        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = []

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
        )
        result = facade.get_report("run-001")

        assert result is None


# =====================================================================
# get_benchmark_return — 从 alpha_stats 提取基准收益率
# =====================================================================


class TestBacktestQueryFacadeGetBenchmarkReturn:
    """BacktestQueryFacade.get_benchmark_return — 从 alpha_stats 提取基准相关数据."""

    def test_get_benchmark_return_extracts_from_alpha_stats(self) -> None:
        """report 含基准数据时提取 benchmark annualized return."""
        # alpha = R - beta * Rb  =>  Rb = (R - alpha) / beta
        # R=15.0, alpha=5.0, beta=0.8  =>  Rb = (15.0 - 5.0) / 0.8 = 12.5
        report = {
            "alpha_stats": {
                "annualized_return": 15.0,
                "alpha_annualized": 5.0,
                "beta": 0.8,
                "tracking_error": 3.0,
                "information_ratio": 1.2,
            },
        }
        facade = _make_facade()
        facade.get_report = MagicMock(return_value=report)  # type: ignore[method-assign]

        result = facade.get_benchmark_return("run-001")

        assert result is not None
        assert result == pytest.approx(12.5)

    def test_get_benchmark_return_returns_none_when_no_benchmark(self) -> None:
        """report 无基准数据（beta=None）时返回 None."""
        report = {
            "alpha_stats": {
                "annualized_return": 15.0,
                "alpha_annualized": None,
                "beta": None,
                "tracking_error": None,
                "information_ratio": None,
            },
        }
        facade = _make_facade()
        facade.get_report = MagicMock(return_value=report)  # type: ignore[method-assign]

        result = facade.get_benchmark_return("run-001")

        assert result is None

    def test_get_benchmark_return_returns_none_when_no_report(self) -> None:
        """report 不存在时返回 None."""
        facade = _make_facade()
        facade.get_report = MagicMock(return_value=None)  # type: ignore[method-assign]

        result = facade.get_benchmark_return("run-001")

        assert result is None

    def test_get_benchmark_return_returns_none_when_no_alpha_stats(self) -> None:
        """report 中没有 alpha_stats 时返回 None."""
        facade = _make_facade()
        facade.get_report = MagicMock(return_value={"run_id": "run-001"})  # type: ignore[method-assign]

        result = facade.get_benchmark_return("run-001")

        assert result is None


# =====================================================================
# get_benchmark_nav_series — 基准 NAV 序列（当前未持久化）
# =====================================================================


class TestBacktestQueryFacadeGetBenchmarkNavSeries:
    """BacktestQueryFacade.get_benchmark_nav_series — 基准 NAV 序列."""

    def test_returns_none_when_no_report(self) -> None:
        """report 不存在时返回 None."""
        facade = _make_facade()
        facade.get_report = MagicMock(return_value=None)  # type: ignore[method-assign]

        result = facade.get_benchmark_nav_series("run-001")

        assert result is None

    def test_returns_none_when_no_benchmark_data(self) -> None:
        """report 无基准数据时返回 None."""
        report = {
            "alpha_stats": {
                "annualized_return": 15.0,
                "beta": None,
            },
        }
        facade = _make_facade()
        facade.get_report = MagicMock(return_value=report)  # type: ignore[method-assign]

        result = facade.get_benchmark_nav_series("run-001")

        assert result is None
