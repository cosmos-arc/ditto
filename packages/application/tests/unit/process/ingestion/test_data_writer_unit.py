"""Tests for IngestionDataWriter."""

from datetime import date

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_metadata_service(mocker):
    """创建 Mock MetadataService。"""
    service = mocker.Mock()
    service.is_trading_day.return_value = True

    # Instrument 相关方法
    service.instrument.register_instruments_batch = mocker.Mock()
    service.instrument.resolve_or_create_instruments_batch = mocker.Mock()
    service.instrument.resolve_instrument_ids_batch = mocker.Mock(return_value={})
    service.instrument.save_industry_classification = mocker.Mock(return_value=1)
    service.instrument.save_industry_mapping = mocker.Mock(return_value=1)

    def register_side_effect(df, source, asset_class, **kwargs):
        _ = df, source, kwargs
        return (f"instrument_store:{asset_class}_basic", f"checksum_{asset_class}")

    def resolve_side_effect(df, source, asset_class, **kwargs):
        _ = source, kwargs
        source_tickers = df["source_ticker"].to_list()
        return {source_tickers[0]: 1_000_000}

    service.instrument.register_instruments_batch.side_effect = register_side_effect
    service.instrument.resolve_or_create_instruments_batch.side_effect = (
        resolve_side_effect
    )

    return service


@pytest.fixture
def mock_market_write_service(mocker):
    """创建 Mock MarketWriteService。"""
    service = mocker.Mock()
    service.save_bars.return_value = 1
    service.save_adj_factor.return_value = 1
    service.save_fund_adj.return_value = 1
    service.save_stock_status.return_value = 1
    service.save_global_index_bars.return_value = 1
    return service


@pytest.mark.unit
def test_global_index_daily_uses_dedicated_pit_writer(
    data_writer,
    mock_market_write_service,
) -> None:
    df = pl.DataFrame(
        {
            "source_ticker": ["SPX"],
            "trade_date": [date(2024, 3, 28)],
            "knowledge_date": [date(2026, 9, 1)],
            "close": [5254.35],
        }
    )

    result = data_writer.write_data("global_index_daily", df, "2024-03-28")

    assert result.file_path == "global_index_daily/2024"
    mock_market_write_service.save_global_index_bars.assert_called_once()
    mock_market_write_service.save_bars.assert_not_called()


@pytest.mark.unit
def test_calendar_write_enriches_adjacent_trading_days(
    data_writer,
    mock_metadata_service,
) -> None:
    df = pl.DataFrame(
        {
            "trade_date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            "is_open": [False, True, True],
            "exchange": ["SSE", "SSE", "SSE"],
        }
    )

    data_writer.write_data("calendar", df, "2024-03-29")

    mock_metadata_service.calendar.save_calendar.assert_called_once()
    mock_metadata_service.calendar.enrich_calendar.assert_called_once_with(
        "2024-01-01",
        "2024-01-03",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dataset", "method_name"),
    [
        ("industry_classification", "save_industry_classification"),
        ("industry_mapping", "save_industry_mapping"),
    ],
)
def test_industry_products_use_metadata_read_model_writer(
    data_writer,
    mock_metadata_service,
    dataset,
    method_name,
) -> None:
    df = pl.DataFrame({"knowledge_date": [date(2026, 9, 1)]})

    result = data_writer.write_data(dataset, df, "2026-09-01")

    assert result.file_path == f"{dataset}/0"
    getattr(mock_metadata_service.instrument, method_name).assert_called_once_with(
        df,
        source="tushare",
    )


@pytest.mark.unit
def test_fund_adj_uses_etf_writer_and_logical_catalog_uri(
    data_writer,
    mock_metadata_service,
    mock_market_write_service,
) -> None:
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "510300.SH": 2_000_001
    }
    df = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"],
            "trade_date": [date(2024, 12, 27)],
            "adj_factor": [1.25],
        }
    )

    result = data_writer.write_data("fund_adj", df, "2024-12-27")

    assert result.file_path == "fund_adj/2024"
    mock_market_write_service.save_fund_adj.assert_called_once()
    mock_market_write_service.save_adj_factor.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dataset", "write_method"),
    [
        ("stock_daily", "save_bars"),
        ("etf_daily", "save_bars"),
        ("index_daily", "save_bars"),
        ("stock_status", "save_stock_status"),
        ("adj_factor", "save_adj_factor"),
        ("fund_adj", "save_fund_adj"),
    ],
)
def test_instrument_scoped_writers_drop_unresolved_provider_rows(
    data_writer,
    mock_metadata_service,
    mock_market_write_service,
    dataset,
    write_method,
) -> None:
    """Unknown provider identifiers must never reach a durable FK writer."""
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "600000.SH": 1_000_001
    }
    df = pl.DataFrame(
        {
            "source_ticker": ["600000.SH", "T00018.SH"],
            "trade_date": [date(2024, 3, 29), date(2024, 3, 29)],
            "close": [10.0, 1.0],
        }
    )

    data_writer.write_data(dataset, df, "2024-03-29")

    method = getattr(mock_market_write_service, write_method)
    written = method.call_args.kwargs["df"]
    assert written["source_ticker"].to_list() == ["600000.SH"]
    assert written["instrument_id"].null_count() == 0


