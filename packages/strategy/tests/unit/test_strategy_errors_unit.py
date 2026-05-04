"""Strategy error hierarchy unit tests."""

from ditto_strategy.errors import (
    PipelineExecutionError,
    SignalGenerationError,
    StrategyError,
    StrategySpecError,
    TemplateNotFoundError,
)


def test_strategy_error_hierarchy() -> None:
    """All strategy domain errors inherit from StrategyError."""
    assert issubclass(StrategySpecError, StrategyError)
    assert issubclass(SignalGenerationError, StrategyError)
    assert issubclass(PipelineExecutionError, StrategyError)
    assert issubclass(TemplateNotFoundError, StrategyError)


def test_strategy_spec_error_is_not_value_error() -> None:
    """StrategySpecError is a domain error, not a builtin value error."""
    assert not issubclass(StrategySpecError, ValueError)


def test_strategy_error_is_ditto_error() -> None:
    """StrategyError inherits from DittoError (kernel root)."""
    from ditto_kernel.exceptions import DittoError

    assert issubclass(StrategyError, DittoError)


def test_strategy_spec_error_carries_details() -> None:
    """StrategySpecError exposes spec_name via details dict."""
    err = StrategySpecError("invalid spec", spec_name="momentum_v1")
    assert err.spec_name == "momentum_v1"
    assert err.details["spec_name"] == "momentum_v1"


def test_strategy_spec_error_without_details() -> None:
    """StrategySpecError works without kwargs."""
    err = StrategySpecError("generic spec error")
    assert err.spec_name == ""
    assert err.details == {}


def test_signal_generation_error() -> None:
    """SignalGenerationError carries stage info."""
    err = SignalGenerationError("signal failed", stage="scoring")
    assert err.details["stage"] == "scoring"


def test_pipeline_execution_error() -> None:
    """PipelineExecutionError carries pipeline info."""
    err = PipelineExecutionError("pipeline crashed", pipeline="etf_rotation")
    assert err.details["pipeline"] == "etf_rotation"


def test_template_not_found_error() -> None:
    """TemplateNotFoundError carries template name."""
    err = TemplateNotFoundError("template missing", template="unknown_tmpl")
    assert err.details["template"] == "unknown_tmpl"
