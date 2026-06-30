"""Tests for BacktestQueryFacade — 回测查询编排 facade 统一入口."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.queries.backtest import RunSummary
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord


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


def _make_run_summary(
    run_id: str = "run-001",
    strategy_id: str = "strat-001",
    status: str = "completed",
) -> RunSummary:
    """构造测试用 RunSummary."""
    return RunSummary(
        run_id=run_id,
        strategy_id=strategy_id,
        status=status,
    )


def _make_artifact_record(
    run_id: str = "run-001",
    file_path: str = "/data/artifacts/run-001",
    artifact_type: ArtifactKind = ArtifactKind.BACKTEST_REPORT,
) -> StrategyArtifactRecord:
    """构造测试用 StrategyArtifactRecord."""
    return StrategyArtifactRecord(
        artifact_id=f"art-{run_id}",
        strategy_id="strat-001",
        run_id=run_id,
        artifact_type=artifact_type,
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
    artifact_reader: MagicMock | None = None,
) -> object:
    """构造 BacktestQueryFacade 实例，注入 mock 依赖."""
    # 延迟导入确保测试在实现前可编写
    from ditto_application.queries.backtest import BacktestQueryFacade

    return BacktestQueryFacade(
        trade_facade=trade_facade
        or MagicMock(
            spec=["query_trades"],
        ),
        run_model=run_model or MagicMock(spec=["list_runs", "get_run"]),
        audit_service=audit_service or MagicMock(spec=["query"]),
        artifact_service=artifact_service or MagicMock(spec=["list_artifacts"]),
        artifact_reader=artifact_reader
        or MagicMock(spec=["read_json", "read_parquet", "exists"]),
    )


# =====================================================================
# list_runs — 委托给 RunReadModel
# =====================================================================


class TestBacktestQueryFacadeListRuns:
    """BacktestQueryFacade.list_runs — 委托给 RunReadModel."""

    def test_list_runs_no_filter(self) -> None:
        """无过滤条件时直接委托，返回 RunSummary 列表."""
        records = [_make_run_record("run-001"), _make_run_record("run-002")]
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.list_runs.return_value = records

        facade = _make_facade(run_model=run_model)
        result = facade.list_runs()

        expected = [_make_run_summary("run-001"), _make_run_summary("run-002")]
        assert result == expected
        run_model.list_runs.assert_called_once_with(
            strategy_id=None,
            status=None,
            start_date=None,
            end_date=None,
            limit=None,
            offset=None,
        )

    def test_list_runs_with_filters(self) -> None:
        """传递过滤条件，返回 RunSummary 列表."""
        records = [_make_run_record("run-001")]
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.list_runs.return_value = records

        facade = _make_facade(run_model=run_model)
        result = facade.list_runs(
            strategy_id="strat-001",
            status="completed",
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        assert result == [_make_run_summary("run-001")]
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
        """找到运行记录时返回 RunSummary."""
        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        facade = _make_facade(run_model=run_model)
        result = facade.get_run("run-001")

        assert result == _make_run_summary("run-001")
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
# get_report — 通过 BacktestArtifactReader 读取 backtest_report.json
# =====================================================================


class TestBacktestQueryFacadeGetReport:
    """BacktestQueryFacade.get_report -- 通过 ArtifactReader 读取 report JSON."""

    def test_get_report_found(self) -> None:
        """运行记录存在且 report JSON 存在时返回内容."""
        report_data = _sample_report_json()

        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        artifact_record = _make_artifact_record(
            run_id="run-001",
            file_path="/data/artifacts/run-001",
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [artifact_record]

        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])
        artifact_reader.read_json.return_value = report_data

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )
        result = facade.get_report("run-001")

        assert result is not None
        assert result["run_id"] == "run-001"
        assert result["initial_cash"] == 1_000_000.0
        assert result["final_nav"] == 1_050_000.0
        artifact_reader.read_json.assert_called_once_with(
            "/data/artifacts/run-001/backtest_report.json",
        )

    def test_get_report_not_found(self) -> None:
        """run_id 不存在时返回 None."""
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = None

        facade = _make_facade(run_model=run_model)
        result = facade.get_report("nonexistent")

        assert result is None

    def test_get_report_missing_json_returns_none(self) -> None:
        """运行记录存在但 backtest_report.json 不存在时返回 None."""
        run = _make_run_record("run-001")
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = run

        artifact_record = _make_artifact_record(
            run_id="run-001",
            file_path="/data/artifacts/run-001",
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [artifact_record]

        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])
        artifact_reader.read_json.return_value = None

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
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

    def test_get_report_prefers_backtest_report_artifact_type(self) -> None:
        """同一 run 有 replay proof 时仍读取 backtest_report 产物目录."""
        report_data = _sample_report_json()
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = _make_run_record("run-001")

        proof_record = _make_artifact_record(
            run_id="run-001",
            file_path="/data/artifacts/run-001-proof",
            artifact_type=ArtifactKind.REPLAY_PROOF,
        )
        report_record = _make_artifact_record(
            run_id="run-001",
            file_path="/data/artifacts/run-001-report",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [proof_record, report_record]

        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])
        artifact_reader.read_json.return_value = report_data

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )

        result = facade.get_report("run-001")

        assert result == report_data
        artifact_reader.read_json.assert_called_once_with(
            "/data/artifacts/run-001-report/backtest_report.json",
        )


# =====================================================================
# get_replay_proof — 通过 BacktestArtifactReader 读取 replay_proof.json
# =====================================================================


class TestBacktestQueryFacadeGetReplayProof:
    """BacktestQueryFacade.get_replay_proof -- 读取 replay proof JSON."""

    def test_get_replay_proof_found(self) -> None:
        """运行和 replay proof artifact 存在时返回 proof 内容."""
        proof_data = {
            "proof_version": 1,
            "original_run_id": "run-original",
            "replay_run_id": "run-replay",
            "is_reproducible": True,
            "nav_correlation": 1.0,
            "max_nav_diff_bps": 0.0,
            "input_data_match": True,
            "manifest_diff": {"has_diff": False},
            "fill_match": None,
            "account_state_match": None,
        }
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = _make_run_record("run-replay")
        proof_record = _make_artifact_record(
            run_id="run-replay",
            file_path="/data/artifacts/run-replay",
            artifact_type=ArtifactKind.REPLAY_PROOF,
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [proof_record]
        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])
        artifact_reader.read_json.return_value = proof_data

        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )

        result = facade.get_replay_proof("run-replay")

        assert result == proof_data
        artifact_reader.read_json.assert_called_once_with(
            "/data/artifacts/run-replay/replay_proof.json",
        )

    def test_get_replay_proof_missing_run_returns_none(self) -> None:
        """run_id 不存在时返回 None."""
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = None
        facade = _make_facade(run_model=run_model)

        result = facade.get_replay_proof("missing")

        assert result is None

    def test_get_replay_proof_missing_artifact_returns_none(self) -> None:
        """运行存在但无 replay proof artifact 时返回 None."""
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = _make_run_record("run-replay")
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [
            _make_artifact_record(
                run_id="run-replay",
                artifact_type=ArtifactKind.BACKTEST_REPORT,
            ),
        ]
        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
        )

        result = facade.get_replay_proof("run-replay")

        assert result is None


# =====================================================================
# get_replay_evidence_summary — 组合 restored report + replay proof
# =====================================================================


class TestBacktestQueryFacadeGetReplayEvidenceSummary:
    """BacktestQueryFacade.get_replay_evidence_summary -- 恢复/重放证据摘要."""

    def test_composes_restored_report_and_replay_proof(self) -> None:
        """summary 应组合原始 restored-run report 与 replay proof 证据."""
        resume_provenance = {
            "from_run_id": "run-root",
            "checkpoint_trade_date": "2026-01-31",
            "checkpoint_completed_days": 21,
            "checkpoint_total_days": 60,
            "checkpoint_nav": 1_020_000.0,
            "account_state_hash": "sha256:account",
            "runtime_state_hash": "sha256:runtime",
        }
        report_data = {
            **_sample_report_json(),
            "run_id": "run-restored",
            "resume_provenance": resume_provenance,
        }
        proof_data = {
            "proof_version": 1,
            "original_run_id": "run-restored",
            "replay_run_id": "run-replay",
            "is_reproducible": True,
            "nav_correlation": 1.0,
            "max_nav_diff_bps": 0.0,
            "input_data_match": True,
            "manifest_diff": {"has_diff": False},
            "fill_match": True,
            "account_state_match": True,
            "original_resume_provenance": resume_provenance,
        }
        run_model = MagicMock(spec=["list_runs", "get_run"])

        def _get_run(run_id: str) -> StrategyRunRecord:
            return _make_run_record(run_id)

        run_model.get_run.side_effect = _get_run

        report_record = _make_artifact_record(
            run_id="run-restored",
            file_path="/data/artifacts/run-restored",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
        )
        proof_record = _make_artifact_record(
            run_id="run-replay",
            file_path="/data/artifacts/run-replay",
            artifact_type=ArtifactKind.REPLAY_PROOF,
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [proof_record, report_record]

        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])

        def _read_json(path: str) -> dict[str, object] | None:
            if path.endswith("/run-restored/backtest_report.json"):
                return report_data
            if path.endswith("/run-replay/replay_proof.json"):
                return proof_data
            return None

        artifact_reader.read_json.side_effect = _read_json
        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )

        summary = facade.get_replay_evidence_summary("run-replay")

        assert summary is not None
        assert summary.run_id == "run-replay"
        assert summary.original_run_id == "run-restored"
        assert summary.replay_run_id == "run-replay"
        assert summary.is_reproducible is True
        assert summary.fill_match is True
        assert summary.account_state_match is True
        assert summary.report_resume_provenance == resume_provenance
        assert summary.proof_resume_provenance == resume_provenance
        assert summary.resume_provenance_match is True
        assert summary.missing_sections == ()

    def test_missing_replay_proof_returns_none(self) -> None:
        """没有 replay proof artifact 时 summary 返回 None."""
        run_model = MagicMock(spec=["list_runs", "get_run"])
        run_model.get_run.return_value = _make_run_record("run-replay")
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = []
        facade = _make_facade(
            run_model=run_model,
            artifact_service=artifact_service,
        )

        assert facade.get_replay_evidence_summary("run-replay") is None


# =====================================================================
# get_nav_series — 通过 BacktestArtifactReader 读取 nav.parquet
# =====================================================================


class TestBacktestQueryFacadeGetNavSeries:
    """BacktestQueryFacade.get_nav_series — 通过 ArtifactReader 读取 nav.parquet."""

    def test_get_nav_series_found(self) -> None:
        """产物存在且 nav.parquet 可读取时返回字典列表."""
        nav_df = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "nav": [1_000_000.0, 1_010_000.0],
            }
        )

        artifact_record = _make_artifact_record(
            run_id="run-001",
            file_path="/data/artifacts/run-001",
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [artifact_record]

        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])
        artifact_reader.read_parquet.return_value = nav_df

        facade = _make_facade(
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )
        result = facade.get_nav_series("run-001")

        assert len(result) == 2
        assert result[0]["date"] == "2024-01-01"
        assert result[0]["nav"] == 1_000_000.0
        assert result[1]["date"] == "2024-01-02"
        assert result[1]["nav"] == 1_010_000.0
        artifact_reader.read_parquet.assert_called_once_with(
            "/data/artifacts/run-001/nav.parquet",
        )

    def test_get_nav_series_no_artifact(self) -> None:
        """产物记录不存在时返回空列表."""
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = []

        facade = _make_facade(artifact_service=artifact_service)
        result = facade.get_nav_series("run-001")

        assert result == []

    def test_get_nav_series_missing_parquet(self) -> None:
        """nav.parquet 不存在时返回空列表."""
        artifact_record = _make_artifact_record(
            run_id="run-001",
            file_path="/data/artifacts/run-001",
        )
        artifact_service = MagicMock(spec=["list_artifacts"])
        artifact_service.list_artifacts.return_value = [artifact_record]

        artifact_reader = MagicMock(spec=["read_json", "read_parquet", "exists"])
        artifact_reader.read_parquet.return_value = None

        facade = _make_facade(
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )
        result = facade.get_nav_series("run-001")

        assert result == []


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
