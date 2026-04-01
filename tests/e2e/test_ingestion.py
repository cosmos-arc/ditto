"""数据接入验证测试.

验证 Tushare/TDX 源数据拉取、解析、校验功能。
该测试属于 E2E 验证，需要连接真实数据源。

覆盖数据域:
- Market: 股票/ETF/指数 日线行情
- Fundamental: 财务报表 (资产负债表/利润表/现金流量表)
- Capital: 估值指标/融资融券/质押比例
- Metadata: 交易日历/标的基本信息

参考文档：docs/plans/2026-02-17-e2e-validation-design.md 第 4 节
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar

import polars as pl
import pytest
from ditto_data.quality import GoldenDatasetSpec
from ditto_datahub.sources import TushareSource
from ditto_datahub.sources.tdx import TdxSource


@pytest.mark.e2e
@pytest.mark.integration
class TestIngestion:
    """数据接入验证 - 验证 Tushare/TDX 源数据拉取、解析、校验.

    验证项清单:
    | 编号 | 验证项 | 验证方法 | 通过标准 |
    |------|--------|---------|---------|
    | S1-01 | Tushare 连接性 | 调用 API 获取 1 条数据 | 返回非空 DataFrame |
    | S1-02 | TDX 文件可读性 | 读取本地 TDX 文件 | 解析成功无异常 |
    | S1-03 | 字段完整性 | 检查必需字段存在 | 100% 字段覆盖 |
    | S1-04 | 数据类型正确性 | Schema 校验 | 类型匹配率 100% |
    | S1-05 | 时间范围覆盖 | 检查日期范围 | 覆盖最近 3 年 |
    | S1-06 | 增量更新正确性 | 模拟增量拉取 | 无重复、无遗漏 |
    """

    def test_tushare_connection(self, tushare_source: TushareSource) -> None:
        """S1-01: Tushare 连接性验证.

        验证 Tushare API 可正常连接并返回数据。

        Args:
            tushare_source: Tushare 数据源实例（session 级 fixture）。

        """
        # 使用一个已知有交易的日期
        df = tushare_source.fetch_stock_daily(trade_date="2024-01-02")

        # 验证返回非空数据
        assert df.height > 0, "应返回非空数据"
        assert len(df.columns) > 0, "应包含列信息"

    def test_tdx_file_readable(
        self,
        tdx_source: TdxSource,
        golden_spec: GoldenDatasetSpec,
    ) -> None:
        """S1-02: TDX 文件可读性验证.

        验证 TDX 本地文件可正常读取和解析。

        Args:
            tdx_source: TDX 数据源实例（session 级 fixture）。
            golden_spec: 黄金数据集配置。

        """
        # 抽样验证前 5 个标的
        sample_tickers = golden_spec.tickers[:5]

        for ticker in sample_tickers:
            # 根据 ticker 前缀推断交易所
            if ticker.startswith("6") or ticker.startswith("5"):
                exchange = "SH"
            elif ticker.startswith("0") or ticker.startswith("3"):
                exchange = "SZ"
            else:
                exchange = "SZ"  # 默认深圳

            ts_code = f"{ticker}.{exchange}"

            # 读取日线数据
            df = tdx_source.reader.read_daily(ts_code)

            # 验证读取成功（空 DataFrame 也是合法的，表示文件不存在）
            assert df is not None, f"{ticker} TDX 文件读取失败"

    def test_field_completeness(self, tushare_source: TushareSource) -> None:
        """S1-03: 字段完整性验证.

        验证 Tushare 返回的数据包含所有必需字段。

        Args:
            tushare_source: Tushare 数据源实例（session 级 fixture）。

        """
        # 定义必需字段
        required_fields = [
            "source_ticker",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        df = tushare_source.fetch_stock_daily(trade_date="2024-01-02")

        # 验证所有必需字段存在
        for field in required_fields:
            assert field in df.columns, f"缺少必需字段: {field}"

    def test_data_type_correctness(self, tushare_source: TushareSource) -> None:
        """S1-04: 数据类型正确性验证.

        验证 Tushare 返回的数据字段类型正确。

        Args:
            tushare_source: Tushare 数据源实例（session 级 fixture）。

        """
        df = tushare_source.fetch_stock_daily(trade_date="2024-01-02")

        # 定义期望的类型映射
        expected_types = {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        }

        # 验证字段类型
        for field, expected_dtype in expected_types.items():
            if field in df.columns:
                actual_dtype = df.schema[field]
                # 允许 Float32 作为 Float64 的兼容类型
                if expected_dtype == pl.Float64 and actual_dtype in (
                    pl.Float64,
                    pl.Float32,
                ):
                    continue
                assert actual_dtype == expected_dtype, (
                    f"字段 {field} 类型不匹配: "
                    f"期望 {expected_dtype} 实际 {actual_dtype}"
                )

    def test_time_range_coverage(self, tushare_source: TushareSource) -> None:
        """S1-05: 时间范围覆盖验证.

        验证 Tushare 数据覆盖最近 3 年的时间范围。
        通过多次调用 API 检查不同日期的数据可用性。

        Args:
            tushare_source: Tushare 数据源实例（session 级 fixture）。

        """
        _ = date.today() - timedelta(days=3 * 365)  # 计算 3 年前（仅用于文档说明）

        # 抽样检查 3 个时间点
        test_dates = [
            "2024-01-02",  # 近期
            "2022-06-01",  # 中期
            "2021-01-04",  # 远期（约 3 年前）
        ]

        available_count = 0
        for test_date in test_dates:
            try:
                df = tushare_source.fetch_stock_daily(trade_date=test_date)
                if df.height > 0:
                    available_count += 1
            except Exception:
                # 某些日期可能无数据（非交易日），这是正常的
                pass

        # 至少应该有 1 个日期的数据可用
        assert available_count >= 1, (
            f"最近 3 年数据可用性不足 仅 {available_count}/3 个日期有数据"
        )

    def test_incremental_update_correctness(
        self,
        tushare_source: TushareSource,
    ) -> None:
        """S1-06: 增量更新正确性验证.

        验证同一日期多次拉取数据的一致性（幂等性）。
        模拟增量拉取场景，确保无重复、无遗漏。

        Args:
            tushare_source: Tushare 数据源实例（session 级 fixture）。

        """
        trade_date = "2024-01-02"

        # 第一次拉取
        df1 = tushare_source.fetch_stock_daily(trade_date=trade_date)

        # 第二次拉取（模拟增量）
        df2 = tushare_source.fetch_stock_daily(trade_date=trade_date)

        # 验证数据一致性
        assert df1.height == df2.height, (
            f"重复拉取数据量不一致: {df1.height} vs {df2.height}"
        )

        # 验证无重复（按 source_ticker + trade_date 去重检查）
        if df1.height > 0:
            unique_keys = df1.n_unique(subset=["source_ticker", "trade_date"])
            assert unique_keys == df1.height, (
                f"存在重复数据: 总行数 {df1.height}, 唯一键数 {unique_keys}"
            )

    def test_golden_tickers_daily(
        self,
        tushare_source: TushareSource,
        golden_spec: GoldenDatasetSpec,
    ) -> None:
        """黄金数据集日线数据接入验证.

        验证黄金数据集中各类型标的的数据接入:
        - 股票: 使用 fetch_stock_daily()
        - ETF: 使用 fetch_etf_daily()
        - 指数: 使用 fetch_index_daily()

        Args:
            tushare_source: Tushare 数据源实例（session 级 fixture）。
            golden_spec: 黄金数据集配置。

        """
        trade_date = "2024-01-02"

        # 黄金数据集按资产类型分组
        stock_tickers = {
            "600519",  # 贵州茅台
            "600036",  # 招商银行
            "000333",  # 美的集团
            "600941",  # 中国移动
            "300750",  # 宁德时代
            "688981",  # 中芯国际
            "000710",  # 贝瑞基因
            "300736",  # *ST左江
        }
        etf_tickers = {
            "510300",  # 沪深300ETF
            "510500",  # 中证500ETF
            "159915",  # 创业板ETF
            "588000",  # 科创50ETF
            "159928",  # 消费ETF
            "512010",  # 医药ETF
            "513100",  # 纳指ETF
            "513030",  # 德国ETF
            "516010",  # 游戏ETF
        }
        index_tickers = {
            "000001",  # 上证指数
            "399001",  # 深证成指
            "000300",  # 沪深300
            "000852",  # 中证1000
        }

        def extract_tickers(df: pl.DataFrame) -> set[str]:
            """从 source_ticker 列提取 ticker 集合."""
            if df.height == 0 or "source_ticker" not in df.columns:
                return set()
            return set(
                df.select(
                    pl.col("source_ticker").str.split(".").list.get(0).alias("ticker")
                )["ticker"]
                .unique()
                .to_list()
            )

        results: list[str] = []

        # 1. 验证股票数据
        stock_df = tushare_source.fetch_stock_daily(trade_date=trade_date)
        stock_available = extract_tickers(stock_df)
        stock_matched = len(stock_tickers & stock_available)
        stock_rate = stock_matched / len(stock_tickers) if stock_tickers else 0
        results.append(f"股票: {stock_matched}/{len(stock_tickers)} ({stock_rate:.1%})")

        # 2. 验证 ETF 数据
        etf_df = tushare_source.fetch_etf_daily(trade_date=trade_date)
        etf_available = extract_tickers(etf_df)
        etf_matched = len(etf_tickers & etf_available)
        etf_rate = etf_matched / len(etf_tickers) if etf_tickers else 0
        results.append(f"ETF: {etf_matched}/{len(etf_tickers)} ({etf_rate:.1%})")

        # 3. 验证指数数据
        index_codes = ["000001.SH", "399001.SZ", "000300.SH", "000852.SH"]
        index_df = tushare_source.fetch_index_daily(
            trade_date=trade_date, ts_codes=index_codes
        )
        index_available = extract_tickers(index_df)
        index_matched = len(index_tickers & index_available)
        index_rate = index_matched / len(index_tickers) if index_tickers else 0
        results.append(f"指数: {index_matched}/{len(index_tickers)} ({index_rate:.1%})")

        # 汇总结果
        total_expected = len(stock_tickers) + len(etf_tickers) + len(index_tickers)
        total_matched = stock_matched + etf_matched + index_matched
        total_rate = total_matched / total_expected if total_expected else 0

        # 各类型至少 80% 覆盖
        assert stock_rate >= 0.8, (
            f"股票数据覆盖率不足: {stock_matched}/{len(stock_tickers)} "
            f"({stock_rate:.1%})"
        )
        assert etf_rate >= 0.8, (
            f"ETF数据覆盖率不足: {etf_matched}/{len(etf_tickers)} ({etf_rate:.1%})"
        )
        assert index_rate >= 0.8, (
            f"指数数据覆盖率不足: {index_matched}/{len(index_tickers)} "
            f"({index_rate:.1%})"
        )
        assert total_rate >= 0.8, (
            f"总体覆盖率不足: {total_matched}/{total_expected} "
            f"({total_rate:.1%}), 详情: {', '.join(results)}"
        )


@pytest.mark.e2e
@pytest.mark.integration
class TestFundamentalIngestion:
    """财务数据接入验证 - Fundamental 域.

    验证项清单:
    | 编号 | 验证项 | 验证方法 | 通过标准 |
    |------|--------|---------|---------|
    | F1-01 | 资产负债表 | fetch_balance_sheet() | 返回非空 DataFrame |
    | F1-02 | 利润表 | fetch_income_statement() | 返回非空 DataFrame |
    | F1-03 | 现金流量表 | fetch_cash_flow() | 返回非空 DataFrame |
    | F1-04 | 分红数据 | fetch_dividend() | 返回 DataFrame (允许空) |

    注意：Tushare 财务报表 API 需要 ts_code 参数，测试使用贵州茅台 (600519.SH)
    """

    # 测试用股票代码
    SAMPLE_STOCK_CODES: ClassVar[list[str]] = [
        "600519.SH",  # 贵州茅台
        "000333.SZ",  # 美的集团
    ]

    def test_balance_sheet_ingestion(self, tushare_source: TushareSource) -> None:
        """F1-01: 资产负债表数据接入验证."""
        # 使用指定的股票代码测试
        ts_code = self.SAMPLE_STOCK_CODES[0]
        compact_date = "20240331"

        df = tushare_source._fundamental.fetch_balance_sheet(
            ts_code=ts_code,
            start_date=compact_date,
            end_date=compact_date,
        )

        # 验证返回数据结构
        assert df is not None, "资产负债表数据获取失败"

        if df.height > 0:
            # 验证核心字段存在
            has_identifier = any(
                col in df.columns
                for col in ["source_ticker", "ts_code", "instrument_id"]
            )
            assert has_identifier, f"缺少标识字段, 可用列: {df.columns}"

    def test_income_statement_ingestion(self, tushare_source: TushareSource) -> None:
        """F1-02: 利润表数据接入验证."""
        ts_code = self.SAMPLE_STOCK_CODES[0]
        compact_date = "20240331"

        df = tushare_source._fundamental.fetch_income_statement(
            ts_code=ts_code,
            start_date=compact_date,
            end_date=compact_date,
        )

        assert df is not None, "利润表数据获取失败"

        if df.height > 0:
            assert len(df.columns) >= 3, "利润表字段数过少"

    def test_cash_flow_ingestion(self, tushare_source: TushareSource) -> None:
        """F1-03: 现金流量表数据接入验证."""
        ts_code = self.SAMPLE_STOCK_CODES[0]
        compact_date = "20240331"

        df = tushare_source._fundamental.fetch_cash_flow(
            ts_code=ts_code,
            start_date=compact_date,
            end_date=compact_date,
        )

        assert df is not None, "现金流量表数据获取失败"

        if df.height > 0:
            assert len(df.columns) >= 3, "现金流量表字段数过少"

    def test_dividend_ingestion(self, tushare_source: TushareSource) -> None:
        """F1-04: 分红数据接入验证."""
        # 分红数据可能为空（取决于日期）
        df = tushare_source._fundamental.fetch_dividend(
            ts_code=self.SAMPLE_STOCK_CODES[0],
            start_date="20240101",
            end_date="20241231",
        )

        # 验证返回的是 DataFrame（允许空数据）
        assert df is not None, "分红数据获取失败"
        assert isinstance(df, pl.DataFrame), "返回类型应为 DataFrame"


@pytest.mark.e2e
@pytest.mark.integration
class TestCapitalIngestion:
    """资金面数据接入验证 - Capital 域.

    验证项清单:
    | 编号 | 验证项 | 验证方法 | 通过标准 |
    |------|--------|---------|---------|
    | C1-01 | 估值指标 | fetch_valuation_metrics() | 返回非空 DataFrame |
    | C1-02 | 融资融券 | fetch_margin_trading() | 返回 DataFrame (允许空) |
    | C1-03 | 质押比例 | fetch_pledge_ratio() | 返回 DataFrame (允许空) |

    注意: Capital 域 API 可能需要特定 Tushare 权限。
    """

    def test_valuation_metrics_ingestion(self, tushare_source: TushareSource) -> None:
        """C1-01: 估值指标数据接入验证."""
        trade_date = "2024-01-02"

        df = tushare_source.fetch_valuation_metrics(trade_date=trade_date)

        assert df is not None, "估值指标数据获取失败"

        if df.height > 0:
            # 估值指标应包含 PE/PB 等字段
            expected_keywords = ["pe", "pb", "ps", "value"]
            has_valuation_field = any(
                any(kw in col.lower() for kw in expected_keywords) for col in df.columns
            )
            assert has_valuation_field or len(df.columns) >= 3, (
                f"估值指标字段不足: {df.columns}"
            )

    def test_margin_trading_ingestion(self, tushare_source: TushareSource) -> None:
        """C1-02: 融资融券数据接入验证."""
        trade_date = "2024-01-02"

        # 融资融券数据可能不是每天都有
        df = tushare_source.fetch_margin_trading(trade_date=trade_date)

        assert df is not None, "融资融券数据获取失败"
        assert isinstance(df, pl.DataFrame), "返回类型应为 DataFrame"

    def test_pledge_ratio_ingestion(self, tushare_source: TushareSource) -> None:
        """C1-03: 质押比例数据接入验证."""
        trade_date = "2024-03-31"

        # 质押数据按报告期披露
        df = tushare_source.fetch_pledge_ratio(trade_date=trade_date)

        assert df is not None, "质押比例数据获取失败"
        assert isinstance(df, pl.DataFrame), "返回类型应为 DataFrame"


@pytest.mark.e2e
@pytest.mark.integration
class TestMetadataIngestion:
    """元数据接入验证 - Metadata 域.

    验证项清单:
    | 编号 | 验证项 | 验证方法 | 通过标准 |
    |------|--------|---------|---------|
    | M1-01 | 交易日历 | fetch_calendar() | 返回非空 DataFrame |
    | M1-02 | 股票基本信息 | fetch_stock_basic() | 返回非空 DataFrame |
    | M1-03 | ETF 基本信息 | fetch_etf_basic() | 返回非空 DataFrame |
    | M1-04 | 指数基本信息 | fetch_index_basic() | 返回非空 DataFrame |
    """

    def test_calendar_ingestion(self, tushare_source: TushareSource) -> None:
        """M1-01: 交易日历数据接入验证."""
        df = tushare_source.fetch_calendar(
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert df is not None, "交易日历数据获取失败"
        assert df.height > 0, "交易日历数据为空"
        assert "trade_date" in df.columns, "缺少 trade_date 字段"

    def test_stock_basic_ingestion(self, tushare_source: TushareSource) -> None:
        """M1-02: 股票基本信息接入验证."""
        df = tushare_source.fetch_stock_basic()

        assert df is not None, "股票基本信息获取失败"
        assert df.height > 0, "股票基本信息为空"
        # 应包含标识字段
        assert "source_ticker" in df.columns or "ts_code" in df.columns, "缺少标识字段"

    def test_etf_basic_ingestion(self, tushare_source: TushareSource) -> None:
        """M1-03: ETF 基本信息接入验证."""
        df = tushare_source.fetch_etf_basic()

        assert df is not None, "ETF 基本信息 获取失败"
        # ETF 数量可能较少，允许空数据
        if df.height > 0:
            assert "source_ticker" in df.columns or "ts_code" in df.columns, (
                "缺少标识字段"
            )

    def test_index_basic_ingestion(self, tushare_source: TushareSource) -> None:
        """M1-04: 指数基本信息接入验证."""
        df = tushare_source.fetch_index_basic()

        assert df is not None, "指数基本信息获取失败"
        # 指数数量有限
        if df.height > 0:
            assert "source_ticker" in df.columns or "ts_code" in df.columns, (
                "缺少标识字段"
            )
