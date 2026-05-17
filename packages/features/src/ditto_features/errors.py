"""Features domain exception root."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "DerivedError",
    "DerivedNotFoundError",
    "DerivedNotImplementedError",
    "DerivedValidationError",
    "DerivedVersionError",
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


class MaterializationError(FeaturesError):
    """因子物化失败."""


class EvaluationError(FeaturesError):
    """因子评估失败."""


class FactorValidationError(FeaturesError):
    """因子验证失败."""


class FeatureStorageError(FeaturesError):
    """因子存储失败."""


# ---------------------------------------------------------------------------
# Derived error hierarchy — derived/feature data domain exceptions.
# Migrated from kernel per B9-K.4.
# ---------------------------------------------------------------------------


class DerivedError(DittoError):
    """衍生数据域基础异常."""

    def __init__(self, message: str, *, derived_id: str | None = None) -> None:
        self.derived_id = derived_id
        details: dict[str, object] | None = (
            {"derived_id": derived_id} if derived_id is not None else None
        )
        super().__init__(message, details=details)


class DerivedNotFoundError(DerivedError):
    """Raised when a derived entity is not found."""

    def __init__(self, *, derived_id: str, version: int | None = None) -> None:
        self.version = version
        msg = f"Derived not found: derived_id={derived_id}"
        if version is not None:
            msg += f" version={version}"
        super().__init__(msg, derived_id=derived_id)


class DerivedVersionError(DerivedError):
    """Raised when version resolution fails."""

    def __init__(self, *, derived_id: str, reason: str) -> None:
        self.reason = reason
        super().__init__(
            f"Version resolution failed for derived_id={derived_id}: {reason}",
            derived_id=derived_id,
        )


class DerivedNotImplementedError(DerivedError):
    """Raised when a feature is not yet implemented."""

    def __init__(self, *, feature: str, derived_id: str | None = None) -> None:
        self.feature = feature
        super().__init__(
            f"Feature not implemented: {feature}",
            derived_id=derived_id,
        )


class DerivedValidationError(DerivedError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str | None = None,
        *,
        derived_id: str | None = None,
        field: str | None = None,
        value: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        if message is not None:
            super().__init__(message, derived_id=derived_id)
        elif field is not None and value is not None and reason is not None:
            super().__init__(
                f"Validation failed for field={field} value={value}: {reason}",
                derived_id=derived_id,
            )
        else:
            raise TypeError(
                (
                    "DerivedValidationError requires either a positional message "
                    "or all of field, value, reason keyword arguments"
                ),
            )
