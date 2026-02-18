#!/usr/bin/env python
"""
E2E 测试数据准备脚本。

生成以下测试数据：
1. TDX 样本目录结构
2. PIT 快照预期数据（从 Tushare API 获取）

使用方法：
    # 仅创建目录结构
    pixi run -e dev python tests/scripts/prepare_e2e_data.py --dirs-only

    # 生成快照数据（需要 TUSHARE_TOKEN）
    pixi run -e dev python tests/scripts/prepare_e2e_data.py --snapshots

    # 指定快照日期
    pixi run -e dev python tests/scripts/prepare_e2e_data.py --snapshots --date 2024-06-30

参考文档：docs/plans/2026-02-17-e2e-validation-design.md
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import polars as pl
import yaml


def load_golden_dataset() -> dict:
    """加载黄金数据集配置."""
    config_path = Path("config/default/golden_dataset.yml")
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_tdx_directory_structure() -> None:
    """创建 TDX 样本目录结构."""
    tdx_root = Path("tests/tdx_samples/vipdoc")

    # 创建交易所目录
    exchanges = ["sh", "sz"]
    for exchange in exchanges:
        exchange_dir = tdx_root / exchange / "lday"
        exchange_dir.mkdir(parents=True, exist_ok=True)

        # 创建 README 说明文件
        readme_path = exchange_dir / "README.md"
        if not readme_path.exists():
            readme_path.write_text(
                f"""# TDX {exchange.upper()} 日线数据目录

该目录存储通达信格式的日线数据文件（.day 格式）。

## 文件命名规范

```
<exchange><code>.day
```

示例：
- `sh600519.day` - 贵州茅台
- `sz000333.day` - 美的集团

## 数据来源

从通达信客户端导出，或使用 tushare2tdx 工具生成。

## 注意事项

