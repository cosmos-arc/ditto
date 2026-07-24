"""Tests for StrategyCatalogService -- 策略 Spec CRUD 与状态治理."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from pytest_mock import MockerFixture


def _make_spec(**overrides: object) -> StrategySpecRecord:
    """构建测试用 StrategySpecRecord."""
    defaults: dict[str, object] = {
        "strategy_id": "strat.momentum_20d",
        "name": "20 日动量策略",
        "spec_json": {"lookback": 20, "instrument_type": "etf"},
        "version": 1,
        "status": "draft",
        "created_at": "2026-03-23T10:00:00+08:00",
        "updated_at": "2026-03-23T10:00:00+08:00",
        "tags": ("momentum", "etf"),
    }
    return StrategySpecRecord(**{**defaults, **overrides})


# ── Model Tests ──────────────────────────────────────────────────────────────


class TestStrategySpecRecord:
    """StrategySpecRecord 模型测试."""

    def test_create_record(self) -> None:
        """正确创建记录."""
        record = _make_spec()
        assert record.strategy_id == "strat.momentum_20d"
        assert record.name == "20 日动量策略"
        assert record.version == 1
        assert record.status == "draft"
        assert record.tags == ("momentum", "etf")

    def test_default_values(self) -> None:
        """默认值正确."""
        record = StrategySpecRecord(
            strategy_id="strat.test",
            name="测试策略",
            spec_json={},
        )
        assert record.version == 1
        assert record.status == "draft"
        assert record.created_at == ""
        assert record.updated_at == ""
        assert record.tags == ()

    def test_record_is_frozen(self) -> None:
        """frozen=True 不可变."""
        record = _make_spec()
        with pytest.raises(FrozenInstanceError):
            record.status = "published"  # type: ignore[misc]


# ── Service Tests ────────────────────────────────────────────────────────────


class TestStrategyCatalogService:
    """StrategyCatalogService 服务测试."""

    def test_save_spec_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """save_spec() 委托给 writer.save()."""
        spec = _make_spec()
        writer = mocker.Mock()
        service = StrategyCatalogService(
            reader=mocker.Mock(),
            writer=writer,
        )

        service.save_spec(spec)

        writer.save.assert_called_once_with(spec)

    def test_get_spec_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """get_spec() 委托给 reader.get_spec()."""
        spec = _make_spec()
        reader = mocker.Mock()
        reader.get_spec = mocker.Mock(return_value=spec)
        service = StrategyCatalogService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.get_spec("strat.momentum_20d", 1)

        assert result is spec
        reader.get_spec.assert_called_once_with("strat.momentum_20d", 1)

    def test_get_spec_default_version(self, mocker: MockerFixture) -> None:
        """get_spec(version=None) 传递 None 给 reader."""
        reader = mocker.Mock()
        reader.get_spec = mocker.Mock(return_value=None)
        service = StrategyCatalogService(
            reader=reader,
            writer=mocker.Mock(),
        )

        service.get_spec("strat.momentum_20d")

        reader.get_spec.assert_called_once_with("strat.momentum_20d", None)

    def test_get_spec_not_found(self, mocker: MockerFixture) -> None:
        """get_spec() 查询不存在时返回 None."""
        reader = mocker.Mock()
        reader.get_spec = mocker.Mock(return_value=None)
        service = StrategyCatalogService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.get_spec("strat.nonexistent", 99)

        assert result is None
        reader.get_spec.assert_called_once_with("strat.nonexistent", 99)

    def test_list_specs_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """list_specs() 委托给 reader.list_specs()."""
        specs = [_make_spec(strategy_id="s1"), _make_spec(strategy_id="s2")]
        reader = mocker.Mock()
        reader.list_specs = mocker.Mock(return_value=specs)
        service = StrategyCatalogService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.list_specs()

        assert result == specs
        reader.list_specs.assert_called_once_with()

    def test_list_versions_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """list_versions() 委托给 reader.list_versions()."""
        versions = [
            _make_spec(strategy_id="s1", version=1),
            _make_spec(strategy_id="s1", version=2),
        ]
        reader = mocker.Mock()
        reader.list_versions = mocker.Mock(return_value=versions)
        service = StrategyCatalogService(
            reader=reader,
            writer=mocker.Mock(),
        )

        result = service.list_versions("s1")

        assert result == versions
        reader.list_versions.assert_called_once_with("s1")

    def test_publish_spec_calls_writer(self, mocker: MockerFixture) -> None:
        """publish_spec() 调用 writer.update_status 并传入 published 状态."""
        writer = mocker.Mock()
        writer.update_status = mocker.Mock(return_value=True)
        service = StrategyCatalogService(
            reader=mocker.Mock(),
            writer=writer,
        )

        result = service.publish_spec("strat.momentum_20d", 1)

        assert result is True
        writer.update_status.assert_called_once_with(
            "strat.momentum_20d", 1, "published"
        )

    def test_publish_spec_not_found(self, mocker: MockerFixture) -> None:
        """publish_spec() 策略不存在时返回 False."""
        writer = mocker.Mock()
        writer.update_status = mocker.Mock(return_value=False)
        service = StrategyCatalogService(
            reader=mocker.Mock(),
            writer=writer,
        )

        result = service.publish_spec("strat.nonexistent", 99)

        assert result is False
        writer.update_status.assert_called_once_with(
            "strat.nonexistent", 99, "published"
        )

    def test_get_active_published_resolves_pointer_to_payload(
        self, mocker: MockerFixture
    ) -> None:
        """get_active_published resolves governance pointer to spec payload."""
        spec = _make_spec(version=2)
        reader = mocker.Mock()
        reader.get_spec = mocker.Mock(return_value=spec)
        active_reader = mocker.Mock()
        active_reader.get_active_pointer = mocker.Mock(
            return_value=mocker.Mock(active_version=2)
        )
        service = StrategyCatalogService(
            reader=reader,
            writer=mocker.Mock(),
            active_pointer_reader=active_reader,
        )

        result = service.get_active_published("strat.momentum_20d")

        assert result is spec
        active_reader.get_active_pointer.assert_called_once_with("strat.momentum_20d")
        reader.get_spec.assert_called_once_with("strat.momentum_20d", 2)

    def test_get_active_published_returns_none_without_reader(
        self, mocker: MockerFixture
    ) -> None:
        """get_active_published returns None when no active pointer reader wired."""
        service = StrategyCatalogService(reader=mocker.Mock(), writer=mocker.Mock())

        assert service.get_active_published("strat.x") is None

    def test_get_active_published_returns_none_when_no_pointer(
        self, mocker: MockerFixture
    ) -> None:
        """get_active_published returns None when no active pointer exists."""
        active_reader = mocker.Mock()
        active_reader.get_active_pointer = mocker.Mock(return_value=None)
        service = StrategyCatalogService(
            reader=mocker.Mock(),
            writer=mocker.Mock(),
            active_pointer_reader=active_reader,
        )

        assert service.get_active_published("strat.x") is None

    def test_get_version_state_returns_state_string(
        self, mocker: MockerFixture
    ) -> None:
        """get_version_state returns governance lifecycle state as string."""
        state_record = mocker.Mock()
        state_record.state = "published"
        version_state_reader = mocker.Mock()
        version_state_reader.get_state = mocker.Mock(return_value=state_record)
        service = StrategyCatalogService(
            reader=mocker.Mock(),
            writer=mocker.Mock(),
            version_state_reader=version_state_reader,
        )

        assert service.get_version_state("strat.x", 2) == "published"
        version_state_reader.get_state.assert_called_once_with("strat.x", 2)

    def test_get_version_state_returns_none_without_reader(
        self, mocker: MockerFixture
    ) -> None:
        """get_version_state returns None when no version state reader wired."""
        service = StrategyCatalogService(reader=mocker.Mock(), writer=mocker.Mock())

        assert service.get_version_state("strat.x", 2) is None

    def test_get_version_state_returns_none_when_no_state(
        self, mocker: MockerFixture
    ) -> None:
        """get_version_state returns None when version has no governance state."""
        version_state_reader = mocker.Mock()
        version_state_reader.get_state = mocker.Mock(return_value=None)
        service = StrategyCatalogService(
            reader=mocker.Mock(),
            writer=mocker.Mock(),
            version_state_reader=version_state_reader,
        )

        assert service.get_version_state("strat.x", 2) is None
