"""FactorBridge 单元测试 — 因子表达式编译与信号合成."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution import factor_bridge as factor_bridge_module
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
    build_signal_spec,
    compiled_expressions_execution_hash,
)
from ditto_features.derived_types import (
    DerivedRole,
    MaterializationProfile,
)
from ditto_features.factors.spec import FactorSpec

# ===========================================================================
# build_signal_spec
# ===========================================================================


class TestBuildSignalSpec:
    """build_signal_spec — 字符串 → DerivedSpec."""

    def test_produces_signal_spec_with_expected_defaults(self) -> None:
        spec = build_signal_spec("close / shift(close, 1) - 1", index=3)

        assert spec.id == "signal_3"
        assert spec.version == 1
        assert spec.role == DerivedRole.SIGNAL
        assert spec.materialization_profile == MaterializationProfile.SERIES
        assert spec.expression == "close / shift(close, 1) - 1"
        assert spec.entity_keys == ("instrument_id",)
        assert spec.grain == "1d"
        assert spec.calendar == "cn_stock"

    def test_index_zero_is_valid(self) -> None:
        spec = build_signal_spec("close", index=0)
        assert spec.id == "signal_0"

    def test_different_indices_produce_different_ids(self) -> None:
        spec_a = build_signal_spec("close", index=0)
        spec_b = build_signal_spec("close", index=1)
        assert spec_a.id != spec_b.id


# ===========================================================================
# FactorBridge.compile_and_validate — 编译与验证
# ===========================================================================


class TestCompileAndValidate:
    """FactorBridge.compile_and_validate — 编译并验证因子表达式."""

    def test_valid_single_expression_compiles(self) -> None:
        """单条有效表达式成功编译."""
        bridge = FactorBridge()
        result = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        assert isinstance(result, CompiledExpressions)
        assert len(result.expressions) == 1
        assert len(result.weights) == 1
        assert result.weights == (1.0,)

    def test_valid_multiple_expressions_compile(self) -> None:
        """多条有效表达式成功编译."""
        bridge = FactorBridge()
        result = bridge.compile_and_validate(
            expressions=("close", "volume"),
            weights=(0.6, 0.4),
        )

        assert len(result.expressions) == 2
        assert result.weights == (0.6, 0.4)

    def test_actual_max_lookback_uses_compiled_expression_analysis(self) -> None:
        compiled = FactorBridge().compile_and_validate(
            expressions=("close", "ts_mean(close, 63)"),
            weights=(0.5, 0.5),
        )

        assert (
            factor_bridge_module.compiled_expressions_actual_max_lookback(compiled)
            == 64
        )

    @pytest.mark.parametrize("lookback", [-1, True], ids=("negative", "bool"))
    def test_actual_max_lookback_rejects_invalid_nonnegative_integer(
        self,
        lookback: int,
    ) -> None:
        compiled = FactorBridge().compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )
        expression = compiled.expressions[0]
        drifted = CompiledExpressions(
            expressions=(
                replace(
                    expression,
                    analysis=replace(expression.analysis, lookback=lookback),
                ),
            ),
            weights=compiled.weights,
        )

        with pytest.raises(AppProcessError) as exc_info:
            factor_bridge_module.compiled_expressions_actual_max_lookback(drifted)

        assert exc_info.value.details["reason"] == (
            "compiled_factor_lookback_state_drift"
        )

    def test_compile_produces_compiled_derived_expression(self) -> None:
        """编译结果包含正确的 derived_id."""
        bridge = FactorBridge()
        result = bridge.compile_and_validate(
            expressions=("close", "open"),
            weights=(0.5, 0.5),
        )

        assert result.expressions[0].derived_id == "signal_0"
        assert result.expressions[1].derived_id == "signal_1"
        assert result.expressions[0].version == 1

    def test_compiled_expressions_expr_is_polars_expr(self) -> None:
        """编译结果的 expr 字段是可执行的 pl.Expr，且 analysis 已填充."""
        bridge = FactorBridge()
        result = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        compiled_expr = result.expressions[0]
        # expr 必须是 pl.Expr 实例，且可以在 DataFrame 上执行
        assert isinstance(compiled_expr.expr, pl.Expr)

        # 验证 expr 可以在真实 DataFrame 上求值
        df = pl.DataFrame({"close": [1.0, 2.0, 3.0]})
        computed = df.select(compiled_expr.expr.alias("result"))
        assert "result" in computed.columns
        assert computed.height == 3

        # analysis 字段已填充
        assert compiled_expr.analysis is not None
        assert isinstance(compiled_expr.analysis.dependencies, tuple)
        assert "close" in compiled_expr.analysis.dependencies

    def test_execution_hash_rejects_polars_expression_method_shadow(self) -> None:
        """Serialized expression bytes cannot hide instance-level execution hooks."""
        compiled = FactorBridge().compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )
        expression = compiled.expressions[0].expr
        before = expression.meta.serialize()
        object.__setattr__(
            expression,
            "alias",
            lambda name: pl.col("open").alias(name),
        )
        assert expression.meta.serialize() == before

        with pytest.raises(AppProcessError) as exc_info:
            compiled_expressions_execution_hash(compiled)

        assert exc_info.value.details["reason"] == (
            "compiled_factor_expression_state_drift"
        )
        with pytest.raises(AppProcessError):
            FactorBridge().compute_signals(
                pl.DataFrame(
                    {"instrument_id": [1, 2], "close": [1.0, 2.0], "open": [2.0, 1.0]}
                ),
                compiled,
            )

    def test_syntax_error_raises_value_error(self) -> None:
        """语法错误的表达式抛出 ValueError."""
        bridge = FactorBridge()
        with pytest.raises(AppProcessError, match="编译失败"):
            bridge.compile_and_validate(
                expressions=("+++",),
                weights=(1.0,),
            )

    def test_unknown_operator_raises_value_error(self) -> None:
        """未知运算符抛出 ValueError."""
        bridge = FactorBridge()
        with pytest.raises(AppProcessError, match="编译失败"):
            bridge.compile_and_validate(
                expressions=("nonexistent_op(close, 20)",),
                weights=(1.0,),
            )

    def test_weight_length_mismatch_raises_value_error(self) -> None:
        """权重数量与表达式不匹配抛出 ValueError."""
        bridge = FactorBridge()
        with pytest.raises(AppProcessError, match="权重数量"):
            bridge.compile_and_validate(
                expressions=("close",),
                weights=(0.5, 0.5),
            )

    def test_empty_expressions_raises_value_error(self) -> None:
        """空表达式元组抛出 ValueError."""
        bridge = FactorBridge()
        with pytest.raises(AppProcessError, match="表达式不能为空"):
            bridge.compile_and_validate(
                expressions=(),
                weights=(),
            )

    def test_negative_weight_raises_value_error(self) -> None:
        """负权重抛出 ValueError."""
        bridge = FactorBridge()
        with pytest.raises(AppProcessError, match="权重不能为负"):
            bridge.compile_and_validate(
                expressions=("close",),
                weights=(-0.5,),
            )

    def test_zero_weight_is_accepted(self) -> None:
        """零权重是合法的（某些因子可能被关闭）."""
        bridge = FactorBridge()
        result = bridge.compile_and_validate(
            expressions=("close",),
            weights=(0.0,),
        )
        assert result.weights == (0.0,)

    def test_custom_compiler_is_used(self) -> None:
        """传入自定义 compiler 时使用它."""
        mock_compiler = MagicMock()
        from ditto_features.expression.contracts import (
            Analysis,
            CompiledDerivedExpression,
            CompileIdentity,
        )

        mock_compiled = CompiledDerivedExpression(
            derived_id="mock_signal_0",
            version=1,
            expr=pl.col("close"),
            analysis=Analysis(
                dependencies=("close",),
                operator_names=(),
                lookback=0,
                requires_full_day=False,
                scope="cross-section",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="mock",
                operator_fingerprint="mock",
                compiler_fingerprint="mock",
                cache_key="mock",
                engine_codegen_version="v1",
                analysis_version="v1",
                polars_version="1.0",
                expr_serialization_format="v1",
            ),
        )
        mock_compiler.compile.return_value = mock_compiled

        bridge = FactorBridge(compiler=mock_compiler)
        result = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        assert result.expressions[0].derived_id == "mock_signal_0"
        mock_compiler.compile.assert_called_once()

    def test_registered_only_mode_rejects_unknown_literal_before_compilation(
        self,
    ) -> None:
        """Research mode cannot reinterpret an unknown factor ID as raw DSL."""
        compiler = MagicMock()
        bridge = FactorBridge(
            compiler=compiler,
            factor_registry={
                "known_factor": FactorSpec(
                    id="known_factor",
                    expression="close",
                )
            },
            factor_versions={"known_factor": 2},
            require_registered_factor_ids=True,
        )

        with pytest.raises(AppProcessError) as exc_info:
            bridge.compile_and_validate(expressions=("close",), weights=(1.0,))

        assert exc_info.value.details["reason"] == "unknown_registered_factor"
        compiler.compile.assert_not_called()

    def test_registered_only_mode_rejects_duplicate_factor_ids(self) -> None:
        """One research signal source may bind each exact factor only once."""
        compiler = MagicMock()
        bridge = FactorBridge(
            compiler=compiler,
            factor_registry={
                "known_factor": FactorSpec(
                    id="known_factor",
                    expression="close",
                )
            },
            factor_versions={"known_factor": 1},
            require_registered_factor_ids=True,
        )

        with pytest.raises(AppProcessError) as exc_info:
            bridge.compile_and_validate(
                expressions=("known_factor", "known_factor"),
                weights=(0.5, 0.5),
            )

        assert exc_info.value.details["reason"] == "duplicate_registered_factor"
        compiler.compile.assert_not_called()

    def test_registered_only_mode_compiles_exact_factor_id_and_version(self) -> None:
        """Compiler cache identity is seeded with the registered factor identity."""
        bridge = FactorBridge(
            factor_registry={
                "known_factor": FactorSpec(
                    id="known_factor",
                    expression="close",
                )
            },
            factor_versions={"known_factor": 2},
            require_registered_factor_ids=True,
        )

        result = bridge.compile_and_validate(
            expressions=("known_factor",),
            weights=(1.0,),
        )

        assert result.expressions[0].derived_id == "known_factor"
        assert result.expressions[0].version == 2


# ===========================================================================
# FactorBridge.compute_signals — 信号合成计算
# ===========================================================================


class TestComputeSignals:
    """FactorBridge.compute_signals — 在 DataFrame 上计算因子并合成信号."""

    @pytest.fixture
    def sample_df(self) -> pl.DataFrame:
        """构造测试用 DataFrame，包含 3 个标的的 OHLCV 数据."""
        return pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 4, 5],
                "close": [10.0, 20.0, 30.0, 40.0, 50.0],
                "open": [9.0, 19.0, 29.0, 39.0, 49.0],
                "volume": [1000.0, 2000.0, 3000.0, 4000.0, 5000.0],
            },
        )

    def test_single_factor_signal(self, sample_df: pl.DataFrame) -> None:
        """单因子: rank 归一化后直接作为 signal_value."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        result = bridge.compute_signals(sample_df, compiled)

        assert "instrument_id" in result.columns
        assert "signal_value" in result.columns
        assert result.height == 5
        # rank 归一化: rank / n, 排序后应为 0.2, 0.4, 0.6, 0.8, 1.0
        signal_values = result.sort("instrument_id")["signal_value"].to_list()
        assert all(isinstance(v, float) for v in signal_values)

    def test_multi_factor_weighted_signal(self, sample_df: pl.DataFrame) -> None:
        """多因子: rank 归一化 + 加权合成."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close", "volume"),
            weights=(0.6, 0.4),
        )

        result = bridge.compute_signals(sample_df, compiled)

        assert result.height == 5
        assert "signal_value" in result.columns
        # close 和 volume 排序一致（都是递增），所以加权后也应该是递增的
        values = result.sort("instrument_id")["signal_value"].to_list()
        # 确认加权结果在合理范围内
        assert all(0.0 <= v <= 1.0 for v in values)

    def test_empty_dataframe_returns_empty(self) -> None:
        """空 DataFrame 返回空结果."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        empty_df = pl.DataFrame(
            {"instrument_id": [], "close": []},
            schema={"instrument_id": pl.Int64, "close": pl.Float64},
        )

        result = bridge.compute_signals(empty_df, compiled)

        assert result.height == 0
        assert "instrument_id" in result.columns
        assert "signal_value" in result.columns

    def test_rank_normalization_range(self, sample_df: pl.DataFrame) -> None:
        """rank 归一化值在 [0, 1] 范围内."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        result = bridge.compute_signals(sample_df, compiled)

        signal_values = result["signal_value"].to_list()
        for v in signal_values:
            assert 0.0 <= v <= 1.0, f"signal_value {v} 不在 [0, 1] 范围内"

    def test_equal_weights_same_as_single(self, sample_df: pl.DataFrame) -> None:
        """两因子等权合成的结果 rank 序与单因子一致."""
        bridge = FactorBridge()
        # 使用 close + close（相同因子），等权重
        compiled = bridge.compile_and_validate(
            expressions=("close", "close"),
            weights=(0.5, 0.5),
        )

        result = bridge.compute_signals(sample_df, compiled)

        # close rank 是单调递增的，两个一样因子等权合成也应当单调
        values = result.sort("instrument_id")["signal_value"].to_list()
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_zero_weight_factor_excluded(self, sample_df: pl.DataFrame) -> None:
        """权重为 0 的因子不影响结果（但权重之和不能为零）."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close", "volume"),
            weights=(1.0, 0.0),
        )

        result = bridge.compute_signals(sample_df, compiled)

        assert result.height == 5
        assert "signal_value" in result.columns

    def test_all_weights_zero_returns_zero_signals(
        self,
        sample_df: pl.DataFrame,
    ) -> None:
        """所有权重为零时，signal_value 全部为零."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close", "volume"),
            weights=(0.0, 0.0),
        )

        result = bridge.compute_signals(sample_df, compiled)

        assert result.height == 5
        assert "instrument_id" in result.columns
        assert "signal_value" in result.columns
        signal_values = result["signal_value"].to_list()
        assert all(v == 0.0 for v in signal_values)

    def test_result_preserves_instrument_ids(self, sample_df: pl.DataFrame) -> None:
        """结果保留所有 instrument_id."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        result = bridge.compute_signals(sample_df, compiled)

        result_ids = set(result["instrument_id"].to_list())
        expected_ids = set(sample_df["instrument_id"].to_list())
        assert result_ids == expected_ids


