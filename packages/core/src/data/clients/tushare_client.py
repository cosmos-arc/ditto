"""
Tushare 数据源客户端.

提供 Tushare Pro 接口的封装，用于获取中国股市数据。
"""

import time
from datetime import date, datetime
from typing import Any

import polars as pl

try:
    import tushare as ts

    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    ts = None

from .base_client import BaseClient, EtfInfo


class TushareClient(BaseClient):
    """Tushare 数据源客户端."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化 Tushare 客户端。

        Args:
            config: 配置字典，需要包含 token

        """
        super().__init__(config)

        if not TUSHARE_AVAILABLE:
            raise ImportError(
                "Tushare not available. Install with: pip install tushare"
            )

        self.token = self.config.get("token")
        if not self.token:
            raise ValueError("Tushare token is required")

        # 请求间隔限制（默认 200 毫秒，免费用户）
        self.min_request_interval = self.config.get(
            "min_request_interval", 0.2
        )  # seconds
        self.last_request_time = 0

        ts.set_token(self.token)

    def connect(self) -> None:
        """建立 Tushare 连接（设置 token）。"""
        # Tushare 使用 token 认证，无需额外连接
        pass

    def disconnect(self) -> None:
        """断开 Tushare 连接。"""
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

        # 获取基金基本信息
        df = ts.fund_basic(market="E")

        if df is None or df.empty:
            return []

        etf_list = []
        for _, row in df.iterrows():
            try:
                etf_info = EtfInfo(
                    ts_code=row["ts_code"],
                    symbol=row["symbol"],
                    name=row["name"],
                    manager=row.get("management", ""),
                    establish_date=datetime.strptime(
                        row.get("setuptime", "20000101"), "%Y%m%d"
                    ).date(),
                    list_date=datetime.strptime(
                        row.get("listing_date", "20000101"), "%Y%m%d"
                    ).date(),
                    fund_type=row.get("fund_type", "ETF"),
                )
                etf_list.append(etf_info)
            except (ValueError, KeyError) as e:
                print(
                    f"Error parsing ETF info for {row.get('ts_code', 'unknown')}: {e}"
                )
                continue

        return etf_list

    def get_daily_data(
        self, ts_code: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """
        获取日线数据。

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含日线数据的 DataFrame

        """
        self._rate_limit()

        # 转换日期格式
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # 获取日线数据
        df = ts.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)

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

        # 重命名列以匹配我们的标准
        df = df.rename(
            columns={"trade_date": "trade_date", "vol": "vol", "amount": "amount"}
        )

        # 转换为 polars DataFrame
        return pl.from_pandas(df)

    def get_adj_factor(
        self, ts_code: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """
        获取复权因子。

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含复权因子的 DataFrame

        """
        self._rate_limit()

        # 转换日期格式
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # 获取复权因子
        df = ts.adj_factor(ts_code=ts_code, start_date=start_str, end_date=end_str)

        if df is None or df.empty:
            return pl.DataFrame(
                schema={"ts_code": str, "trade_date": str, "adj_factor": float}
            )

        # 转换为 polars DataFrame
        return pl.from_pandas(df)

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
                # 检查负因子
                negative_factors = adj_factors.filter(pl.col("adj_factor") <= 0).height
                if negative_factors > 0:
                    issues.append(
                        f"Found {negative_factors} non-positive adjustment factors"
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
