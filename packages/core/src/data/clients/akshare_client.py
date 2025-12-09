"""
AkShare 数据源客户端.

提供 AkShare 接口的封装，用于获取中国股市开源数据。
"""

import time
from datetime import date, datetime
from typing import Any

import polars as pl

try:
    import akshare as ak

    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    ak = None

from .base_client import BaseClient, EtfInfo


class AkShareClient(BaseClient):
    """AkShare 数据源客户端。"""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化 AkShare 客户端。

        Args:
            config: 配置字典

        """
        super().__init__(config)

        if not AKSHARE_AVAILABLE:
            raise ImportError(
                "AkShare not available. Install with: pip install akshare"
            )

        # AkShare 没有严格的频率限制，但为了服务器稳定，设置最小间隔
        self.min_request_interval = self.config.get(
            "min_request_interval", 0.5
        )  # seconds
        self.last_request_time = 0

    def connect(self) -> None:
        """建立 AkShare 连接。"""
        # AkShare 是纯 Python 库，无需连接
        pass

    def disconnect(self) -> None:
        """断开 AkShare 连接。"""
        pass

    def _rate_limit(self) -> None:
        """实现请求频率限制。"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

        self.last_request_time = time.time()

    def get_etf_list(self) -> list[EtfInfo]:
        """获取 ETF 列表。"""
        self._rate_limit()

        try:
            # 获取 ETF 基金列表
            df = ak.fund_etf_basic()

            if df is None or df.empty:
                return []

            etf_list = []
            for _, row in df.iterrows():
                try:
                    etf_info = EtfInfo(
                        ts_code=row.get("基金代码", ""),
                        symbol=row.get("基金代码", ""),
                        name=row.get("基金名称", ""),
                        manager=row.get("基金管理人", ""),
                        establish_date=datetime.strptime(
                            row.get("成立日期", "20000101"), "%Y-%m-%d"
                        ).date(),
                        list_date=datetime.strptime(
                            row.get("上市日期", "20000101"), "%Y-%m-%d"
                        ).date(),
                        fund_type=row.get("基金类型", "ETF"),
                    )
                    etf_list.append(etf_info)
                except (ValueError, KeyError) as e:
                    print(
                        f"Error parsing ETF info for {row.get('基金代码', 'unknown')}: {e}"
                    )
                    continue

            return etf_list

        except Exception as e:
            print(f"Error fetching ETF list from AkShare: {e}")
            return []

    def get_daily_data(
        self, ts_code: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """
        获取日线数据。

        Args:
            ts_code: 股票代码（例如：sh000001）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含日线数据的 DataFrame

        """
        self._rate_limit()

        try:
            # AkShare 的股票代码格式可能需要调整
            symbol = ts_code.upper()

            # 获取历史行情数据
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")

            # 使用 stock_zh_a_hist 获取A股数据
            if symbol.startswith(("SH", "SZ")):
                # 去掉前缀，只保留数字
                code = symbol[2:]
                market = "sh" if symbol.startswith("SH") else "sz"

                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",  # 前复权
                )
            else:
                # 默认按 A 股处理
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",
                )

            if df is None or df.empty:
                # 返回空 DataFrame，保持列结构一致
                return pl.DataFrame(
                    schema={
                        "ts_code": str,
                        "trade_date": str,
                        "open": float,
                        "high": float,
                        "low": float,
                        "close": float,
                        "pre_close": float,
                        "change": float,
                        "pct_chg": float,
                        "vol": float,
                        "amount": float,
                    }
                )

            # 添加 ts_code 列
            df["ts_code"] = symbol

            # 重命名和转换列以匹配我们的标准
            df = df.rename(
                columns={
                    "日期": "trade_date",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "vol",
                    "成交额": "amount",
                }
            )

            # 计算涨跌幅
            df["pre_close"] = df["close"].shift(1)
            df["change"] = df["close"] - df["pre_close"]
            df["pct_chg"] = (df["change"] / df["pre_close"] * 100).round(2)

            # 转换数据类型
            df["trade_date"] = df["trade_date"].dt.strftime("%Y%m%d")

            # 选择需要的列
            columns = [
                "ts_code",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "change",
                "pct_chg",
                "vol",
                "amount",
            ]
            df = df[columns]

            # 转换为 polars DataFrame
            return pl.from_pandas(df)

        except Exception as e:
            print(f"Error fetching daily data for {ts_code}: {e}")
            return pl.DataFrame(
                schema={
                    "ts_code": str,
                    "trade_date": str,
                    "open": float,
                    "high": float,
                    "low": float,
                    "close": float,
                    "pre_close": float,
                    "change": float,
                    "pct_chg": float,
                    "vol": float,
                    "amount": float,
                }
            )

    def get_adj_factor(
        self, ts_code: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """
        获取复权因子。

        注意：AkShare 主要提供复权后的价格，复权因子需要计算。

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含复权因子的 DataFrame（通常都为 1.0）

        """
        self._rate_limit()

        try:
            # AkShare 不直接提供复权因子，返回默认值
            dates = pl.date_range(
                start_date, end_date, interval="1d", eager=True
            ).to_series()

            df = pl.DataFrame(
                {
                    "ts_code": ts_code,
                    "trade_date": dates.dt.strftime("%Y%m%d"),
                    "adj_factor": 1.0,
                }
            )

            return df

        except Exception as e:
            print(f"Error fetching adj factor for {ts_code}: {e}")
            return pl.DataFrame(
                schema={"ts_code": str, "trade_date": str, "adj_factor": float}
            )

    def validate_data_quality(self, ts_code: str) -> dict[str, Any]:
        """
        验证数据质量。

        Args:
            ts_code: 股票代码

        Returns:
            数据质量报告

        """
        try:
            # 获取最近一个月的数据进行质量检查
            end_date = date.today()
            start_date = date(end_date.year, end_date.month - 1, end_date.day)

            daily_data = self.get_daily_data(ts_code, start_date, end_date)
            adj_factors = self.get_adj_factor(ts_code, start_date, end_date)

            issues = []

            # 检查缺失数据
            if daily_data.is_empty():
                issues.append("No daily data found")
            else:
                # 检查必需列
                required_cols = [
                    "ts_code",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "vol",
                ]
                missing_cols = [
                    col for col in required_cols if col not in daily_data.columns
                ]
                if missing_cols:
                    issues.append(f"Missing required columns: {missing_cols}")

                # 检查空值
                null_counts = daily_data.select(
                    [
                        pl.col(col).null_count().alias(f"{col}_nulls")
                        for col in required_cols
                    ]
                ).row(0)

                for col, null_count in zip(required_cols, null_counts, strict=False):
                    if null_count > 0:
                        issues.append(f"Column {col} has {null_count} null values")

                # 检查价格一致性
                if "high" in daily_data.columns and "low" in daily_data.columns:
                    invalid_prices = daily_data.filter(
                        pl.col("high") < pl.col("low")
                    ).height
                    if invalid_prices > 0:
                        issues.append(f"Found {invalid_prices} records with high < low")

            # 检查复权因子
            if not adj_factors.is_empty():
                # AkShare 的复权因子应该都是 1.0
                non_one_factors = adj_factors.filter(pl.col("adj_factor") != 1.0).height
                if non_one_factors > 0:
                    issues.append(
                        f"Found {non_one_factors} non-unit adjustment factors"
                    )

            return {
                "ts_code": ts_code,
                "daily_records": daily_data.height,
                "adj_factor_records": adj_factors.height,
                "issues": issues,
                "quality_score": max(0, 100 - len(issues) * 10),
            }

        except Exception as e:
            return {
                "ts_code": ts_code,
                "error": str(e),
                "issues": [f"Validation failed: {e}"],
                "quality_score": 0,
            }