@pytest.fixture
def mock_fundamental_store(mocker):
    """创建 Mock FundamentalStore。"""
    service = mocker.Mock()
    service.save_balance_sheet.return_value = 1
    service.save_income_statement.return_value = 1
    service.save_cash_flow.return_value = 1
    service.save_dividend.return_value = 1
    return service


@pytest.fixture
def mock_capital_store(mocker):
    """创建 Mock CapitalStore。"""
    service = mocker.Mock()
    service.save_valuation_metrics.return_value = 1
    service.save_margin_trading.return_value = 1
    service.save_pledge_ratio.return_value = 1
    service.save_index_weight.return_value = 2
    return service


@pytest.mark.unit
def test_index_weight_writes_observation_facts(
    data_writer,
    mock_metadata_service,
    mock_capital_store,
) -> None:
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "600000.SH": 1_000_001,
        "600036.SH": 1_000_002,
    }
    df = pl.DataFrame(
        {
            "index_code": ["000300.SH", "000300.SH"],
            "source_ticker": ["600000.SH", "600036.SH"],
            "trade_date": [date(2024, 12, 27), date(2024, 12, 27)],
            "weight": [60.0, 40.0],
        }
    )

    result = data_writer.write_data("index_weight", df, "2024-12-27")

    assert result.file_path == "index_weight/2024"
    written = mock_capital_store.save_index_weight.call_args.args[0]
    assert written.select("index_id").to_series().to_list() == [
        "000300.SH",
        "000300.SH",
    ]
    assert written.select("instrument_id").to_series().to_list() == [
        1_000_001,
        1_000_002,
    ]
    assert written.select("trade_date").to_series().to_list() == [
        date(2024, 12, 27),
        date(2024, 12, 27),
    ]


@pytest.mark.unit
def test_index_weight_requires_observation_date(
    data_writer,
    mock_metadata_service,
    mock_capital_store,
) -> None:
    """#452: 不伪造生效区间；缺观察日的帧 fail closed."""
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "600000.SH": 1_000_001,
    }
    df = pl.DataFrame(
        {
            "index_code": ["000300.SH"],
            "source_ticker": ["600000.SH"],
            "weight": [100.0],
        }
    )

    with pytest.raises(AppProcessError, match="trade_date"):
        data_writer.write_data("index_weight", df, "2024-12-27")

    mock_capital_store.save_index_weight.assert_not_called()


@pytest.mark.unit
def test_index_weight_rejects_incomplete_weight_total(
    data_writer,
    mock_metadata_service,
    mock_capital_store,
) -> None:
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "600000.SH": 1_000_001,
        "600036.SH": 1_000_002,
    }
    df = pl.DataFrame(
        {
            "index_code": ["000300.SH", "000300.SH"],
            "source_ticker": ["600000.SH", "600036.SH"],
            "trade_date": [date(2024, 12, 27), date(2024, 12, 27)],
            "weight": [60.0, 30.0],
        }
    )

    with pytest.raises(AppProcessError, match="outside 2% tolerance"):
        data_writer.write_data("index_weight", df, "2024-12-27")

    mock_capital_store.save_index_weight.assert_not_called()


@pytest.fixture
def mock_macro_service(mocker):
    """创建 Mock MacroService。"""
    service = mocker.Mock()
    save_result = mocker.Mock()
    save_result.records_written = 1
    service.save_indicators.return_value = save_result
    return service


@pytest.fixture
def data_writer(
    mock_metadata_service,
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_macro_service,
):
    """创建 IngestionDataWriter 实例。"""
    return IngestionDataWriter(
        metadata_service=mock_metadata_service,
        market_write_service=mock_market_write_service,
        fundamental_store=mock_fundamental_store,
        capital_store=mock_capital_store,
        macro_service=mock_macro_service,
        source_name="tushare",
    )


