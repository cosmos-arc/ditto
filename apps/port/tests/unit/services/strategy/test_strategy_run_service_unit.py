"""StrategyRunService 单元测试 — Port 层策略运行编排服务。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from ditto_core.backtest.data_feed import Slice
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.strategy.context import StrategyContext
from ditto_core.strategy.models import TargetPortfolio
from ditto_core.strategy.pipeline import StrategyPipeline
from ditto_datahub.models.strategy import StrategyArtifactRecord
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_port.services.strategy.input_assembler import StrategyInputAssembler
from ditto_port.services.strategy.strategy_run_service import (
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunService,
    StrategyRunServiceConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


TRADE_DATE = "2026-01-15"


def _make_target_portfolio(
    trade_date: str = TRADE_DATE,
    strategy_id: str = "test",
    run_id: str = "run-1",
) -> TargetPortfolio:
    """创建 TargetPortfolio 用于测试。"""
    return TargetPortfolio(
        trade_date=trade_date,
        strategy_id=strategy_id,
        run_id=run_id,
        positions={"ETF-001": 0.6, "ETF-002": 0.3},
        cash_target=0.1,
    )


def _make_fake_slice(trade_date: str = TRADE_DATE) -> Slice:
    """构造 fake Slice 用于测试。"""
    return Slice(
        step_time=datetime(2026, 1, 15, 9, 30),
        trade_date=trade_date,
        bars={
            "ETF-001": MarketSnapshot(
                trade_date=trade_date,
                instrument_id="ETF-001",
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                prev_close=10.0,
                volume=1000000,
                amount=10200000.0,
            ),
        },
        benchmark_close=3000.0,
    )


def _make_mock_pipeline(target: TargetPortfolio | None = None) -> MagicMock:
    """创建 mock StrategyPipeline。"""
    pipeline = MagicMock(spec=StrategyPipeline)
    pipeline.run.return_value = target or _make_target_portfolio()
    return pipeline


def _make_mock_assembler() -> MagicMock:
    """创建 mock StrategyInputAssembler。"""
    assembler = MagicMock(spec=StrategyInputAssembler)
    # 返回一个最小 StrategyInputBundle — 仅用于验证调用参数
    import polars as pl
    from ditto_core.strategy.pipeline import StrategyInputBundle

    assembler.assemble.return_value = StrategyInputBundle(
        trade_date=TRADE_DATE,
        strategy_id="default",
        run_id="",
        instruments=pl.DataFrame({"instrument_id": ["ETF-001"]}),
        market_data=pl.DataFrame(
            {
                "instrument_id": ["ETF-001"],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "volume": [1000000.0],
            }
        ),
        signal_values=pl.DataFrame(
            {"instrument_id": ["ETF-001"], "signal_value": [0.02]}
        ),
        parameters={},
        benchmark_close=3000.0,
    )
    return assembler


def _make_service(
    config: StrategyRunServiceConfig | None = None,
    pipeline: MagicMock | None = None,
    assembler: MagicMock | None = None,
    artifact_service: StrategyArtifactService | None = None,
) -> StrategyRunService:
    """创建 StrategyRunService 实例（依赖均为 mock）。"""
    if config is None:
        config = StrategyRunServiceConfig()
    return StrategyRunService(
        config=config,
        pipeline=pipeline or _make_mock_pipeline(),
        assembler=assembler or _make_mock_assembler(),
        artifact_service=artifact_service,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResearchMode:
    """RESEARCH 模式测试。"""

    def test_research_mode_returns_target_portfolio(self) -> None:
        """RESEARCH 模式返回包含 TargetPortfolio 的 StrategyRunResult。"""
        target = _make_target_portfolio()
        service = _make_service(
            config=StrategyRunServiceConfig(mode=StrategyRunMode.RESEARCH),
            pipeline=_make_mock_pipeline(target),
        )
        slice_ = _make_fake_slice()

        result = service.run(TRADE_DATE, slice_)

        assert isinstance(result, StrategyRunResult)
        assert result.target == target
        assert result.mode == StrategyRunMode.RESEARCH
        assert result.trade_date == TRADE_DATE

    def test_recommendation_mode_without_artifact_service(self) -> None:
        """RECOMMENDATION 模式在无 artifact_service 时正常运行（无持久化）。"""
        target = _make_target_portfolio()
        service = _make_service(
            config=StrategyRunServiceConfig(mode=StrategyRunMode.RECOMMENDATION),
            pipeline=_make_mock_pipeline(target),
            artifact_service=None,
        )
        slice_ = _make_fake_slice()

        result = service.run(TRADE_DATE, slice_)

        assert isinstance(result, StrategyRunResult)
        assert result.target == target
        assert result.mode == StrategyRunMode.RECOMMENDATION


class TestRecommendationMode:
    """RECOMMENDATION 模式持久化测试。"""

    def test_recommendation_mode_persists_signal(self) -> None:
        """RECOMMENDATION 模式调用 artifact_service.save_artifact。"""
        mock_artifact_service = MagicMock(spec=StrategyArtifactService)
        target = _make_target_portfolio()
        service = _make_service(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                run_id="run-001",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            pipeline=_make_mock_pipeline(target),
            artifact_service=mock_artifact_service,
        )
        slice_ = _make_fake_slice()

        service.run(TRADE_DATE, slice_)

        mock_artifact_service.save_artifact.assert_called_once()
        artifact = mock_artifact_service.save_artifact.call_args[0][0]
        assert isinstance(artifact, StrategyArtifactRecord)
        assert artifact.artifact_type == "signal_snapshot"
        assert artifact.strategy_id == "momentum-etf"
        assert artifact.run_id == "run-001"

    def test_persist_signal_metadata(self) -> None:
        """持久化的 metadata 包含 positions 和 cash_target。"""
        mock_artifact_service = MagicMock(spec=StrategyArtifactService)
        target = _make_target_portfolio()
        service = _make_service(
            config=StrategyRunServiceConfig(
                strategy_id="test",
                run_id="run-001",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            pipeline=_make_mock_pipeline(target),
            artifact_service=mock_artifact_service,
        )
        slice_ = _make_fake_slice()

        service.run(TRADE_DATE, slice_)

        artifact = mock_artifact_service.save_artifact.call_args[0][0]
        assert artifact.metadata["trade_date"] == TRADE_DATE
        assert artifact.metadata["positions"] == {"ETF-001": 0.6, "ETF-002": 0.3}
        assert artifact.metadata["cash_target"] == 0.1


class TestRunId:
    """run_id 传播测试。"""

    def test_run_id_propagated(self) -> None:
        """Config 中的 run_id 传播到 result。"""
        service = _make_service(
            config=StrategyRunServiceConfig(
                strategy_id="test",
                run_id="my-custom-run-id",
            ),
        )
        slice_ = _make_fake_slice()

        result = service.run(TRADE_DATE, slice_)

        assert result.run_id == "my-custom-run-id"

    def test_run_id_auto_generated(self) -> None:
        """空 run_id 时自动生成。"""
        service = _make_service(
            config=StrategyRunServiceConfig(
                strategy_id="test",
                run_id="",
            ),
        )
        slice_ = _make_fake_slice()

        result = service.run(TRADE_DATE, slice_)

        assert len(result.run_id) == 8
        assert result.run_id.isalnum()


class TestAssemblerAndPipelineCalls:
    """验证 assembler / pipeline 调用参数。"""

    def test_assembler_called_with_correct_date(self) -> None:
        """assembler.assemble() 使用正确的 trade_date 调用。"""
        mock_assembler = _make_mock_assembler()
        service = _make_service(assembler=mock_assembler)
        slice_ = _make_fake_slice()

        service.run(TRADE_DATE, slice_)

        mock_assembler.assemble.assert_called_once_with(TRADE_DATE, slice_)

    def test_pipeline_called_with_context_and_bundle(self) -> None:
        """pipeline.run() 使用 StrategyContext 和 input_bundle 调用。"""
        mock_pipeline = _make_mock_pipeline()
        mock_assembler = _make_mock_assembler()
        service = _make_service(
            pipeline=mock_pipeline,
            assembler=mock_assembler,
        )
        slice_ = _make_fake_slice()

        service.run(TRADE_DATE, slice_)

        mock_pipeline.run.assert_called_once()
        args = mock_pipeline.run.call_args[0]
        assert isinstance(args[0], StrategyContext)
        # args[1] 是 assembler 返回的 StrategyInputBundle
        assert args[1] is mock_assembler.assemble.return_value


class TestFrozenDataclasses:
    """frozen dataclass 不可变性测试。"""

    def test_frozen_config(self) -> None:
        """StrategyRunServiceConfig 是 frozen 的。"""
        config = StrategyRunServiceConfig(strategy_id="test")
        with pytest.raises(FrozenInstanceError):
            config.strategy_id = "changed"  # type: ignore[misc]

    def test_frozen_result(self) -> None:
        """StrategyRunResult 是 frozen 的。"""
        result = StrategyRunResult(
            run_id="run-1",
            trade_date=TRADE_DATE,
            strategy_id="test",
            target=_make_target_portfolio(),
            mode=StrategyRunMode.RESEARCH,
        )
        with pytest.raises(FrozenInstanceError):
            result.run_id = "changed"  # type: ignore[misc]


class TestEnumAndProperty:
    """枚举值与属性测试。"""

    def test_strategy_run_mode_values(self) -> None:
        """StrEnum 值为正确的字符串。"""
        assert StrategyRunMode.RESEARCH == "research"
        assert StrategyRunMode.RECOMMENDATION == "recommendation"
        assert isinstance(StrategyRunMode.RESEARCH, str)

    def test_mode_property(self) -> None:
        """mode property 返回配置中的模式值。"""
        service = _make_service(
            config=StrategyRunServiceConfig(mode=StrategyRunMode.RECOMMENDATION),
        )
        assert service.mode == StrategyRunMode.RECOMMENDATION

        service_research = _make_service(
            config=StrategyRunServiceConfig(mode=StrategyRunMode.RESEARCH),
        )
        assert service_research.mode == StrategyRunMode.RESEARCH
