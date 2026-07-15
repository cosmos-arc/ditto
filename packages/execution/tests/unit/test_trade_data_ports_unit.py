"""TradeDataPort ISP 拆分验证 — 3 窄 Port 的类型和结构正确性."""

from __future__ import annotations

from typing import Protocol, get_type_hints

import pytest
from ditto_execution.contracts import (
    AccountDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_execution.models import (
    AccountSnapshotRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)
from ditto_execution.storage.sqlite.trade.service import TradeService

# ---------------------------------------------------------------------------
# Protocol 类型检查
# ---------------------------------------------------------------------------


class TestIntentDataPort:
    """IntentDataPort — 交易意图聚合窄 Port（4 方法）."""

    def test_is_protocol(self) -> None:
        assert issubclass(IntentDataPort, Protocol)

    def test_method_count(self) -> None:
        methods = [
            m
            for m in dir(IntentDataPort)
            if not m.startswith("_") and callable(getattr(IntentDataPort, m, None))
        ]
        assert len(methods) == 4

    @pytest.mark.parametrize(
        "method_name",
        ["save_intent", "get_intent", "list_intents", "update_intent_status"],
    )
    def test_has_intent_methods(self, method_name: str) -> None:
        assert hasattr(IntentDataPort, method_name)

    def test_save_intent_signature(self) -> None:
        hints = get_type_hints(IntentDataPort.save_intent)
        assert hints.get("record") is SignalRecord

    def test_get_intent_return_type(self) -> None:
        hints = get_type_hints(IntentDataPort.get_intent)
        assert "return" in hints


class TestFillDataPort:
    """FillDataPort — 成交聚合窄 Port（3 方法）."""

    def test_is_protocol(self) -> None:
        assert issubclass(FillDataPort, Protocol)

    def test_method_count(self) -> None:
        methods = [
            m
            for m in dir(FillDataPort)
            if not m.startswith("_") and callable(getattr(FillDataPort, m, None))
        ]
        assert len(methods) == 3

    @pytest.mark.parametrize(
        "method_name",
        ["save_fill", "find_fill", "list_fills"],
    )
    def test_has_fill_methods(self, method_name: str) -> None:
        assert hasattr(FillDataPort, method_name)

    def test_save_fill_signature(self) -> None:
        hints = get_type_hints(FillDataPort.save_fill)
        assert hints.get("record") is FillRecord


class TestPositionDataPort:
    """PositionDataPort — 持仓聚合窄 Port（2 方法）."""

    def test_is_protocol(self) -> None:
        assert issubclass(PositionDataPort, Protocol)

    def test_method_count(self) -> None:
        methods = [
            m
            for m in dir(PositionDataPort)
            if not m.startswith("_") and callable(getattr(PositionDataPort, m, None))
        ]
        assert len(methods) == 2

    @pytest.mark.parametrize(
        "method_name",
        ["save_position", "list_positions"],
    )
    def test_has_position_methods(self, method_name: str) -> None:
        assert hasattr(PositionDataPort, method_name)

    def test_save_position_signature(self) -> None:
        hints = get_type_hints(PositionDataPort.save_position)
        assert hints.get("record") is PositionRecord


class TestAccountDataPort:
    """AccountDataPort — account baseline aggregate narrow port."""

    def test_is_protocol(self) -> None:
        assert issubclass(AccountDataPort, Protocol)

    @pytest.mark.parametrize(
        "method_name",
        [
            "save_account_baseline",
            "get_latest_account_snapshot",
            "list_account_snapshots",
        ],
    )
    def test_has_account_methods(self, method_name: str) -> None:
        assert hasattr(AccountDataPort, method_name)

    def test_save_baseline_accepts_account_snapshot(self) -> None:
        hints = get_type_hints(AccountDataPort.save_account_baseline)
        assert hints.get("account") is AccountSnapshotRecord


# ---------------------------------------------------------------------------
# TradeService 结构兼容性
# ---------------------------------------------------------------------------


class TestTradeServiceCompatibility:
    """TradeService 自动满足全部 3 个窄 Port（结构化子类型）."""

    def test_satisfies_intent_port(self) -> None:
        for method_name in (
            "save_intent",
            "get_intent",
            "list_intents",
            "update_intent_status",
        ):
            assert hasattr(TradeService, method_name)

    def test_satisfies_fill_port(self) -> None:
        for method_name in ("save_fill", "find_fill", "list_fills"):
            assert hasattr(TradeService, method_name)

    def test_satisfies_position_port(self) -> None:
        for method_name in ("save_position", "list_positions"):
            assert hasattr(TradeService, method_name)

    def test_satisfies_account_port(self) -> None:
        for method_name in (
            "save_account_baseline",
            "get_latest_account_snapshot",
            "list_account_snapshots",
        ):
            assert hasattr(TradeService, method_name)