- 文件为二进制格式，每条记录 32 字节
- 日期格式：YYYYMMDD（4 字节整数）
- 价格单位：元（4 字节浮点数）
"""
            )

    print(f"✅ TDX 目录结构已创建: {tdx_root}")


def get_source_ticker(ticker: str, exchange: str) -> str:
    """转换为 Tushare source_ticker 格式."""
    exchange_map = {
        "XSHG": "SH",
        "XSHE": "SZ",
        "SW": "SI",
    }
    tushare_exchange = exchange_map.get(exchange, "SZ")
    return f"{ticker}.{tushare_exchange}"


def fetch_snapshot_data(
    tushare_source,
    ticker: str,
    exchange: str,
    as_of_date: str,
) -> pl.DataFrame | None:
    """从 Tushare 获取快照数据."""
    source_ticker = get_source_ticker(ticker, exchange)

    try:
        # 根据交易所推断资产类型
        if exchange == "SW":
            # SW 指数需要单独处理
            return None

        # 尝试获取日线数据
        df = tushare_source.fetch_stock_daily(trade_date=as_of_date)

        if df.is_empty():
            return None

        # 过滤指定 ticker
        if "source_ticker" in df.columns:
            df = df.filter(pl.col("source_ticker") == source_ticker)

        return df if not df.is_empty() else None

    except Exception as e:
        print(f"  ⚠️ 获取 {source_ticker} 数据失败: {e}")
        return None


def generate_pit_snapshots(as_of_date: str) -> int:
    """生成 PIT 快照预期数据."""
    import keyring
    from ditto_datahub.config import DataSourceSettings
    from ditto_datahub.sources import TushareSource
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
        print("❌ TUSHARE_TOKEN 未配置，无法生成快照数据")
        print("   请设置环境变量: export TUSHARE_TOKEN=your_token")
        return 0

    # 初始化数据源
    tushare_source = TushareSource(settings=DataSourceSettings(), token=token)

    # 加载黄金数据集
    config = load_golden_dataset()
    tickers = config.get("tickers", [])

    # 快照目录
    snapshot_dir = Path("tests/fixtures/golden_expected/daily_snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0

    print(f"📊 生成 PIT 快照 (as_of={as_of_date})...")

    for ticker_info in tickers:
        ticker = ticker_info["ticker"]
        name = ticker_info["name"]
        exchange = ticker_info["exchange"]
        asset_type = ticker_info.get("asset_type", "stock")

        print(f"  处理 {ticker} ({name})...")

        # 根据资产类型获取数据
        df = None
        try:
            if asset_type == "stock":
                df = tushare_source.fetch_stock_daily(trade_date=as_of_date)
                if not df.is_empty() and "source_ticker" in df.columns:
                    source_ticker = get_source_ticker(ticker, exchange)
                    df = df.filter(pl.col("source_ticker") == source_ticker)

            elif asset_type == "etf":
                df = tushare_source.fetch_etf_daily(trade_date=as_of_date)
                if not df.is_empty() and "source_ticker" in df.columns:
                    source_ticker = get_source_ticker(ticker, exchange)
                    df = df.filter(pl.col("source_ticker") == source_ticker)

            elif asset_type in ("index_market", "index_style"):
                source_ticker = get_source_ticker(ticker, exchange)
                df = tushare_source.fetch_index_daily(
                    trade_date=as_of_date,
                    ts_codes=[source_ticker],
                )

            if df is not None and not df.is_empty():
                # 保存快照
                snapshot_file = snapshot_dir / f"{ticker}_as_of_{as_of_date}.parquet"
                df.write_parquet(snapshot_file)
                success_count += 1
                print(f"    ✅ 已保存: {snapshot_file.name}")
            else:
                print("    ⚠️ 无数据")

        except Exception as e:
            print(f"    ❌ 失败: {e}")

    print(f"\n✅ 成功生成 {success_count}/{len(tickers)} 个快照")
    return success_count


def verify_data_completeness() -> bool:
    """验证测试数据完整性."""
    print("🔍 验证测试数据完整性...")

    issues = []

    # 检查 TDX 目录
    tdx_sh = Path("tests/tdx_samples/vipdoc/sh/lday")
    tdx_sz = Path("tests/tdx_samples/vipdoc/sz/lday")

    sh_files = list(tdx_sh.glob("*.day")) if tdx_sh.exists() else []
    sz_files = list(tdx_sz.glob("*.day")) if tdx_sz.exists() else []

    print(f"  TDX SH 文件: {len(sh_files)}")
    print(f"  TDX SZ 文件: {len(sz_files)}")

    if len(sh_files) + len(sz_files) == 0:
        issues.append("TDX 样本文件为空（预期需要 .day 文件）")

    # 检查快照文件
    snapshot_dir = Path("tests/fixtures/golden_expected/daily_snapshots")
    snapshot_files = (
        list(snapshot_dir.glob("*.parquet")) if snapshot_dir.exists() else []
    )

    print(f"  PIT 快照文件: {len(snapshot_files)}")

    if len(snapshot_files) == 0:
        issues.append("PIT 快照文件为空（预期需要 .parquet 文件）")

    # 检查黄金数据集配置
    config = load_golden_dataset()
    tickers = config.get("tickers", [])
    print(f"  黄金数据集标的: {len(tickers)}")

    if len(tickers) == 0:
        issues.append("黄金数据集配置为空")

    if issues:
        print("\n⚠️ 发现以下问题:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print("\n✅ 数据完整性验证通过")
    return True


def main() -> None:
    """主函数."""
    parser = argparse.ArgumentParser(
        description="E2E 测试数据准备脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 仅创建目录结构
  python tests/scripts/prepare_e2e_data.py --dirs-only

  # 生成快照数据
  python tests/scripts/prepare_e2e_data.py --snapshots

  # 验证数据完整性
  python tests/scripts/prepare_e2e_data.py --verify
        """,
    )

    parser.add_argument(
        "--dirs-only",
        action="store_true",
        help="仅创建目录结构，不获取数据",
    )
    parser.add_argument(
        "--snapshots",
        action="store_true",
        help="生成 PIT 快照预期数据",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="2024-06-28",
        help="快照日期 (默认: 2024-06-28，最近交易日)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="验证测试数据完整性",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("E2E 测试数据准备")
    print("=" * 60)

    if args.dirs_only:
        create_tdx_directory_structure()
        return

    if args.verify:
        verify_data_completeness()
        return

    if args.snapshots:
        create_tdx_directory_structure()
        generate_pit_snapshots(args.date)
        verify_data_completeness()
        return

    # 默认：创建目录 + 验证
    create_tdx_directory_structure()
    verify_data_completeness()


if __name__ == "__main__":
    main()
