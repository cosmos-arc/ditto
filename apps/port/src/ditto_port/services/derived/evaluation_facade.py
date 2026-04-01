"""Re-export shim — 实际实现已迁移至 ditto_app.query.evaluation."""

from ditto_app.query.evaluation import EvaluationOptions, FactorEvaluationFacade

__all__ = ["EvaluationOptions", "FactorEvaluationFacade"]
