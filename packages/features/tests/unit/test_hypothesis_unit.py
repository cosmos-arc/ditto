"""Hypothesis → Expression 桥接点单元测试。"""

from __future__ import annotations

import dataclasses

import pytest
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression import ExpressionCompiler
from ditto_features.expression.hypothesis import Hypothesis, hypothesis_to_expression


class TestHypothesisCreation:
    """Hypothesis dataclass 创建与字段验证。"""

    def test_hypothesis_creation(self) -> None:
        """创建 Hypothesis 实例，验证字段正确赋值。"""
        meta = {"source": "gpt-5", "confidence": "0.85"}
        h = Hypothesis(
            natural_language="高动量+低波动率的ETF表现更好",
            expression_draft="ts_momentum(close, 20) / ts_std(close, 20)",
            metadata=meta,
        )
        assert h.natural_language == "高动量+低波动率的ETF表现更好"
        assert h.expression_draft == "ts_momentum(close, 20) / ts_std(close, 20)"
        assert h.metadata == meta

    def test_hypothesis_frozen(self) -> None:
        """验证 frozen dataclass 修改属性抛出 FrozenInstanceError。"""
        h = Hypothesis(
            natural_language="test",
            expression_draft="close",
            metadata={},
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.natural_language = "changed"  # type: ignore[misc]

    def test_hypothesis_metadata_default(self) -> None:
        """metadata 默认为空 dict。"""
        h = Hypothesis(
            natural_language="test",
            expression_draft="close",
        )
        assert h.metadata == {}


class TestHypothesisToExpression:
    """hypothesis_to_expression 占位实现验证。"""

    def test_returns_expression_draft(self) -> None:
        """占位实现直接透传 expression_draft。"""
        h = Hypothesis(
            natural_language="收盘价本身",
            expression_draft="close",
            metadata={},
        )
        assert hypothesis_to_expression(h) == "close"

    def test_returns_complex_draft(self) -> None:
        """复杂表达式透传。"""
        draft = "ts_momentum(close, 20) / ts_std(close, 20)"
        h = Hypothesis(
            natural_language="高动量+低波动率",
            expression_draft=draft,
            metadata={},
        )
        assert hypothesis_to_expression(h) == draft

    def test_output_compilable_by_expression_compiler(self) -> None:
        """hypothesis_to_expression 的输出可被 ExpressionCompiler 编译。"""
        h = Hypothesis(
            natural_language="收盘价",
            expression_draft="close",
            metadata={"source": "unit-test"},
        )
        expr_str = hypothesis_to_expression(h)
        spec = DerivedSpec(
            id="hypothesis_test_close",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression=expr_str,
        )
        compiler = ExpressionCompiler()
        result = compiler.compile(spec)
        assert result.derived_id == "hypothesis_test_close"
        assert result.version == 1
        assert result.expr is not None
