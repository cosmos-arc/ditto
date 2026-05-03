"""Risk error hierarchy tests."""

from ditto_kernel.exceptions import DittoError


def test_risk_error_hierarchy() -> None:
    from ditto_risk.errors import (
        ConstraintViolationError,
        DrawdownThresholdError,
        ExposureLimitError,
        RiskError,
    )

    assert issubclass(RiskError, DittoError)
    assert issubclass(ConstraintViolationError, RiskError)
    assert issubclass(ExposureLimitError, RiskError)
    assert issubclass(DrawdownThresholdError, RiskError)