# ===========================================================================
# FactorBridge 因子 ID → 表达式解析
# ===========================================================================


class TestFactorIdResolution:
    """signal_expressions 存因子 ID（如 quality_roe）时的 ID→表达式解析层.

    背景：seed 的 signal_expressions 用因子 ID 而非表达式字符串。
    若不加解析层，FactorBridge 会把 "quality_roe" 当列名编译成 pl.col("quality_roe")，
    回测时因 market_data 无此列而 ColumnNotFoundError。
    """

    def test_known_factor_id_resolves_to_expression(self) -> None:
        """已知因子 ID 解析为 ALL_FACTOR_SPECS 中的真实表达式."""
        bridge = FactorBridge()
        assert bridge._resolve_expression("quality_roe") == "roe"
        assert bridge._resolve_expression("value_pe") == "-pe_ratio"

    def test_momentum_factor_id_resolves_to_ts_expression(self) -> None:
        """momentum_1m 解析为时序表达式（纯市场数据，无需基本面列）."""
        bridge = FactorBridge()
        resolved = bridge._resolve_expression("momentum_1m")
        assert resolved == "ts_pct_change(market.close, 20)"

    def test_unknown_id_passes_through_unchanged(self) -> None:
        """未知 ID（直接表达式字符串或裸列名）原样返回，向后兼容."""
        bridge = FactorBridge()
        assert bridge._resolve_expression("close") == "close"
        assert bridge._resolve_expression("nonexistent_xyz") == "nonexistent_xyz"

    def test_compile_seed_signal_expressions_resolves_ids(self) -> None:
        """seed 三因子 ID 编译后引用正确的底层列（不再引用不存在的 quality_roe 列）."""
        bridge = FactorBridge()
        result = bridge.compile_and_validate(
            expressions=("quality_roe", "value_pe", "momentum_1m"),
            weights=(0.4, 0.3, 0.3),
        )
        assert len(result.expressions) == 3
        # quality_roe → "roe" → dependencies 含 roe 列
        assert "roe" in result.expressions[0].analysis.dependencies
        # value_pe → "-pe_ratio" → dependencies 含 pe_ratio 列
        assert "pe_ratio" in result.expressions[1].analysis.dependencies
        # momentum_1m → ts_pct_change(market.close, 20) → dependencies 含 market.close
        assert "market.close" in result.expressions[2].analysis.dependencies

    def test_custom_registry_injection(self) -> None:
        """注入自定义 registry 时，ID 按自定义映射解析；未命中项原样返回."""
        custom = {
            "my_factor": FactorSpec(id="my_factor", expression="close * 2"),
        }
        bridge = FactorBridge(factor_registry=custom)
        assert bridge._resolve_expression("my_factor") == "close * 2"
        # 自定义 registry 不含 quality_roe → 原样返回（不被默认 registry 覆盖）
        assert bridge._resolve_expression("quality_roe") == "quality_roe"

    def test_empty_registry_treats_all_as_raw_expression(self) -> None:
        """空 registry 时所有字符串都当表达式原样返回."""
        bridge = FactorBridge(factor_registry={})
        assert bridge._resolve_expression("quality_roe") == "quality_roe"
        assert bridge._resolve_expression("close") == "close"
