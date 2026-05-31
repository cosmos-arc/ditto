"""Universe command handler unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.commands.universe import (
    CreateCustomUniverseCommand,
    CreateCustomUniverseHandler,
    DeleteCustomUniverseCommand,
    DeleteCustomUniverseHandler,
    UpdateCustomUniverseCommand,
    UpdateCustomUniverseHandler,
)
from ditto_application.exceptions import AppCommandError


class TestCreateCustomUniverseHandler:
    """Tests for CreateCustomUniverseHandler."""

    def test_create_custom_universe(self) -> None:
        """创建自定义 universe."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
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
        service.universe.create_universe.assert_called_once_with(
            universe_id="my-portfolio",
            name="我的组合",
            description="自定义持仓",
            universe_type="custom",
            source_ref=None,
        )

    def test_create_returns_detail(self) -> None:
        """创建后返回 universe 详情."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
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
        # 首次调用返回旧数据（用于 existence check），再次调用返回新数据
        service.universe.get_universe_detail.side_effect = [
            {
                "universe_id": "my-portfolio",
                "name": "旧名称",
                "universe_type": "custom",
                "description": "旧描述",
            },
            {
                "universe_id": "my-portfolio",
                "name": "新名称",
                "description": "新描述",
                "universe_type": "custom",
            },
        ]
        service.universe.update_universe.return_value = True
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="新名称",
            description="新描述",
        )
        result = handler.handle(cmd)
        assert result["universe_id"] == "my-portfolio"
        assert result["name"] == "新名称"
        service.universe.update_universe.assert_called_once_with(
            "my-portfolio",
            "新名称",
            "新描述",
        )

    def test_update_calls_update_universe_not_create(
        self,
    ) -> None:
        """更新应调用 update_universe 而非 create_universe."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "my-portfolio",
            "name": "旧名称",
            "universe_type": "custom",
            "description": "旧描述",
        }
        service.universe.update_universe.return_value = True
        service.universe.get_universe_detail.return_value = {
            "universe_id": "my-portfolio",
            "name": "新名称",
            "description": "新描述",
            "universe_type": "custom",
        }
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="新名称",
            description="新描述",
        )
        handler.handle(cmd)
        # 应调用 update_universe 而非 create_universe
        service.universe.update_universe.assert_called_once_with(
            "my-portfolio",
            "新名称",
            "新描述",
        )
        service.universe.create_universe.assert_not_called()

    def test_update_preset_universe_raises_permission_error(
        self,
    ) -> None:
        """更新预设 universe 应抛 PermissionError."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "csi300",
            "name": "沪深300",
            "universe_type": "preset",
        }
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="csi300",
            name="修改名称",
        )
        with pytest.raises(
            AppCommandError,
            match="Preset universe cannot be modified",
        ) as exc_info:
            handler.handle(cmd)
        assert exc_info.value.details == {
            "universe_id": "csi300",
            "reason": "non_custom_universe",
            "universe_type": "preset",
            "operation": "update",
        }
        service.universe.update_universe.assert_not_called()

    def test_update_nonexistent_raises(self) -> None:
        """更新不存在的 universe 抛 ValueError."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = None
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="missing",
            name="x",
        )
        with pytest.raises(AppCommandError, match="Universe not found") as exc_info:
            handler.handle(cmd)
        assert exc_info.value.details == {
            "universe_id": "missing",
            "reason": "not_found",
        }

    def test_update_with_members_calls_replace_constituents(self) -> None:
        """更新时传入 members 应调用 replace_constituents."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "my-portfolio",
            "name": "新名称",
            "universe_type": "custom",
        }
        service.universe.update_universe.return_value = True
        service.universe.replace_constituents.return_value = 3
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="新名称",
            members=["1", "2", "3"],
            effective_date="2026-04-14",
        )
        handler.handle(cmd)

        service.universe.replace_constituents.assert_called_once()
        call_args = service.universe.replace_constituents.call_args
        assert call_args[0][0] == "my-portfolio"
        records = call_args[0][1]
        assert len(records) == 3
        assert records[0]["instrument_id"] == 1
        assert records[0]["effective_from"] == "2026-04-14"
        assert call_args[0][2] == "2026-04-14"

    def test_update_with_invalid_member_raises_app_command_error(self) -> None:
        """Invalid member ids raise typed command errors."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "my-portfolio",
            "name": "新名称",
            "universe_type": "custom",
        }
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="新名称",
            members=["abc"],
            effective_date="2026-04-14",
        )

        with pytest.raises(AppCommandError, match="members") as exc_info:
            handler.handle(cmd)

        assert exc_info.value.details == {
            "universe_id": "my-portfolio",
            "field": "members",
            "index": 0,
            "value": "abc",
        }
        service.universe.replace_constituents.assert_not_called()

    def test_update_without_members_skips_replace(self) -> None:
        """未传 members 时不应调用 replace_constituents."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "my-portfolio",
            "name": "新名称",
            "universe_type": "custom",
        }
        service.universe.update_universe.return_value = True
        handler = UpdateCustomUniverseHandler(metadata_service=service)
        cmd = UpdateCustomUniverseCommand(
            universe_id="my-portfolio",
            name="新名称",
        )
        handler.handle(cmd)

        service.universe.replace_constituents.assert_not_called()


class TestDeleteCustomUniverseHandler:
    """Tests for DeleteCustomUniverseHandler."""

    def test_delete_custom_universe_calls_delete(self) -> None:
        """删除自定义 universe 应调用 delete_universe."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "my-portfolio",
            "universe_type": "custom",
        }
        handler = DeleteCustomUniverseHandler(metadata_service=service)
        cmd = DeleteCustomUniverseCommand(universe_id="my-portfolio")
        result = handler.handle(cmd)
        assert result is True
        service.universe.delete_universe.assert_called_once_with("my-portfolio")

    def test_delete_preset_universe_raises(self) -> None:
        """删除预设 universe 抛 ValueError (403)."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = {
            "universe_id": "csi300",
            "universe_type": "index",
        }
        handler = DeleteCustomUniverseHandler(metadata_service=service)
        cmd = DeleteCustomUniverseCommand(universe_id="csi300")
        with pytest.raises(AppCommandError, match="Cannot delete preset") as exc_info:
            handler.handle(cmd)
        assert exc_info.value.details == {
            "universe_id": "csi300",
            "reason": "non_custom_universe",
            "universe_type": "index",
            "operation": "delete",
        }
        service.universe.delete_universe.assert_not_called()

    def test_delete_nonexistent_raises(self) -> None:
        """删除不存在的 universe 抛 ValueError (404)."""
        service = MagicMock()
        service.universe.get_universe_detail.return_value = None
        handler = DeleteCustomUniverseHandler(metadata_service=service)
        cmd = DeleteCustomUniverseCommand(universe_id="missing")
        with pytest.raises(AppCommandError, match="Universe not found") as exc_info:
            handler.handle(cmd)
        assert exc_info.value.details == {
            "universe_id": "missing",
            "reason": "not_found",
        }
        service.universe.delete_universe.assert_not_called()
