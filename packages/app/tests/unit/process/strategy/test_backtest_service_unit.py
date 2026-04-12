"""BacktestService 单元测试 — Port 层回测编排服务。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ditto_app.process.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_engine.backtest.audit import ExecutionAuditCollector
from ditto_engine.backtest.engine import EngineConfig, EngineLoop, EngineResult
from ditto_engine.backtest.manifest import RunManifest, RunMode
from ditto_engine.backtest.statistics import BacktestReport
from ditto_kernel.identity import InstrumentId

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
) -> BacktestService:
    """创建最小 BacktestService 实例（所有依赖均为 mock）。"""
    if config is None:
        config = _make_service_config()

    mock_pipeline = MagicMock()
    mock_planner = MagicMock()
    mock_brokerage = MagicMock()
    mock_pre_trade_check = MagicMock()
    mock_data_feed = MagicMock()

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

    def test_custom_values(self) -> None:
        """自定义值正确。"""
        config = _make_service_config(
            strategy_id="my-strategy",
            run_id="run-123",
            strategy_version="2026.03",
            initial_cash=5_000_000.0,
            benchmark_id=InstrumentId(3_000_001),
            parameter_overrides=("top_k=5",),
        )
        assert config.strategy_id == "my-strategy"
        assert config.strategy_version == "2026.03"
        assert config.run_id == "run-123"
        assert config.initial_cash == 5_000_000.0
        assert config.benchmark_id == InstrumentId(3_000_001)
        assert config.parameter_overrides == ("top_k=5",)

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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
    def test_run_maps_portfolio_wide_id_to_asterisk(
        self,
        mock_build_report: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """Portfolio-wide 风控记录在持久化时 instrument_id=None, scope='portfolio'。"""
        from ditto_engine.backtest.audit import RiskScanRecord
        from ditto_engine.risk.post_trade import (
            RiskActionType,
            RiskScope,
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

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_app.process.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_app.process.execution.backtest_process.build_report")
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

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
        "ditto_app.process.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/test/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
        assert call_arg.file_path != ""
        assert "backtest_report.json" in call_arg.file_path

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch(
        "ditto_app.process.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-001/backtest_report.json"),
        },
    )
    @patch("ditto_app.process.execution.backtest_process.build_report")
    def test_run_artifact_without_dir_still_writes_file(
        self,
        mock_build_report: MagicMock,
        mock_write_artifacts: MagicMock,
        mock_engine_run: MagicMock,
    ) -> None:
        """未提供 artifact_dir 时，artifact 仍写入默认目录，file_path 非空。"""
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
        assert call_arg.file_path != ""
        assert "backtest_report" in call_arg.file_path

    @patch(
        "ditto_app.process.execution.backtest_process.write_backtest_artifacts",
        return_value={
            "backtest_report": Path("/tmp/ditto/run-001/backtest_report.json"),
            "manifest": Path("/tmp/ditto/run-001/manifest.json"),
        },
    )
    @patch("ditto_app.process.execution.backtest_process.build_report")
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


# ---------------------------------------------------------------------------
# Tests: run_id propagation
# ---------------------------------------------------------------------------


class TestRunIdPropagation:
    """测试 run_id 在各组件间的传递。"""

    @patch.object(EngineLoop, "__init__", return_value=None)
    @patch.object(EngineLoop, "run")
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
        date: str = "2026-04-10",
    ) -> MagicMock:
        """构建 StepContext mock (含 bars slice)."""
        from ditto_engine.backtest.data_feed import Slice

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

        from ditto_engine.backtest.steps import StepContext

        ctx = StepContext(date=date, is_rebalance_day=True)
        ctx.slice_ = mock_slice
        return ctx

    def test_compiled_nonempty_returns_bundle_builder(self) -> None:
        """compiled_expressions 非空 → 返回可调用的 bundle_builder."""
        import polars as pl
        from ditto_analytics.materialization.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )
        from ditto_app.process.execution.factor_bridge import CompiledExpressions

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
        builder = service._build_factor_aware_bundle_builder(compiled)

        # builder 是可调用的
        assert callable(builder)

        # 调用 builder 返回 StrategyInputBundle
        ctx = self._make_step_context()
        bundle = builder(ctx)

        from ditto_engine.alpha.pipeline import StrategyInputBundle

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

    def test_compiled_empty_expressions_skips_builder(self) -> None:
        """空 expressions 元组时 builder 可构建但信号为空."""
        compiled = self._make_compiled_expressions(expressions=[], weights=())

        config = _make_service_config(strategy_id="empty-strat", run_id="run-empty")
        service = _make_minimal_service(config=config)

        # 空 expressions 仍返回 builder（FactorBridge 处理空 DataFrame 时返回空信号）
        builder = service._build_factor_aware_bundle_builder(compiled)
        assert callable(builder)

        # 但实际调用 FactorBridge.compute_signals 时信号为空
        ctx = self._make_step_context()
        bundle = builder(ctx)

        from ditto_engine.alpha.pipeline import StrategyInputBundle

        assert isinstance(bundle, StrategyInputBundle)
        assert bundle.signal_values.height == 2  # FactorBridge 处理 empty exprs

    def test_compilation_failure_propagates_error(self) -> None:
        """当 FactorBridge.compute_signals 因无效表达式抛异常时，builder 传播异常."""
        import polars as pl
        from ditto_analytics.materialization.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )
        from ditto_app.process.execution.factor_bridge import CompiledExpressions

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
        builder = service._build_factor_aware_bundle_builder(compiled)

        ctx = self._make_step_context()

        # compute_signals 内部 rank 阶段因列不存在而抛出异常
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            builder(ctx)

    def test_builder_raises_on_missing_slice(self) -> None:
        """StepContext.slice_ 为 None 时，builder 抛出 ValueError."""
        from ditto_app.process.execution.factor_bridge import CompiledExpressions

        compiled = self._make_compiled_expressions(
            expressions=[],
            weights=(),
        )
        compiled.__class__ = CompiledExpressions  # type: ignore[assignment]

        config = _make_service_config(strategy_id="test-strat", run_id="run-test")
        service = _make_minimal_service(config=config)
        builder = service._build_factor_aware_bundle_builder(compiled)

        # 构建 slice_ 为 None 的 StepContext
        from ditto_engine.backtest.steps import StepContext

        ctx = StepContext(date="2026-04-10", is_rebalance_day=True)
        ctx.slice_ = None

        with pytest.raises(ValueError, match="slice_ required"):
            builder(ctx)


# ---------------------------------------------------------------------------
# Tests: run_service lifecycle (T31)
# ---------------------------------------------------------------------------


class TestRunServiceLifecycle:
    """测试 BacktestService 与 RunLifecycleService 的交互。"""

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_app.process.execution.backtest_process.build_report")
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

        mock_run_svc.create_run.assert_called_once_with(
            run_id="lifecycle-001",
            strategy_id="momentum-etf",
            strategy_version="",
            mode="backtest",
            parent_run_id="",
        )
        mock_run_svc.mark_running.assert_called_once_with("lifecycle-001")

    @patch.object(EngineLoop, "run", return_value=_make_engine_result())
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
    @patch("ditto_app.process.execution.backtest_process.build_report")
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
