"""Analysis error hierarchy tests."""

from ditto_analysis.errors import AnalysisError, ResearchDatasetError
from ditto_kernel.exceptions import DittoError


def test_analysis_error_hierarchy() -> None:
    assert issubclass(AnalysisError, DittoError)
    assert issubclass(ResearchDatasetError, AnalysisError)


def test_research_dataset_error_carries_details() -> None:
    err = ResearchDatasetError("invalid dataset", dataset_id="research.demo")
    assert err.details == {"dataset_id": "research.demo"}
