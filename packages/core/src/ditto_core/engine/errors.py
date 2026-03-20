"""Derived engine error hierarchy."""

from __future__ import annotations

__all__ = [
    "DerivedDependencyError",
    "DerivedError",
    "DerivedMaterializationError",
    "DerivedNotFoundError",
    "DerivedNotImplementedError",
    "DerivedValidationError",
    "DerivedVersionError",
]


class DerivedError(Exception):
    """Base exception for all derived-related errors."""

    def __init__(self, message: str, *, derived_id: str | None = None) -> None:
        self.derived_id = derived_id
        super().__init__(message)


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


class DerivedMaterializationError(DerivedError):
    """Raised when materialization fails."""

    def __init__(self, *, derived_id: str, version: int, reason: str) -> None:
        self.version = version
        self.reason = reason
        super().__init__(
            f"Materialization failed for derived_id={derived_id} "
            + f"version={version}: {reason}",
            derived_id=derived_id,
        )


class DerivedDependencyError(DerivedError):
    """Raised when a dependency is missing or invalid."""

    def __init__(
        self, *, derived_id: str, missing: list[str], available: list[str]
    ) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing dependencies for derived_id={derived_id}: "
            + f"{missing}. Available: {available}",
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
