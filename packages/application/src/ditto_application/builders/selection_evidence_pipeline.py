"""Small construction seam for lane-attested selection-evidence pipelines."""

from collections.abc import Sequence

from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.selection_evidence import (
    SelectionEvidenceSink,
    SelectionExposurePolicy,
)
from ditto_strategy.alpha.specs import StrategyKind

__all__ = ["build_selection_evidence_pipeline"]


def build_selection_evidence_pipeline(
    stages: Sequence[DecisionStage],
    *,
    evidence_sink: SelectionEvidenceSink | None,
    strategy_kind: StrategyKind,
) -> StrategyPipeline:
    """Bind the frozen strategy lane to its exposure-evidence policy."""
    exposure_policy = None
    if evidence_sink is not None:
        exposure_policy = (
            SelectionExposurePolicy.stock()
            if strategy_kind is StrategyKind.STOCK_SELECTION
            else SelectionExposurePolicy.etf()
        )
    return StrategyPipeline(
        stages,
        evidence_sink=evidence_sink,
        exposure_policy=exposure_policy,
    )
