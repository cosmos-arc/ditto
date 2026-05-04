"""Facade compatibility tests — verify re-export paths work correctly."""

from __future__ import annotations


def test_pre_trade_facade_exports_checks() -> None:
    from ditto_risk.constraints.checks import NoShortSellCheck as NewPath
    from ditto_risk.pre_trade import NoShortSellCheck

    assert NoShortSellCheck is NewPath


def test_pre_trade_facade_exports_context_types() -> None:
    from ditto_risk.constraints.context import (
        Decision as CDecision,
    )
    from ditto_risk.constraints.context import (
        OrderCheckResult as CResult,
    )
    from ditto_risk.constraints.context import (
        PreTradeContext as CContext,
    )
    from ditto_risk.pre_trade import Decision, OrderCheckResult, PreTradeContext

    assert Decision is CDecision
    assert OrderCheckResult is CResult
    assert PreTradeContext is CContext


def test_pre_trade_facade_exports_concentration_check() -> None:
    from ditto_risk.exposure.checks import ConcentrationPreCheck as ExPath
    from ditto_risk.pre_trade import ConcentrationPreCheck

    assert ConcentrationPreCheck is ExPath


def test_pre_trade_facade_exports_protocol() -> None:
    from ditto_risk.constraints.checks import PreTradeRiskCheck as CProtocol
    from ditto_risk.pre_trade import PreTradeRiskCheck

    assert PreTradeRiskCheck is CProtocol


def test_package_init_exports_all_types() -> None:
    """Verify __init__.py re-exports all public symbols."""
    import ditto_risk

    assert hasattr(ditto_risk, "RiskMetrics")
    assert hasattr(ditto_risk, "ExposureData")
    assert hasattr(ditto_risk, "DrawdownStats")
    assert hasattr(ditto_risk, "MaxDrawdownRule")
    assert hasattr(ditto_risk, "SingleLossLimitRule")
    assert hasattr(ditto_risk, "ConcentrationLimitRule")
    assert hasattr(ditto_risk, "MarketAnomalyRule")


def test_subdomain_packages_export_rules() -> None:
    """Verify subdomain __init__.py export their public symbols."""
    from ditto_risk.constraints import Decision, NoShortSellCheck
    from ditto_risk.drawdown import MaxDrawdownRule, SingleLossLimitRule
    from ditto_risk.exposure import (
        ConcentrationLimitRule,
        ConcentrationPreCheck,
        MarketAnomalyRule,
    )

    # All symbols are importable
    assert NoShortSellCheck is not None
    assert Decision is not None
    assert MaxDrawdownRule is not None
    assert SingleLossLimitRule is not None
    assert ConcentrationPreCheck is not None
    assert ConcentrationLimitRule is not None
    assert MarketAnomalyRule is not None
