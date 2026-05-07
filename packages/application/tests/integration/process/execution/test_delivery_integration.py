"""DeliveryRouter 信号推送集成测试 — 验证 _build_context 输出满足全部通知模板."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_application.execution_dto import TradeIntent
from ditto_application.processes.execution.delivery import DeliveryRouter
from jinja2 import Template

TEMPLATES_DIR = Path(
    "packages/apps/src/ditto_apps/registry/infra/notification_templates"
)


def _make_intent(
    instrument_id: int = 100,
    direction: str = "buy",
    current_weight: float = 0.05,
    target_weight: float = 0.10,
    delta_weight: float = 0.05,
    signal_date: str = "2025-01-15",
) -> TradeIntent:
    return TradeIntent(
        intent_id="intent-001",
        strategy_id="test-strategy",
        signal_date=signal_date,
        instrument_id=instrument_id,
        direction=direction,
        target_weight=target_weight,
        current_weight=current_weight,
        delta_weight=delta_weight,
    )


def _render_template(template_name: str, context: dict[str, object]) -> str:
    template_path = TEMPLATES_DIR / template_name
    content = template_path.read_text(encoding="utf-8")
    template = Template(content)
    return template.render(context)


def _full_context(
    strategy_id: str = "test-strategy",
    signal_date: str = "2025-01-15",
) -> dict[str, object]:
    intents = [
        _make_intent(instrument_id=100, direction="buy"),
        _make_intent(instrument_id=200, direction="sell"),
    ]
    context = DeliveryRouter._build_context(strategy_id, intents, signal_date)
    context["level"] = "info"
    context["timestamp"] = "2025-01-15T10:30:00Z"
    return context


class TestBuildContextMatchesTemplates:
    """_build_context 输出 + level/timestamp 能渲染全部通知模板."""

    def test_telegram_template_renders(self) -> None:
        context = _full_context()
        rendered = _render_template("signal_trading_telegram.j2", context)
        assert "test-strategy" in rendered
        assert "2025-01-15" in rendered
        assert "BUY" in rendered
        assert "SELL" in rendered

    def test_email_template_renders(self) -> None:
        context = _full_context()
        rendered = _render_template("signal_trading_email.j2", context)
        assert "test-strategy" in rendered
        assert "2025-01-15" in rendered
        assert "BUY" in rendered
        assert "SELL" in rendered

    def test_webhook_template_renders(self) -> None:
        context = _full_context()
        rendered = _render_template("signal_trading_webhook.j2", context)
        assert '"strategy_id": "test-strategy"' in rendered
        assert '"signal_date": "2025-01-15"' in rendered
        assert '"alert_type": "signal_trading"' in rendered


class TestBuildContextFieldsCorrectness:
    """_build_context 各字段计算正确性."""

    def test_context_fields(self) -> None:
        intents = [
            _make_intent(instrument_id=100, direction="buy"),
            _make_intent(instrument_id=200, direction="sell"),
        ]
        ctx = DeliveryRouter._build_context("strat-A", intents, "2025-06-01")

        assert ctx["strategy_id"] == "strat-A"
        assert ctx["signal_date"] == "2025-06-01"
        assert ctx["buy_count"] == 1
        assert ctx["sell_count"] == 1
        assert ctx["total_intents"] == 2
        assert len(ctx["actions"]) == 2

    def test_action_fields_rounded(self) -> None:
        intents = [
            _make_intent(
                current_weight=0.123456,
                target_weight=0.789012,
                delta_weight=-0.665556,
            ),
        ]
        ctx = DeliveryRouter._build_context("strat-B", intents, "2025-06-01")
        action = ctx["actions"][0]

        assert action["current_weight"] == 0.1235
        assert action["target_weight"] == 0.789
        assert action["delta_weight"] == -0.6656

    def test_empty_intents(self) -> None:
        ctx = DeliveryRouter._build_context("strat-C", [], "2025-06-01")

        assert ctx["buy_count"] == 0
        assert ctx["sell_count"] == 0
        assert ctx["total_intents"] == 0
        assert ctx["actions"] == []


class TestBuildContextWithMixedIntents:
    """混合买卖 intents 的计数验证."""

    def test_mixed_buy_sell_counts(self) -> None:
        intents = [
            _make_intent(instrument_id=100, direction="buy"),
            _make_intent(instrument_id=200, direction="buy"),
            _make_intent(instrument_id=300, direction="sell"),
            _make_intent(instrument_id=400, direction="buy"),
            _make_intent(instrument_id=500, direction="sell"),
        ]
        ctx = DeliveryRouter._build_context("strat-D", intents, "2025-06-01")

        assert ctx["buy_count"] == 3
        assert ctx["sell_count"] == 2
        assert ctx["total_intents"] == 5
        assert len(ctx["actions"]) == 5

    def test_all_buys(self) -> None:
        intents = [
            _make_intent(instrument_id=i, direction="buy") for i in range(100, 105)
        ]
        ctx = DeliveryRouter._build_context("strat-E", intents, "2025-06-01")

        assert ctx["buy_count"] == 5
        assert ctx["sell_count"] == 0

    def test_all_sells(self) -> None:
        intents = [
            _make_intent(instrument_id=i, direction="sell") for i in range(200, 204)
        ]
        ctx = DeliveryRouter._build_context("strat-F", intents, "2025-06-01")

        assert ctx["buy_count"] == 0
        assert ctx["sell_count"] == 4


class TestTemplateUndefinedDetection:
    """直接渲染验证无 UndefinedError — 模板变量全部满足."""

    @pytest.mark.parametrize(
        "template_name",
        [
            "signal_trading_telegram.j2",
            "signal_trading_email.j2",
            "signal_trading_webhook.j2",
        ],
    )
    def test_no_undefined_error(self, template_name: str) -> None:
        context = _full_context()
        rendered = _render_template(template_name, context)
        assert rendered
        assert "test-strategy" in rendered
