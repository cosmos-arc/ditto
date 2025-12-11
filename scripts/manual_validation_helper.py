#!/usr/bin/env python3
"""
手工验证辅助脚本.

导出数据供手工验证使用
"""

# ruff: noqa: PLR0912, PLR0915, E501

import os
import sys
from pathlib import Path

import pandas as pd
import polars as pl
from ditto_core.data.service import DataService
from ditto_foundation.config import get_settings

# 设置Windows控制台输出编码为UTF-8
if sys.platform == "win32":
    os.system("chcp 65001 >nul")

# Constants
LIMIT_UP_THRESHOLD = 9.8
LIMIT_DOWN_THRESHOLD = -9.8


def export_for_manual_validation() -> None:
    """导出数据供手工验证."""
    print("导出手工验证数据...")

    # Golden Dataset 标的
    symbols = ["510300.SH", "516010.SH", "513100.SH", "000300.SH"]

    settings = get_settings()

    with DataService(
        duckdb_path=settings.database.duckdb_path,
        sqlite_path=settings.database.sqlite_path,
    ) as data_service:
        # 创建输出目录
        output_dir = Path("validation")
        output_dir.mkdir(exist_ok=True)

        # 获取数据库连接
        duckdb = data_service.get_duckdb()

        # 导出收盘价数据(2024年1-5月)
        print("\n1. 导出收盘价数据...")
        close_prices = {}

        for symbol in symbols:
            try:
                # 直接查询数据库
                query = """
                    SELECT
                        trade_date as date,
                        close_price as close
                    FROM daily_price
                    WHERE symbol = ?
                        AND trade_date BETWEEN '2024-01-01' AND '2024-05-31'
                    ORDER BY trade_date
                """
                result = duckdb.execute(query, [symbol]).fetchall()

                if result:
                    df = pl.DataFrame(result, schema=["date", "close"])
                    close_prices[symbol] = df
                    print(f"  [OK] {symbol}: {len(df)} 条记录")
                else:
                    print(f"  [WARN] {symbol}: 无数据")
            except Exception as e:
                print(f"  [ERROR] {symbol}: 获取数据失败 - {e}")

        # 导出为Excel文件
        if close_prices:
            with pd.ExcelWriter(
                output_dir / "close_prices_2024Q1Q2.xlsx", engine="openpyxl"
            ) as writer:
                for symbol, df in close_prices.items():
                    df.to_pandas().to_excel(writer, sheet_name=symbol, index=False)

            output_path = output_dir / "close_prices_2024Q1Q2.xlsx"
            print(f"\n[OK] 收盘价数据已导出至: {output_path}")

        # 导出复权因子数据
        print("\n2. 导出复权因子数据...")
        adj_factors = {}

        for symbol in symbols:
            try:
                # 查询复权因子
                query = """
                    SELECT
                        ex_date as date,
                        adj_factor,
                        adj_type,
                        description
                    FROM adjustment_factors
                    WHERE symbol = ?
                        AND ex_date BETWEEN '2022-01-01' AND '2024-12-31'
                    ORDER BY ex_date
                """
                result = duckdb.execute(query, [symbol]).fetchall()

                if result:
                    df = pl.DataFrame(
                        result, schema=["date", "adj_factor", "adj_type", "description"]
                    )
                    adj_factors[symbol] = df
                    print(f"  [OK] {symbol}: {len(df)} 条记录")
                else:
                    print(f"  [WARN] {symbol}: 无复权因子数据")
            except Exception as e:
                print(f"  [ERROR] {symbol}: 获取复权因子失败 - {e}")

        if adj_factors:
            with pd.ExcelWriter(
                output_dir / "adj_factors_2022-2024.xlsx", engine="openpyxl"
            ) as writer:
                for symbol, df in adj_factors.items():
                    df.to_pandas().to_excel(writer, sheet_name=symbol, index=False)

            adj_path = output_dir / "adj_factors_2022-2024.xlsx"
            print(f"\n[OK] 复权因子数据已导出至: {adj_path}")

        # 导出可能的涨跌停日期
        print("\n3. 查找涨跌停日期...")
        limit_up_down_dates = []

        for symbol in symbols:
            try:
                # 查询原始数据并计算涨跌幅
                query = """
                    SELECT
                        trade_date as date,
                        close_price as close
                    FROM daily_price
                    WHERE symbol = ?
                        AND trade_date BETWEEN '2023-01-01' AND '2024-12-31'
                    ORDER BY trade_date
                """
                result = duckdb.execute(query, [symbol]).fetchall()

                if result:
                    df = pl.DataFrame(result, schema=["date", "close"])

                    # 计算涨跌幅
                    df_with_change = df.with_columns(
                        [
                            (
                                (pl.col("close") - pl.col("close").shift(1))
                                / pl.col("close").shift(1)
                                * 100
                            ).alias("pct_change")
                        ]
                    )

                    # 找出涨跌停(涨跌停阈值: ±10%, ST股: ±5%)
                    limit_up = df_with_change.filter(
                        pl.col("pct_change") >= LIMIT_UP_THRESHOLD
                    )
                    limit_down = df_with_change.filter(
                        pl.col("pct_change") <= LIMIT_DOWN_THRESHOLD
                    )

                    if not limit_up.empty or not limit_down.empty:
                        print(f"\n{symbol} 涨跌停日期:")

                        if not limit_up.empty:
                            print("  涨停:")
                            for row in limit_up.select(
                                ["date", "close", "pct_change"]
                            ).to_dicts()[:10]:
                                print(
                                    f"    {row['date']}: {row['close']:.3f} (+{row['pct_change']:.2f}%)"
                                )
                                limit_up_down_dates.append(
                                    {
                                        "symbol": symbol,
                                        "date": row["date"],
                                        "close": row["close"],
                                        "pct_change": row["pct_change"],
                                        "type": "涨停",
                                    }
                                )

                        if not limit_down.empty:
                            print("  跌停:")
                            for row in limit_down.select(
                                ["date", "close", "pct_change"]
                            ).to_dicts()[:10]:
                                print(
                                    f"    {row['date']}: {row['close']:.3f} ({row['pct_change']:.2f}%)"
                                )
                                limit_up_down_dates.append(
                                    {
                                        "symbol": symbol,
                                        "date": row["date"],
                                        "close": row["close"],
                                        "pct_change": row["pct_change"],
                                        "type": "跌停",
                                    }
                                )
                    else:
                        print(f"\n{symbol}: 无涨跌停日期")
            except Exception as e:
                print(f"\n[ERROR] {symbol}: 查找涨跌停失败 - {e}")

        # 保存涨跌停日期到文件
        if limit_up_down_dates:
            limit_df = pl.DataFrame(limit_up_down_dates)
            limit_df.to_pandas().to_excel(
                output_dir / "limit_up_down_dates.xlsx", index=False
            )
            print(
                f"\n[OK] 涨跌停日期已导出至: {output_dir / 'limit_up_down_dates.xlsx'}"
            )

        # 导出原始数据供详细检查
        print("\n4. 导出原始日线数据(2023-2024)...")
        raw_data = {}

        for symbol in symbols:
            try:
                # 查询所有字段
                query = """
                    SELECT
                        trade_date as date,
                        open_price as open,
                        high_price as high,
                        low_price as low,
                        close_price as close,
                        volume,
                        amount,
                        turnover_rate,
                        pe_ratio,
                        pb_ratio
                    FROM daily_price
                    WHERE symbol = ?
                        AND trade_date BETWEEN '2023-01-01' AND '2024-12-31'
                    ORDER BY trade_date
                """
                result = duckdb.execute(query, [symbol]).fetchall()

                if result:
                    df = pl.DataFrame(
                        result,
                        schema=[
                            "date",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume",
                            "amount",
                            "turnover_rate",
                            "pe_ratio",
                            "pb_ratio",
                        ],
                    )
                    raw_data[symbol] = df
                    print(f"  [OK] {symbol}: {len(df)} 条记录")
            except Exception as e:
                print(f"  [ERROR] {symbol}: 获取数据失败 - {e}")

        if raw_data:
            with pd.ExcelWriter(
                output_dir / "raw_daily_data_2023-2024.xlsx", engine="openpyxl"
            ) as writer:
                for symbol, df in raw_data.items():
                    df.to_pandas().to_excel(writer, sheet_name=symbol, index=False)

            print(
                f"\n[OK] 原始日线数据已导出至: {output_dir / 'raw_daily_data_2023-2024.xlsx'}"
            )

        print("\n=== 验证文件导出完成 ===")
        print(f"输出目录: {output_dir.absolute()}")
        print("文件列表:")
        print(f"  - 收盘价数据: {output_dir / 'close_prices_2024Q1Q2.xlsx'}")
        print(f"  - 复权因子: {output_dir / 'adj_factors_2022-2024.xlsx'}")
        print(f"  - 涨跌停日期: {output_dir / 'limit_up_down_dates.xlsx'}")
        print(f"  - 原始数据: {output_dir / 'raw_daily_data_2023-2024.xlsx'}")


if __name__ == "__main__":
    export_for_manual_validation()
