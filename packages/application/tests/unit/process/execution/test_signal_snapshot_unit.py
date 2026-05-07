"""SignalSnapshotProcess 单元测试 — 信号快照 + 交易意图推导."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _make_target_portfolio(
    positions: dict[int, float],
) -> MagicMock:
    """构建 TargetPortfolioLike mock."""

    class _Target:
        @property
        def positions(self) -> dict[int, float]:
            return positions

    return _Target()


def _make_signal_delivery() -> MagicMock:
    """构建 SignalDeliveryProtocol mock，限制方法白名单."""
    return MagicMock(spec=["send_signal"])


def _make_position_reader(
    positions: dict[int, float],
) -> MagicMock:
    """构建 PositionReader mock，返回指定持仓."""
    reader = MagicMock(spec=["get_current_positions"])
    reader.get_current_positions.return_value = positions
    return reader


# ===========================================================================
# TestGenerateIntents — 核心推导逻辑
# ===========================================================================


class TestGenerateIntents:
    """SignalSnapshotProcess.generate_intents — 对比持仓推导交易意图."""

    def test_empty_positions_with_target_generates_all_buy(self) -> None:
        """空持仓 + 有目标 -> 全部生成 BUY intents."""
        from ditto_application.execution_dto import TradeIntent
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({1001: 0.4, 1002: 0.6})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 2
        directions = {i.instrument_id: i.direction for i in intents}
        assert directions[1001] == "buy"
        assert directions[1002] == "buy"

        # 验证 delta_weight 正确
        for intent in intents:
            assert isinstance(intent, TradeIntent)
            assert intent.strategy_id == "strat-1"
            assert intent.signal_date == "2026-04-11"
            assert intent.status == "pending"
            assert intent.intent_id != ""

    def test_holdings_with_no_target_generates_all_sell(self) -> None:
        """有持仓 + 无目标（空 target）-> 全部生成 SELL intents."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({1001: 0.5, 1002: 0.5})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({})
        intents = process.generate_intents(
            strategy_id="strat-2",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 2
        for intent in intents:
            assert intent.direction == "sell"
            assert intent.target_weight == 0.0
            assert intent.delta_weight < 0

    def test_mixed_positions_partial_buy_sell(self) -> None:
        """混合持仓 -> 生成部分 BUY/SELL intents."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        current = {1001: 0.2, 1002: 0.3, 1003: 0.5}
        target_positions = {1001: 0.4, 1002: 0.1, 1004: 0.5}

        reader = _make_position_reader(current)
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio(target_positions)
        intents = process.generate_intents(
            strategy_id="strat-3",
            signal_date="2026-04-11",
            target=target,
        )

        intent_map = {i.instrument_id: i for i in intents}

        # 1001: 0.4 - 0.2 = +0.2 -> buy
        assert intent_map[1001].direction == "buy"
        assert intent_map[1001].delta_weight == pytest.approx(0.2)

        # 1002: 0.1 - 0.3 = -0.2 -> sell
        assert intent_map[1002].direction == "sell"
        assert intent_map[1002].delta_weight == pytest.approx(-0.2)

        # 1003: 不在 target 中 -> 0.0 - 0.5 = -0.5 -> sell
        assert intent_map[1003].direction == "sell"
        assert intent_map[1003].delta_weight == pytest.approx(-0.5)

        # 1004: 不在 current 中 -> 0.5 - 0.0 = +0.5 -> buy
        assert intent_map[1004].direction == "buy"
        assert intent_map[1004].delta_weight == pytest.approx(0.5)

    def test_below_threshold_no_intent(self) -> None:
        """低于阈值 -> 不生成 intent."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        current = {1001: 0.3}
        target_positions = {1001: 0.35}  # delta = 0.05 < 0.01 阈值 不对, 用 0.1 阈值

        reader = _make_position_reader(current)
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio(target_positions)
        intents = process.generate_intents(
            strategy_id="strat-4",
            signal_date="2026-04-11",
            target=target,
            threshold=0.1,
        )

        assert len(intents) == 0

    def test_exactly_at_threshold_no_intent(self) -> None:
        """delta 恰好等于阈值 -> 不生成 intent（严格大于才触发）."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        current = {1001: 0.2}
        target_positions = {1001: 0.3}  # delta = 0.1 == threshold

        reader = _make_position_reader(current)
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio(target_positions)
        intents = process.generate_intents(
            strategy_id="strat-5",
            signal_date="2026-04-11",
            target=target,
            threshold=0.1,
        )

        assert len(intents) == 0

    def test_just_above_threshold_generates_intent(self) -> None:
        """delta 略大于阈值 -> 生成 intent."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        current = {1001: 0.2}
        target_positions = {1001: 0.31}  # delta = 0.11 > 0.1

        reader = _make_position_reader(current)
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio(target_positions)
        intents = process.generate_intents(
            strategy_id="strat-6",
            signal_date="2026-04-11",
            target=target,
            threshold=0.1,
        )

        assert len(intents) == 1
        assert intents[0].direction == "buy"

    def test_default_threshold_is_0_01(self) -> None:
        """默认阈值 0.01 — delta = 0.005 不触发, delta = 0.02 触发."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({1001: 0.3})
        process = SignalSnapshotProcess(position_reader=reader)

        # delta = 0.005 < 0.01 -> no intent
        target_low = _make_target_portfolio({1001: 0.305})
        intents_low = process.generate_intents(
            strategy_id="strat-7",
            signal_date="2026-04-11",
            target=target_low,
        )
        assert len(intents_low) == 0

        # delta = 0.02 > 0.01 -> intent
        target_high = _make_target_portfolio({1001: 0.32})
        intents_high = process.generate_intents(
            strategy_id="strat-7",
            signal_date="2026-04-11",
            target=target_high,
        )
        assert len(intents_high) == 1

    def test_no_change_no_intents(self) -> None:
        """目标与持仓完全一致 -> 无 intent."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        current = {1001: 0.5, 1002: 0.5}
        target_positions = {1001: 0.5, 1002: 0.5}

        reader = _make_position_reader(current)
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio(target_positions)
        intents = process.generate_intents(
            strategy_id="strat-8",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 0


# ===========================================================================
# TestSignalDelivery — 信号推送
# ===========================================================================


class TestSignalDelivery:
    """SignalSnapshotProcess — 信号推送集成."""

    def test_calls_send_signal_with_intents(self) -> None:
        """生成 intents 后调用 signal_delivery.send_signal()."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({})
        delivery = _make_signal_delivery()
        process = SignalSnapshotProcess(
            position_reader=reader,
            signal_delivery=delivery,
        )

        target = _make_target_portfolio({1001: 1.0})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        delivery.send_signal.assert_called_once_with("strat-1", intents)

    def test_no_delivery_does_not_raise(self) -> None:
        """无推送器时不抛异常（graceful degradation）."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({1001: 1.0})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 1

    def test_delivery_not_called_when_no_intents(self) -> None:
        """无 intents 时不调用 send_signal."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        current = {1001: 0.5}
        target_positions = {1001: 0.5}

        reader = _make_position_reader(current)
        delivery = _make_signal_delivery()
        process = SignalSnapshotProcess(
            position_reader=reader,
            signal_delivery=delivery,
        )

        target = _make_target_portfolio(target_positions)
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 0
        delivery.send_signal.assert_not_called()


# ===========================================================================
# TestTradeIntentFields — TradeIntent 字段正确性
# ===========================================================================


class TestTradeIntentFields:
    """generate_intents 输出的 TradeIntent 字段语义正确."""

    def test_buy_intent_fields(self) -> None:
        """BUY intent: target_weight > current_weight, delta > 0."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({1001: 0.1})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({1001: 0.4})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 1
        intent = intents[0]
        assert intent.instrument_id == 1001
        assert intent.target_weight == pytest.approx(0.4)
        assert intent.current_weight == pytest.approx(0.1)
        assert intent.delta_weight == pytest.approx(0.3)
        assert intent.direction == "buy"
        assert intent.quantity is None
        assert intent.status == "pending"

    def test_sell_intent_fields(self) -> None:
        """SELL intent: target_weight < current_weight, delta < 0."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({1002: 0.6})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({1002: 0.2})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 1
        intent = intents[0]
        assert intent.instrument_id == 1002
        assert intent.target_weight == pytest.approx(0.2)
        assert intent.current_weight == pytest.approx(0.6)
        assert intent.delta_weight == pytest.approx(-0.4)
        assert intent.direction == "sell"

    def test_intent_ids_are_unique(self) -> None:
        """每个 intent 的 intent_id 唯一."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({1001: 0.3, 1002: 0.3, 1003: 0.4})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        intent_ids = [i.intent_id for i in intents]
        assert len(set(intent_ids)) == len(intent_ids)

    def test_liquidation_intent_target_weight_zero(self) -> None:
        """清仓 intent: target_weight = 0.0."""
        from ditto_application.processes.execution.signal_snapshot import (
            SignalSnapshotProcess,
        )

        reader = _make_position_reader({1001: 0.8})
        process = SignalSnapshotProcess(position_reader=reader)

        target = _make_target_portfolio({})
        intents = process.generate_intents(
            strategy_id="strat-1",
            signal_date="2026-04-11",
            target=target,
        )

        assert len(intents) == 1
        assert intents[0].target_weight == 0.0
        assert intents[0].current_weight == pytest.approx(0.8)
        assert intents[0].delta_weight == pytest.approx(-0.8)
        assert intents[0].direction == "sell"
