"""
Ditto Analytics — 因子表达式编译、物化计划、因子计算、因子评估、研究数据集.

子包导出各自完整的公共 API，此模块仅提供最常用的便利入口。
完整 API 请直接导入子包：
    ``ditto_analytics.expression``,
    ``ditto_analytics.materialization`` 等。
"""

from ditto_analytics.expression import CompiledDerivedExpression, ExpressionCompiler
from ditto_analytics.factors import FactorContext, FactorSpec
from ditto_analytics.materialization import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
    DerivedMaterializationResult,
)
from ditto_analytics.research import ResearchDatasetSpec
from ditto_analytics.validation import validate_derived_spec

__version__ = "0.1.0"

__all__ = [
    "CompiledDerivedExpression",
    "DerivedExecutionPlan",
    "DerivedMaterializationRequest",
    "DerivedMaterializationResult",
    "ExpressionCompiler",
    "FactorContext",
    "FactorSpec",
    "ResearchDatasetSpec",
    "validate_derived_spec",
]
