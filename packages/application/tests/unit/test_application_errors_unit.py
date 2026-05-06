"""Tests for application-layer error taxonomy."""

from ditto_application.exceptions import (
    AppBuilderError,
    AppCommandError,
    AppConfigurationError,
    AppError,
    AppProcessError,
    AppQueryError,
)


def test_application_errors_preserve_details() -> None:
    err = AppCommandError("bad command", command="trade")

    assert isinstance(err, AppError)
    assert err.details == {"command": "trade"}


def test_application_error_taxonomy_extends_app_error() -> None:
    error_types = (
        AppConfigurationError,
        AppCommandError,
        AppQueryError,
        AppProcessError,
        AppBuilderError,
    )

    for error_type in error_types:
        assert issubclass(error_type, AppError)
