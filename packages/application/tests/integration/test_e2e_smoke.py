"""
端到端冒烟测试 — FactorBridge + BacktestRunHandler 集成.

验证从数据查询→因子编译→信号计算→命令触发的完整流程。
"""

from __future__ import annotations

from unittest.mock import Mock

import polars as pl
import pytest
from ditto_application.command.backtest import BacktestRunCommand, BacktestRunHandler
from ditto_application.process.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
    build_signal_spec,
)
from ditto_application.process.execution.strategy_types import RunLifecycleService
from ditto_data.services.strategy.strategy_catalog_service import StrategyCatalogService
from ditto_features.expression.compiler import ExpressionCompiler

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def factor_bridge() -> FactorBridge:
    """FactorBridge with real ExpressionCompiler."""
    return FactorBridge(compiler=ExpressionCompiler())


@pytest.fixture
def mock_catalog_service() -> Mock:
    """Mock StrategyCatalogService with a published strategy."""
    service = Mock(spec=StrategyCatalogService)
    record = Mock()
    record.spec_json = {
        "signal_expressions": ["ts_mean(close, 5)", "ts_std(close, 10)"],
        "signal_weights": [0.6, 0.4],
    }
    service.get_spec.return_value = record
    return service


@pytest.fixture
def mock_run_service() -> Mock:
    """Mock RunLifecycleService."""
    service = Mock(spec=RunLifecycleService)
    service.create_run.return_value = None
    return service


@pytest.fixture
def handler(
    mock_catalog_service: Mock,
    mock_run_service: Mock,
    factor_bridge: FactorBridge,
) -> BacktestRunHandler:
    """BacktestRunHandler with real FactorBridge."""
    return BacktestRunHandler(
        catalog_service=mock_catalog_service,
        run_service=mock_run_service,
        factor_bridge=factor_bridge,
    )


# ---------------------------------------------------------------------------
# FactorBridge 端到端
# ---------------------------------------------------------------------------


class TestFactorBridgeEndToEnd:
    """验证 FactorBridge 从表达式字符串到 signal_value 的完整流程."""

    def test_compile_and_compute_roundtrip(self, factor_bridge: FactorBridge) -> None:
        """表达式字符串 → 编译 → DataFrame 计算 → signal_value 列."""
        expressions = ("ts_mean(close, 5)",)
        weights = (1.0,)

        compiled = factor_bridge.compile_and_validate(expressions, weights)
        assert isinstance(compiled, CompiledExpressions)
        assert len(compiled.expressions) == 1

        # 构造测试 DataFrame
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 4, 5],
                "close": [10.0, 11.0, 12.0, 13.0, 14.0],
            },
        )

        result = factor_bridge.compute_signals(df, compiled)
        assert "instrument_id" in result.columns
        assert "signal_value" in result.columns
        assert result.height == 5

    def test_multi_factor_weighted_combination(
        self, factor_bridge: FactorBridge
    ) -> None:
        """多因子加权合成 signal_value — 使用简单列表达式."""
        expressions = ("close", "volume")
        weights = (0.7, 0.3)

        compiled = factor_bridge.compile_and_validate(expressions, weights)
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "close": [10.0, 20.0, 30.0],
                "volume": [1000.0, 2000.0, 3000.0],
            },
        )

        result = factor_bridge.compute_signals(df, compiled)
        signal_values = result["signal_value"].to_list()
        assert all(v is not None for v in signal_values)
        assert all(isinstance(v, float) for v in signal_values)

    def test_build_signal_spec_produces_valid_spec(self) -> None:
        """build_signal_spec 产生有效的 DerivedSpec."""
        spec = build_signal_spec("ts_mean(close, 20)", index=0)
        assert spec.id == "signal_0"
        assert spec.expression == "ts_mean(close, 20)"
        assert spec.role.value == "signal"


# ---------------------------------------------------------------------------
# BacktestRunHandler 端到端
# ---------------------------------------------------------------------------


