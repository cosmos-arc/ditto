"""BacktestService 控制面编排单元测试 — run 生命周期集成。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from ditto_app.process.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_engine.backtest.statistics import BacktestReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGINE_LOOP_PATH = "ditto_app.process.execution.backtest_process.EngineLoop"
BUILD_REPORT_PATH = "ditto_app.process.execution.backtest_process.build_report"


def _make_service_config(
    strategy_id: str = "momentum-etf",
    run_id: str = "run-001",
    strategy_version: str = "",
    start_date: str = "2026-01-01",
    end_date: str = "2026-03-01",
) -> BacktestServiceConfig:
    """创建 BacktestServiceConfig。"""
    return BacktestServiceConfig(
        strategy_id=strategy_id,
        run_id=run_id,
        strategy_version=strategy_version,
        start_date=start_date,
        end_date=end_date,
    )


def _make_service(
    config: BacktestServiceConfig | None = None,
    run_service: MagicMock | None = None,
) -> BacktestService:
    """创建带 run_service 的 BacktestService。"""
    if config is None:
        config = _make_service_config()

    mock_pipeline = MagicMock()
    mock_planner = MagicMock()
    mock_brokerage = MagicMock()
    mock_pre_trade_check = MagicMock()
    mock_data_feed = MagicMock()

    options = BacktestServiceOptions(run_service=run_service)

    return BacktestService(
        config=config,
        pipeline=mock_pipeline,
        planner=mock_planner,
        brokerage=mock_brokerage,
        pre_trade_check=mock_pre_trade_check,
        data_feed=mock_data_feed,
        options=options,
    )


def _make_fake_report() -> MagicMock:
    """创建 fake BacktestReport。"""
    report = MagicMock(spec=BacktestReport)
    report.run_id = "run-001"
    report.risk_log = ()
    report.pre_trade_log = ()
    report.initial_cash = 1_000_000.0
    report.aggregated_trade_stats = MagicMock(total_trades=10)
    report.alpha_stats = MagicMock(
        sharpe_ratio=1.0,
        max_drawdown=-3.0,
    )
    report.period = ("2026-01-01", "2026-03-01")
    return report


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBacktestRunWithLifecycle:
    """测试 BacktestService.run() 与 run 生命周期集成。"""

    @patch(BUILD_REPORT_PATH)
    @patch(ENGINE_LOOP_PATH)
    def test_run_creates_and_completes_run(
        self,
        MockEngineLoop: MagicMock,
        mock_build_report: MagicMock,
    ) -> None:
        """run() 创建 run → 运行 → 标记 completed。"""
        mock_build_report.return_value = _make_fake_report()

        mock_loop = MockEngineLoop.return_value
        mock_loop.run.return_value.run_id = "run-001"

        mock_run_service = MagicMock()
        service = _make_service(run_service=mock_run_service)
        service.run()

        # 验证生命周期调用
        mock_run_service.create_run.assert_called_once_with(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="",
            mode="backtest",
            parent_run_id="",
        )
        mock_run_service.mark_running.assert_called_once_with("run-001")
        mock_run_service.mark_completed.assert_called_once_with("run-001")
        mock_run_service.mark_failed.assert_not_called()

    @patch(BUILD_REPORT_PATH)
    @patch(ENGINE_LOOP_PATH)
    def test_run_passes_strategy_version_to_run_lifecycle(
        self,
        MockEngineLoop: MagicMock,
        mock_build_report: MagicMock,
    ) -> None:
        """生命周期创建时带上 strategy_version。"""
        mock_build_report.return_value = _make_fake_report()
        MockEngineLoop.return_value.run.return_value.run_id = "run-001"

        mock_run_service = MagicMock()
        service = _make_service(
            config=_make_service_config(strategy_version="2026.03"),
            run_service=mock_run_service,
        )

        service.run()

        mock_run_service.create_run.assert_called_once_with(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            mode="backtest",
            parent_run_id="",
        )

    @patch(BUILD_REPORT_PATH)
    @patch(ENGINE_LOOP_PATH)
    def test_run_marks_failed_on_engine_error(
        self,
        MockEngineLoop: MagicMock,
        mock_build_report: MagicMock,
    ) -> None:
        """引擎异常时标记 failed。"""
        mock_build_report.side_effect = RuntimeError("engine crash")
        # 确保 EngineLoop mock 已生效（构造不会报错）
        MockEngineLoop.return_value.run.return_value.run_id = "run-001"

        mock_run_service = MagicMock()
        service = _make_service(run_service=mock_run_service)

        with pytest.raises(RuntimeError, match="engine crash"):
            service.run()

        mock_run_service.create_run.assert_called_once()
        mock_run_service.mark_running.assert_called_once()
        mock_run_service.mark_failed.assert_called_once()
        mock_run_service.mark_completed.assert_not_called()

    @patch(BUILD_REPORT_PATH)
    @patch(ENGINE_LOOP_PATH)
    def test_run_with_empty_run_id_uses_generated_id_for_lifecycle(
        self,
        MockEngineLoop: MagicMock,
        mock_build_report: MagicMock,
    ) -> None:
        """run_id 为空时，生命周期各阶段使用同一个预生成 run_id。"""
        fake_report = _make_fake_report()
        fake_report.run_id = "generated-run"
        mock_build_report.return_value = fake_report

        mock_loop = MockEngineLoop.return_value
        mock_loop.run.return_value.run_id = "generated-run"

        mock_run_service = MagicMock()
        service = _make_service(
            config=_make_service_config(run_id=""),
            run_service=mock_run_service,
        )

        service.run()

        create_run_kwargs = mock_run_service.create_run.call_args.kwargs
        generated_run_id = create_run_kwargs["run_id"]
        assert generated_run_id != ""
        assert create_run_kwargs["strategy_id"] == "momentum-etf"
        assert create_run_kwargs["mode"] == "backtest"
        mock_run_service.mark_running.assert_called_once_with(generated_run_id)
        mock_run_service.mark_completed.assert_called_once_with(generated_run_id)

    @patch(BUILD_REPORT_PATH)
    @patch(ENGINE_LOOP_PATH)
    def test_run_marks_failed_with_same_run_id_and_error_message(
        self,
        MockEngineLoop: MagicMock,
        mock_build_report: MagicMock,
    ) -> None:
        """失败时使用同一个 run_id，并保留原始错误消息。"""
        mock_build_report.side_effect = RuntimeError("engine crash")
        MockEngineLoop.return_value.run.return_value.run_id = "generated-run"

        mock_run_service = MagicMock()
        service = _make_service(
            config=_make_service_config(run_id=""),
            run_service=mock_run_service,
        )

        with pytest.raises(RuntimeError, match="engine crash"):
            service.run()

        create_run_kwargs = mock_run_service.create_run.call_args.kwargs
        generated_run_id = create_run_kwargs["run_id"]
        assert generated_run_id != ""
        mock_run_service.mark_running.assert_called_once_with(generated_run_id)
        mock_run_service.mark_failed.assert_called_once_with(
            generated_run_id,
            "engine crash",
        )

    @patch(BUILD_REPORT_PATH)
    @patch(ENGINE_LOOP_PATH)
    def test_run_without_run_service_skips_lifecycle(
        self,
        MockEngineLoop: MagicMock,
        mock_build_report: MagicMock,
    ) -> None:
        """未提供 run_service 时，跳过生命周期管理。"""
        fake_report = _make_fake_report()
        mock_build_report.return_value = fake_report

        mock_loop = MockEngineLoop.return_value
        mock_loop.run.return_value.run_id = "run-001"

        service = _make_service(run_service=None)
        result = service.run()

        assert result is fake_report
