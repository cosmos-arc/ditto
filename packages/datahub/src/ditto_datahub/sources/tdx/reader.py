"""通达信 .day 文件读取器."""

import struct
from pathlib import Path

import polars as pl


class TdxReader:
    """
    通达信日线数据读取器.

    .day 文件格式：
    - 每条记录 32 字节
    - 格式：日期(4) 开(4) 高(4) 低(4) 收(4) 成交额(4) 成交量(4) 保留(4)
    - 价格单位：元（已转换为 float）
    - 成交量单位：手（需要 × 100 转换为股）
    """

    RECORD_FORMAT = "<IIIIIfII"
    RECORD_SIZE = 32

    def __init__(self, tdx_path: Path) -> None:
        """
        初始化读取器.

        Args:
            tdx_path: 通达信 vipdoc 目录路径
                (如 D:/new_tdx/vipdoc)

        """
        self.tdx_path = Path(tdx_path)

    def read_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        读取日线数据.

        Args:
            ts_code: 股票代码（如 000001.SZ）
            start_date: 开始日期（YYYYMMDD，包含）
            end_date: 结束日期（YYYYMMDD，包含）

        Returns:
            DataFrame with columns:
            - trade_date: 交易日期（YYYYMMDD）
            - open, high, low, close: 价格（元）
            - vol: 成交量（股）
            - amount: 成交额（元）

        """
        # 解析市场代码
        market = self._parse_market(ts_code)
        ticker = ts_code.split(".")[0]

        # 定位 .day 文件
        day_file = self._locate_day_file(market, ticker)
        if not day_file.exists():
            return pl.DataFrame(schema=self._schema())

        # 读取二进制数据
        records = self._read_day_file(day_file, start_date, end_date)

        # 转换为 DataFrame
        df = pl.DataFrame(records, schema=self._schema())

        return df

    def _parse_market(self, ts_code: str) -> str:
        """解析市场代码."""
        suffix = ts_code.split(".")[1] if "." in ts_code else ""
        market_map = {
            "SH": "sh",
            "SZ": "sz",
            "BJ": "bj",
        }
        return market_map.get(suffix, "sz")

    def _locate_day_file(self, market: str, ticker: str) -> Path:
        """定位 .day 文件."""
        # 通达信目录结构：vipdoc/{市场}/lday/{代码}.day
        return self.tdx_path / market / "lday" / f"{ticker}.day"

    def _read_day_file(
        self,
        day_file: Path,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, str | float]]:
        """读取 .day 文件."""
        records: list[dict[str, str | float]] = []

        with day_file.open("rb") as f:
            while True:
                data = f.read(self.RECORD_SIZE)
                if len(data) < self.RECORD_SIZE:
                    break

                values = struct.unpack(self.RECORD_FORMAT, data)

                # 解析日期
                trade_date = values[0]  # YYYYMMDD int

                # 日期过滤
                if start_date and trade_date < int(start_date):
                    continue
                if end_date and trade_date > int(end_date):
                    continue

                # 解析价格（已经转换为 float，单位：元）
                open_price = float(values[1]) / 100
                high_price = float(values[2]) / 100
                low_price = float(values[3]) / 100
                close_price = float(values[4]) / 100

                # 解析成交量和成交额
                amount = float(values[5])  # 成交额（元）
                vol = float(values[6]) * 100  # 成交量（手 → 股）

                records.append(
                    {
                        "trade_date": str(trade_date),
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "vol": vol,
                        "amount": amount,
                    }
                )

        return records

    def _schema(self) -> dict[str, pl.DataType]:
        """返回输出 schema."""
        return {
            "trade_date": pl.String(),
            "open": pl.Float64(),
            "high": pl.Float64(),
            "low": pl.Float64(),
            "close": pl.Float64(),
            "vol": pl.Float64(),
            "amount": pl.Float64(),
        }

    def fetch_stock_daily_bars(
        self,
        ts_codes: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """
        批量获取股票日线数据（用于跨源对比）.

        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            DataFrame with columns:
            source_ticker, trade_date, open, high, low, close, vol, amount

        """
        all_data: list[pl.DataFrame] = []

        for ts_code in ts_codes:
            df = self.read_daily(ts_code, start_date=trade_date, end_date=trade_date)
            if df.height > 0:
                df = df.with_columns(
                    source_ticker=pl.lit(ts_code),
                )
                all_data.append(df)

        if not all_data:
            return pl.DataFrame(
                schema={
                    "source_ticker": pl.String,
                    "trade_date": pl.String,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "vol": pl.Float64,
                    "amount": pl.Float64,
                }
            )

        return pl.concat(all_data)