class TestBacktestRunHandlerEndToEnd:
    """验证 BacktestRunHandler 完整编排: 校验→预编译→创建记录."""

    def test_full_handler_flow(self, handler: BacktestRunHandler) -> None:
        """成功触发: 校验→因子预编译→创建 RunRecord."""
        command = BacktestRunCommand(
            strategy_id="momentum-etf",
            start_date="2025-01-01",
            end_date="2025-03-31",
            initial_cash=1_000_000.0,
        )

        result = handler.handle(command)

        assert result.run_id  # non-empty
        assert result.strategy_id == "momentum-etf"
        assert result.status == "pending"

    def test_handler_pre_compiles_factors(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
    ) -> None:
        """Handler 预编译策略中的因子表达式."""
        command = BacktestRunCommand(
            strategy_id="momentum-etf",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        handler.handle(command)

        # 验证 get_spec 被调用
        mock_catalog_service.get_spec.assert_called_once_with("momentum-etf")

    def test_handler_with_factor_bridge_integration(
        self,
        mock_catalog_service: Mock,
        mock_run_service: Mock,
    ) -> None:
        """FactorBridge 集成: 编译策略表达式并产生 CompiledExpressions."""
        factor_bridge = FactorBridge(compiler=ExpressionCompiler())
        handler = BacktestRunHandler(
            catalog_service=mock_catalog_service,
            run_service=mock_run_service,
            factor_bridge=factor_bridge,
        )

        command = BacktestRunCommand(
            strategy_id="test-strategy",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        result = handler.handle(command)
        assert result.status == "pending"
        assert result.strategy_id == "test-strategy"

    def test_handler_rejects_invalid_strategy(
        self,
        mock_catalog_service: Mock,
        mock_run_service: Mock,
        factor_bridge: FactorBridge,
    ) -> None:
        """策略不存在时 ValueError."""
        mock_catalog_service.get_spec.return_value = None
        handler = BacktestRunHandler(
            catalog_service=mock_catalog_service,
            run_service=mock_run_service,
            factor_bridge=factor_bridge,
        )

        command = BacktestRunCommand(
            strategy_id="nonexistent",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        with pytest.raises(ValueError, match="Strategy not found"):
            handler.handle(command)


# ---------------------------------------------------------------------------
# Pipeline 组件装配验证
# ---------------------------------------------------------------------------


class TestPipelineAssembly:
    """验证 Engine 层 Pipeline 组件可正确装配."""

    def test_regime_score_engine_assembly(self) -> None:
        """RegimeScoreEngine 可正确创建和计算."""
        from ditto_strategy.alpha.builtins.regime import (
            RegimeConfig,
            RegimeScoreEngine,
        )

        class SimpleIndicator:
            """测试用 Indicator — 固定返回 0.7."""

            name: str = "test"
            weight: float = 1.0

            def compute(self, frame: pl.DataFrame) -> float:
                return 0.7

        config = RegimeConfig(
            indicators=(SimpleIndicator(),),
            bull_threshold=0.6,
            bear_threshold=0.4,
        )
        engine = RegimeScoreEngine(config)

        df = pl.DataFrame({"close": [10.0, 11.0, 12.0]})
        result = engine.score(df)

        assert 0.0 <= result.score <= 100.0
        assert result.label == "bull"
        assert len(result.indicator_values) == 1

    def test_factor_bridge_produces_signal_value_column(self) -> None:
        """FactorBridge 最终产出 instrument_id + signal_value 两列."""
        bridge = FactorBridge(compiler=ExpressionCompiler())
        compiled = bridge.compile_and_validate(
            ("ts_mean(close, 3)",),
            (1.0,),
        )

        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "close": [10.0, 20.0, 30.0],
            },
        )

        result = bridge.compute_signals(df, compiled)
        assert set(result.columns) == {"instrument_id", "signal_value"}
        assert result.height == 3
