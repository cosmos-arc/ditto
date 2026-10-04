"""Features domain exception root."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "DerivedError",
    "DerivedIntegrityError",
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


class DerivedError(FeaturesError):
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


class DerivedIntegrityError(DerivedError):
    """
    Raised when an artifact partition fails the read-side honesty gate.

    覆盖两类拒绝：分区 checkpoint 不是 COMPLETE（部分写入/在途重算）与
    文件内容 checksum 与目录记录不一致（身份漂移）。两者都必须 fail closed。
    """

    def __init__(
        self,
        *,
        derived_id: str,
        version: int,
        partition_key: str,
        reason: str,
        expected_checksum: str | None = None,
        actual_checksum: str | None = None,
    ) -> None:
        self.version = version
        self.partition_key = partition_key
        self.reason = reason
        self.expected_checksum = expected_checksum
        self.actual_checksum = actual_checksum
        msg = (
            f"Derived artifact integrity refused: derived_id={derived_id} "
            f"version={version} partition={partition_key}: {reason}"
        )
        details: dict[str, object] = {
            "derived_id": derived_id,
            "version": version,
            "partition_key": partition_key,
            "reason": reason,
        }
        if expected_checksum is not None:
            details["expected_checksum"] = expected_checksum
        if actual_checksum is not None:
            details["actual_checksum"] = actual_checksum
        super().__init__(msg, derived_id=derived_id)
        self.details.update(details)


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
