"""StrategyCommandHandler 单元测试 — 策略 CRUD 命令处理（governance-backed）."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppCommandError
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.governance.service import (
    GovernanceService,
    StrategyGovernanceError,
)
from ditto_strategy.models import StrategySpecRecord


def _make_governance_service() -> MagicMock:
    """构建 GovernanceService mock，包含全部公开方法."""
    return MagicMock(spec=GovernanceService)


def _make_catalog_service() -> MagicMock:
    """构建 StrategyCatalogService mock（Update 路径读 existing record）."""
    return MagicMock(spec=["get_spec"])


def _valid_spec_json() -> dict[str, object]:
    """返回可被 canonical_spec_hash_for_record 解析的合法 spec_json payload."""
    return asdict(SEED_STRATEGY_SPECS["seed_etf_trend_swing"])


# ---------------------------------------------------------------------------
# CreateStrategyHandler
# ---------------------------------------------------------------------------


class TestCreateStrategyHandler:
    """CreateStrategyHandler — 创建策略 Spec（经 governance 写 draft 版本）."""

    def test_handle_creates_new_spec(self) -> None:
        """Handler 构建 record 并调 governance.create_draft，返回 StrategySpecInfo."""
        from ditto_application.commands.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        gov_mock = _make_governance_service()
        handler = CreateStrategyHandler(governance=gov_mock)

        spec_json = _valid_spec_json()
        cmd = CreateStrategyCommand(
            strategy_id="strat-1",
            name="Test Strategy",
            spec_json=spec_json,
        )
        result = handler.handle(cmd)

        assert result.strategy_id == "strat-1"
        assert result.name == "Test Strategy"
        assert result.spec_json == spec_json
        assert result.status == "draft"
        assert result.version == 1
        assert result.tags == ()
        assert result.created_at != ""
        assert result.updated_at != ""
        gov_mock.create_draft.assert_called_once()
        call_kwargs = gov_mock.create_draft.call_args.kwargs
        assert call_kwargs["strategy_id"] == "strat-1"
        assert call_kwargs["version"] == 1
        saved_record = call_kwargs["spec_record"]
        assert saved_record.strategy_id == "strat-1"
        assert saved_record.version == 1

    def test_handle_with_tags(self) -> None:
        """Handler 正确传递 tags 字段."""
        from ditto_application.commands.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        gov_mock = _make_governance_service()
        handler = CreateStrategyHandler(governance=gov_mock)

        cmd = CreateStrategyCommand(
            strategy_id="strat-2",
            name="Tagged Strategy",
            spec_json=_valid_spec_json(),
            tags=("etf", "intraday"),
        )
        result = handler.handle(cmd)

        assert result.tags == ("etf", "intraday")
        gov_mock.create_draft.assert_called_once()

    def test_handle_with_version_defaults_to_one(self) -> None:
        """新建策略 version 默认为 1."""
        from ditto_application.commands.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        gov_mock = _make_governance_service()
        handler = CreateStrategyHandler(governance=gov_mock)

        cmd = CreateStrategyCommand(
            strategy_id="strat-3",
            name="Version Test",
            spec_json=_valid_spec_json(),
        )
        result = handler.handle(cmd)

        assert result.version == 1

    def test_handle_raises_on_duplicate_strategy_id(self) -> None:
        """重复 strategy_id → governance IntegrityError → AppCommandError."""
        from ditto_application.commands.strategy import (
            CreateStrategyCommand,
            CreateStrategyHandler,
        )

        gov_mock = _make_governance_service()
        gov_mock.create_draft.side_effect = sqlite3.IntegrityError(
            "UNIQUE constraint failed: strategy_spec.strategy_id",
        )
        handler = CreateStrategyHandler(governance=gov_mock)

        cmd = CreateStrategyCommand(
            strategy_id="strat-dup",
            name="Dup",
            spec_json=_valid_spec_json(),
        )

        with pytest.raises(AppCommandError, match="Strategy already exists: strat-dup"):
            handler.handle(cmd)

        gov_mock.create_draft.assert_called_once()


# ---------------------------------------------------------------------------
# UpdateStrategyHandler
# ---------------------------------------------------------------------------


class TestUpdateStrategyHandler:
    """UpdateStrategyHandler — 更新策略 Spec（append-only 派生 governance draft）."""

    def test_handle_updates_existing_spec(self) -> None:
        """Handler 基于已有记录派生新版本并调 governance.create_draft."""
        from ditto_application.commands.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        catalog_mock = _make_catalog_service()
        gov_mock = _make_governance_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Old Name",
            spec_json={"type": "momentum"},
            version=1,
            status="draft",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        catalog_mock.get_spec.return_value = existing

        handler = UpdateStrategyHandler(
            catalog_service=catalog_mock,
            governance=gov_mock,
        )
        spec_json = _valid_spec_json()
        cmd = UpdateStrategyCommand(
            strategy_id="strat-1",
            name="New Name",
            spec_json=spec_json,
            version=1,
        )
        result = handler.handle(cmd)

        assert result.strategy_id == "strat-1"
        assert result.name == "New Name"
        assert result.spec_json == spec_json
        assert result.version == 2  # existing.version + 1
        assert result.status == "draft"
        assert result.created_at == "2026-01-01T00:00:00Z"
        assert result.updated_at != ""
        gov_mock.create_draft.assert_called_once()
        call_kwargs = gov_mock.create_draft.call_args.kwargs
        assert call_kwargs["strategy_id"] == "strat-1"
        assert call_kwargs["version"] == 2
        saved_record = call_kwargs["spec_record"]
        assert saved_record.strategy_id == "strat-1"
        assert saved_record.version == 2
        assert saved_record.parent_version == 1
        catalog_mock.get_spec.assert_called_once_with("strat-1")

    def test_handle_raises_on_version_conflict(self) -> None:
        """existing.version 与 command.version 不匹配时抛出 AppCommandError."""
        from ditto_application.commands.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        catalog_mock = _make_catalog_service()
        gov_mock = _make_governance_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Old Name",
            spec_json={"type": "momentum"},
            version=3,
            status="draft",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        catalog_mock.get_spec.return_value = existing

        handler = UpdateStrategyHandler(
            catalog_service=catalog_mock,
            governance=gov_mock,
        )
        cmd = UpdateStrategyCommand(
            strategy_id="strat-1",
            name="New Name",
            spec_json={"type": "momentum", "window": 20},
            version=2,
        )

        with pytest.raises(
            AppCommandError,
            match="Version conflict for strategy strat-1: expected 3, got 2",
        ):
            handler.handle(cmd)
        gov_mock.create_draft.assert_not_called()

    def test_handle_succeeds_when_version_matches(self) -> None:
        """version 匹配时正常更新，新版本为 existing.version + 1."""
        from ditto_application.commands.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        catalog_mock = _make_catalog_service()
        gov_mock = _make_governance_service()
        existing = StrategySpecRecord(
            strategy_id="strat-1",
            name="Old Name",
            spec_json={"type": "momentum"},
            version=1,
            status="draft",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        catalog_mock.get_spec.return_value = existing

        handler = UpdateStrategyHandler(
            catalog_service=catalog_mock,
            governance=gov_mock,
        )
        cmd = UpdateStrategyCommand(
            strategy_id="strat-1",
            name="New Name",
            spec_json=_valid_spec_json(),
            version=1,
        )
        result = handler.handle(cmd)

        assert result.version == 2
        assert result.name == "New Name"
        gov_mock.create_draft.assert_called_once()

    def test_handle_raises_on_missing_spec(self) -> None:
        """策略不存在时抛出 AppCommandError."""
        from ditto_application.commands.strategy import (
            UpdateStrategyCommand,
            UpdateStrategyHandler,
        )

        catalog_mock = _make_catalog_service()
        gov_mock = _make_governance_service()
        catalog_mock.get_spec.return_value = None

        handler = UpdateStrategyHandler(
            catalog_service=catalog_mock,
            governance=gov_mock,
        )
        cmd = UpdateStrategyCommand(
            strategy_id="missing",
            name="Ghost",
            spec_json={},
        )

        with pytest.raises(AppCommandError, match="Strategy not found: missing"):
            handler.handle(cmd)
        gov_mock.create_draft.assert_not_called()


# ---------------------------------------------------------------------------
# PublishStrategyHandler
# ---------------------------------------------------------------------------


class TestPublishStrategyHandler:
    """PublishStrategyHandler — 发布策略 Spec（经 governance publish_and_activate）."""

    def test_handle_publishes_draft(self) -> None:
        """Handler 调 governance.publish_and_activate，返回 True."""
        from ditto_application.commands.strategy import (
            PublishStrategyCommand,
            PublishStrategyHandler,
        )

        gov_mock = _make_governance_service()
        handler = PublishStrategyHandler(governance=gov_mock)
        cmd = PublishStrategyCommand(strategy_id="strat-1", version=2)
        result = handler.handle(cmd)

        assert result is True
        gov_mock.publish_and_activate.assert_called_once()
        call_kwargs = gov_mock.publish_and_activate.call_args.kwargs
        assert call_kwargs["strategy_id"] == "strat-1"
        assert call_kwargs["version"] == 2

    def test_handle_raises_on_missing_version(self) -> None:
        """version 不存在/已 deprecated → governance error → AppCommandError."""
        from ditto_application.commands.strategy import (
            PublishStrategyCommand,
            PublishStrategyHandler,
        )

        gov_mock = _make_governance_service()
        gov_mock.publish_and_activate.side_effect = StrategyGovernanceError(
            "cannot revive deprecated version: ghost/1",
        )
        handler = PublishStrategyHandler(governance=gov_mock)
        cmd = PublishStrategyCommand(strategy_id="ghost", version=1)

        with pytest.raises(
            AppCommandError, match="Strategy version not found: ghost v1"
        ):
            handler.handle(cmd)

        gov_mock.publish_and_activate.assert_called_once()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestStrategyCommandProtocolConformance:
    """所有 Strategy Handler 满足 CommandHandler Protocol."""

    def test_create_handler_satisfies_protocol(self) -> None:
        from ditto_application.commands.protocols import CommandHandler
        from ditto_application.commands.strategy import CreateStrategyHandler

        gov_mock = _make_governance_service()
        handler = CreateStrategyHandler(governance=gov_mock)
        assert isinstance(handler, CommandHandler)

    def test_update_handler_satisfies_protocol(self) -> None:
        from ditto_application.commands.protocols import CommandHandler
        from ditto_application.commands.strategy import UpdateStrategyHandler

        catalog_mock = _make_catalog_service()
        gov_mock = _make_governance_service()
        handler = UpdateStrategyHandler(
            catalog_service=catalog_mock,
            governance=gov_mock,
        )
        assert isinstance(handler, CommandHandler)

    def test_publish_handler_satisfies_protocol(self) -> None:
        from ditto_application.commands.protocols import CommandHandler
        from ditto_application.commands.strategy import PublishStrategyHandler

        gov_mock = _make_governance_service()
        handler = PublishStrategyHandler(governance=gov_mock)
        assert isinstance(handler, CommandHandler)
