"""Tests for FrameCol constants and validate_frame schema protection.

AAA 测试模式：Arrange → Act → Assert。
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.frame import FrameCol, validate_frame

# ---------------------------------------------------------------------------
# FrameCol 常量
# ---------------------------------------------------------------------------


class TestFrameCol:
    """FrameCol 列名常量定义验证。"""

    def test_instrument_id_constant(self) -> None:
        """INSTRUMENT_ID 应为 'instrument_id'。"""
        assert FrameCol.INSTRUMENT_ID == "instrument_id"

    def test_signal_constant(self) -> None:
        """SIGNAL 应为 'signal_value'。"""
        assert FrameCol.SIGNAL == "signal_value"

    def test_score_constant(self) -> None:
        """SCORE 应为 'score'。"""
        assert FrameCol.SCORE == "score"

    def test_weight_constant(self) -> None:
        """WEIGHT 应为 'weight'。"""
        assert FrameCol.WEIGHT == "weight"

    def test_regime_constant(self) -> None:
        """REGIME 应为 'regime'。"""
        assert FrameCol.REGIME == "regime"

    def test_reason_codes_constant(self) -> None:
        """REASON_CODES 应为 'reason_codes'。"""
        assert FrameCol.REASON_CODES == "reason_codes"

    def test_all_constants_are_strings(self) -> None:
        """所有常量值应为 str 类型。"""
        for attr_name in dir(FrameCol):
            if attr_name.startswith("_"):
                continue
            value = getattr(FrameCol, attr_name)
            assert isinstance(value, str), (
                f"FrameCol.{attr_name} expected str, got {type(value)}"
            )


# ---------------------------------------------------------------------------
# validate_frame — debug 模式
# ---------------------------------------------------------------------------


class TestValidateFrameDebug:
    """validate_frame 在 debug 模式下的行为。"""

    def test_valid_frame_passes(self) -> None:
        """包含所有必需列的 frame 不应抛出异常。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "signal_value": [0.5, 0.6],
            },
        )
        # 不应抛出异常
        validate_frame(frame, (FrameCol.INSTRUMENT_ID, FrameCol.SIGNAL))

    def test_empty_required_passes(self) -> None:
        """required 为空元组时，任何 frame 都应通过。"""
        frame = pl.DataFrame({"x": [1]})
        validate_frame(frame, ())

    def test_missing_columns_raises_assertion(self) -> None:
        """缺少必需列时应抛出 ValueError。"""
        frame = pl.DataFrame({"x": [1]})
        with pytest.raises(
            ValueError,
            match="DecisionFrame missing required columns",
        ):
            validate_frame(frame, (FrameCol.INSTRUMENT_ID,))

    def test_missing_some_columns_reports_all(self) -> None:
        """缺少多列时，错误信息应包含所有缺失列。"""
        frame = pl.DataFrame({"x": [1]})
        with pytest.raises(ValueError, match="signal_value") as exc_info:
            validate_frame(frame, (FrameCol.INSTRUMENT_ID, FrameCol.SIGNAL))
        assert "instrument_id" in str(exc_info.value)

    def test_extra_columns_pass(self) -> None:
        """额外列不影响校验通过。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "signal_value": [0.5],
                "extra_col": [42],
            },
        )
        validate_frame(frame, (FrameCol.INSTRUMENT_ID, FrameCol.SIGNAL))

    def test_empty_frame_with_required_columns_passes(self) -> None:
        """空 frame 但包含必需列（schema 正确）时应通过。"""
        frame = pl.DataFrame(
            {"instrument_id": []},
            schema={"instrument_id": pl.Int64},
        )
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))


# ---------------------------------------------------------------------------
# validate_frame — 按阶段验证
# ---------------------------------------------------------------------------


class TestValidateFramePerStage:
    """验证各 Pipeline 阶段的输出 frame 通过校验。"""

    def test_universe_stage_output(self) -> None:
        """UniverseStage 输出应包含 instrument_id。"""
        from ditto_engine.alpha.builtins import UniverseStage

        frame = pl.DataFrame({"instrument_id": [1, 2, 3]})
        ctx = StrategyContext()
        stage = UniverseStage(instrument_ids=frozenset({1, 2}))
        result = stage.process(frame, ctx)
        validate_frame(result, (FrameCol.INSTRUMENT_ID,))

    def test_signal_stage_output(self) -> None:
        """SignalStage 输出应包含 instrument_id + signal_value。"""
        from ditto_engine.alpha.builtins import SignalStage

        frame = pl.DataFrame({"instrument_id": [1, 2]})
        ctx = StrategyContext()
        stage = SignalStage(signal_column="signal_value", source_column=None)
        result = stage.process(frame, ctx)
        validate_frame(result, (FrameCol.INSTRUMENT_ID, FrameCol.SIGNAL))

    def test_scoring_stage_output(self) -> None:
        """ScoringStage 输出应包含 instrument_id + score。"""
        from ditto_engine.alpha.builtins import ScoringStage

        frame = pl.DataFrame(
            {"instrument_id": [1, 2], "signal_value": [0.5, 0.6]},
        )
        ctx = StrategyContext()
        stage = ScoringStage(output_column="score")
        result = stage.process(frame, ctx)
        validate_frame(result, (FrameCol.INSTRUMENT_ID, FrameCol.SCORE))

    def test_selection_stage_output(self) -> None:
        """SelectionStage 输出应包含 instrument_id + score。"""
        from ditto_engine.alpha.builtins import SelectionStage

        frame = pl.DataFrame(
            {"instrument_id": [1, 2, 3], "score": [0.9, 0.5, 0.3]},
        )
        ctx = StrategyContext()
        stage = SelectionStage(top_k=2, score_column="score")
        result = stage.process(frame, ctx)
        validate_frame(result, (FrameCol.INSTRUMENT_ID, FrameCol.SCORE))


# ---------------------------------------------------------------------------
# validate_frame — release 模式模拟
# ---------------------------------------------------------------------------


class TestValidateFrameReleaseMode:
    """验证 validate_frame 的 release 模式设计。"""

    def test_function_uses_debug_guard(self) -> None:
        """
        验证 validate_frame 使用 ValueError 进行帧验证。

        validate_frame 通过 raise ValueError 报告缺失列，
        替代原来的 assert + __debug__ 守卫方案，确保在所有模式下都有效。
        """
        import inspect

        source = inspect.getsource(validate_frame)
        assert "ValueError" in source, "validate_frame 应使用 ValueError 报告缺失列"

    def test_debug_mode_raises_on_missing(self) -> None:
        """缺少列时应抛出 ValueError。"""
        frame = pl.DataFrame({"x": [1]})
        with pytest.raises(
            ValueError,
            match="DecisionFrame missing required columns",
        ):
            validate_frame(frame, (FrameCol.INSTRUMENT_ID,))

    def test_validate_frame_is_callable(self) -> None:
        """validate_frame 应可正常调用。"""
        frame = pl.DataFrame({"instrument_id": [1]})
        result = validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        assert result is None