@pytest.mark.unit
class TestWriteCapital:
    """测试 _write_capital 方法。"""

    def test_write_capital_valuation_metrics_writes_successfully(
        self,
        data_writer,
        mock_capital_store,
    ) -> None:
        """验证 valuation_metrics 数据写入成功。"""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "pe_ratio": [12.5],
                "pb_ratio": [1.8],
                "market_cap": [1000000000.0],
            }
        )

        # Act
        result = data_writer.write_data(
            dataset="valuation_metrics",
            df=df,
            trade_date="2024-12-27",
        )

        # Assert
        assert result.rows_written == 1
        assert not result.blocked
        mock_capital_store.save_valuation_metrics.assert_called_once()

    def test_write_capital_margin_trading_writes_successfully(
        self,
        data_writer,
        mock_capital_store,
    ) -> None:
        """验证 margin_trading 数据写入成功。"""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "fin_buy_amount": [1000000.0],
                "fin_refund_amount": [500000.0],
            }
        )

        # Act
        result = data_writer.write_data(
            dataset="margin_trading",
            df=df,
            trade_date="2024-12-27",
        )

        # Assert
        assert result.rows_written == 1
        assert not result.blocked
        mock_capital_store.save_margin_trading.assert_called_once()

    def test_write_capital_pledge_ratio_writes_successfully(
        self,
        data_writer,
        mock_capital_store,
    ) -> None:
        """验证 pledge_ratio 数据写入成功。"""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "pledge_ratio": [0.15],
            }
        )

        # Act
        result = data_writer.write_data(
            dataset="pledge_ratio",
            df=df,
            trade_date="2024-12-27",
        )

        # Assert
        assert result.rows_written == 1
        assert not result.blocked
        mock_capital_store.save_pledge_ratio.assert_called_once()


@pytest.mark.unit
class TestWriteFundamental:
    """测试基本面写入路径。"""

    def test_write_fundamental_filters_unresolved_tickers_without_schema_error(
        self,
        data_writer,
        mock_fundamental_store,
    ) -> None:
        """空 instrument_id mapping 不应导致 Polars join dtype 错误。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["999999.SZ"],
                "report_date": [date(2024, 12, 31)],
                "announcement_date": [date(2025, 1, 7)],
                "knowledge_date": [date(2025, 1, 8)],
                "effective_from": [date(2025, 1, 8)],
                "effective_to": [None],
                "total_assets": [1_000_000.0],
            }
        )

        result = data_writer.write_data(
            dataset="balance_sheet",
            df=df,
            trade_date="2025-01-07",
        )

        assert result.rows_written == 0
        assert not result.blocked
        mock_fundamental_store.save_balance_sheet.assert_not_called()


@pytest.mark.unit
class TestToWriteResult:
    """Test _to_write_result helper."""

    def test_to_write_result_never_infers_blocked(self):
        """_to_write_result 不应从 rows_written==0 推断 blocked。
        blocked 只应由显式 DQ 检查设置。"""
        from ditto_application.processes.ingestion.data_writer import _to_write_result

        df = pl.DataFrame({"a": [1, 2, 3]})

        # 零行写入 — blocked 应为 False（不是 DQ 阻断）
        result = _to_write_result("test_ds", 2024, df, rows_written=0)
        assert result.blocked is False
        assert result.rows_written == 0

        # 正常写入 — blocked 应为 False
        result = _to_write_result("test_ds", 2024, df, rows_written=3)
        assert result.blocked is False
        assert result.rows_written == 3


def test_fuyao_unsorted_bars_preserve_early_identity(
    mock_metadata_service,
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_macro_service,
):
    first_seen = {}

    def resolve(tickers, *, evidence_dates, **kwargs):
        for ticker in tickers:
            first_seen.setdefault(ticker, evidence_dates[ticker])
        return {
            ticker: 1000001
            for ticker in tickers
            if first_seen[ticker] <= evidence_dates[ticker]
        }

    mock_metadata_service.instrument.resolve_fuyao_instrument_ids.side_effect = resolve
    writer = IngestionDataWriter(
        metadata_service=mock_metadata_service,
        market_write_service=mock_market_write_service,
        fundamental_store=mock_fundamental_store,
        capital_store=mock_capital_store,
        macro_service=mock_macro_service,
        source_name="fuyao",
    )
    writer.write_data(
        "stock_daily",
        pl.DataFrame(
            {
                "source_ticker": ["600000.SH", "600000.SH"],
                "trade_date": [date(2026, 9, 2), date(2026, 9, 1)],
                "close": [12.0, 11.0],
            }
        ),
        "2026-09-02",
    )
    written = mock_market_write_service.save_bars.call_args.kwargs["df"]
    assert written["close"].to_list() == [11.0, 12.0]
    assert written["instrument_id"].to_list() == [1000001, 1000001]


@pytest.mark.unit
def test_every_write_route_resolves_to_a_handler_method():
    """#434 回归：_HANDLER_NAMES 曾映射 4 个从未定义的方法名（futures/earnings/
    index_valuation 写入路径 AttributeError，每日流静默失败）。契约：映射表里
    每个路由都能在 IngestionDataWriter 上解析到可调用方法。"""
    for write_kind, handler_name in IngestionDataWriter._HANDLER_NAMES.items():
        handler = getattr(IngestionDataWriter, handler_name, None)
        assert callable(handler), (
            f"{write_kind.value} maps to missing method {handler_name!r}"
        )


@pytest.mark.unit
def test_every_registered_dataset_has_a_write_route():
    """契约：注册表中每个非 UNSUPPORTED 数据集的 write_kind 都有映射条目。"""
    from ditto_application.processes.ingestion.dataset_registry import (
        WriteKind,
        default_dataset_registry,
    )

    routes = IngestionDataWriter._HANDLER_NAMES
    for registration in default_dataset_registry().registrations():
        if registration.write_kind is WriteKind.UNSUPPORTED:
            continue
        assert registration.write_kind in routes, (
            f"{registration.dataset.value} has write_kind "
            f"{registration.write_kind.value} without a handler route"
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dataset", "store_call"),
    [
        ("futures_daily", ("market", "save_futures_daily")),
        ("futures_basic", ("market", "save_futures_basic")),
        ("earnings_forecast", ("fundamental", "save_earnings_forecast")),
        ("earnings_express", ("fundamental", "save_earnings_express")),
    ],
)
def test_previously_unrouted_writes_dispatch_to_store(
    data_writer,
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    dataset,
    store_call,
):
    """#434 回归：这四个数据集的 write_data 之前在 handler 解析处 AttributeError。"""
    mock_market_write_service.save_futures_daily.return_value = 1
    mock_market_write_service.save_futures_basic.return_value = 1
    mock_fundamental_store.save_earnings_forecast.return_value = 1
    mock_fundamental_store.save_earnings_express.return_value = 1
    frame = pl.DataFrame(
        {
            "source_ticker": ["RB2410.SHF"],
            "trade_date": [date(2024, 10, 11)],
            "knowledge_date": [date(2024, 10, 11)],
        }
    )
    result = data_writer.write_data(dataset, frame, "2024-10-11")
    store_group, method_name = store_call
    store = {
        "market": mock_market_write_service,
        "fundamental": mock_fundamental_store,
    }[store_group]
    getattr(store, method_name).assert_called_once()
    assert result.rows_written == 1


