"""coordinator_factory 单元测试 — create_coordinator 上下文管理器."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.coordinator_factory import (
    CoordinatorRuntimeContext,
    CoordinatorServices,
    create_coordinator,
)
from ditto_application.processes.ingestion.source_selection import (
    AutoSourceIngestionCoordinator,
)
from ditto_data.catalog import (
    InMemoryDataCatalog,
)
from ditto_data.models import Source
from ditto_data.models.ingestion import IngestionResult
from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_data.sources.registry import SourceRegistry
from ditto_kernel.instrument import InstrumentIngestParams
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
)


def _set_source(
    services: CoordinatorServices, name: str, source: object | None
) -> None:
    """测试替身注入：source_accessor 运行时是 MagicMock，静态声明是
    SourceAccessor——替身替换经本单点放宽，不逐处 cast。"""
    cast("Any", services.source_accessor).__setattr__(name, source)


def _make_services() -> CoordinatorServices:
    """创建 create_coordinator 所需的 mock 服务."""
    return CoordinatorServices(
        metadata_service=MagicMock(),
        market_service=MagicMock(),
        market_write_service=MagicMock(),
        fundamental_store=MagicMock(),
        capital_store=MagicMock(),
        macro_service=MagicMock(),
        source_accessor=MagicMock(),
        ingestion_log_store=MagicMock(),
    )


def _make_services_with_source_registry(
    registry: SourceRegistry,
) -> CoordinatorServices:
    """创建带 SourceRegistry 的服务聚合."""
    return CoordinatorServices(
        metadata_service=MagicMock(),
        market_service=MagicMock(),
        market_write_service=MagicMock(),
        fundamental_store=MagicMock(),
        capital_store=MagicMock(),
        macro_service=MagicMock(),
        source_accessor=MagicMock(),
        ingestion_log_store=MagicMock(),
        source_registry=registry,
    )


@contextmanager
def _patch_coordinator_init():
    """patch IngestionCoordinator.__init__ 避免真实初始化."""
    with patch(
        "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_cls, mock_instance


class TestCreateCoordinatorStringSource:
    """字符串 source_name → Source 枚举 → 创建协调器."""

    def test_valid_string_creates_coordinator(self) -> None:
        services = _make_services()
        mock_source = MagicMock()
        _set_source(services, "tushare", mock_source)

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
    """无效 source_name 抛出 AppProcessError."""

    def test_invalid_string_raises_app_process_error(self) -> None:
        services = _make_services()
        with (
            _patch_coordinator_init() as (mock_cls, _),
            pytest.raises(AppProcessError, match="Unknown source") as exc_info,
        ):
            with create_coordinator(services, source_name="invalid_source"):
                pass

        mock_cls.assert_not_called()
        assert "invalid_source" in str(exc_info.value)


class TestCreateCoordinatorFredDegradation:
    """FRED 数据源不可用时降级."""

    def test_fred_unavailable_degrades_gracefully(self) -> None:
        services = _make_services()
        _set_source(services, "tushare", MagicMock())
        _set_source(services, "fred", None)

        with _patch_coordinator_init() as (mock_cls, mock_instance):
            with create_coordinator(services, source_name="tushare") as coordinator:
                assert coordinator is mock_instance

            call_kwargs = mock_cls.call_args
            assert call_kwargs.kwargs["fred_source"] is None

    def test_fred_available(self) -> None:
        services = _make_services()
        mock_fred = MagicMock()
        _set_source(services, "tushare", MagicMock())
        _set_source(services, "fred", mock_fred)

        with _patch_coordinator_init() as (mock_cls, _):
            with create_coordinator(services, source_name="tushare"):
                pass

            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["fred_source"] is mock_fred


class TestCreateCoordinatorSourceRegistryRouting:
    """按 source_name + Fetcher Protocol 选择数据源."""

    def test_fred_source_routes_macro_fetcher_only(self) -> None:
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)

        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)

        with _patch_coordinator_init() as (mock_cls, _):
            with create_coordinator(services, source_name="fred"):
                pass

            call_kwargs = mock_cls.call_args.kwargs
            fetchers = call_kwargs["fetchers"]
            assert fetchers.metadata is tushare_source
            assert fetchers.market is tushare_source
            assert fetchers.fundamental is tushare_source
            assert fetchers.capital is tushare_source
            assert fetchers.macro is fred_source
            assert call_kwargs["config"].source_name == "fred"

    def test_auto_source_routes_macro_repair_to_missing_fred_asset(self) -> None:
        """source=auto 时，macro 多源数据集按 catalog/SLA 选择修复源."""
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)
        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)
        with _evidence_support.evidence_stores() as stores:
            # tushare 请求过该日期但从未完成 → stale;fred 从未覆盖 → missing。
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="a" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
                complete=False,
            )
            tushare_coordinator = MagicMock(name="tushare_coordinator")
            fred_coordinator = MagicMock(name="fred_coordinator")

            with patch(
                "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator",
                side_effect=[tushare_coordinator, fred_coordinator],
            ):
                with create_coordinator(
                    services,
                    source_name="auto",
                    runtime=CoordinatorRuntimeContext(
                        snapshot_reader=stores.snapshots,
                        lifecycle_reader=stores.lifecycle,
                    ),
                ) as coordinator:
                    coordinator.ingest_date("macro_indicators", "2024-12-27")

        tushare_coordinator.ingest_date.assert_not_called()
        fred_coordinator.ingest_date.assert_called_once_with(
            "macro_indicators",
            "2024-12-27",
            False,
        )

    def test_auto_source_keeps_single_source_datasets_on_default_source(self) -> None:
        """source=auto 不应把 Tushare-only 数据集误路由到 FRED."""
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)
        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)
        tushare_coordinator = MagicMock(name="tushare_coordinator")
        fred_coordinator = MagicMock(name="fred_coordinator")

        with patch(
            "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator",
            side_effect=[tushare_coordinator, fred_coordinator],
        ):
            with create_coordinator(
                services,
                source_name="auto",
                runtime=CoordinatorRuntimeContext(catalog_reader=InMemoryDataCatalog()),
            ) as coordinator:
                coordinator.ingest_date("stock_daily", "2024-12-27")

        tushare_coordinator.ingest_date.assert_called_once_with(
            "stock_daily",
            "2024-12-27",
            False,
        )
        fred_coordinator.ingest_date.assert_not_called()

    def test_auto_source_range_uses_dataset_schedule_and_delegates_per_date(
        self,
    ) -> None:
        """source=auto 的 range 摄取应逐日选择 source，而非落回默认单源 range."""
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)
        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)
        # metadata_service 运行时是 MagicMock；返回值注入单点放宽。
        cast("Any", services.metadata_service).list_trading_days.return_value = [
            "2024-12-27",
            "2024-12-30",
        ]
        tushare_coordinator = MagicMock(name="tushare_coordinator")
        fred_coordinator = MagicMock(name="fred_coordinator")

        with patch(
            "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator",
            side_effect=[tushare_coordinator, fred_coordinator],
        ):
            with create_coordinator(
                services,
                source_name="auto",
                runtime=CoordinatorRuntimeContext(catalog_reader=InMemoryDataCatalog()),
            ) as coordinator:
                coordinator.ingest_range("stock_daily", "2024-12-27", "2024-12-31")

        tushare_coordinator.ingest_range.assert_not_called()
        fred_coordinator.ingest_range.assert_not_called()
        assert tushare_coordinator.ingest_date.call_args_list == [
            call("stock_daily", "2024-12-27", False),
            call("stock_daily", "2024-12-30", False),
        ]
        fred_coordinator.ingest_date.assert_not_called()

    def test_auto_source_range_routes_each_macro_date_independently(self) -> None:
        """source=auto 的 range 摄取应允许同一数据集不同日期选择不同源."""
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)
        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)
        with _evidence_support.evidence_stores() as stores:
            # 12-27 未完成(stale)→ fred;12-28 已完成(fresh)→ tushare。
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="b" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
                complete=False,
            )
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-28",
                request_end="2024-12-28",
                checksum="c" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
            )
            tushare_coordinator = MagicMock(name="tushare_coordinator")
            fred_coordinator = MagicMock(name="fred_coordinator")

            with patch(
                "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator",
                side_effect=[tushare_coordinator, fred_coordinator],
            ):
                with create_coordinator(
                    services,
                    source_name="auto",
                    runtime=CoordinatorRuntimeContext(
                        snapshot_reader=stores.snapshots,
                        lifecycle_reader=stores.lifecycle,
                    ),
                ) as coordinator:
                    coordinator.ingest_range(
                        "macro_indicators",
                        "2024-12-27",
                        "2024-12-28",
                    )

            tushare_coordinator.ingest_range.assert_not_called()
            fred_coordinator.ingest_range.assert_not_called()
            tushare_coordinator.ingest_date.assert_called_once_with(
                "macro_indicators",
                "2024-12-28",
                False,
            )
            fred_coordinator.ingest_date.assert_called_once_with(
                "macro_indicators",
                "2024-12-27",
                False,
            )

    def test_auto_source_instrument_ingestion_uses_catalog_source_selection(
        self,
    ) -> None:
        """source=auto 的 instrument 摄取也应按 catalog/SLA 选择 source."""
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)
        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)
        with _evidence_support.evidence_stores() as stores:
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-31",
                request_end="2024-12-31",
                checksum="d" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
                complete=False,
            )
            tushare_coordinator = MagicMock(name="tushare_coordinator")
            fred_coordinator = MagicMock(name="fred_coordinator")
            params = InstrumentIngestParams(
                ticker="CPI",
                start_date="2024-12-31",
                end_date="2024-12-31",
            )

            with patch(
                "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator",
                side_effect=[tushare_coordinator, fred_coordinator],
            ):
                with create_coordinator(
                    services,
                    source_name="auto",
                    runtime=CoordinatorRuntimeContext(
                        snapshot_reader=stores.snapshots,
                        lifecycle_reader=stores.lifecycle,
                    ),
                ) as coordinator:
                    coordinator.ingest_by_instrument("macro_indicators", params)

            tushare_coordinator.ingest_by_instrument.assert_not_called()
            fred_coordinator.ingest_by_instrument.assert_called_once_with(
                "macro_indicators",
                params,
                False,
            )

    def test_auto_source_instrument_range_routes_each_date_independently(
        self,
    ) -> None:
        """instrument-level source=auto 应逐日选择 source，而非整段单源委派."""
        registry = SourceRegistry()
        tushare_source = MagicMock(name="tushare_source")
        fred_source = MagicMock(name="fred_source")
        for protocol in (
            MetadataFetcher,
            MarketFetcher,
            FundamentalFetcher,
            CapitalFetcher,
            MacroFetcher,
        ):
            registry.register("tushare", protocol, tushare_source)
        registry.register("fred", MacroFetcher, fred_source)
        services = _make_services_with_source_registry(registry)
        _set_source(services, "tushare", tushare_source)
        _set_source(services, "fred", fred_source)
        with _evidence_support.evidence_stores() as stores:
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="e" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
                complete=False,
            )
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-28",
                request_end="2024-12-28",
                checksum="f" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
            )
            tushare_coordinator = MagicMock(name="tushare_coordinator")
            fred_coordinator = MagicMock(name="fred_coordinator")
            fred_coordinator.ingest_by_instrument.return_value = IngestionResult(
                dataset="macro_indicators",
                trade_date="2024-12-27",
                status="success",
                row_count=1,
            )
            tushare_coordinator.ingest_by_instrument.return_value = IngestionResult(
                dataset="macro_indicators",
                trade_date="2024-12-28",
                status="success",
                row_count=2,
            )
            params = InstrumentIngestParams(
                ticker="CPI",
                start_date="2024-12-27",
                end_date="2024-12-28",
            )

            with patch(
                "ditto_application.processes.ingestion.coordinator_factory.IngestionCoordinator",
                side_effect=[tushare_coordinator, fred_coordinator],
            ):
                with create_coordinator(
                    services,
                    source_name="auto",
                    runtime=CoordinatorRuntimeContext(
                        snapshot_reader=stores.snapshots,
                        lifecycle_reader=stores.lifecycle,
                    ),
                ) as coordinator:
                    result = coordinator.ingest_by_instrument(
                        "macro_indicators", params
                    )

        fred_coordinator.ingest_by_instrument.assert_called_once_with(
            "macro_indicators",
            InstrumentIngestParams(
                ticker="CPI",
                start_date="2024-12-27",
                end_date="2024-12-27",
            ),
            False,
        )
        tushare_coordinator.ingest_by_instrument.assert_called_once_with(
            "macro_indicators",
            InstrumentIngestParams(
                ticker="CPI",
                start_date="2024-12-28",
                end_date="2024-12-28",
            ),
            False,
        )
        assert result == IngestionResult(
            dataset="macro_indicators",
            trade_date="2024-12-27",
            status="success",
            row_count=3,
            message=(
                "instrument range auto-source completed: success=2, failed=0, skipped=0"
            ),
        )

    def test_auto_source_fails_closed_when_selected_source_is_unsupported(
        self,
    ) -> None:
        """source=auto 选中不支持当前 dataset 的来源时应在编排层 fail closed."""
        fred_coordinator = MagicMock(name="fred_coordinator")
        coordinator = AutoSourceIngestionCoordinator(
            {"fred": fred_coordinator},
        )

        with pytest.raises(AppProcessError, match="does not support dataset") as exc:
            coordinator.ingest_date("stock_daily", "2024-12-27")

        assert exc.value.details == {
            "field": "source_name",
            "value": "fred",
            "dataset": "stock_daily",
            "supported": ["tushare", "fuyao"],
            "operation": "ingest_date",
            "selection_date": "2024-12-27",
        }
        fred_coordinator.ingest_date.assert_not_called()

    def test_auto_source_range_fails_closed_with_selection_date_when_unsupported(
        self,
    ) -> None:
        """range 内单日选到 unsupported source 时，错误必须指明 selection date."""
        fred_coordinator = MagicMock(name="fred_coordinator")
        coordinator = AutoSourceIngestionCoordinator(
            {"fred": fred_coordinator},
            date_range_lister=lambda _dataset, _start, _end: [
                "2024-12-27",
                "2024-12-30",
            ],
        )

        with pytest.raises(AppProcessError, match="does not support dataset") as exc:
            coordinator.ingest_range("stock_daily", "2024-12-27", "2024-12-30")

        assert exc.value.details == {
            "field": "source_name",
            "value": "fred",
            "dataset": "stock_daily",
            "supported": ["tushare", "fuyao"],
            "operation": "ingest_date",
            "selection_date": "2024-12-27",
        }
        fred_coordinator.ingest_date.assert_not_called()

    def test_auto_source_range_fallback_fails_closed_when_default_unsupported(
        self,
    ) -> None:
        """无逐日枚举器时，range fallback 也必须复用 source capability guard."""
        fred_coordinator = MagicMock(name="fred_coordinator")
        coordinator = AutoSourceIngestionCoordinator(
            {"fred": fred_coordinator},
            date_range_lister=None,
        )

        with pytest.raises(AppProcessError, match="does not support dataset") as exc:
            coordinator.ingest_range("stock_daily", "2024-12-27", "2024-12-30")

        assert exc.value.details == {
            "field": "source_name",
            "value": "fred",
            "dataset": "stock_daily",
            "supported": ["tushare", "fuyao"],
            "operation": "ingest_range",
            "start_date": "2024-12-27",
            "end_date": "2024-12-30",
        }
        fred_coordinator.ingest_range.assert_not_called()

    def test_auto_source_instrument_fails_closed_when_selected_source_is_unsupported(
        self,
    ) -> None:
        """instrument-level source=auto 也必须复用同一 source capability guard."""
        fred_coordinator = MagicMock(name="fred_coordinator")
        coordinator = AutoSourceIngestionCoordinator(
            {"fred": fred_coordinator},
        )
        params = InstrumentIngestParams(
            ticker="000001.SZ",
            start_date="2024-12-01",
            end_date="2024-12-27",
        )

        with pytest.raises(AppProcessError, match="does not support dataset") as exc:
            coordinator.ingest_by_instrument("stock_daily", params)

        assert exc.value.details == {
            "field": "source_name",
            "value": "fred",
            "dataset": "stock_daily",
            "supported": ["tushare", "fuyao"],
            "operation": "ingest_by_instrument",
            "selection_date": "2024-12-27",
        }
        fred_coordinator.ingest_by_instrument.assert_not_called()


class TestCreateCoordinatorCatalog:
    """catalog writer 运行时注入."""

    def test_passes_catalog_writer_to_config(self) -> None:
        services = _make_services()
        _set_source(services, "tushare", MagicMock())
        catalog = InMemoryDataCatalog()

        with _patch_coordinator_init() as (mock_cls, _):
            with create_coordinator(
                services,
                source_name="tushare",
                runtime=CoordinatorRuntimeContext(catalog_writer=catalog),
            ):
                pass

            config = mock_cls.call_args.kwargs["config"]
            assert config.catalog_writer is catalog

    def test_passes_catalog_reader_to_config(self) -> None:
        services = _make_services()
        _set_source(services, "tushare", MagicMock())
        catalog = InMemoryDataCatalog()

        with _patch_coordinator_init() as (mock_cls, _):
            with create_coordinator(
                services,
                source_name="tushare",
                runtime=CoordinatorRuntimeContext(catalog_reader=catalog),
            ):
                pass

            config = mock_cls.call_args.kwargs["config"]
            assert config.catalog_reader is catalog
