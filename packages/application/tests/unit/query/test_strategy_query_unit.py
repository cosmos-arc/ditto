"""Tests for StrategyQueryFacade — 封装 StrategyCatalogService 只读查询."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.contracts import (
    StrategyActiveInfo,
    StrategySpecInfo,
    StrategyVersionInfo,
)
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_strategy.governance.models import (
    ReviewOutcome,
    StrategyActivePointer,
    StrategyVersion,
    StrategyVersionState,
    StrategyVersionStateRecord,
)
from ditto_strategy.models import StrategySpecRecord


def _make_record(
    strategy_id: str = "s-1",
    name: str = "test",
    version: int = 1,
) -> StrategySpecRecord:
    return StrategySpecRecord(
        strategy_id=strategy_id,
        name=name,
        spec_json={},
        version=version,
    )


def _make_spec_info(
    strategy_id: str = "s-1",
    name: str = "test",
    version: int = 1,
    status: str = "unknown",
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


def _make_version(version: int = 1, parent: int | None = None) -> StrategyVersion:
    return StrategyVersion(
        strategy_id="s-1",
        version=version,
        parent_version=parent,
        schema_version=1,
        spec_hash="a" * 64,
        created_at="2026-07-25T00:00:00Z",
    )


def _make_state(
    version: int = 1,
    state: StrategyVersionState = StrategyVersionState.PUBLISHED,
    review: ReviewOutcome = ReviewOutcome.APPROVED,
) -> StrategyVersionStateRecord:
    return StrategyVersionStateRecord(
        strategy_id="s-1",
        version=version,
        state=state,
        review_outcome=review,
        state_revision=1,
    )


def _make_pointer(version: int = 1, revision: int = 1) -> StrategyActivePointer:
    return StrategyActivePointer(
        strategy_id="s-1",
        active_version=version,
        pointer_revision=revision,
        activation_event_id="e1",
    )


class TestStrategyQueryFacadeListVersions:
    """list_versions projects governance versions + state into StrategyVersionInfo."""

    def test_returns_version_info_from_governance(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        state_reader = MagicMock(spec=["get_state"])
        governance_reader.list_versions.return_value = (_make_version(2, parent=1),)
        state_reader.get_state.return_value = _make_state(2)
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            version_state_reader=state_reader,
            governance_version_reader=governance_reader,
        )

        result = facade.list_versions("s-1")

        assert result == [
            StrategyVersionInfo(
                strategy_id="s-1",
                version=2,
                parent_version=1,
                spec_hash="a" * 64,
                state="published",
                review_outcome="approved",
                created_at="2026-07-25T00:00:00Z",
            )
        ]
        governance_reader.list_versions.assert_called_once_with("s-1")
        state_reader.get_state.assert_called_once_with("s-1", 2)

    def test_returns_empty_when_no_versions(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.list_versions.return_value = ()
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec"]),
            governance_version_reader=governance_reader,
        )

        assert facade.list_versions("s-1") == []

    def test_returns_empty_without_governance_reader(self) -> None:
        facade = StrategyQueryFacade(MagicMock(spec=["list_specs", "get_spec"]))

        assert facade.list_versions("s-1") == []


class TestStrategyQueryFacadeGetActive:
    """get_active joins the active pointer with the published payload."""

    def test_returns_pointer_and_payload(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        catalog = MagicMock(spec=["list_specs", "get_spec", "get_active_published"])
        governance_reader.get_active_pointer.return_value = _make_pointer(
            version=2, revision=3
        )
        catalog.get_active_published.return_value = _make_record("s-1", version=2)
        facade = StrategyQueryFacade(
            catalog, governance_version_reader=governance_reader
        )

        result = facade.get_active("s-1")

        assert result is not None
        assert isinstance(result, StrategyActiveInfo)
        assert result.active_version == 2
        assert result.pointer_revision == 3
        assert result.spec.version == 2
        assert result.spec.status == "active"
        catalog.get_active_published.assert_called_once_with("s-1")

    def test_returns_none_when_no_pointer(self) -> None:
        governance_reader = MagicMock(spec=["list_versions", "get_active_pointer"])
        governance_reader.get_active_pointer.return_value = None
        facade = StrategyQueryFacade(
            MagicMock(spec=["list_specs", "get_spec", "get_active_published"]),
            governance_version_reader=governance_reader,
        )

        assert facade.get_active("s-1") is None

    def test_returns_none_without_governance_reader(self) -> None:
        facade = StrategyQueryFacade(MagicMock(spec=["list_specs", "get_spec"]))

        assert facade.get_active("s-1") is None
