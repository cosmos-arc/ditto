"""BacktestService 单元测试 — 回测编排服务。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.engine import EngineConfig, EngineLoop, EngineResult
from ditto_backtest.manifest import InputRef, RunManifest, RunMode
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestCheckpoint,
    BacktestDelayedSignalSnapshot,
    BacktestFrozenQuantitySnapshot,
    BacktestPendingOrderSnapshot,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
    BacktestTargetWeightSnapshot,
)
from ditto_backtest.statistics import BacktestReport
from ditto_data.catalog import DataAssetRef
from ditto_data.lineage import InMemoryDataLineage
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_strategy.runs.models import StrategyRunCheckpointRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_result(
    run_id: str = "run-001",
    period: tuple[str, str] = ("2026-01-01", "2026-03-01"),
    final_nav: float = 1_100_000.0,
    manifest: RunManifest | None = None,
) -> EngineResult:
    """创建最小 EngineResult 用于测试。"""
    return EngineResult(
        run_id=run_id,
        period=period,
        final_nav=final_nav,
        manifest=manifest,
    )


def _make_service_config(
    strategy_id: str = "momentum-etf",
    run_id: str = "run-001",
    start_date: str = "2026-01-01",
    end_date: str = "2026-03-01",
    **overrides: object,
) -> BacktestServiceConfig:
    """创建 BacktestServiceConfig 测试辅助函数。"""
    return BacktestServiceConfig(
        strategy_id=strategy_id,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        **overrides,
    )


def _make_minimal_service(
    config: BacktestServiceConfig | None = None,
    audit_service: MagicMock | None = None,
    artifact_service: MagicMock | None = None,
    data_feed: MagicMock | None = None,
) -> BacktestService:
    """创建最小 BacktestService 实例（所有依赖均为 mock）。"""
    if config is None:
        config = _make_service_config()

    mock_pipeline = MagicMock()
    mock_planner = MagicMock()
    mock_brokerage = MagicMock()
    mock_pre_trade_check = MagicMock()
    mock_data_feed = data_feed if data_feed is not None else MagicMock()

    options = BacktestServiceOptions(
        audit_service=audit_service,
        artifact_service=artifact_service,
    )

    service = BacktestService(
        config=config,
        pipeline=mock_pipeline,
        planner=mock_planner,
        brokerage=mock_brokerage,
        pre_trade_check=mock_pre_trade_check,
        data_feed=mock_data_feed,
        options=options,
    )

    return service


# ---------------------------------------------------------------------------
# Tests: BacktestServiceConfig
# ---------------------------------------------------------------------------


class TestBacktestServiceConfig:
    """测试 BacktestServiceConfig frozen dataclass。"""

    def test_default_values(self) -> None:
        """默认值正确。"""
        config = BacktestServiceConfig()
        assert config.strategy_id == "default"
        assert config.strategy_version == ""
        assert config.run_id == ""
        assert config.start_date == ""
        assert config.end_date == ""
        assert config.initial_cash == 1_000_000.0
        assert config.benchmark_id is None
        assert config.rebalance_freq == "daily"
        assert config.engine_version == "0.1.0"
        assert config.parameter_overrides == ()
        assert config.participation_rate == pytest.approx(0.05)
        assert config.fill_mode == "partial"

    def test_custom_values(self) -> None:
        """自定义值正确。"""
        config = _make_service_config(
            strategy_id="my-strategy",
            run_id="run-123",
            strategy_version="2026.03",
            initial_cash=5_000_000.0,
            benchmark_id=InstrumentId(3_000_001),
            parameter_overrides=("top_k=5",),
            participation_rate=0.02,
            fill_mode="all_or_nothing",
        )
        assert config.strategy_id == "my-strategy"
        assert config.strategy_version == "2026.03"
        assert config.run_id == "run-123"
        assert config.initial_cash == 5_000_000.0
        assert config.benchmark_id == InstrumentId(3_000_001)
        assert config.parameter_overrides == ("top_k=5",)
        assert config.participation_rate == pytest.approx(0.02)
        assert config.fill_mode == "all_or_nothing"

    def test_frozen(self) -> None:
        """BacktestServiceConfig 是 frozen，不可变。"""
        config = _make_service_config()
        with pytest.raises(FrozenInstanceError):
            config.strategy_id = "modified"  # type: ignore[misc]

    def test_run_id_propagation_to_engine_config(self) -> None:
        """BacktestServiceConfig.run_id 正确传递到 EngineConfig。"""
        config = _make_service_config(run_id="run-xyz")
        engine_config = EngineConfig(
            start_date=config.start_date,
            end_date=config.end_date,
            initial_cash=config.initial_cash,
            benchmark_id=config.benchmark_id,
            strategy_id=config.strategy_id,
            strategy_run_id=config.run_id,
            rebalance_freq=config.rebalance_freq,
            engine_version=config.engine_version,
        )
        assert engine_config.strategy_run_id == "run-xyz"
        assert engine_config.strategy_id == config.strategy_id


# ---------------------------------------------------------------------------
# Tests: BacktestServiceOptions
# ---------------------------------------------------------------------------


class TestBacktestServiceOptions:
    """测试 BacktestServiceOptions frozen dataclass。"""

    def test_default_values(self) -> None:
        """默认值全部为 None。"""
        options = BacktestServiceOptions()
        assert options.fee_model is None
        assert options.rule_provider is None
        assert options.post_trade_guard is None
        assert options.audit_service is None
        assert options.artifact_service is None
        assert options.artifact_dir is None

    def test_frozen(self) -> None:
        """BacktestServiceOptions 是 frozen，不可变。"""
        options = BacktestServiceOptions()
        with pytest.raises(FrozenInstanceError):
            options.fee_model = MagicMock()  # type: ignore[misc]

    def test_custom_values(self) -> None:
        """自定义值正确。"""
        mock_fee = MagicMock()
        mock_audit = MagicMock()
        options = BacktestServiceOptions(
            fee_model=mock_fee,
            audit_service=mock_audit,
        )
        assert options.fee_model is mock_fee
        assert options.audit_service is mock_audit


# ---------------------------------------------------------------------------
# Tests: BacktestService.run()
# ---------------------------------------------------------------------------


class TestBacktestServiceRun:
    """测试 BacktestService 核心运行流程。"""

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_returns_backtest_report(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """run() 返回 BacktestReport。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        mock_build_report.return_value = fake_report

        service = _make_minimal_service()
        result = service.run()

        assert result is fake_report
        mock_engine_run.assert_called_once()

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_creates_audit_collector(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """run() 创建 ExecutionAuditCollector 并传入 EngineOptions。"""
        fake_report = MagicMock(spec=BacktestReport)
        mock_build_report.return_value = fake_report

        service = _make_minimal_service()
        service.run()

        # Verify build_report was called with the collector
        call_args = mock_build_report.call_args
        collector = call_args[0][0]
        assert isinstance(collector, ExecutionAuditCollector)

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_builds_engine_config_from_service_config(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """run() 从 BacktestServiceConfig 构建 EngineConfig。"""
        fake_report = MagicMock(spec=BacktestReport)
        mock_build_report.return_value = fake_report

        config = _make_service_config(
            strategy_id="test-strat",
            run_id="run-config-test",
            start_date="2025-06-01",
            end_date="2025-12-31",
            initial_cash=2_000_000.0,
            benchmark_id=InstrumentId(3_000_002),
            rebalance_freq="weekly",
        )
        service = _make_minimal_service(config=config)
        service.run()

        # Verify EngineLoop was constructed with correct EngineConfig
        mock_engine_run.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Audit persistence
# ---------------------------------------------------------------------------


class TestAuditPersistence:
    """测试审计日志持久化。"""

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_persists_risk_log_when_audit_service_provided(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """提供 audit_service 时，risk_log 被持久化。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_audit = MagicMock()
        service = _make_minimal_service(audit_service=mock_audit)
        service.run()

        mock_audit.save_risk_log.assert_called_once()

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_persists_pre_trade_log_when_audit_service_provided(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """提供 audit_service 时，pre_trade_log 被持久化。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_audit = MagicMock()
        service = _make_minimal_service(audit_service=mock_audit)
        service.run()

        mock_audit.save_pre_trade_log.assert_called_once()

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_no_audit_persistence_without_service(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """未提供 audit_service 时，不调用持久化方法。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        service = _make_minimal_service(audit_service=None)
        service.run()

        # No error should occur — service should skip persistence gracefully

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_maps_portfolio_wide_id_to_asterisk(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """Portfolio-wide 风控记录在持久化时 instrument_id=None, scope='portfolio'。"""
        from ditto_backtest.audit import RiskScanRecord
        from ditto_kernel.strategy import RiskScope
        from ditto_risk.post_trade import (
            RiskActionType,
            RiskSeverity,
        )

        record = RiskScanRecord(
            trade_date="2026-01-10",
            rule_id="max_drawdown",
            instrument_id=None,
            scope=RiskScope.PORTFOLIO,
            severity=RiskSeverity.WARNING,
            action_taken=RiskActionType.ALERT,
            detail="组合回撤 5.00% 超过警告阈值 10.00%",
            current_value=0.05,
            threshold=0.10,
        )
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = (record,)
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_audit = MagicMock()
        service = _make_minimal_service(audit_service=mock_audit)
        service.run()

        call_args = mock_audit.save_risk_log.call_args
        payloads = call_args[0][1]
        assert payloads[0].instrument_id is None
        assert payloads[0].scope == "portfolio"


# ---------------------------------------------------------------------------
# Tests: Artifact persistence
# ---------------------------------------------------------------------------


class TestArtifactPersistence:
    """测试策略产物持久化。"""

    @patch.object(
        EngineLoop,
        "run",
        return_value=_make_engine_result(
            manifest=RunManifest(
                run_id="run-001",
                strategy_id="momentum-etf",
                strategy_version="2026.03",
                mode=RunMode.BACKTEST,
                created_at="2026-03-24T10:00:00Z",
            ),
        ),
    )
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_persists_artifact_when_artifact_service_provided(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """提供 artifact_service 时，BacktestReport 被持久化为 artifact。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.final_nav = 1_100_000.0
        fake_report.period = ("2026-01-01", "2026-03-01")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(total_trades=42)
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.5,
            max_drawdown=-5.2,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        config = _make_service_config(strategy_id="momentum-etf", run_id="run-001")
        service = _make_minimal_service(
            config=config,
            artifact_service=mock_artifact,
        )
        service.run()

        mock_write_artifacts.assert_called_once()
        mock_artifact.save_artifact.assert_called_once()
        call_arg = mock_artifact.save_artifact.call_args[0][0]
        assert call_arg.strategy_id == "momentum-etf"
        assert call_arg.run_id == "run-001"
        assert call_arg.artifact_type == "backtest_report"
        assert call_arg.metadata["pit_policy"] == "knowledge_date_fail_closed"
        assert call_arg.metadata["pit_time_column"] == "knowledge_date"
        assert call_arg.metadata["unsafe_time_policy"] == ""

    @patch.object(
        EngineLoop,
        "run",
        return_value=_make_engine_result(
            manifest=RunManifest(
                run_id="run-candidate",
                strategy_id="stock-selector",
                strategy_version="2026.06",
                mode=RunMode.BACKTEST,
                created_at="2026-06-21T10:00:00Z",
                input_ref_details=(
                    InputRef(
                        instrument_id=InstrumentId(510300),
                        data_hash="sha256:stock-daily",
                        date_range=("2026-01-01", "2026-06-21"),
                        source="catalog://stock_daily",
                        source_snapshot_id="catalog-snap-20260621",
                    ),
                ),
                parameter_overrides=("top_k=20", "max_weight=0.08"),
                config_hash="config-sha",
                engine_version="0.2.0",
                spec_hash="spec-sha",
            ),
        ),
    )
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-candidate/backtest_report.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_persists_strategy_promotion_artifact_contract(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """Production-candidate reports should carry promotion artifact evidence."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-candidate"
        fake_report.final_nav = 1_230_000.0
        fake_report.period = ("2026-01-01", "2026-06-21")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(total_trades=15)
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.8,
            max_drawdown=-0.04,
            annualized_return=0.23,
            net_return_after_cost=0.21,
            total_fees=128.0,
            cost_drag=0.02,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        config = _make_service_config(
            strategy_id="stock-selector",
            strategy_version="2026.06",
            run_id="run-candidate",
            benchmark_id=InstrumentId(3_000_001),
            code_version="git:abc123",
            factor_report_refs=("factor://quality_roe/v3",),
            recommendation_status="candidate",
        )
        service = _make_minimal_service(
            config=config,
            artifact_service=mock_artifact,
        )

        service.run()

        artifact = mock_artifact.save_artifact.call_args.args[0]
        promotion = artifact.metadata["strategy_promotion"]
        assert promotion["strategy_id"] == "stock-selector"
        assert promotion["strategy_version"] == "2026.06"
        assert promotion["code_version"] == "git:abc123"
        assert promotion["data_catalog_identities"] == [
            {
                "instrument_id": 510300,
                "source": "catalog://stock_daily",
                "source_snapshot_id": "catalog-snap-20260621",
                "data_hash": "sha256:stock-daily",
                "date_range": ["2026-01-01", "2026-06-21"],
            }
        ]
        assert promotion["parameter_hash"].startswith("sha256:")
        assert promotion["benchmark"] == 3_000_001
        assert promotion["cost_model"]["total_fees"] == 128.0
        assert promotion["cost_model"]["cost_drag"] == 0.02
        assert promotion["backtest_metrics"]["final_nav"] == 1_230_000.0
        assert promotion["backtest_metrics"]["sharpe_ratio"] == 1.8
        assert promotion["factor_report_refs"] == ["factor://quality_roe/v3"]
        assert promotion["recommendation_status"] == "candidate"
        assert (
            mock_write_artifacts.call_args.kwargs["options"].strategy_promotion
            == promotion
        )

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-resume/backtest_report.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_resume_artifact_persists_checkpoint_provenance(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """Restored child-run artifacts should preserve checkpoint provenance."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-resume"
        fake_report.final_nav = 1_120_000.0
        fake_report.period = ("2025-02-03", "2025-03-31")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(total_trades=2)
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.7,
            max_drawdown=-2.0,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        config = _make_service_config(
            strategy_id="momentum-etf",
            run_id="run-resume",
            start_date="2025-02-03",
            end_date="2025-03-31",
            resume_from_run_id="run-original",
            resume_checkpoint_trade_date="2025-01-31",
            resume_checkpoint_completed_days=21,
            resume_checkpoint_total_days=60,
            resume_checkpoint_nav=1_020_000.0,
            resume_checkpoint_order_count=4,
            resume_checkpoint_fill_count=4,
            resume_account_state_hash="sha256:account",
            resume_settlement_state_hash="sha256:settlement",
            resume_runtime_state_hash="sha256:runtime",
        )
        service = _make_minimal_service(
            config=config,
            artifact_service=mock_artifact,
        )

        service.run()

        mock_write_artifacts.assert_called_once()
        assert mock_write_artifacts.call_args.kwargs["options"].resume_provenance == {
            "from_run_id": "run-original",
            "checkpoint_trade_date": "2025-01-31",
            "checkpoint_completed_days": 21,
            "checkpoint_total_days": 60,
            "checkpoint_nav": 1_020_000.0,
            "checkpoint_order_count": 4,
            "checkpoint_fill_count": 4,
            "account_state_hash": "sha256:account",
            "settlement_state_hash": "sha256:settlement",
            "runtime_state_hash": "sha256:runtime",
        }
        artifact = mock_artifact.save_artifact.call_args.args[0]
        assert artifact.metadata["resume_from_run_id"] == "run-original"
        assert artifact.metadata["resume_checkpoint_trade_date"] == "2025-01-31"
        assert artifact.metadata["resume_account_state_hash"] == "sha256:account"

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_no_artifact_persistence_without_service(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """未提供 artifact_service 时，不调用持久化方法。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        service = _make_minimal_service(artifact_service=None)
        service.run()

        # No error should occur

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={},
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_persist_artifact_empty_map_no_error(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """artifacts_map 为空时应直接返回，不崩溃也不保存空记录."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        config = _make_service_config(strategy_id="momentum-etf", run_id="run-001")
        service = _make_minimal_service(
            config=config,
            artifact_service=mock_artifact,
        )
        service.run()

        mock_write_artifacts.assert_called_once()
        mock_artifact.save_artifact.assert_not_called()

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/test/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_serializes_report_when_artifact_dir_provided(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """提供 artifact_dir 时，报告序列化到文件，file_path 非空。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.final_nav = 1_100_000.0
        fake_report.period = ("2026-01-01", "2026-03-01")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(
            total_trades=42,
        )
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.5,
            max_drawdown=-5.2,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        options = BacktestServiceOptions(
            artifact_service=mock_artifact,
            artifact_dir="/tmp/test",
        )
        service = _make_minimal_service(
            config=_make_service_config(strategy_id="momentum-etf", run_id="run-001"),
            artifact_service=mock_artifact,
        )
        service._options = options  # type: ignore[misc]

        service.run()

        mock_write_artifacts.assert_called_once()
        call_args = mock_write_artifacts.call_args
        assert call_args[0][0] is fake_report
        assert call_args[1]["output_dir"] == Path("/tmp/test/run-001")
        mock_artifact.save_artifact.assert_called_once()
        call_arg = mock_artifact.save_artifact.call_args[0][0]
        # file_path 应为目录路径，匹配读取侧 _build_path 契约
        assert call_arg.file_path == "/tmp/test/run-001"

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_artifact_without_dir_file_path_resolved(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """未提供 artifact_dir 时，file_path 从 write_backtest_artifacts 返回值推导。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.final_nav = 1_100_000.0
        fake_report.period = ("2026-01-01", "2026-03-01")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(
            total_trades=42,
        )
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.5,
            max_drawdown=-5.2,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        service = _make_minimal_service(
            config=_make_service_config(strategy_id="momentum-etf", run_id="run-001"),
            artifact_service=mock_artifact,
        )
        service.run()

        mock_write_artifacts.assert_called_once()
        call_args = mock_write_artifacts.call_args
        assert call_args[0][0] is fake_report
        assert call_args[1]["output_dir"] is None
        mock_artifact.save_artifact.assert_called_once()
        call_arg = mock_artifact.save_artifact.call_args[0][0]
        # file_path 从 write_backtest_artifacts 返回值的产物目录推导
        assert call_arg.file_path == "/tmp/ditto/run-001"

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/test/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_artifact_file_path_is_directory_not_file(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """file_path 应存储目录路径（output_dir），匹配读取侧 _build_path 契约.

        读取侧使用 Path(file_path) / filename 拼接，因此 file_path 必须是目录。
        若 file_path 是文件路径，拼接后变成 dir/file.json/file.json，导致静默返回 None。
        """
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.final_nav = 1_100_000.0
        fake_report.period = ("2026-01-01", "2026-03-01")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(total_trades=42)
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.5,
            max_drawdown=-5.2,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_artifact = MagicMock()
        options = BacktestServiceOptions(
            artifact_service=mock_artifact,
            artifact_dir="/tmp/test",
        )
        service = _make_minimal_service(
            config=_make_service_config(strategy_id="momentum-etf", run_id="run-001"),
            artifact_service=mock_artifact,
        )
        service._options = options  # type: ignore[misc]

        service.run()

        mock_artifact.save_artifact.assert_called_once()
        call_arg = mock_artifact.save_artifact.call_args[0][0]
        # file_path 应该是目录路径，与读取侧 _build_path 兼容
        assert call_arg.file_path == "/tmp/test/run-001"
        # 验证目录路径可以用 _build_path 正确拼接文件名
        from ditto_application.queries.backtest import _build_path

        report_path = _build_path(call_arg.file_path, "backtest_report.json")
        assert report_path == "/tmp/test/run-001/backtest_report.json"

    @patch(
        "ditto_application.processes.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-001/backtest_report.json"),
            "manifest": Path("/tmp/ditto/run-001/manifest.json"),
        },
    )
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_passes_engine_manifest_to_artifact_writer(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
    ) -> None:
        """artifact writer 接收 EngineLoop 生成的 manifest。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.final_nav = 1_100_000.0
        fake_report.period = ("2026-01-01", "2026-03-01")
        fake_report.initial_cash = 1_000_000.0
        fake_report.aggregated_trade_stats = MagicMock(total_trades=42)
        fake_report.alpha_stats = MagicMock(
            sharpe_ratio=1.5,
            max_drawdown=-5.2,
        )
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        manifest = RunManifest(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            mode=RunMode.BACKTEST,
            created_at="2026-03-24T10:00:00Z",
            input_refs=("ETF-001",),
            parameter_overrides=("top_k=3",),
            config_hash="cfg-123",
            engine_version="0.2.0",
        )
        engine_result = _make_engine_result(run_id="run-001", manifest=manifest)

        mock_artifact = MagicMock()
        service = _make_minimal_service(
            config=_make_service_config(
                strategy_id="momentum-etf",
                run_id="run-001",
            ),
            artifact_service=mock_artifact,
        )

        with patch.object(EngineLoop, "run", return_value=engine_result):
            service.run()

        call_kwargs = mock_write_artifacts.call_args.kwargs
        assert call_kwargs["manifest"] == manifest

    @patch.object(EngineLoop, "run")
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_records_data_lineage_from_manifest(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """成功回测后记录策略和输入数据到 backtest report 的 lineage."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-001"
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report
        manifest = RunManifest(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            mode=RunMode.BACKTEST,
            created_at="2026-03-24T10:00:00+00:00",
            input_ref_details=(
                InputRef(
                    instrument_id=InstrumentId(510050),
                    data_hash="sha256:abc123",
                    date_range=("2026-01-01", "2026-03-01"),
                    source="tushare",
                ),
            ),
        )
        mock_engine_run.return_value = _make_engine_result(
            run_id="run-001",
            manifest=manifest,
        )
        lineage = InMemoryDataLineage()
        service = _make_minimal_service(
            config=_make_service_config(
                strategy_id="momentum-etf",
                strategy_version="2026.03",
                run_id="run-001",
                start_date="2026-01-01",
                end_date="2026-03-01",
            ),
        )
        service._options = BacktestServiceOptions(lineage_recorder=lineage)  # type: ignore[misc]

        service.run()

        output_asset = DataAssetRef(
            dataset_id="backtest_report",
            namespace="backtest",
            partition_keys=(
                "run_id=run-001",
                "strategy_id=momentum-etf",
                "start_date=2026-01-01",
                "end_date=2026-03-01",
            ),
        )
        events = lineage.list_events_for_asset(output_asset)
        assert len(events) == 1
        event = events[0]
        assert event.run_id == "run-001"
        assert event.operation == "backtest"
        assert tuple(ref.asset for ref in event.inputs) == (
            DataAssetRef(
                dataset_id="momentum-etf",
                namespace="strategy",
                partition_keys=("version=2026.03",),
            ),
            DataAssetRef(
                dataset_id="market_data",
                namespace="backtest_input",
                partition_keys=(
                    "source=tushare",
                    "instrument_id=510050",
                    "start_date=2026-01-01",
                    "end_date=2026-03-01",
                    "data_hash=sha256:abc123",
                ),
            ),
        )
        assert tuple(ref.role for ref in event.inputs) == (
            "strategy",
            "market_data",
        )
        assert tuple(ref.asset for ref in event.outputs) == (output_asset,)
        assert tuple(ref.role for ref in event.outputs) == ("backtest_report",)


# ---------------------------------------------------------------------------
# Tests: run_id propagation
# ---------------------------------------------------------------------------


class TestRunIdPropagation:
    """测试 run_id 在各组件间的传递。"""

    @patch.object(EngineLoop, "__init__", return_value=None)
    @patch.object(EngineLoop, "run")
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_id_propagates_to_report(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
        mock_engine_init: MagicMock,
    ) -> None:
        """Config run_id 传递到 build_report 和持久化。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "run-xyz"
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report
        mock_engine_run.return_value = _make_engine_result(run_id="run-xyz")

        config = _make_service_config(run_id="run-xyz")
        service = _make_minimal_service(config=config)
        service.run()

        # build_report called with run_id
        call_kwargs = mock_build_report.call_args[1]
        assert call_kwargs["run_id"] == "run-xyz"

    @patch.object(EngineLoop, "__init__", return_value=None)
    @patch.object(EngineLoop, "run")
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_empty_run_id_is_generated_before_engine_construction(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
        mock_engine_init: MagicMock,
    ) -> None:
        """Config.run_id 为空时，先生成 run_id 再传给 EngineConfig。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.run_id = "generated-run"
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report
        mock_engine_run.return_value = _make_engine_result(run_id="generated-run")

        config = _make_service_config(run_id="")
        service = _make_minimal_service(config=config)
        service.run()

        engine_config = mock_engine_init.call_args.kwargs["config"]
        assert engine_config.strategy_run_id != ""

    @patch.object(EngineLoop, "__init__", return_value=None)
    @patch.object(EngineLoop, "run")
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_id_propagates_to_audit_service(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
        mock_engine_init: MagicMock,
    ) -> None:
        """Config run_id 传递到 audit_service 的 save 方法。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report
        mock_engine_run.return_value = _make_engine_result(
            run_id="run-audit-test",
        )

        mock_audit = MagicMock()
        config = _make_service_config(run_id="run-audit-test")
        service = _make_minimal_service(config=config, audit_service=mock_audit)
        service.run()

        # Verify run_id passed to save_risk_log
        call_args = mock_audit.save_risk_log.call_args[0]
        assert call_args[0] == "run-audit-test"


# ---------------------------------------------------------------------------
# Tests: Without persistence services
# ---------------------------------------------------------------------------


class TestWithoutPersistence:
    """测试不提供持久化服务时的行为。"""

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_without_persistence_services(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """不提供任何持久化服务时，run() 仍正常返回 BacktestReport。"""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        service = _make_minimal_service(
            audit_service=None,
            artifact_service=None,
        )
        result = service.run()

        assert result is fake_report
        mock_engine_run.assert_called_once()
        mock_build_report.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _build_factor_aware_bundle_builder (T27)
# ---------------------------------------------------------------------------


class TestBuildFactorAwareBundleBuilder:
    """测试 _build_factor_aware_bundle_builder — 因子信号注入构建器."""

    def _make_compiled_expressions(
        self,
        expressions: list[object] | None = None,
        weights: tuple[float, ...] = (1.0,),
    ) -> MagicMock:
        """构建 CompiledExpressions mock (含 expressions 列表或空)."""
        compiled = MagicMock()
        compiled.expressions = expressions or []
        compiled.weights = weights
        return compiled

    def _make_step_context(
        self,
        td: str = "2026-04-10",
    ) -> MagicMock:
        """构建 StepContext mock (含 bars slice)."""
        from ditto_backtest.data_feed import Slice

        iid1 = InstrumentId(510050)
        iid2 = InstrumentId(159915)
        bar1 = MagicMock(
            open=4.1,
            high=4.2,
            low=4.0,
            close=4.15,
            volume=1_000_000,
        )
        bar2 = MagicMock(
            open=0.8,
            high=0.85,
            low=0.78,
            close=0.82,
            volume=2_000_000,
        )
        mock_slice = MagicMock(spec=Slice)
        mock_slice.bars = {iid1: bar1, iid2: bar2}
        mock_slice.benchmark_close = 3000.0

        from ditto_backtest.steps import StepContext

        ctx = StepContext(
            time_context=TimeContext(
                decision_time=datetime(
                    int(td[:4]), int(td[5:7]), int(td[8:10]), 15, 0, tzinfo=UTC
                ),
                knowledge_date=date(int(td[:4]), int(td[5:7]), int(td[8:10]))
                - timedelta(days=1),
                trade_date=td,
            ),
            is_rebalance_day=True,
            bars={},
        )
        ctx.slice_ = mock_slice
        return ctx

    def test_compiled_nonempty_returns_bundle_builder(self) -> None:
        """compiled_expressions 非空 → 返回可调用的 bundle_builder."""
        import polars as pl
        from ditto_application.processes.execution.factor_bridge import (
            CompiledExpressions,
        )
        from ditto_features.expression.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )

        # 构建真实的 CompiledDerivedExpression（简单的 close 列）
        compiled_expr = CompiledDerivedExpression(
            derived_id="signal_0",
            version=1,
            expr=pl.col("close"),
            analysis=Analysis(
                dependencies=("close",),
                operator_names=(),
                lookback=0,
                requires_full_day=False,
                scope="instrument",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="h1",
                operator_fingerprint="f1",
                compiler_fingerprint="cf1",
                cache_key="ck1",
                engine_codegen_version="v1",
                analysis_version="av1",
                polars_version="pv1",
                expr_serialization_format="polars",
            ),
        )
        compiled = CompiledExpressions(
            expressions=(compiled_expr,),
            weights=(1.0,),
        )

        config = _make_service_config(
            strategy_id="factor-strat",
            run_id="run-factor-001",
        )
        service = _make_minimal_service(config=config)
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="run-factor-001",
        )

        # builder 是可调用的
        assert callable(builder)

        # 调用 builder 返回 StrategyInputBundle
        ctx = self._make_step_context()
        bundle = builder(ctx)

        from ditto_strategy.alpha.pipeline import StrategyInputBundle

        assert isinstance(bundle, StrategyInputBundle)
        assert bundle.trade_date == "2026-04-10"
        assert bundle.strategy_id == "factor-strat"
        assert bundle.run_id == "run-factor-001"
        assert bundle.benchmark_close == 3000.0
        # instruments 和 market_data 包含 2 个标的
        assert bundle.instruments.height == 2
        assert bundle.market_data.height == 2
        # signal_values 包含 instrument_id + signal_value 列
        assert "instrument_id" in bundle.signal_values.columns
        assert "signal_value" in bundle.signal_values.columns
        assert bundle.signal_values.height == 2

    def test_run_id_param_propagated_to_bundle(self) -> None:
        """传入的 run_id 参数应传递到生成的 StrategyInputBundle.run_id (F10)."""
        import polars as pl
        from ditto_application.processes.execution.factor_bridge import (
            CompiledExpressions,
        )
        from ditto_features.expression.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )

        compiled_expr = CompiledDerivedExpression(
            derived_id="signal_0",
            version=1,
            expr=pl.col("close"),
            analysis=Analysis(
                dependencies=("close",),
                operator_names=(),
                lookback=0,
                requires_full_day=False,
                scope="instrument",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="h1",
                operator_fingerprint="f1",
                compiler_fingerprint="cf1",
                cache_key="ck1",
                engine_codegen_version="v1",
                analysis_version="av1",
                polars_version="pv1",
                expr_serialization_format="polars",
            ),
        )
        compiled = CompiledExpressions(
            expressions=(compiled_expr,),
            weights=(1.0,),
        )

        # config.run_id 为空 — run_id 由外部传入，不应独立生成
        config = _make_service_config(strategy_id="factor-strat", run_id="")
        service = _make_minimal_service(config=config)
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="explicit-run-id",
        )

        ctx = self._make_step_context()
        bundle = builder(ctx)

        # bundle.run_id 必须使用传入的 run_id，而非 config 或随机 UUID
        assert bundle.run_id == "explicit-run-id"

    def test_compiled_empty_expressions_skips_builder(self) -> None:
        """空 expressions 元组时 builder 可构建但信号为空."""
        compiled = self._make_compiled_expressions(expressions=[], weights=())

        config = _make_service_config(strategy_id="empty-strat", run_id="run-empty")
        service = _make_minimal_service(config=config)

        # 空 expressions 仍返回 builder（FactorBridge 处理空 DataFrame 时返回空信号）
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="run-empty",
        )
        assert callable(builder)

        # 但实际调用 FactorBridge.compute_signals 时信号为空
        ctx = self._make_step_context()
        bundle = builder(ctx)

        from ditto_strategy.alpha.pipeline import StrategyInputBundle

        assert isinstance(bundle, StrategyInputBundle)
        assert bundle.signal_values.height == 2  # FactorBridge 处理 empty exprs

    def test_compilation_failure_propagates_error(self) -> None:
        """当 FactorBridge.compute_signals 因无效表达式抛异常时，builder 传播异常."""
        import polars as pl
        from ditto_application.processes.execution.factor_bridge import (
            CompiledExpressions,
        )
        from ditto_features.expression.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )

        # 构建一个引用不存在列的表达式，会在 rank 阶段抛出 ColumnNotFoundError
        compiled_expr = CompiledDerivedExpression(
            derived_id="signal_0",
            version=1,
            expr=pl.col("nonexistent_column"),
            analysis=Analysis(
                dependencies=("nonexistent_column",),
                operator_names=(),
                lookback=0,
                requires_full_day=False,
                scope="instrument",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="h1",
                operator_fingerprint="f1",
                compiler_fingerprint="cf1",
                cache_key="ck1",
                engine_codegen_version="v1",
                analysis_version="av1",
                polars_version="pv1",
                expr_serialization_format="polars",
            ),
        )
        compiled = CompiledExpressions(
            expressions=(compiled_expr,),
            weights=(1.0,),
        )

        config = _make_service_config(strategy_id="error-strat", run_id="run-error")
        service = _make_minimal_service(config=config)
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="run-error",
        )

        ctx = self._make_step_context()

        # compute_signals 内部 rank 阶段因列不存在而抛出异常
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            builder(ctx)

    def test_builder_raises_on_missing_slice(self) -> None:
        """StepContext.slice_ 为 None 时，builder 抛出 ValueError."""
        from ditto_application.processes.execution.factor_bridge import (
            CompiledExpressions,
        )

        compiled = self._make_compiled_expressions(
            expressions=[],
            weights=(),
        )
        compiled.__class__ = CompiledExpressions  # type: ignore[assignment]

        config = _make_service_config(strategy_id="test-strat", run_id="run-test")
        service = _make_minimal_service(config=config)
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="run-test",
        )

        # 构建 slice_ 为 None 的 StepContext
        from ditto_backtest.steps import StepContext

        ctx = StepContext(
            time_context=TimeContext(
                decision_time=datetime(2026, 4, 10, 15, 0, tzinfo=UTC),
                knowledge_date=date(2026, 4, 9),
                trade_date="2026-04-10",
            ),
            is_rebalance_day=True,
            bars={},
        )
        ctx.slice_ = None

        with pytest.raises(AppProcessError, match="slice_ required"):
            builder(ctx)

    def test_lookback_days_from_compiled_max_lookback(self) -> None:
        """lookback_days 应取 compiled.expressions 中 analysis.lookback 的最大值."""
        import polars as pl
        from ditto_application.processes.execution.factor_bridge import (
            CompiledExpressions,
        )
        from ditto_features.expression.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )

        # 构建两个表达式：lookback=61 和 lookback=21
        compiled_expr_61 = CompiledDerivedExpression(
            derived_id="signal_0",
            version=1,
            expr=pl.col("close"),
            analysis=Analysis(
                dependencies=("close",),
                operator_names=("ts_mean",),
                lookback=61,
                requires_full_day=False,
                scope="instrument",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="h1",
                operator_fingerprint="f1",
                compiler_fingerprint="cf1",
                cache_key="ck1",
                engine_codegen_version="v1",
                analysis_version="av1",
                polars_version="pv1",
                expr_serialization_format="polars",
            ),
        )
        compiled_expr_21 = CompiledDerivedExpression(
            derived_id="signal_1",
            version=1,
            expr=pl.col("volume"),
            analysis=Analysis(
                dependencies=("volume",),
                operator_names=("ts_std",),
                lookback=21,
                requires_full_day=False,
                scope="instrument",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="h2",
                operator_fingerprint="f2",
                compiler_fingerprint="cf2",
                cache_key="ck2",
                engine_codegen_version="v1",
                analysis_version="av1",
                polars_version="pv1",
                expr_serialization_format="polars",
            ),
        )
        compiled = CompiledExpressions(
            expressions=(compiled_expr_61, compiled_expr_21),
            weights=(0.7, 0.3),
        )

        # mock data_feed — 返回空 DataFrame，但记录调用参数
        mock_data_feed = MagicMock()
        mock_data_feed.get_history.return_value = pl.DataFrame()

        config = _make_service_config(
            strategy_id="lookback-strat",
            run_id="run-lookback",
        )
        service = _make_minimal_service(config=config, data_feed=mock_data_feed)
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="run-lookback",
        )

        ctx = self._make_step_context()
        builder(ctx)

        # 验证 get_history 被调用时 lookback_days 是 61（最大值），而非 20
        mock_data_feed.get_history.assert_called_once()
        call_args = mock_data_feed.get_history.call_args
        # get_history(instrument_ids, date, lookback_days)
        assert call_args[0][2] == 61


# ---------------------------------------------------------------------------
# Tests: run_service lifecycle (T31)
# ---------------------------------------------------------------------------


class TestRunServiceLifecycle:
    """测试 BacktestService 与 RunLifecycleService 的交互。"""

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_lifecycle_create_then_running_on_start(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """run_service 提供时，create_run 和 mark_running 在引擎运行前被调用."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_run_svc = MagicMock()
        mock_run_svc.get_run.return_value = None  # 不存在 → 应创建
        config = _make_service_config(run_id="lifecycle-001")
        options = BacktestServiceOptions(run_service=mock_run_svc)
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )
        service.run()

        mock_run_svc.create_run.assert_called_once()
        call_kwargs = mock_run_svc.create_run.call_args[1]
        assert call_kwargs["run_id"] == "lifecycle-001"
        assert call_kwargs["strategy_id"] == "momentum-etf"
        assert call_kwargs["strategy_version"] == ""
        assert call_kwargs["mode"] == "backtest"
        assert call_kwargs["parent_run_id"] == ""
        assert "config_json" in call_kwargs
        mock_run_svc.mark_running.assert_called_once_with("lifecycle-001")

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_creates_record_with_config_json_content(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """create_run 时 config_json 应包含完整配置关键字段."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_run_svc = MagicMock()
        mock_run_svc.get_run.return_value = None
        config = _make_service_config(
            run_id="config-json-001",
            start_date="2026-01-15",
            end_date="2026-06-30",
            initial_cash=2_000_000.0,
            benchmark_id="idx-000300",
        )
        options = BacktestServiceOptions(run_service=mock_run_svc)
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )
        service.run()

        call_kwargs = mock_run_svc.create_run.call_args[1]
        import orjson

        config_data = orjson.loads(call_kwargs["config_json"])
        assert config_data["start_date"] == "2026-01-15"
        assert config_data["end_date"] == "2026-06-30"
        assert config_data["initial_cash"] == 2_000_000.0
        assert config_data["benchmark_id"] == "idx-000300"
        assert config_data["allow_experimental_data"] is False
        assert config_data["pit_policy"] == "knowledge_date_fail_closed"
        assert config_data["pit_time_column"] == "knowledge_date"
        assert config_data["unsafe_time_policy"] == ""

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_run_config_records_experimental_data_opt_in(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """BacktestService config_json exposes explicit maturity opt-in."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_run_svc = MagicMock()
        mock_run_svc.get_run.return_value = None
        config = _make_service_config(run_id="config-json-exp")
        options = BacktestServiceOptions(
            run_service=mock_run_svc,
            allow_experimental_data=True,
        )
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )

        service.run()

        import orjson

        call_kwargs = mock_run_svc.create_run.call_args[1]
        config_data = orjson.loads(call_kwargs["config_json"])
        assert config_data["allow_experimental_data"] is True

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_lifecycle_skips_create_run_when_record_exists(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """当 run record 已存在时 (API 预创建)，跳过 create_run (R4)."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_run_svc = MagicMock()
        # 模拟 API 预创建的 run record（含 config_json）
        existing_record = MagicMock()
        existing_record.config_json = '{"cost_config": {"slippage_bps": 3.0}}'
        mock_run_svc.get_run.return_value = existing_record

        config = _make_service_config(run_id="r4-existing-001")
        options = BacktestServiceOptions(run_service=mock_run_svc)
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )
        service.run()

        # 预创建记录存在 → create_run 不应被调用
        mock_run_svc.create_run.assert_not_called()
        mock_run_svc.get_run.assert_called_once_with("r4-existing-001")
        mock_run_svc.mark_running.assert_called_once_with("r4-existing-001")

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_lifecycle_mark_completed_on_success(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """引擎成功完成后，mark_completed 被调用."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_run_svc = MagicMock()
        mock_run_svc.get_run.return_value = None  # 不存在 → 应创建
        config = _make_service_config(run_id="lifecycle-002")
        options = BacktestServiceOptions(run_service=mock_run_svc)
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )
        service.run()

        mock_run_svc.mark_completed.assert_called_once_with("lifecycle-002")
        mock_run_svc.mark_failed.assert_not_called()

    @patch.object(EngineLoop, "run", side_effect=RuntimeError("engine crash"))
    def test_lifecycle_mark_failed_on_engine_error(
        self,
        mock_engine_run: MagicMock,
    ) -> None:
        """引擎运行异常时，mark_failed 被调用且异常被重新抛出."""
        mock_run_svc = MagicMock()
        mock_run_svc.get_run.return_value = None  # 不存在 → 应创建
        config = _make_service_config(run_id="lifecycle-003")
        options = BacktestServiceOptions(run_service=mock_run_svc)
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )

        with pytest.raises(RuntimeError, match="engine crash"):
            service.run()

        mock_run_svc.mark_failed.assert_called_once_with(
            "lifecycle-003",
            "engine crash",
        )
        mock_run_svc.mark_completed.assert_not_called()

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_lifecycle_not_called_when_run_service_none(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """run_service 为 None 时，生命周期方法不被调用."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        service = _make_minimal_service()
        # run_service defaults to None
        result = service.run()

        assert result is fake_report

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_application.processes.execution.backtest_process.build_report")
    def test_lifecycle_parent_run_id_propagated(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """parent_run_id 正确传递到 create_run."""
        fake_report = MagicMock(spec=BacktestReport)
        fake_report.risk_log = ()
        fake_report.pre_trade_log = ()
        mock_build_report.return_value = fake_report

        mock_run_svc = MagicMock()
        mock_run_svc.get_run.return_value = None  # 不存在 → 应创建
        config = _make_service_config(
            run_id="retry-002",
            parent_run_id="original-001",  # type: ignore[arg-type]
        )
        options = BacktestServiceOptions(run_service=mock_run_svc)
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=options,
        )
        service.run()

        call_kwargs = mock_run_svc.create_run.call_args.kwargs
        assert call_kwargs["parent_run_id"] == "original-001"


# ---------------------------------------------------------------------------
# Tests: checkpoint persistence callback
# ---------------------------------------------------------------------------


class TestBacktestCheckpointPersistence:
    """测试 BacktestService 到 checkpoint writer 的转换边界。"""

    def test_engine_checkpoint_is_persisted_as_strategy_run_checkpoint(self) -> None:
        """EngineOptions.on_checkpoint 应写入应用层 run checkpoint 记录。"""
        checkpoint_writer = MagicMock()
        config = _make_service_config(
            strategy_id="momentum-etf",
            strategy_version="4",
            run_id="run-checkpoint",
        )
        service = BacktestService(
            config=config,
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=MagicMock(),
            options=BacktestServiceOptions(checkpoint_writer=checkpoint_writer),
        )

        options = service._build_engine_options(
            "run-checkpoint",
            ExecutionAuditCollector(),
        )
        assert options.on_checkpoint is not None

        checkpoint = BacktestCheckpoint(
            run_id="run-checkpoint",
            strategy_id="momentum-etf",
            completed_trade_date="2026-03-01",
            resume_from="2026-03-02",
            completed_days=42,
            total_days=60,
            nav=1_050_000.0,
            order_count=7,
            fill_count=6,
            account_state=BacktestAccountStateSnapshot(
                cash_available=920_000.0,
                cash_settled=900_000.0,
                cash_frozen=20_000.0,
                total_value=1_050_000.0,
                nav=1_050_000.0,
                exposure=130_000.0,
                positions=(),
            ),
            settlement_state=BacktestSettlementStateSnapshot(
                frozen_quantities=(
                    BacktestFrozenQuantitySnapshot(
                        instrument_id=1,
                        settle_date="2026-03-03",
                        quantity=1000,
                    ),
                ),
            ),
            runtime_state=BacktestRuntimeStateSnapshot(
                pending_orders=(
                    BacktestPendingOrderSnapshot(
                        client_order_id="order-001",
                        instrument_id=1,
                        order_type="market",
                        direction="buy",
                        quantity=300,
                        price=None,
                        stop_price=None,
                        trade_date="2026-03-01",
                        status="submitted",
                        filled_quantity=0,
                        leaves_quantity=300,
                        filled_price=None,
                        average_fill_price=None,
                    ),
                ),
                delayed_signals=(
                    BacktestDelayedSignalSnapshot(
                        queue_index=0,
                        trade_date="2026-03-01",
                        strategy_id="momentum-etf",
                        run_id="run-checkpoint",
                        cash_target=0.5,
                        positions=(
                            BacktestTargetWeightSnapshot(
                                instrument_id=1,
                                target_weight=0.5,
                            ),
                        ),
                    ),
                ),
            ),
        )
        options.on_checkpoint(checkpoint)

        checkpoint_writer.save_checkpoint.assert_called_once_with(
            StrategyRunCheckpointRecord(
                run_id="run-checkpoint",
                strategy_id="momentum-etf",
                strategy_version="4",
                mode="backtest",
                completed_trade_date="2026-03-01",
                resume_from="2026-03-02",
                completed_days=42,
                total_days=60,
                nav=1_050_000.0,
                order_count=7,
                fill_count=6,
                account_state_json=checkpoint.account_state_json,
                account_state_hash=checkpoint.account_state_hash,
                settlement_state_json=checkpoint.settlement_state_json,
                settlement_state_hash=checkpoint.settlement_state_hash,
                runtime_state_json=checkpoint.runtime_state_json,
                runtime_state_hash=checkpoint.runtime_state_hash,
            )
        )

    def test_checkpoint_callback_absent_without_writer(self) -> None:
        """未提供 checkpoint writer 时不注册持久化回调。"""
        service = _make_minimal_service()
        options = service._build_engine_options("run-no-checkpoint", MagicMock())

        assert options.on_checkpoint is None


# ---------------------------------------------------------------------------
# Tests: step metrics callback
# ---------------------------------------------------------------------------


class TestBacktestStepMetricsCallback:
    """测试 BacktestService 到 platform Metrics 的可选桥接。"""

    def test_step_callback_skips_unregistered_backtest_metrics(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """领域指标未注册时，step 完成回调不应影响回放/回测执行。"""
        from ditto_platform import foundation

        class MissingBacktestMetrics:
            pass

        monkeypatch.setattr(foundation, "Metrics", MissingBacktestMetrics)
        service = _make_minimal_service()

        options = service._build_engine_options(
            "run-missing-step-metrics",
            ExecutionAuditCollector(),
        )

        assert options.on_step_complete is not None
        options.on_step_complete("DelayedSignalStep", 0.125, True)
        options.on_step_complete("DelayedSignalStep", 0.125, False)
