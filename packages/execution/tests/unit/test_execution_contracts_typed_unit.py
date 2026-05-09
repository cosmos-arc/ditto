"""Execution contracts — 类型化参数验证."""

from typing import get_type_hints

from ditto_execution.contracts import TradeAuditor


def test_trade_auditor_save_risk_log_uses_risk_payload() -> None:
    hints = get_type_hints(TradeAuditor.save_risk_log)
    assert "object" not in str(hints.get("records", ""))
    assert "RiskScanPayload" in str(hints.get("records", ""))


def test_trade_auditor_save_pre_trade_log_uses_pre_trade_payload() -> None:
    hints = get_type_hints(TradeAuditor.save_pre_trade_log)
    assert "object" not in str(hints.get("records", ""))
    assert "PreTradeDecisionPayload" in str(hints.get("records", ""))


def test_trade_auditor_save_trade_fill_log_uses_trade_fill_payload() -> None:
    hints = get_type_hints(TradeAuditor.save_trade_fill_log)
    assert "object" not in str(hints.get("records", ""))
    assert "TradeFillPayload" in str(hints.get("records", ""))
