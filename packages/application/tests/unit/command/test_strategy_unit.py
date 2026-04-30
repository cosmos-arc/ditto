"""StrategyCommandHandler 单元测试 — 策略 CRUD 命令处理."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_data.models.strategy import StrategySpecRecord


def _make_catalog_service() -> MagicMock:
    """构建 StrategyCatalogService mock，包含全部公开方法."""
    return MagicMock(
        spec=["save_spec", "get_spec", "list_specs", "list_versions", "publish_spec"],
    )


# ---------------------------------------------------------------------------
# CreateStrategyHandler
# ---------------------------------------------------------------------------


class TestCreateStrategyHandler:
    """CreateStrategyHandler — 创建策略 Spec."""

    def test_handle_creates_new_spec(self) -> None:
        """Handler 构建 StrategySpecRecord 并调用 save_spec，返回 StrategySpecInfo."""
        from ditto_application.command.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        service = _make_catalog_service()
        handler = CreateStrategyHandler(catalog_service=service)

        cmd = CreateStrategyCommand(
            strategy_id="strat-1",
            name="Test Strategy",
            spec_json={"type": "momentum"},
        )
        result = handler.handle(cmd)

        assert result.strategy_id == "strat-1"
        assert result.name == "Test Strategy"
        assert result.spec_json == {"type": "momentum"}
        assert result.status == "draft"
        assert result.version == 1
        assert result.tags == ()
        assert result.created_at != ""
        assert result.updated_at != ""
        service.save_spec.assert_called_once()
        saved_record = service.save_spec.call_args.args[0]
        assert saved_record.strategy_id == "strat-1"

    def test_handle_with_tags(self) -> None:
        """Handler 正确传递 tags 字段."""
        from ditto_application.command.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        service = _make_catalog_service()
        handler = CreateStrategyHandler(catalog_service=service)

        cmd = CreateStrategyCommand(
            strategy_id="strat-2",
            name="Tagged Strategy",
            spec_json={"type": "mean_reversion"},
            tags=("etf", "intraday"),
        )
        result = handler.handle(cmd)

        assert result.tags == ("etf", "intraday")
        service.save_spec.assert_called_once()

    def test_handle_with_version_defaults_to_one(self) -> None:
        """新建策略 version 默认为 1."""
        from ditto_application.command.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        service = _make_catalog_service()
        handler = CreateStrategyHandler(catalog_service=service)

        cmd = CreateStrategyCommand(
            strategy_id="strat-3",
            name="Version Test",
            spec_json={"type": "trend"},
        )
        result = handler.handle(cmd)

        assert result.version == 1


# ---------------------------------------------------------------------------
# UpdateStrategyHandler
# ---------------------------------------------------------------------------


class TestUpdateStrategyHandler:
    """UpdateStrategyHandler — 更新策略 Spec."""

    def test_handle_updates_existing_spec(self) -> None:
        """Handler 基于已有记录构建新版本并保存."""
        from ditto_application.command.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        service = _make_catalog_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Old Name",
            spec_json={"type": "momentum"},
            version=1,
            status="draft",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        service.get_spec.return_value = existing

        handler = UpdateStrategyHandler(catalog_service=service)
        cmd = UpdateStrategyCommand(
            strategy_id="strat-1",
            name="New Name",
            spec_json={"type": "momentum", "window": 20},
            version=1,
        )
        result = handler.handle(cmd)

        assert result.strategy_id == "strat-1"
        assert result.name == "New Name"
        assert result.spec_json == {"type": "momentum", "window": 20}
        assert result.version == 2  # command.version + 1
        assert result.status == "draft"
        assert result.created_at == "2026-01-01T00:00:00Z"
        assert result.updated_at != ""
        service.save_spec.assert_called_once()
        saved_record = service.save_spec.call_args.args[0]
        assert saved_record.strategy_id == "strat-1"
        service.get_spec.assert_called_once_with("strat-1")

    def test_handle_raises_on_version_conflict(self) -> None:
        """existing.version 与 command.version 不匹配时抛出 ValueError."""
        from ditto_application.command.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        service = _make_catalog_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Old Name",
            spec_json={"type": "momentum"},
            version=3,
            status="draft",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        service.get_spec.return_value = existing

        handler = UpdateStrategyHandler(catalog_service=service)
        cmd = UpdateStrategyCommand(
            strategy_id="strat-1",
            name="New Name",
            spec_json={"type": "momentum", "window": 20},
            version=2,
        )

        with pytest.raises(
            ValueError,
            match="Version conflict for strategy strat-1: expected 3, got 2",
        ):
            handler.handle(cmd)

    def test_handle_succeeds_when_version_matches(self) -> None:
        """version 匹配时正常更新，新版本为 existing.version + 1."""
        from ditto_application.command.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        service = _make_catalog_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Old Name",
            spec_json={"type": "momentum"},
            version=1,
            status="draft",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        service.get_spec.return_value = existing

        handler = UpdateStrategyHandler(catalog_service=service)
        cmd = UpdateStrategyCommand(
            strategy_id="strat-1",
            name="New Name",
            spec_json={"type": "momentum", "window": 20},
            version=1,
        )
        result = handler.handle(cmd)

        assert result.version == 2
        assert result.name == "New Name"
        service.save_spec.assert_called_once()

    def test_handle_raises_on_missing_spec(self) -> None:
        """策略不存在时抛出 ValueError."""
        from ditto_application.command.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        service = _make_catalog_service()
        service.get_spec.return_value = None

        handler = UpdateStrategyHandler(catalog_service=service)
        cmd = UpdateStrategyCommand(
            strategy_id="missing",
            name="Ghost",
            spec_json={},
        )

        with pytest.raises(ValueError, match="Strategy not found: missing"):
            handler.handle(cmd)


# ---------------------------------------------------------------------------
# PublishStrategyHandler
# ---------------------------------------------------------------------------


class TestPublishStrategyHandler:
    """PublishStrategyHandler — 发布策略 Spec."""

    def test_handle_publishes_draft(self) -> None:
        """Handler 验证存在后调用 publish_spec，返回 True."""
        from ditto_application.command.strategy import (
            PublishStrategyCommand,
            PublishStrategyHandler,
        )

        service = _make_catalog_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Draft",
            spec_json={},
            version=2,
            status="draft",
        )
        service.get_spec.return_value = existing
        service.publish_spec.return_value = True

        handler = PublishStrategyHandler(catalog_service=service)
        cmd = PublishStrategyCommand(strategy_id="strat-1", version=2)
        result = handler.handle(cmd)

        assert result is True
        service.get_spec.assert_called_once_with("strat-1", 2)
        service.publish_spec.assert_called_once_with("strat-1", 2)

    def test_handle_raises_on_missing_spec(self) -> None:
        """策略不存在时抛出 ValueError."""
        from ditto_application.command.strategy import (
            PublishStrategyCommand,
            PublishStrategyHandler,
        )

        service = _make_catalog_service()
        service.get_spec.return_value = None

        handler = PublishStrategyHandler(catalog_service=service)
        cmd = PublishStrategyCommand(strategy_id="ghost", version=1)

        with pytest.raises(ValueError, match="Strategy not found: ghost v1"):
            handler.handle(cmd)

    def test_handle_returns_false_on_failure(self) -> None:
        """publish_spec 返回 False 时，Handler 返回 False."""
        from ditto_application.command.strategy import (
            PublishStrategyCommand,
            PublishStrategyHandler,
        )

        service = _make_catalog_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Draft",
            spec_json={},
            version=1,
            status="draft",
        )
        service.get_spec.return_value = existing
        service.publish_spec.return_value = False

        handler = PublishStrategyHandler(catalog_service=service)
        cmd = PublishStrategyCommand(strategy_id="strat-1", version=1)
        result = handler.handle(cmd)

        assert result is False


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestStrategyCommandProtocolConformance:
    """所有 Strategy Handler 满足 CommandHandler Protocol."""

    def test_create_handler_satisfies_protocol(self) -> None:
        from ditto_application.command.protocols import CommandHandler
        from ditto_application.command.strategy import CreateStrategyHandler

        service = _make_catalog_service()
        handler = CreateStrategyHandler(catalog_service=service)
        assert isinstance(handler, CommandHandler)

    def test_update_handler_satisfies_protocol(self) -> None:
        from ditto_application.command.protocols import CommandHandler
        from ditto_application.command.strategy import UpdateStrategyHandler

        service = _make_catalog_service()
        handler = UpdateStrategyHandler(catalog_service=service)
        assert isinstance(handler, CommandHandler)

    def test_publish_handler_satisfies_protocol(self) -> None:
        from ditto_application.command.protocols import CommandHandler
        from ditto_application.command.strategy import PublishStrategyHandler

        service = _make_catalog_service()
        handler = PublishStrategyHandler(catalog_service=service)
        assert isinstance(handler, CommandHandler)
