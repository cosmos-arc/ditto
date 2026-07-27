"""Closed-graph validation for one research selection-evidence collector."""

from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceCollector

from ditto_application.exceptions import AppProcessError

__all__ = ["require_pristine_selection_evidence_graph"]


def _error(reason: str) -> AppProcessError:
    return AppProcessError(
        "frozen research backtest construction failed",
        details={"code": "REPRODUCIBILITY_FAILED", "reason": reason},
    )


def require_pristine_selection_evidence_graph(
    *,
    pipeline: StrategyPipeline,
    collector: SelectionEvidenceCollector,
    stages: object,
) -> None:
    """Reject substituted, active, pending, indexed, or committed evidence state."""
    if (
        type(collector) is not SelectionEvidenceCollector
        or type(stages) is not tuple
        or vars(pipeline).get("_evidence_sink") is not collector
    ):
        raise _error("constructed_strategy_pipeline_state_drift")
    if not collector.is_pristine:
        raise _error("selection_evidence_collector_not_pristine")
