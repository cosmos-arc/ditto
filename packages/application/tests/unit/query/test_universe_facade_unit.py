"""UniverseQueryFacade unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
from ditto_application.query.universe import UniverseQueryFacade


class TestListUniverses:
    """Tests for list_universes."""

    def test_returns_list_of_dicts(self) -> None:
        """list_universes 返回字典列表."""
        service = MagicMock()
        service.list_universes_df.return_value = pl.DataFrame(
            {"universe_id": ["csi300", "csi500"], "name": ["沪深300", "中证500"]},
        )
        facade = UniverseQueryFacade(metadata_service=service)
        result = facade.list_universes()
        assert len(result) == 2
        assert result[0]["universe_id"] == "csi300"
        assert result[1]["name"] == "中证500"

    def test_empty_result(self) -> None:
        """空结果返回空列表."""
        service = MagicMock()
        service.list_universes_df.return_value = pl.DataFrame()
        facade = UniverseQueryFacade(metadata_service=service)
        assert facade.list_universes() == []

    def test_type_filter_passed(self) -> None:
        """universe_type 过滤器正确透传."""
        service = MagicMock()
        service.list_universes_df.return_value = pl.DataFrame()
        facade = UniverseQueryFacade(metadata_service=service)
        facade.list_universes(universe_type="custom")
        service.list_universes_df.assert_called_once_with("custom")


class TestGetUniverseDetail:
    """Tests for get_universe_detail."""

    def test_existing_universe(self) -> None:
        """存在的 universe 返回字典."""
        service = MagicMock()
        service.get_universe_detail.return_value = {
            "universe_id": "csi300",
            "name": "沪深300",
            "universe_type": "index",
        }
        facade = UniverseQueryFacade(metadata_service=service)
        result = facade.get_universe_detail("csi300")
        assert result is not None
        assert result["universe_id"] == "csi300"

    def test_nonexistent_universe(self) -> None:
        """不存在的 universe 返回 None."""
        service = MagicMock()
        service.get_universe_detail.return_value = None
        facade = UniverseQueryFacade(metadata_service=service)
        assert facade.get_universe_detail("missing") is None


class TestGetMembers:
    """Tests for get_members."""

    def test_returns_instrument_ids(self) -> None:
        """返回 instrument_id 列表."""
        service = MagicMock()
        service.get_universe.return_value = [100, 200, 300]
        facade = UniverseQueryFacade(metadata_service=service)
        result = facade.get_members("csi300", asof="2025-01-01")
        assert result == [100, 200, 300]
        service.get_universe.assert_called_once_with("csi300", "2025-01-01")

    def test_no_asof(self) -> None:
        """不传 asof 调用 get_universe(universe_id, None)."""
        service = MagicMock()
        service.get_universe.return_value = [100]
        facade = UniverseQueryFacade(metadata_service=service)
        facade.get_members("csi300")
        service.get_universe.assert_called_once_with("csi300", None)
