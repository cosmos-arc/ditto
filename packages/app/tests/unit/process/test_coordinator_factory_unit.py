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
        services.source_service.get_source.return_value = mock_source

        with _patch_coordinator_init() as (mock_cls, mock_instance):
            with create_coordinator(
                services,
                source_name="tushare",
            ) as coordinator:
                assert coordinator is mock_instance

            # 验证 source_service.get_source 被正确调用
            services.source_service.get_source.assert_any_call(Source.TUSHARE)
            # 验证 IngestionCoordinator 被创建
            mock_cls.assert_called_once()
            assert mock_cls.call_args.kwargs["source"] is mock_source

    def test_case_insensitive(self) -> None:
        services = _make_services()
        with _patch_coordinator_init() as (_, _):
            with create_coordinator(services, source_name="TUSHARE"):
                pass
            services.source_service.get_source.assert_any_call(Source.TUSHARE)


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

            services.source_service.get_source.assert_any_call(Source.TUSHARE)
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

        # 不应创建协调器
        mock_cls.assert_not_called()
        assert "invalid_source" in str(exc_info.value)


class TestCreateCoordinatorFredDegradation:
    """FRED 数据源不可用时降级."""

    def test_fred_unavailable_degrades_gracefully(self) -> None:
        services = _make_services()

        # 主数据源正常，FRED 不可用
        def get_source_side_effect(source: Source) -> MagicMock:
            if source == Source.FRED:
                raise RuntimeError("FRED not configured")
            return MagicMock()

        services.source_service.get_source.side_effect = get_source_side_effect

        with _patch_coordinator_init() as (mock_cls, mock_instance):
            with create_coordinator(services, source_name="tushare") as coordinator:
                assert coordinator is mock_instance

            # 验证协调器创建时 fred_source 为 None
            call_kwargs = mock_cls.call_args
            config = call_kwargs.kwargs["config"]
            assert config.fred_source is None

    def test_fred_available(self) -> None:
        services = _make_services()
        mock_fred = MagicMock()
        services.source_service.get_source.return_value = MagicMock()

        # FRED 可用时返回 mock
        with _patch_coordinator_init() as (mock_cls, _):
            call_count = 0
            original_source = MagicMock()

            def get_source_side_effect(source: Source) -> MagicMock:
                nonlocal call_count
                call_count += 1
                if source == Source.FRED:
                    return mock_fred
                return original_source

            services.source_service.get_source.side_effect = get_source_side_effect

            with create_coordinator(services, source_name="tushare"):
                pass

            assert call_count >= 2
            config = mock_cls.call_args.kwargs["config"]
            assert config.fred_source is mock_fred
            assert isinstance(mock_fred, MagicMock)
