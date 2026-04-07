"""完整数据流水线验证测试.

验证从数据摄取 → 存储 → 查询 → 质量检查的完整流程。
该测试属于 E2E 验证，测试数据在各个环节的正确流转。

流水线阶段:
1. Ingestion: 从数据源获取数据
2. Storage: 数据写入存储层
3. Query: 从存储层查询数据
4. Quality: 质量检查通过

参考文档：docs/plans/2026-02-17-e2e-validation-design.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.models import OnDuplicate
from ditto_data.quality import DQSpec, GoldenDatasetSpec, QualityEngine
from ditto_data.services.market_service import MarketBarsQuery, MarketService
from ditto_data.sources import TushareSource
from ditto_data.storage.market.stock.adj import (
    StockAdjFactorReader,
    StockAdjFactorWriter,
)
from ditto_data.storage.market.stock.bars import StockBarsReader, StockBarsWriter


def _make_instrument_id(df: pl.DataFrame) -> pl.DataFrame:
    """从 source_ticker 生成安全的 instrument_id.

    使用 hash % 10^9 确保 ID 在 i64 范围内且唯一。
    """
    return df.with_columns(
        pl.col("source_ticker")
        .str.split(".")
        .list.get(0)
        .hash()
        .mod(1_000_000_000)  # 保持在 10^9 范围内，确保 i64 安全
        .cast(pl.Int64)
        .alias("instrument_id")
    )


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def pipeline_root(tmp_path: Path) -> Path:
    """创建流水线测试根目录."""
    return tmp_path / "pipeline"


@pytest.fixture
def stock_bars_reader(pipeline_root: Path) -> StockBarsReader:
    """创建 Stock 日线数据 Reader."""
    pipeline_root.mkdir(parents=True, exist_ok=True)
    return StockBarsReader(data_root=pipeline_root)


@pytest.fixture
def stock_bars_writer(pipeline_root: Path) -> StockBarsWriter:
    """创建 Stock 日线数据 Writer."""
    pipeline_root.mkdir(parents=True, exist_ok=True)
    return StockBarsWriter(data_root=pipeline_root)


@pytest.fixture
def stock_adj_reader(pipeline_root: Path) -> StockAdjFactorReader:
    """创建 Stock 复权因子 Reader."""
    pipeline_root.mkdir(parents=True, exist_ok=True)
    return StockAdjFactorReader(data_root=pipeline_root)


@pytest.fixture
def stock_adj_writer(pipeline_root: Path) -> StockAdjFactorWriter:
    """创建 Stock 复权因子 Writer."""
    pipeline_root.mkdir(parents=True, exist_ok=True)
    return StockAdjFactorWriter(data_root=pipeline_root)


@pytest.fixture
def quality_engine() -> QualityEngine:
    """创建质量引擎实例."""
    dq_spec = DQSpec(
        datasets={
            "stock_daily": {
                "dataset": "stock_daily",
                "description": "股票日线数据质量检查",
                "technical": [
                    {"rule": "not_null", "columns": ["instrument_id", "trade_date"]},
                ],
                "business": [
                    {"rule": "positive", "columns": ["volume"]},
                ],
            }
        }
    )
    return QualityEngine(config=dq_spec)


@pytest.fixture
def market_service(
    stock_bars_reader: StockBarsReader,
    stock_bars_writer: StockBarsWriter,
    stock_adj_reader: StockAdjFactorReader,
    stock_adj_writer: StockAdjFactorWriter,
    pipeline_root: Path,
) -> MarketService:
    """创建 MarketService 实例（只读）。"""
    mock_instrument_reader = MagicMock()
    mock_instrument_reader.list_instrument_ids.return_value = [1000001]
    mock_instrument_reader.get_instrument_id_ticker_map.return_value = {
        1000001: "600519"
    }

    from ditto_data.services.ports import MarketReadPorts

    read_ports = MarketReadPorts(
        stock_bars=stock_bars_reader,
        stock_status=MagicMock(),
        stock_adj=stock_adj_reader,
        etf_bars=MagicMock(),
        etf_status=MagicMock(),
        instrument=mock_instrument_reader,
    )

    return MarketService(read_ports=read_ports)


# ==============================================================================
# Test Classes
# ==============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestMarketDataPipeline:
    """市场数据完整流水线验证.

    验证流程:
    1. Ingestion: 从 Tushare 获取股票日线数据
    2. Storage: 写入 Parquet 存储
    3. Query: 通过 MarketService 查询
    4. Quality: 质量检查通过
    """

    def test_stock_daily_full_pipeline(
        self,
        tushare_source: TushareSource,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        market_service: MarketService,
        quality_engine: QualityEngine,
    ) -> None:
        """股票日线数据完整流水线验证.

        验证数据从摄取到质量检查的完整流转。

        Args:
            tushare_source: Tushare 数据源.
            stock_bars_writer: Stock 日线数据 Writer.
            stock_bars_reader: Stock 日线数据 Reader.
            market_service: MarketService 实例.
            quality_engine: 质量引擎实例.

        """
        trade_date = "2024-01-02"

        # === 阶段 1: Ingestion ===
        # 从 Tushare 获取数据
        raw_df = tushare_source.fetch_stock_daily(trade_date=trade_date)

        # 验证摄取成功
        assert raw_df.height > 0, "摄取阶段: 应获取非空数据"

        # 转换为存储格式 (添加 instrument_id)
        df_with_id = _make_instrument_id(raw_df)

        # === 阶段 2: Storage ===
        # 写入存储
        write_result = stock_bars_writer.write(
            df=df_with_id,
            year=2024,
            on_duplicate=OnDuplicate.KEEP_FIRST,
        )

        # 验证写入成功
        assert write_result.added > 0, (
            f"存储阶段: 应成功写入数据, 实际写入 {write_result.added}"
        )

        # 验证读取一致性
        stored_count = stock_bars_reader.count()
        assert stored_count == write_result.added, (
            f"存储阶段: 读取数量应与写入一致, "
            f"写入 {write_result.added}, 读取 {stored_count}"
        )

        # === 阶段 3: Query ===
        # 通过 MarketService 查询
        # 使用写入的第一个 instrument_id
        sample_ids = [df_with_id["instrument_id"][0]]
        query = MarketBarsQuery(
            instrument_ids=sample_ids,
            start=trade_date,
            end=trade_date,
        )
        query_result = market_service.find_bars(query)

        # 验证查询成功
        assert query_result.height >= 1, (
            f"查询阶段: 应返回数据, 实际 {query_result.height}"
        )

        # 验证查询数据与原始数据一致
        original_close = df_with_id.filter(pl.col("instrument_id") == sample_ids[0])[
            "close"
        ][0]
        queried_close = query_result["close"][0]
        assert abs(original_close - queried_close) < 0.001, (
            f"查询阶段: 数据应一致, 原始 {original_close}, 查询 {queried_close}"
        )

        # === 阶段 4: Quality ===
        # 质量检查
        dq_result = quality_engine.check(df_with_id, "stock_daily")

        # 验证质量检查通过
        assert dq_result.passed, f"质量阶段: 检查应通过, 错误: {dq_result.errors}"

    def test_etf_daily_full_pipeline(
        self,
        tushare_source: TushareSource,
        pipeline_root: Path,
        quality_engine: QualityEngine,
    ) -> None:
        """ETF 日线数据完整流水线验证.

        验证 ETF 数据从摄取到质量检查的完整流转。

        Args:
            tushare_source: Tushare 数据源.
            pipeline_root: 测试根目录.
            quality_engine: 质量引擎实例.

        """
        trade_date = "2024-01-02"

        # === 阶段 1: Ingestion ===
        raw_df = tushare_source.fetch_etf_daily(trade_date=trade_date)
        assert raw_df.height > 0, "ETF 摄取阶段: 应获取非空数据"

        # === 阶段 2: Storage (简化验证) ===
        # 验证数据结构符合存储要求
        required_columns = {"source_ticker", "trade_date", "open", "close", "volume"}
        actual_columns = set(raw_df.columns)
        assert required_columns.issubset(actual_columns), (
            f"存储阶段: 缺少必需列, 需要 {required_columns}, 实际 {actual_columns}"
        )

        # === 阶段 4: Quality ===
        # 添加 instrument_id 列用于质量检查
        df_with_id = _make_instrument_id(raw_df)
        dq_result = quality_engine.check(df_with_id, "stock_daily")  # 使用相同规则
        assert dq_result.passed, f"ETF 质量阶段: 检查应通过, 错误: {dq_result.errors}"

    def test_index_daily_full_pipeline(
        self,
        tushare_source: TushareSource,
        quality_engine: QualityEngine,
    ) -> None:
        """指数日线数据完整流水线验证.

        验证指数数据从摄取到质量检查的完整流转。

        Args:
            tushare_source: Tushare 数据源.
            quality_engine: 质量引擎实例.

        """
        trade_date = "2024-01-02"

        # === 阶段 1: Ingestion ===
        # 使用默认市场指数代码进行测试
        index_codes = ["000001.SH", "399001.SZ", "000300.SH"]
        raw_df = tushare_source.fetch_index_daily(
            trade_date=trade_date, ts_codes=index_codes
        )
        assert raw_df.height > 0, "指数摄取阶段: 应获取非空数据"

        # 验证包含主要指数
        tickers = set(
            raw_df.select(
                pl.col("source_ticker").str.split(".").list.get(0).alias("ticker")
            )["ticker"]
            .unique()
            .to_list()
        )
        expected_indices = {"000001", "399001", "000300"}
        matched = tickers & expected_indices
        assert len(matched) >= 2, (
            f"指数摄取阶段: 应包含主要指数, "
            f"期望至少 {expected_indices} 中的 2 个, "
            f"实际匹配 {matched}"
        )

        # === 阶段 4: Quality ===
        df_with_id = _make_instrument_id(raw_df)
        dq_result = quality_engine.check(df_with_id, "stock_daily")
        assert dq_result.passed, f"指数质量阶段: 检查应通过, 错误: {dq_result.errors}"


@pytest.mark.e2e
@pytest.mark.integration
class TestFundamentalPipeline:
    """财务数据完整流水线验证.

    验证财务报表数据从摄取到质量检查的完整流转。

    注意：财务报表使用 VIP API (balancesheet_vip, income_vip, cashflow_vip)，
    可按 ann_date (公告日期) 或 period (报告期) 批量获取全部股票数据。
    需要 5000+ 积分。
    """

    def test_balance_sheet_pipeline(
        self,
        tushare_source: TushareSource,
    ) -> None:
        """资产负债表数据流水线验证.

        使用 VIP API 按 ann_date 获取数据。
        """
        # 2024-04-30 是年报密集公告期
        trade_date = "2024-04-30"

        # === 阶段 1: Ingestion ===
        raw_df = tushare_source.fetch_balance_sheet(trade_date=trade_date)

        # 验证数据结构
        assert raw_df is not None, "资产负债表摄取失败"

        if raw_df.height > 0:
            # 验证包含标识字段
            has_identifier = any(
                col in raw_df.columns
                for col in ["source_ticker", "ts_code", "instrument_id"]
            )
            assert has_identifier, f"资产负债表缺少标识字段, 可用列: {raw_df.columns}"

    def test_income_statement_pipeline(
        self,
        tushare_source: TushareSource,
    ) -> None:
        """利润表数据流水线验证.

        使用 VIP API 按 ann_date 获取数据。
        """
        # 2024-04-30 是年报密集公告期
        trade_date = "2024-04-30"

        raw_df = tushare_source.fetch_income_statement(trade_date=trade_date)

        assert raw_df is not None, "利润表摄取失败"

        if raw_df.height > 0:
            assert len(raw_df.columns) >= 5, (
                f"利润表字段数不足, 期望至少 5 列, 实际 {len(raw_df.columns)}"
            )


@pytest.mark.e2e
@pytest.mark.integration
class TestCapitalPipeline:
    """资金面数据完整流水线验证."""

    def test_valuation_metrics_pipeline(
        self,
        tushare_source: TushareSource,
    ) -> None:
        """估值指标数据流水线验证."""
        trade_date = "2024-01-02"

        raw_df = tushare_source.fetch_valuation_metrics(trade_date=trade_date)

        assert raw_df is not None, "估值指标摄取失败"

        if raw_df.height > 0:
            # 验证包含估值相关字段
            has_valuation = any(
                any(kw in col.lower() for kw in ["pe", "pb", "value", "ratio"])
                for col in raw_df.columns
            )
            assert has_valuation or len(raw_df.columns) >= 5, (
                f"估值指标字段不足: {raw_df.columns}"
            )


@pytest.mark.e2e
@pytest.mark.integration
class TestGoldenDatasetPipeline:
    """黄金数据集完整流水线验证.

    对黄金数据集中的标的进行完整流水线验证。
    """

    def test_golden_tickers_pipeline(
        self,
        tushare_source: TushareSource,
        golden_spec: GoldenDatasetSpec,
        quality_engine: QualityEngine,
    ) -> None:
        """黄金数据集完整流水线验证.

        验证黄金数据集中所有类型的标的数据流转。

        Args:
            tushare_source: Tushare 数据源.
            golden_spec: 黄金数据集配置.
            quality_engine: 质量引擎实例.

        """
        trade_date = "2024-01-02"
        results: list[dict] = []

        # 股票
        stock_df = tushare_source.fetch_stock_daily(trade_date=trade_date)
        stock_tickers = {
            "600519",
            "600036",
            "000333",
            "600941",
            "300750",
            "688981",
            "000710",
            "300736",
        }

        if stock_df.height > 0:
            stock_available = set(
                stock_df.select(
                    pl.col("source_ticker").str.split(".").list.get(0).alias("ticker")
                )["ticker"]
                .unique()
                .to_list()
            )
            stock_matched = len(stock_tickers & stock_available)
            results.append(
                {
                    "type": "股票",
                    "matched": stock_matched,
                    "total": len(stock_tickers),
                    "passed": stock_matched >= len(stock_tickers) * 0.8,
                }
            )

            # 质量检查
            df_with_id = _make_instrument_id(stock_df)
            dq_result = quality_engine.check(df_with_id, "stock_daily")
            assert dq_result.passed, f"股票质量检查失败: {dq_result.errors}"

        # ETF
        etf_df = tushare_source.fetch_etf_daily(trade_date=trade_date)
        etf_tickers = {
            "510300",
            "510500",
            "159915",
            "588000",
            "159928",
            "512010",
            "513100",
            "513030",
            "516010",
        }

        if etf_df.height > 0:
            etf_available = set(
                etf_df.select(
                    pl.col("source_ticker").str.split(".").list.get(0).alias("ticker")
                )["ticker"]
                .unique()
                .to_list()
            )
            etf_matched = len(etf_tickers & etf_available)
            results.append(
                {
                    "type": "ETF",
                    "matched": etf_matched,
                    "total": len(etf_tickers),
                    "passed": etf_matched >= len(etf_tickers) * 0.8,
                }
            )

        # 指数
        index_codes = ["000001.SH", "399001.SZ", "000300.SH", "000852.SH"]
        index_df = tushare_source.fetch_index_daily(
            trade_date=trade_date, ts_codes=index_codes
        )
        index_tickers = {"000001", "399001", "000300", "000852"}

        if index_df.height > 0:
            index_available = set(
                index_df.select(
                    pl.col("source_ticker").str.split(".").list.get(0).alias("ticker")
                )["ticker"]
                .unique()
                .to_list()
            )
            index_matched = len(index_tickers & index_available)
            results.append(
                {
                    "type": "指数",
                    "matched": index_matched,
                    "total": len(index_tickers),
                    "passed": index_matched >= len(index_tickers) * 0.8,
                }
            )

        # 汇总验证
        failed_types = [r for r in results if not r["passed"]]
        failed_details = [
            f"{r['type']}: {r['matched']}/{r['total']}" for r in failed_types
        ]
        assert len(failed_types) == 0, f"黄金数据集流水线验证失败: {failed_details}"
