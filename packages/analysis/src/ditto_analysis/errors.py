"""Analysis — 研究分析错误定义。"""

from ditto_kernel.exceptions import DittoError

__all__ = [
    "AnalysisError",
    "ExperimentIdentityError",
    "ExperimentSpecError",
    "ExperimentStateTransitionError",
    "ResearchDatasetError",
]


class AnalysisError(DittoError):
    """分析层基础错误。"""


class ResearchDatasetError(AnalysisError):
    """研究数据集操作错误。"""


class ExperimentIdentityError(AnalysisError):
    """Experiment control-plane identity is absent or malformed."""


class ExperimentSpecError(AnalysisError):
    """An immutable experiment domain specification is invalid."""


class ExperimentStateTransitionError(AnalysisError):
    """An observed experiment status transition is unknown or illegal."""
