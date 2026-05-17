"""
Ditto Analysis public API.

Root barrel 只重导出 AnalysisError、ResearchDatasetError、ResearchDatasetSpec.
研究 control-plane 其余模型（DatasetSnapshot, SpineSnapshot, SpineSpec）
请通过 ditto_analysis.research 直接引用。
"""

from ditto_analysis.errors import AnalysisError, ResearchDatasetError
from ditto_analysis.research.domain import ResearchDatasetSpec

__all__ = [
    "AnalysisError",
    "ResearchDatasetError",
    "ResearchDatasetSpec",
]
