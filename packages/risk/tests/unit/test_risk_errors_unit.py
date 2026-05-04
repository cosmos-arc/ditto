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


def test_risk_error_carries_details() -> None:
    from ditto_risk.errors import ExposureLimitError

    err = ExposureLimitError("exposure too high", limit=0.3, current=0.35)
    assert err.details == {"limit": 0.3, "current": 0.35}
