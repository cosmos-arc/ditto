"""DeliveryRouter unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.execution_dto import TradeIntent
from ditto_app.process.execution.delivery import DeliveryRouter
from ditto_infra.services.notification import AlertManager, NotificationLevel


def _make_intent(
    instrument_id: int = 100,
    direction: str = "buy",
    delta_weight: float = 0.05,
    signal_date: str = "2025-01-15",
) -> TradeIntent:
    return TradeIntent(
        intent_id="abc",
        strategy_id="test-strategy",
        signal_date=signal_date,
        instrument_id=instrument_id,
        direction=direction,
        target_weight=0.1,
        current_weight=0.05,
        delta_weight=delta_weight,
    )


class TestDeliveryRouterDeliver:
    """Tests for DeliveryRouter.deliver."""

    def test_deliver_sends_notification(self) -> None:
        """正常推送信号通知."""
        alert_manager = MagicMock(spec=AlertManager)
        alert_manager.send_alert.return_value = {"telegram": True}
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [
            _make_intent(direction="buy"),
            _make_intent(instrument_id=200, direction="sell"),
        ]
        result = router.deliver("test-strategy", intents, "2025-01-15")
        assert result == {"telegram": True}
        alert_manager.send_alert.assert_called_once()
        call_args = alert_manager.send_alert.call_args
        assert call_args[0][0] == "signal_trading"
        assert call_args[0][2] == NotificationLevel.INFO

    def test_deliver_empty_intents(self) -> None:
        """空 intents 不推送."""
        alert_manager = MagicMock(spec=AlertManager)
        router = DeliveryRouter(alert_manager=alert_manager)
        result = router.deliver("test-strategy", [], "2025-01-15")
        assert result == {}
        alert_manager.send_alert.assert_not_called()

    def test_deliver_fire_and_forget(self) -> None:
        """推送失败不阻塞（fire-and-forget）."""
        alert_manager = MagicMock(spec=AlertManager)
        alert_manager.send_alert.side_effect = RuntimeError("network error")
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [_make_intent()]
        # 不抛异常
        result = router.deliver("test-strategy", intents, "2025-01-15")
        assert result == {}

    def test_deliver_context_contains_strategy_info(self) -> None:
        """通知上下文包含策略信息."""
        alert_manager = MagicMock(spec=AlertManager)
        alert_manager.send_alert.return_value = {}
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [_make_intent()]
        router.deliver("my-strategy", intents, "2025-06-01")
        call_args = alert_manager.send_alert.call_args
        context = call_args[0][1]
        assert context["strategy_id"] == "my-strategy"
        assert context["signal_date"] == "2025-06-01"
        assert context["total_intents"] == 1

    def test_deliver_noop_when_no_alert_manager(self) -> None:
        """未注入 AlertManager 时等价 NoOp."""
        router = DeliveryRouter()
        intents = [_make_intent()]
        result = router.deliver("test-strategy", intents, "2025-01-15")
        assert result == {}

    def test_deliver_context_actions_fields(self) -> None:
        """通知上下文 actions 包含完整字段."""
        alert_manager = MagicMock(spec=AlertManager)
        alert_manager.send_alert.return_value = {}
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [_make_intent(instrument_id=300, direction="buy", delta_weight=0.03)]
        router.deliver("my-strategy", intents, "2025-06-01")
        call_args = alert_manager.send_alert.call_args
        context = call_args[0][1]
        assert "actions" in context
        assert len(context["actions"]) == 1
        action = context["actions"][0]
        assert action["instrument_id"] == 300
        assert action["action"] == "buy"
        assert "current_weight" in action
        assert "target_weight" in action
        assert "delta_weight" in action

    def test_deliver_uses_signal_trading_template(self) -> None:
        """deliver 使用 signal_trading 模板名."""
        alert_manager = MagicMock(spec=AlertManager)
        alert_manager.send_alert.return_value = {}
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [_make_intent()]
        router.deliver("test-strategy", intents, "2025-01-15")
        call_args = alert_manager.send_alert.call_args
        assert call_args[0][0] == "signal_trading"
        assert call_args[0][2] == NotificationLevel.INFO


class TestDeliveryRouterRenderMarkdown:
    """Tests for DeliveryRouter.render_markdown."""

    def test_render_contains_key_info(self) -> None:
        """Markdown 包含策略名/日期/买卖信息."""
        alert_manager = MagicMock(spec=AlertManager)
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [
            _make_intent(instrument_id=100, direction="buy"),
            _make_intent(instrument_id=200, direction="sell"),
        ]
        md = router.render_markdown("test-strategy", intents, "2025-01-15")
        assert "test-strategy" in md
        assert "2025-01-15" in md
        assert "BUY" in md
        assert "SELL" in md

    def test_render_empty_intents(self) -> None:
        """空 intents 返回空字符串."""
        alert_manager = MagicMock(spec=AlertManager)
        router = DeliveryRouter(alert_manager=alert_manager)
        assert router.render_markdown("test", [], "2025-01-15") == ""


class TestDeliveryRouterSendSignal:
    """Tests for DeliveryRouter implementing SignalDeliveryProtocol."""

    def test_send_signal_delegates_to_deliver(self) -> None:
        """send_signal 从 intents 推断 signal_date 并调用 deliver."""
        alert_manager = MagicMock(spec=AlertManager)
        alert_manager.send_alert.return_value = {"test": True}
        router = DeliveryRouter(alert_manager=alert_manager)
        intents = [_make_intent(signal_date="2025-03-01")]
        router.send_signal("my-strategy", intents)
        alert_manager.send_alert.assert_called_once()
