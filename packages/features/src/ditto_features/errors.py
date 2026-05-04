"""Features domain exception root."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "EvaluationError",
    "FactorValidationError",
    "FeatureStorageError",
    "FeaturesError",
    "MaterializationError",
]


class FeaturesError(DittoError):
    """
    因子域基础异常.

    所有因子域异常的统一祖先，供上层统一捕获和映射。
    """

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(message)
        self.details: dict[str, object] = dict(kwargs) if kwargs else {}
        if details:
            self.details.update(details)


class MaterializationError(FeaturesError):
    """因子物化失败."""


class EvaluationError(FeaturesError):
    """因子评估失败."""


class FactorValidationError(FeaturesError):
    """因子验证失败."""


class FeatureStorageError(FeaturesError):
    """因子存储失败."""
