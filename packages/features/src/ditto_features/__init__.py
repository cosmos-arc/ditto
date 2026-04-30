"""
Ditto Features — 因子表达式编译、物化计划、因子计算、因子评估.

子包导出各自完整的公共 API，此模块仅提供最常用的便利入口。
"""

from ditto_features.expression import CompiledDerivedExpression, ExpressionCompiler
from ditto_features.factors import FactorContext, FactorSpec
from ditto_features.materialization import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
)
from ditto_features.validation import validate_derived_spec

__version__ = "0.1.0"

__all__ = [
    "CompiledDerivedExpression",
    "DerivedExecutionPlan",
    "DerivedMaterializationRequest",
    "DerivedMaterializationResult",
    "ExpressionCompiler",
    "FactorContext",
    "FactorSpec",
    "validate_derived_spec",
]
