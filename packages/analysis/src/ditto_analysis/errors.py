"""Analysis — 研究分析错误定义。"""

from ditto_kernel.exceptions import DittoError

__all__ = ["AnalysisError", "ResearchDatasetError"]


class AnalysisError(DittoError):
    """分析层基础错误。"""


class ResearchDatasetError(AnalysisError):
    """研究数据集操作错误。"""
