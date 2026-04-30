"""Tests for StrategyQueryFacade — 封装 StrategyCatalogService 只读查询."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.contracts import StrategySpecInfo
from ditto_application.query.strategy import StrategyQueryFacade
from ditto_data.models.strategy import StrategySpecRecord


def _make_record(
    strategy_id: str = "s-1",
    name: str = "test",
    version: int = 1,
    status: str = "draft",
) -> StrategySpecRecord:
    return StrategySpecRecord(
        strategy_id=strategy_id,
        name=name,
        spec_json={},
        version=version,
        status=status,
    )


def _make_spec_info(
    strategy_id: str = "s-1",
    name: str = "test",
    version: int = 1,
    status: str = "draft",
) -> StrategySpecInfo:
    return StrategySpecInfo(
        strategy_id=strategy_id,
        name=name,
        spec_json={},
        version=version,
        status=status,
    )


class TestStrategyQueryFacadeListSpecs:
    """StrategyQueryFacade.list_specs 委托 catalog_service 并转换为 StrategySpecInfo."""

    def test_returns_spec_info_from_service(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        records = [_make_record("s-1"), _make_record("s-2")]
        service.list_specs.return_value = records
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.list_specs()

        expected = [_make_spec_info("s-1"), _make_spec_info("s-2")]
        assert result == expected
        service.list_specs.assert_called_once()

    def test_returns_empty_list(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        service.list_specs.return_value = []
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.list_specs()

        assert result == []


class TestStrategyQueryFacadeGetSpec:
    """StrategyQueryFacade.get_spec — 委托 catalog_service 并转换为 StrategySpecInfo."""

    def test_returns_spec_info(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        record = _make_record("s-1")
        service.get_spec.return_value = record
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.get_spec("s-1")

        assert result == _make_spec_info("s-1")
        service.get_spec.assert_called_once_with("s-1", None)

    def test_returns_none_when_not_found(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        service.get_spec.return_value = None
        facade = StrategyQueryFacade(catalog_service=service)

        result = facade.get_spec("missing")

        assert result is None
        service.get_spec.assert_called_once_with("missing", None)

    def test_passes_version_to_service(self) -> None:
        service = MagicMock(spec=["list_specs", "get_spec", "list_versions"])
        service.get_spec.return_value = _make_record()
        facade = StrategyQueryFacade(catalog_service=service)

        facade.get_spec("s-1", version=3)

        service.get_spec.assert_called_once_with("s-1", 3)
