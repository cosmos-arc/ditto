"""Universe command handler unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_app.command.universe import (
    CreateCustomUniverseCommand,
    CreateCustomUniverseHandler,
    DeleteCustomUniverseCommand,
    DeleteCustomUniverseHandler,
    UpdateCustomUniverseCommand,
    UpdateCustomUniverseHandler,
)


class TestCreateCustomUniverseHandler:
    """Tests for CreateCustomUniverseHandler."""

    def test_create_custom_universe(self) -> None:
        """创建自定义 universe."""
        service = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = {
            "universe_id": "my-portfolio",
            "name": "我的组合",
            "universe_type": "custom",
        }
        handler = CreateCustomUniverseHandler(metadata_service=service)
        cmd = CreateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="我的组合",
            description="自定义持仓",
        )
        result = handler.handle(cmd)
        assert result["universe_id"] == "my-portfolio"
        assert result["name"] == "我的组合"
        service._universe_writer.create_universe.assert_called_once_with(
            universe_id="my-portfolio",
            name="我的组合",
            description="自定义持仓",
            universe_type="custom",
            source_ref=None,
        )

    def test_create_returns_detail(self) -> None:
        """创建后返回 universe 详情."""
        service = MagicMock()
        service._universe_writer = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = {
            "universe_id": "test",
            "name": "Test",
            "universe_type": "custom",
        }
        handler = CreateCustomUniverseHandler(metadata_service=service)
        cmd = CreateCustomUniverseCommand(universe_id="test", name="Test")
        result = handler.handle(cmd)
        assert result["universe_type"] == "custom"


class TestUpdateCustomUniverseHandler:
    """Tests for UpdateCustomUniverseHandler."""

    def test_update_name_and_description(self) -> None:
        """更新 universe 名称和描述."""
        service = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = {
            "universe_id": "my-portfolio",
            "name": "旧名称",
            "universe_type": "custom",
        }
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="新名称",
            description="新描述",
        )
        result = handler.handle(cmd)
        assert result["universe_id"] == "my-portfolio"

    def test_update_nonexistent_raises(self) -> None:
        """更新不存在的 universe 抛 ValueError."""
        service = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = None
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="missing",
            name="x",
        )
        with pytest.raises(ValueError, match="Universe not found"):
            handler.handle(cmd)


class TestDeleteCustomUniverseHandler:
    """Tests for DeleteCustomUniverseHandler."""

    def test_delete_custom_universe_calls_writer(self) -> None:
        """删除自定义 universe 应调用 writer.delete_universe."""
        service = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = {
            "universe_id": "my-portfolio",
            "universe_type": "custom",
        }
        handler = DeleteCustomUniverseHandler(metadata_service=service)
        cmd = DeleteCustomUniverseCommand(universe_id="my-portfolio")
        result = handler.handle(cmd)
        assert result is True
        service._universe_writer.delete_universe.assert_called_once_with(
            "my-portfolio",
        )

    def test_delete_preset_universe_raises(self) -> None:
        """删除预设 universe 抛 ValueError (403)."""
        service = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = {
            "universe_id": "csi300",
            "universe_type": "index",
        }
        handler = DeleteCustomUniverseHandler(metadata_service=service)
        cmd = DeleteCustomUniverseCommand(universe_id="csi300")
        with pytest.raises(ValueError, match="Cannot delete preset"):
            handler.handle(cmd)
        service._universe_writer.delete_universe.assert_not_called()

    def test_delete_nonexistent_raises(self) -> None:
        """删除不存在的 universe 抛 ValueError (404)."""
        service = MagicMock()
        service._universe_reader = MagicMock()
        service._universe_reader.get_universe.return_value = None
        handler = DeleteCustomUniverseHandler(metadata_service=service)
        cmd = DeleteCustomUniverseCommand(universe_id="missing")
        with pytest.raises(ValueError, match="Universe not found"):
            handler.handle(cmd)
        service._universe_writer.delete_universe.assert_not_called()
