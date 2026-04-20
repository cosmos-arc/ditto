"""coordinator_factory 单元测试 — create_coordinator 上下文管理器."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from ditto_app.process.ingestion.coordinator_factory import (
    CoordinatorServices,
    create_coordinator,
)
from ditto_data.models import Source


def _make_services() -> CoordinatorServices:
    """创建 create_coordinator 所需的 mock 服务."""
    return CoordinatorServices(
        metadata_service=MagicMock(),
        market_service=MagicMock(),
        market_write_service=MagicMock(),
        fundamental_service=MagicMock(),
        capital_service=MagicMock(),
        macro_service=MagicMock(),
        source_service=MagicMock(),
        ingestion_log_service=MagicMock(),
    )


@contextmanager
def _patch_coordinator_init():
    """patch IngestionCoordinator.__init__ 避免真实初始化."""
    with patch(
        "ditto_app.process.ingestion.coordinator_factory.IngestionCoordinator"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_cls, mock_instance


class TestCreateCoordinatorStringSource:
    """字符串 source_name → Source 枚举 → 创建协调器."""

    def test_valid_string_creates_coordinator(self) -> None:
        services = _make_services()
        mock_source = MagicMock()
        services.source_service.tushare = mock_source

        with _patch_coordinator_init() as (mock_cls, mock_instance):
            with create_coordinator(
                services,
                source_name="tushare",
            ) as coordinator:
                assert coordinator is mock_instance

            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["fetchers"].metadata is mock_source

    def test_case_insensitive(self) -> None:
        services = _make_services()
        with _patch_coordinator_init() as (_, _):
            with create_coordinator(services, source_name="TUSHARE"):
                pass


class TestCreateCoordinatorEnumSource:
    """Source 枚举直接传入."""

    def test_enum_source_creates_coordinator(self) -> None:
        services = _make_services()
        with _patch_coordinator_init() as (mock_cls, mock_instance):
            with create_coordinator(
                services,
                source_name=Source.TUSHARE,
            ) as coordinator:
                assert coordinator is mock_instance

            mock_cls.assert_called_once()


class TestCreateCoordinatorInvalidSource:
    """无效 source_name 抛出 ValueError."""

    def test_invalid_string_raises_value_error(self) -> None:
        services = _make_services()
        with (
            _patch_coordinator_init() as (mock_cls, _),
            pytest.raises(ValueError, match="Unknown source") as exc_info,
        ):
            with create_coordinator(services, source_name="invalid_source"):
                pass

        mock_cls.assert_not_called()
        assert "invalid_source" in str(exc_info.value)


class TestCreateCoordinatorFredDegradation:
    """FRED 数据源不可用时降级."""

    def test_fred_unavailable_degrades_gracefully(self) -> None:
        services = _make_services()
        services.source_service.tushare = MagicMock()
        services.source_service.fred = None

        with _patch_coordinator_init() as (mock_cls, mock_instance):
            with create_coordinator(services, source_name="tushare") as coordinator:
                assert coordinator is mock_instance

            call_kwargs = mock_cls.call_args
            assert call_kwargs.kwargs["fred_source"] is None

    def test_fred_available(self) -> None:
        services = _make_services()
        mock_fred = MagicMock()
        services.source_service.tushare = MagicMock()
        services.source_service.fred = mock_fred

        with _patch_coordinator_init() as (mock_cls, _):
            with create_coordinator(services, source_name="tushare"):
                pass

            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["fred_source"] is mock_fred
