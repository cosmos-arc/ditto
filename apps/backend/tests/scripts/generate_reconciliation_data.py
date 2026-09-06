#!/usr/bin/env python
"""
生成跨源对账预期数据的脚本。

从 Tushare API 获取实际数据并保存为 Parquet 格式，
用于 E2E 测试中的跨源对账验证。

使用方法：
    uv run --no-sync python tests/scripts/generate_reconciliation_data.py
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
import yaml


def load_golden_dataset() -> dict:
    """加载黄金数据集配置."""
    config_path = Path("config/default/golden_dataset.yml")
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_source_ticker(ticker: str, exchange: str) -> str:
    """转换为 Tushare source_ticker 格式."""
    exchange_map = {
        "XSHG": "SH",
        "XSHE": "SZ",
        "SW": "SI",
    }
    tushare_exchange = exchange_map.get(exchange, "SZ")
    return f"{ticker}.{tushare_exchange}"


def generate_reconciliation_parquet(as_of_date: str) -> int:
    """生成对账预期 Parquet 文件."""
    import keyring
    from ditto_data.config import DataSourceSettings
    from ditto_data.sources.tushare.tushare_source import TushareSource
    from keyring.errors import KeyringError

    # 获取 Token
    token = None
    try:
        token = keyring.get_password("ditto", "tushare")
    except KeyringError:
        pass

    if not token:
        token = os.environ.get("TUSHARE_TOKEN")

    if not token:
        print("❌ TUSHARE_TOKEN 未配置，无法生成对账数据")
        print("   请设置环境变量: export TUSHARE_TOKEN=your_token")
        return 0

    # 初始化数据源
    tushare_source = TushareSource(settings=DataSourceSettings(), token=token)

    # 加载黄金数据集
    config = load_golden_dataset()
    tickers = config.get("tickers", [])

    # 收集所有数据
    all_data = []

    print(f"📊 生成对账数据 (as_of={as_of_date})...")

    for ticker_info in tickers:
        ticker = ticker_info["ticker"]
        name = ticker_info["name"]
        exchange = ticker_info["exchange"]
        asset_type = ticker_info.get("asset_type", "stock")
        source_ticker = get_source_ticker(ticker, exchange)

        print(f"  处理 {ticker} ({name})...")

        try:
            df = None

            if asset_type == "stock":
                df = tushare_source.fetch_stock_daily(trade_date=as_of_date)
            elif asset_type == "etf":
                df = tushare_source.fetch_etf_daily(trade_date=as_of_date)
            elif asset_type in ("index_market", "index_style"):
                df = tushare_source.fetch_index_daily(
                    trade_date=as_of_date,
                    ts_codes=[source_ticker],
                )

            if df is not None and not df.is_empty():
                if "source_ticker" in df.columns:
                    df = df.filter(pl.col("source_ticker") == source_ticker)

                if not df.is_empty():
                    # 添加标识信息
                    df = df.with_columns(
                        [
                            pl.lit(name).alias("name"),
                            pl.lit(asset_type).alias("asset_type"),
                            pl.lit(exchange).alias("exchange"),
                        ]
                    )
                    all_data.append(df)
                    print("    ✅ 已获取数据")
                else:
                    print("    ⚠️ 无匹配数据")
            else:
                print("    ⚠️ 无数据")

        except Exception as e:
            print(f"    ❌ 失败: {e}")

    if all_data:
        # 合并所有数据
        combined = pl.concat(all_data)

        # 保存为 Parquet
        output_path = (
            Path("tests/fixtures/golden_expected/reconciliation")
            / f"reconciliation_{as_of_date}.parquet"
        )
        combined.write_parquet(output_path)
        print(f"\n✅ 已保存: {output_path}")
        return len(all_data)

    return 0


def main() -> None:
    """主函数."""
    import argparse

    parser = argparse.ArgumentParser(description="生成跨源对账预期数据")
    parser.add_argument(
        "--date",
        type=str,
        default="2024-06-28",
        help="对账日期 (默认: 2024-06-28)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("跨源对账数据生成")
    print("=" * 60)

    count = generate_reconciliation_parquet(args.date)
    print(f"\n成功生成 {count} 个标的的对账数据")


if __name__ == "__main__":
    main()
