"""
The one registered prediction-scored selection pipeline (#565 W3).

Lives in the processes package so the wiring verifier can rebuild and pin
the exact stage shape without importing the builders package (the
application package must stay acyclic: builders may import processes,
never the reverse).
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_strategy.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.pipeline import DecisionStage, StrategyPipeline
from ditto_strategy.alpha.selection_evidence import (
    SelectionEvidenceSink,
    SelectionExposurePolicy,
)

from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.experiments._execution_bundle_inputs import (
    PREDICTION_EXECUTOR_IMPLEMENTATION_KEY,
    PredictionExecutorBinding,
)

__all__ = ["build_frozen_prediction_pipeline"]


@dataclass(frozen=True)
class _NullScoreFilterStage:
    """
    Drop unscored instruments before selection (#565 W3).

    A null ``score`` after raw scoring means the frozen model emitted no
    score for that instrument this session. The prediction executor has no
    frozen imputation policy for missing scores, so such instruments carry
    no signal and must not ride into top-k selection on identity ordering.
    """

    score_column: str = "score"

    def process(
        self,
        frame: pl.DataFrame,
        context: object,
    ) -> pl.DataFrame:
        _ = context
        return frame.filter(pl.col(self.score_column).is_not_null())


def build_frozen_prediction_pipeline(
    binding: PredictionExecutorBinding,
    *,
    evidence_sink: SelectionEvidenceSink | None = None,
) -> StrategyPipeline:
    """
    Build the one registered prediction-scored selection pipeline (#565 W3).

    The strategy layer consumes the frozen model scores as its precomputed
    ``signal_value`` column: raw pass-through scoring (descending — higher
    prediction ranks first), null-score instruments dropped (no frozen
    imputation policy exists for missing model scores), top-k selection,
    and the pipeline's equal-weight fallback for allocation. No factor
    evaluation, no catalog lookup, and no analysis import — the score's
    provenance lives entirely in the frozen binding and its
    content-addressed predictions input.
    """
    if type(binding) is not PredictionExecutorBinding:
        raise AppBuilderError(
            "frozen prediction execution binding is unsupported or drifted",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "prediction_execution_binding_drift",
            },
        )
    if (
        binding.implementation_key != PREDICTION_EXECUTOR_IMPLEMENTATION_KEY
        or binding.executor_contract_version != 1
    ):
        raise AppBuilderError(
            "frozen prediction execution binding is unsupported or drifted",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "prediction_execution_binding_drift",
            },
        )
    stages: tuple[DecisionStage, ...] = (
        SignalStage(source_column="signal_value"),
        ScoringStage(
            method=ScoringMethod.RAW,
            ascending=False,
            factor_bindings=(),
            evidence_sink=evidence_sink,
        ),
        _NullScoreFilterStage(),
        SelectionStage(top_k=binding.top_k, evidence_sink=evidence_sink),
    )
    return StrategyPipeline(
        stages,
        evidence_sink=evidence_sink,
        exposure_policy=SelectionExposurePolicy.stock(),
    )
