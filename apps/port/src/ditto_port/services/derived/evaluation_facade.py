"""Port-layer factor evaluation facade."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_core.engine.evaluation.evaluator import (
    EvaluationConfig,
    FactorEvaluator,
)
from ditto_core.engine.evaluation.report import FactorEvaluationReport
from ditto_datahub.services.derived import DerivedArtifactReader
from ditto_datahub.services.forward_return_service import ForwardReturnService

__all__ = ["EvaluationOptions", "FactorEvaluationFacade"]


@dataclass(frozen=True)
class EvaluationOptions:
    """
    Evaluation configuration parameters.

    Attributes:
        start: Evaluation start date (``YYYY-MM-DD``).  When ``None``
            the earliest date in the artifact is used.
        end: Evaluation end date (``YYYY-MM-DD``).  When ``None``
            the latest date in the artifact is used.
        holding_period: Forward-return holding period in trading days.
        n_quantiles: Number of quantile groups.
        asset_class: ``"stock"`` or ``"etf"``.
        adj: Adjustment type (``"none"``, ``"qfq"``, ``"hfq"``).

    """

    start: str | None = None
    end: str | None = None
    holding_period: int = 5
    n_quantiles: int = 5
    asset_class: str = "stock"
    adj: str = "none"


_DEFAULT_OPTIONS = EvaluationOptions()


class FactorEvaluationFacade:
    """
    Port-layer entry point for factor evaluation.

    Coordinates artifact loading via :class:`DerivedArtifactReader`,
    forward-return computation via :class:`ForwardReturnService`, and
    metric aggregation via :class:`FactorEvaluator`.
    """

    def __init__(
        self,
        *,
        artifact_reader: DerivedArtifactReader,
        forward_return_service: ForwardReturnService,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._forward_return_service = forward_return_service

    def evaluate(
        self,
        factor_id: str,
        version: int,
        *,
        options: EvaluationOptions = _DEFAULT_OPTIONS,
    ) -> FactorEvaluationReport:
        """
        Evaluate a single factor and return a complete report.

        Args:
            factor_id: Derived artifact identifier.
            version: Artifact version to evaluate.
            options: Evaluation configuration.  When omitted, sensible
                defaults are used.

        Returns:
            A :class:`FactorEvaluationReport` with ``factor_id`` and
            ``factor_version`` set from the request parameters.

        """
        factor_df = self._artifact_reader.read_frame(
            derived_id=factor_id,
            version=version,
            start=options.start,
            end=options.end,
        )

        evaluator = FactorEvaluator(
            forward_return_provider=self._forward_return_service,
        )
        config = EvaluationConfig(
            asset_class=options.asset_class,
            adj=options.adj,
            holding_period=options.holding_period,
            n_quantiles=options.n_quantiles,
        )
        report = evaluator.evaluate(
            factor_df,
            config=config,
            start=options.start,
            end=options.end,
        )

        # The evaluator defaults to factor_id="unknown".  Stamp the
        # actual identity so callers can trace the result.
        return FactorEvaluationReport(
            factor_id=factor_id,
            factor_version=version,
            evaluation_period=report.evaluation_period,
            holding_period=report.holding_period,
            n_quantiles=report.n_quantiles,
            rank_ic_summary=report.rank_ic_summary,
            pearson_ic_summary=report.pearson_ic_summary,
            ic_decay=report.ic_decay,
            ic_half_life=report.ic_half_life,
            ic_autocorrelation=report.ic_autocorrelation,
            quantile_annual_returns=report.quantile_annual_returns,
            long_short=report.long_short,
            avg_turnover=report.avg_turnover,
            net_return_after_cost=report.net_return_after_cost,
            turnover_adjusted_ir=report.turnover_adjusted_ir,
            sub_period_ic=report.sub_period_ic,
            n_observations=report.n_observations,
            n_dates=report.n_dates,
            computed_at=report.computed_at,
        )