@pytest.mark.unit
def test_index_valuation_write_enriches_and_persists(
    data_writer,
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_metadata_service,
):
    """#434 回归：index_valuation 走 instrument_id 富集后写 capital store。"""
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "000001.SH": 101
    }
    frame = pl.DataFrame(
        {
            "source_ticker": ["000001.SH"],
            "trade_date": [date(2024, 10, 11)],
            "knowledge_date": [date(2024, 10, 12)],
            "total_mv": [1.0],
        }
    )
    mock_capital_store.save_index_valuation.return_value = 1
    result = data_writer.write_data("index_valuation", frame, "2024-10-11")
    mock_capital_store.save_index_valuation.assert_called_once()
    assert result.rows_written == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dataset", "store_method"),
    [
        ("moneyflow", "save_moneyflow"),
        ("cyq_perf", "save_cyq_perf"),
        ("hk_hold", "save_hk_hold"),
        ("hsgt_top10", "save_hsgt_top10"),
        ("top_list", "save_top_list"),
        ("top_inst", "save_top_inst"),
        ("fina_indicator", "save_fina_indicator"),
        ("fund_portfolio", "save_fund_portfolio"),
        ("limit_list", "save_limit_list"),
        ("fund_share", "save_fund_share"),
    ],
)
def test_new_dataset_routes_dispatch_to_stores(
    data_writer,
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_metadata_service,
    dataset,
    store_method,
):
    """#518-#523：十条新写入路由全路径分发（防 #434 类缺失 handler 复发）."""
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "600519.SH": 101
    }
    for store in (
        mock_capital_store,
        mock_fundamental_store,
        mock_market_write_service,
    ):
        getattr(store, store_method).return_value = 1
    frame = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"],
            "trade_date": [date(2026, 9, 30)],
            "knowledge_date": [date(2026, 10, 1)],
        }
    )
    result = data_writer.write_data(dataset, frame, "2026-09-30")
    calls = [
        (mock_capital_store, store_method),
        (mock_fundamental_store, store_method),
        (mock_market_write_service, store_method),
    ]
    dispatched = [name for store, name in calls if getattr(store, name).call_count == 1]
    assert dispatched, f"{dataset} did not dispatch to any store"
    assert result.rows_written == 1
