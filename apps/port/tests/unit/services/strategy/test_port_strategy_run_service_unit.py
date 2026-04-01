"""StrategyRunService 单元测试 — Port 层策略运行编排服务。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from ditto_datahub.models.strategy import StrategyArtifactRecord
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.execution.reality.market import MarketSnapshot
from ditto_engine.strategy.context import StrategyContext
from ditto_engine.strategy.models import TargetPortfolio
from ditto_engine.strategy.pipeline import StrategyPipeline
from ditto_engine.strategy.specs import ParamConstraint, StrategySpec
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
        positions={1: 0.6, 2: 0.3},
        cash_target=0.1,
    )


def _make_fake_slice(trade_date: str = TRADE_DATE) -> Slice:
    """构造 fake Slice 用于测试。"""
    return Slice(
        step_time=datetime(2026, 1, 15, 9, 30),
        trade_date=trade_date,
        bars={
            1: MarketSnapshot(
                trade_date=trade_date,
                instrument_id=1,
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
    from ditto_engine.strategy.pipeline import StrategyInputBundle

    assembler.assemble.return_value = StrategyInputBundle(
        trade_date=TRADE_DATE,
        strategy_id="default",
        run_id="",
        instruments=pl.DataFrame({"instrument_id": [1]}),
        market_data=pl.DataFrame(
            {
                "instrument_id": [1],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "volume": [1000000.0],
            }
        ),
        signal_values=pl.DataFrame({"instrument_id": [1], "signal_value": [0.02]}),
        parameters={},
        benchmark_close=3000.0,
    )
    return assembler


def _make_service(
    config: StrategyRunServiceConfig | None = None,
    pipeline: MagicMock | None = None,
    assembler: MagicMock | None = None,
    artifact_service: StrategyArtifactService | None = None,
    run_service: MagicMock | None = None,
) -> StrategyRunService:
    """创建 StrategyRunService 实例（依赖均为 mock）。"""
    if config is None:
        config = StrategyRunServiceConfig()
    return StrategyRunService(
        config=config,
        pipeline=pipeline or _make_mock_pipeline(),
        assembler=assembler or _make_mock_assembler(),
        artifact_service=artifact_service,
        run_service=run_service,
    )


def _make_spec_with_invalid_type() -> StrategySpec:
    """创建 param 类型不匹配的 StrategySpec。"""
    return StrategySpec(
        strategy_id="test",
        name="测试策略",
        template="etf_rotation",
        universe="etf-a",
        asset_class="etf",
        params={"lookback": "abc"},
        param_constraints=(ParamConstraint(name="lookback", dtype="int"),),
    )


def _make_spec_with_out_of_range() -> StrategySpec:
    """创建 param 超出范围的 StrategySpec。"""
    return StrategySpec(
        strategy_id="test",
        name="测试策略",
        template="etf_rotation",
        universe="etf-a",
        asset_class="etf",
        params={"lookback": 200},
        param_constraints=(
            ParamConstraint(name="lookback", dtype="int", min_value=1, max_value=100),
        ),
    )


def _make_spec_valid() -> StrategySpec:
    """创建参数合法的 StrategySpec。"""
    return StrategySpec(
        strategy_id="test",
        name="测试策略",
        template="etf_rotation",
        universe="etf-a",
        asset_class="etf",
        params={"lookback": 20},
        param_constraints=(
            ParamConstraint(name="lookback", dtype="int", min_value=1, max_value=100),
        ),
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
        assert artifact.metadata["positions"] == {1: 0.6, 2: 0.3}
        assert artifact.metadata["cash_target"] == 0.1

    def test_recommendation_mode_manages_run_lifecycle(self) -> None:
        """RECOMMENDATION 模式应创建并推进 run 生命周期。"""
        mock_artifact_service = MagicMock(spec=StrategyArtifactService)
        mock_run_service = MagicMock()
        target = _make_target_portfolio(run_id="run-001")
        service = StrategyRunService(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                strategy_version="2026.03",
                run_id="run-001",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            pipeline=_make_mock_pipeline(target),
            assembler=_make_mock_assembler(),
            artifact_service=mock_artifact_service,
            run_service=mock_run_service,
        )

        result = service.run(TRADE_DATE, _make_fake_slice())

        assert result.run_id == "run-001"
        mock_run_service.create_run.assert_called_once_with(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="2026.03",
            mode="recommendation",
        )
        mock_run_service.mark_running.assert_called_once_with("run-001")
        mock_run_service.mark_completed.assert_called_once_with("run-001")
        mock_run_service.mark_failed.assert_not_called()

    def test_auto_generated_run_id_flows_into_assembler_and_lifecycle(self) -> None:
        """空 run_id 时生成的真实 run_id 应传给 assembler 与 lifecycle。"""
        mock_run_service = MagicMock()
        mock_assembler = _make_mock_assembler()
        slice_ = _make_fake_slice()
        service = StrategyRunService(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                run_id="",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            pipeline=_make_mock_pipeline(),
            assembler=mock_assembler,
            run_service=mock_run_service,
        )

        result = service.run(TRADE_DATE, slice_)

        create_run_kwargs = mock_run_service.create_run.call_args.kwargs
        generated_run_id = create_run_kwargs["run_id"]
        assert result.run_id == generated_run_id
        assert len(generated_run_id) == 8
        mock_assembler.assemble.assert_called_once_with(
            TRADE_DATE,
            slice_,
            run_id=generated_run_id,
        )
        mock_run_service.mark_running.assert_called_once_with(generated_run_id)
        mock_run_service.mark_completed.assert_called_once_with(generated_run_id)

    def test_pipeline_failure_marks_run_failed(self) -> None:
        """pipeline 抛错时应将 run 标记为 failed，并保留原始错误消息。"""
        mock_run_service = MagicMock()
        mock_pipeline = _make_mock_pipeline()
        mock_pipeline.run.side_effect = RuntimeError("pipeline exploded")
        service = StrategyRunService(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                run_id="run-001",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            pipeline=mock_pipeline,
            assembler=_make_mock_assembler(),
            run_service=mock_run_service,
        )

        with pytest.raises(RuntimeError, match="pipeline exploded"):
            service.run(TRADE_DATE, _make_fake_slice())

        mock_run_service.create_run.assert_called_once_with(
            run_id="run-001",
            strategy_id="momentum-etf",
            strategy_version="",
            mode="recommendation",
        )
        mock_run_service.mark_running.assert_called_once_with("run-001")
        mock_run_service.mark_failed.assert_called_once_with(
            "run-001",
            "pipeline exploded",
        )
        mock_run_service.mark_completed.assert_not_called()


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

        result = service.run(TRADE_DATE, slice_)

        mock_assembler.assemble.assert_called_once_with(
            TRADE_DATE,
            slice_,
            run_id=result.run_id,
        )

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


class TestParamValidation:
    """spec 参数校验测试。"""

    def test_invalid_param_type_raises(self) -> None:
        """param 类型不匹配时抛出 ValueError，消息包含"类型错误"。"""
        spec = _make_spec_with_invalid_type()
        config = StrategyRunServiceConfig(spec=spec)
        service = _make_service(config=config)
        slice_ = _make_fake_slice()

        with pytest.raises(ValueError, match="类型错误"):
            service.run(TRADE_DATE, slice_)

    def test_param_out_of_range_raises(self) -> None:
        """param 超出范围时抛出 ValueError。"""
        spec = _make_spec_with_out_of_range()
        config = StrategyRunServiceConfig(spec=spec)
        service = _make_service(config=config)
        slice_ = _make_fake_slice()

        with pytest.raises(ValueError, match="最大值"):
            service.run(TRADE_DATE, slice_)

    def test_valid_params_passes(self) -> None:
        """合法参数时正常执行 run()。"""
        spec = _make_spec_valid()
        config = StrategyRunServiceConfig(spec=spec)
        service = _make_service(config=config)
        slice_ = _make_fake_slice()

        result = service.run(TRADE_DATE, slice_)

        assert isinstance(result, StrategyRunResult)
        assert result.target is not None

    def test_no_spec_skips_validation(self) -> None:
        """spec 为 None 时跳过校验，正常执行。"""
        config = StrategyRunServiceConfig()  # spec 默认 None
        service = _make_service(config=config)
        slice_ = _make_fake_slice()

        result = service.run(TRADE_DATE, slice_)

        assert isinstance(result, StrategyRunResult)
