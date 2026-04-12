"""DeliveryRouter unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.process.execution.delivery import DeliveryRouter, NotificationPort
from ditto_app.types import TradeIntent


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
        sender = MagicMock(spec=NotificationPort)
        sender.send.return_value = {"telegram": True}
        router = DeliveryRouter(sender=sender)
        intents = [
            _make_intent(direction="buy"),
            _make_intent(instrument_id=200, direction="sell"),
        ]
        result = router.deliver("test-strategy", intents, "2025-01-15")
        assert result == {"telegram": True}
        sender.send.assert_called_once()

    def test_deliver_empty_intents(self) -> None:
        """空 intents 不推送."""
        sender = MagicMock(spec=NotificationPort)
        router = DeliveryRouter(sender=sender)
        result = router.deliver("test-strategy", [], "2025-01-15")
        assert result == {}
        sender.send.assert_not_called()

    def test_deliver_fire_and_forget(self) -> None:
        """推送失败不阻塞（fire-and-forget）."""
        sender = MagicMock(spec=NotificationPort)
        sender.send.side_effect = RuntimeError("network error")
        router = DeliveryRouter(sender=sender)
        intents = [_make_intent()]
        # 不抛异常
        result = router.deliver("test-strategy", intents, "2025-01-15")
        assert result == {}

    def test_deliver_context_contains_strategy_info(self) -> None:
        """通知上下文包含策略信息."""
        sender = MagicMock(spec=NotificationPort)
        sender.send.return_value = {}
        router = DeliveryRouter(sender=sender)
        intents = [_make_intent()]
        router.deliver("my-strategy", intents, "2025-06-01")
        call_args = sender.send.call_args
        context = (
            call_args[0][1] if call_args[0] else call_args.kwargs.get("context", {})
        )
        assert context["strategy_id"] == "my-strategy"
        assert context["signal_date"] == "2025-06-01"
        assert context["total_intents"] == 1


class TestDeliveryRouterRenderMarkdown:
    """Tests for DeliveryRouter.render_markdown."""

    def test_render_contains_key_info(self) -> None:
        """Markdown 包含策略名/日期/买卖信息."""
        sender = MagicMock(spec=NotificationPort)
        router = DeliveryRouter(sender=sender)
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
        sender = MagicMock(spec=NotificationPort)
        router = DeliveryRouter(sender=sender)
        assert router.render_markdown("test", [], "2025-01-15") == ""


class TestDeliveryRouterSendSignal:
    """Tests for DeliveryRouter implementing SignalDeliveryProtocol."""

    def test_send_signal_delegates_to_deliver(self) -> None:
        """send_signal 从 intents 推断 signal_date 并调用 deliver."""
        sender = MagicMock(spec=NotificationPort)
        sender.send.return_value = {"test": True}
        router = DeliveryRouter(sender=sender)
        intents = [_make_intent(signal_date="2025-03-01")]
        router.send_signal("my-strategy", intents)
        sender.send.assert_called_once()
