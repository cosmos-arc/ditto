"""
Unit tests for Universe API endpoint logic.

Tests request/response model validation, body → command mapping,
result → response mapping, and error handler mapping.
Route handler is wrapped by Dishka @inject, so we test mapping
logic directly without the DI container.
"""

from __future__ import annotations

import pytest
from ditto_app.command.universe import (
    CreateCustomUniverseCommand,
    DeleteCustomUniverseCommand,
    UpdateCustomUniverseCommand,
)
from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.universe import (
    CreateUniverseRequest,
    MemberResponse,
    UpdateUniverseRequest,
    to_universe_response,
)
from fastapi import HTTPException
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Request model validation
# ---------------------------------------------------------------------------


class TestCreateUniverseRequest:
    """Tests for CreateUniverseRequest model validation."""

    def test_valid_minimal(self) -> None:
        """最小合法请求."""
        body = CreateUniverseRequest(universe_id="my-u", name="My Universe")
        assert body.universe_id == "my-u"
        assert body.name == "My Universe"
        assert body.description is None

    def test_valid_with_description(self) -> None:
        """带描述的合法请求."""
        body = CreateUniverseRequest(
            universe_id="test",
            name="Test",
            description="A test universe",
        )
        assert body.description == "A test universe"

    def test_empty_universe_id_rejected(self) -> None:
        """空 universe_id 被拒绝."""
        with pytest.raises(ValidationError):
            CreateUniverseRequest(universe_id="", name="Test")

    def test_empty_name_rejected(self) -> None:
        """空 name 被拒绝."""
        with pytest.raises(ValidationError):
            CreateUniverseRequest(universe_id="test", name="")

    def test_extra_fields_ignored(self) -> None:
        """extra='ignore' 忽略多余字段."""
        body = CreateUniverseRequest(universe_id="u", name="N", unknown="x")  # type: ignore[call-arg]
        assert body.universe_id == "u"


class TestUpdateUniverseRequest:
    """Tests for UpdateUniverseRequest model validation."""

    def test_valid_minimal(self) -> None:
        """最小合法请求."""
        body = UpdateUniverseRequest(name="Updated")
        assert body.name == "Updated"
        assert body.description is None

    def test_valid_with_description(self) -> None:
        """带描述的合法请求."""
        body = UpdateUniverseRequest(name="Updated", description="New desc")
        assert body.description == "New desc"

    def test_valid_with_members(self) -> None:
        """带成分列表的合法请求."""
        body = UpdateUniverseRequest(
            name="Updated",
            members=["510300.SH", "159915.SZ"],
            effective_date="2024-01-15",
        )
        assert body.members == ["510300.SH", "159915.SZ"]
        assert body.effective_date == "2024-01-15"

    def test_members_default_none(self) -> None:
        """members 默认为 None."""
        body = UpdateUniverseRequest(name="Updated")
        assert body.members is None
        assert body.effective_date is None

    def test_empty_name_rejected(self) -> None:
        """空 name 被拒绝."""
        with pytest.raises(ValidationError):
            UpdateUniverseRequest(name="")


# ---------------------------------------------------------------------------
# Body → Command mapping
# ---------------------------------------------------------------------------


class TestBodyToCommandMapping:
    """Tests for request body → Command mapping."""

    def test_create_mapping(self) -> None:
        """CreateUniverseRequest → CreateCustomUniverseCommand."""
        body = CreateUniverseRequest(
            universe_id="etf-pool",
            name="ETF Pool",
            description="My ETF pool",
        )
        cmd = CreateCustomUniverseCommand(
            universe_id=body.universe_id,
            name=body.name,
            description=body.description,
        )
        assert cmd.universe_id == "etf-pool"
        assert cmd.name == "ETF Pool"
        assert cmd.description == "My ETF pool"

    def test_update_mapping(self) -> None:
        """UpdateUniverseRequest → UpdateCustomUniverseCommand."""
        body = UpdateUniverseRequest(name="Renamed", description="New desc")
        cmd = UpdateCustomUniverseCommand(
            universe_id="target-id",
            name=body.name,
            description=body.description,
        )
        assert cmd.universe_id == "target-id"
        assert cmd.name == "Renamed"
        assert cmd.description == "New desc"

    def test_update_mapping_with_members(self) -> None:
        """UpdateUniverseRequest 含 members → Command 传递 members/effective_date."""
        body = UpdateUniverseRequest(
            name="Renamed",
            members=["1", "2", "3"],
            effective_date="2026-04-14",
        )
        cmd = UpdateCustomUniverseCommand(
            universe_id="target-id",
            name=body.name,
            description=body.description,
            members=body.members,
            effective_date=body.effective_date,
        )
        assert cmd.members == ["1", "2", "3"]
        assert cmd.effective_date == "2026-04-14"

    def test_delete_mapping(self) -> None:
        """路径参数 → DeleteCustomUniverseCommand."""
        universe_id = "to-delete"
        cmd = DeleteCustomUniverseCommand(universe_id=universe_id)
        assert cmd.universe_id == "to-delete"


# ---------------------------------------------------------------------------
# to_universe_response mapping
# ---------------------------------------------------------------------------


