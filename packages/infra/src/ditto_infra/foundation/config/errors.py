"""Configuration initialization errors."""

from __future__ import annotations


class ConfigInitError(Exception):
    """
    Raised when configuration initialization fails during startup.

    This error is raised when one or more configuration providers fail
    during the STARTUP initialization scope with fail_fast=True.

    Attributes:
        failed_providers: List of provider names that failed.
        details: Mapping of provider names to their error messages.

    """

    def __init__(
        self,
        failed_providers: list[str],
        details: dict[str, str],
    ) -> None:
        """
        Initialize ConfigInitError.

        Args:
            failed_providers: List of provider names that failed initialization.
            details: Mapping of provider names to their error messages.

        """
        self.failed_providers = failed_providers
        self.details = details
        message = f"Startup initialization failed for: {', '.join(failed_providers)}"
        super().__init__(message)


__all__ = ["ConfigInitError"]
