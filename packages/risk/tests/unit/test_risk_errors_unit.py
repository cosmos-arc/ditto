"""Risk error hierarchy tests."""

from ditto_kernel.exceptions import DittoError


def test_risk_error_hierarchy() -> None:
    from ditto_risk.errors import (
        RiskConfigurationError,
        RiskContractError,
        RiskError,
    )

    assert issubclass(RiskError, DittoError)
    assert issubclass(RiskConfigurationError, RiskError)
    assert issubclass(RiskContractError, RiskError)


def test_risk_error_carries_details() -> None:
    from ditto_risk.errors import RiskConfigurationError

    err = RiskConfigurationError("invalid threshold", field="max_exposure", limit=0.3)
    assert err.details == {"field": "max_exposure", "limit": 0.3}


def test_risk_errors_do_not_model_risk_findings() -> None:
    from ditto_risk import errors

    assert not hasattr(errors, "ConstraintViolationError")
    assert not hasattr(errors, "ExposureLimitError")
    assert not hasattr(errors, "DrawdownThresholdError")