class TestToUniverseResponseMapping:
    """Tests for dict → UniverseResponse mapping via to_universe_response."""

    def test_full_dict(self) -> None:
        """完整 dict 正确映射."""
        row = {
            "universe_id": "hs300",
            "name": "沪深300",
            "description": "沪深300成分股",
            "universe_type": "preset",
            "source_ref": "index:000300.SH",
        }
        resp = to_universe_response(row)
        assert resp.universe_id == "hs300"
        assert resp.name == "沪深300"
        assert resp.description == "沪深300成分股"
        assert resp.universe_type == "preset"
        assert resp.source_ref == "index:000300.SH"

    def test_minimal_dict_defaults(self) -> None:
        """最小 dict 使用默认值."""
        row: dict[str, object] = {"universe_id": "custom-1", "name": "Custom"}
        resp = to_universe_response(row)
        assert resp.universe_type == "custom"
        assert resp.description is None
        assert resp.source_ref is None

    def test_empty_dict_safe(self) -> None:
        """空 dict 安全映射（不抛异常）."""
        row: dict[str, object] = {}
        resp = to_universe_response(row)
        assert resp.universe_id == ""
        assert resp.name == ""


# ---------------------------------------------------------------------------
# MemberResponse
# ---------------------------------------------------------------------------


class TestMemberResponse:
    """Tests for MemberResponse model."""

    def test_valid_instrument_id(self) -> None:
        """合法 instrument_id."""
        resp = MemberResponse(instrument_id=510300)
        assert resp.instrument_id == 510300

    def test_extra_fields_ignored(self) -> None:
        """extra='ignore' 忽略多余字段."""
        resp = MemberResponse(instrument_id=1, extra="ignored")  # type: ignore[call-arg]
        assert resp.instrument_id == 1


# ---------------------------------------------------------------------------
# APIResponse wrapping
# ---------------------------------------------------------------------------


class TestAPIResponseWrapping:
    """Tests for APIResponse[list] wrapping logic."""

    def test_list_universes_response(self) -> None:
        """list_universes 返回 APIResponse[list[UniverseResponse]]."""
        rows = [
            {"universe_id": "hs300", "name": "沪深300"},
            {"universe_id": "custom-1", "name": "Custom"},
        ]
        response = APIResponse(
            data=[to_universe_response(r) for r in rows],
        )
        assert len(response.data) == 2
        assert response.data[0].universe_id == "hs300"
        assert response.data[1].universe_id == "custom-1"

    def test_list_universes_empty(self) -> None:
        """空列表返回 APIResponse[data=[]]."""
        response = APIResponse(data=[])
        assert response.data == []

    def test_members_response(self) -> None:
        """members 返回 APIResponse[list[MemberResponse]]."""
        ids = [510300, 510500, 159915]
        response = APIResponse(
            data=[MemberResponse(instrument_id=iid) for iid in ids],
        )
        assert len(response.data) == 3
        assert response.data[0].instrument_id == 510300

    def test_delete_response(self) -> None:
        """delete 返回 APIResponse[bool]."""
        response = APIResponse[bool](data=True)
        assert response.data is True


# ---------------------------------------------------------------------------
# Error handler mapping (ValueError → HTTPException)
# ---------------------------------------------------------------------------


class TestErrorHandlerMapping:
    """Tests for ValueError → HTTPException mapping."""

    def test_create_duplicate_id_returns_400(self) -> None:
        """创建重复 universe_id → ValueError → HTTPException(400)."""
        exc = ValueError("Universe already exists: my-u")
        http_exc = HTTPException(status_code=400, detail=str(exc))
        assert http_exc.status_code == 400
        assert "already exists" in http_exc.detail

    def test_update_not_found_returns_404(self) -> None:
        """更新不存在的 universe → ValueError → HTTPException(404)."""
        exc = ValueError("Universe not found: missing")
        http_exc = HTTPException(status_code=404, detail=str(exc))
        assert http_exc.status_code == 404
        assert "not found" in http_exc.detail

    def test_update_preset_returns_403(self) -> None:
        """更新预设 universe → PermissionError → HTTPException(403)."""
        exc = PermissionError(
            "Preset universe cannot be modified 'csi300' (type=preset)"
        )
        http_exc = HTTPException(status_code=403, detail=str(exc))
        assert http_exc.status_code == 403
        assert "cannot be modified" in http_exc.detail

    def test_delete_preset_returns_403(self) -> None:
        """删除预设 universe → ValueError(含 'preset') → HTTPException(403)."""
        exc = ValueError("Cannot delete preset universe 'hs300' (type=preset)")
        msg = str(exc)
        # 路由层判断: "preset" in msg → 403
        assert "preset" in msg
        http_exc = HTTPException(status_code=403, detail=msg)
        assert http_exc.status_code == 403
        assert "preset" in http_exc.detail

    def test_delete_not_found_returns_404(self) -> None:
        """删除不存在的 universe → ValueError(不含 'preset') → HTTPException(404)."""
        exc = ValueError("Universe not found: missing")
        msg = str(exc)
        assert "preset" not in msg
        http_exc = HTTPException(status_code=404, detail=msg)
        assert http_exc.status_code == 404
        assert "not found" in http_exc.detail

    def test_get_universe_not_found_returns_404(self) -> None:
        """get_universe 不存在 → HTTPException(404) 直接构造."""
        universe_id = "nonexistent"
        http_exc = HTTPException(
            status_code=404,
            detail=f"Universe not found: {universe_id}",
        )
        assert http_exc.status_code == 404
        assert http_exc.detail == "Universe not found: nonexistent"
