#!/usr/bin/env python3
"""
测试数据流脚本 - 验证DataReader/DataWriter架构.

这个脚本测试完整的数据流程：
1. 创建测试数据
2. 使用DataWriter写入数据
3. 使用DataReader读取数据
4. 验证数据完整性
"""

import sys
from datetime import datetime
from pathlib import Path

try:
    import polars as pl
    from ditto_core.data.services.data_reader import DataReader
    from ditto_core.data.services.data_writer import DataWriter
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/test_data_flow.py")
    sys.exit(1)

# Import CSV adapter for testing
sys.path.append(str(Path(__file__).parent))
from csv_adapter import CSVAdapter


def test_etf_info_flow() -> None:
    """测试ETF信息数据流程."""
    print("\n=== 测试ETF信息数据流程 ===")

    # 创建测试数据目录
    data_dir = Path("data/test_etf_flow")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 创建测试数据
    print("\n1. 创建ETF信息测试数据...")
    test_etf_data = pl.DataFrame(
        {
            "symbol": ["510300.SH", "516010.SH", "513100.SH"],
            "name": ["沪深300ETF", "游戏ETF", "纳指ETF"],
            "list_date": ["2012-04-26", "2015-06-18", "2013-11-06"],
            "market": ["SHSE", "SHSE", "SHSE"],
            "knowledge_date": [datetime.now() for _ in range(3)],
        }
    )
    print(f"  创建测试数据: {len(test_etf_data)} 条记录")

    # 2. 写入数据
    print("\n2. 写入数据...")
    writer.store_etf_info(test_etf_data)
    print("  [OK] 数据写入成功")

    # 3. 读取数据
    print("\n3. 读取数据...")
    read_data = reader.get_etf_list()
    print(f"  读取数据: {len(read_data)} 条记录")

    # 4. 验证数据
    print("\n4. 验证数据...")
    assert len(read_data) == 3, f"期望3条记录，实际{len(read_data)}条"
    assert set(read_data["symbol"].to_list()) == {"510300.SH", "516010.SH", "513100.SH"}
    assert "name" in read_data.columns
    assert "list_date" in read_data.columns
    print("  [OK] 数据验证成功")


def test_daily_data_flow() -> None:
    """测试日线数据流程."""
    print("\n=== 测试日线数据流程 ===")

    # 创建测试数据目录
    data_dir = Path("data/test_daily_flow")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 创建测试数据
    print("\n1. 创建日线数据测试数据...")
    test_daily_data = pl.DataFrame(
        {
            "symbol": ["510300.SH"] * 5 + ["516010.SH"] * 5,
            "date": [
                "2024-12-01",
                "2024-12-02",
                "2024-12-03",
                "2024-12-04",
                "2024-12-05",
            ]
            * 2,
            "open": [4.0, 4.05, 4.03, 4.08, 4.06, 1.5, 1.52, 1.49, 1.53, 1.51],
            "high": [4.1, 4.08, 4.09, 4.10, 4.09, 1.55, 1.53, 1.54, 1.55, 1.54],
            "low": [3.98, 4.02, 4.01, 4.05, 4.04, 1.48, 1.48, 1.47, 1.50, 1.49],
            "close": [4.05, 4.03, 4.08, 4.06, 4.07, 1.52, 1.49, 1.53, 1.51, 1.52],
            "volume": [1000000, 1100000, 1200000, 1300000, 1400000] * 2,
            "amount": [
                4050000,
                4433000,
                4896000,
                5278000,
                5698000,
                760000,
                777800,
                812700,
                795200,
                821600,
            ],
        }
    )
    print(f"  创建测试数据: {len(test_daily_data)} 条记录")

    # 2. 写入数据
    print("\n2. 写入数据...")
    writer.store_daily_data(test_daily_data)
    print("  [OK] 数据写入成功")

    # 3. 读取数据
    print("\n3. 读取数据...")
    # 读取510300.SH的数据
    read_data = reader.get_daily_data("510300.SH", "2024-12-01", "2024-12-05")
    print(f"  读取510300.SH数据: {len(read_data)} 条记录")

    # 4. 验证数据
    print("\n4. 验证数据...")
    assert len(read_data) == 5, f"期望5条记录，实际{len(read_data)}条"
    assert read_data["symbol"].to_list() == ["510300.SH"] * 5
    assert "date" in read_data.columns
    assert "close" in read_data.columns
    assert read_data["close"][0] == 4.05
    print("  [OK] 510300.SH数据验证成功")

    # 读取516010.SH的数据
    read_data_2 = reader.get_daily_data("516010.SH", "2024-12-01", "2024-12-05")
    assert len(read_data_2) == 5, f"期望5条记录，实际{len(read_data_2)}条"
    assert read_data_2["symbol"].to_list() == ["516010.SH"] * 5
    print("  [OK] 516010.SH数据验证成功")


def test_adjustment_factors_flow() -> None:
    """测试复权因子数据流程."""
    print("\n=== 测试复权因子数据流程 ===")

    # 创建测试数据目录
    data_dir = Path("data/test_adj_flow")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 创建测试数据
    print("\n1. 创建复权因子测试数据...")
    test_adj_data = pl.DataFrame(
        {
            "symbol": ["510300.SH", "510300.SH", "516010.SH"],
            "ex_date": ["2024-06-01", "2024-12-01", "2024-06-01"],
            "adj_factor": [0.95, 0.98, 0.92],
            "adj_type": ["dividend", "dividend", "dividend"],
            "description": ["2024年中期分红", "2024年末分红", "2024年中期分红"],
        }
    )
    print(f"  创建测试数据: {len(test_adj_data)} 条记录")

    # 2. 写入数据
    print("\n2. 写入数据...")
    writer.store_adjustment_factors(test_adj_data)
    print("  [OK] 数据写入成功")

    # 3. 读取数据
    print("\n3. 读取数据...")
    read_data = reader.get_adjustment_factors("510300.SH")
    print(f"  读取510300.SH复权因子: {len(read_data)} 条记录")

    # 4. 验证数据
    print("\n4. 验证数据...")
    assert len(read_data) == 2, f"期望2条记录，实际{len(read_data)}条"
    assert read_data["symbol"].to_list() == ["510300.SH", "510300.SH"]
    assert "ex_date" in read_data.columns
    assert "adj_factor" in read_data.columns
    print("  [OK] 复权因子数据验证成功")


def test_trading_calendar_flow() -> None:
    """测试交易日历数据流程."""
    print("\n=== 测试交易日历数据流程 ===")

    # 创建测试数据目录
    data_dir = Path("data/test_calendar_flow")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 创建测试数据
    print("\n1. 创建交易日历测试数据...")
    test_calendar_data = pl.DataFrame(
        {
            "date": [
                "2024-12-01",
                "2024-12-02",
                "2024-12-03",
                "2024-12-04",
                "2024-12-05",
            ],
            "is_trading_day": [True, True, False, True, True],  # 12月3日为非交易日
            "market": ["all"] * 5,
        }
    )
    print(f"  创建测试数据: {len(test_calendar_data)} 条记录")

    # 2. 写入数据
    print("\n2. 写入数据...")
    writer.store_trading_calendar(test_calendar_data)
    print("  [OK] 数据写入成功")

    # 3. 读取数据
    print("\n3. 读取数据...")
    read_data = reader.get_trading_calendar("2024-12-01", "2024-12-05")
    print(f"  读取交易日历: {len(read_data)} 条记录")

    # 4. 验证数据
    print("\n4. 验证数据...")
    assert len(read_data) == 5, f"期望5条记录，实际{len(read_data)}条"
    assert "date" in read_data.columns
    assert "is_trading_day" in read_data.columns
    assert not read_data.filter(pl.col("date") == pl.date(2024, 12, 3))[
        "is_trading_day"
    ][0]
    print("  [OK] 交易日历数据验证成功")


def test_cross_symbol_data_consistency() -> None:
    """测试跨标的 数据一致性."""
    print("\n=== 测试跨标的 数据一致性 ===")

    # 创建测试数据目录
    data_dir = Path("data/test_consistency")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 写入多个标的的数据
    print("\n1. 写入多个标的的数据...")
    symbols = ["510300.SH", "516010.SH", "513100.SH"]
    dates = ["2024-12-01", "2024-12-02", "2024-12-03"]

    records = []
    for symbol in symbols:
        for i, date in enumerate(dates):
            base_price = {"510300.SH": 4.0, "516010.SH": 1.5, "513100.SH": 50.0}[symbol]
            price = base_price * (1 + i * 0.01)
            records.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "open": price * 0.995,
                    "high": price * 1.01,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 1000000 + i * 100000,
                }
            )

    test_data = pl.DataFrame(records)
    writer.store_daily_data(test_data)
    print(f"  写入数据: {len(test_data)} 条记录")

    # 2. 读取并验证一致性
    print("\n2. 读取并验证数据一致性...")
    for symbol in symbols:
        df = reader.get_daily_data(symbol, "2024-12-01", "2024-12-03")
        assert len(df) == 3, f"{symbol}期望3条记录，实际{len(df)}条"
        # Convert dates to string for comparison
        date_strings = [str(d) for d in df["date"].to_list()]
        assert all(
            ds in ["2024-12-01", "2024-12-02", "2024-12-03"] for ds in date_strings
        )
        print(f"  [OK] {symbol} 数据一致性验证成功")

    # 3. 测试日期范围过滤
    print("\n3. 测试日期范围过滤...")
    filtered_df = reader.get_daily_data("510300.SH", "2024-12-02", "2024-12-03")
    assert len(filtered_df) == 2, f"期望2条记录，实际{len(filtered_df)}条"
    # Convert dates to string for comparison
    filtered_date_strings = [str(d) for d in filtered_df["date"].to_list()]
    assert all(ds in ["2024-12-02", "2024-12-03"] for ds in filtered_date_strings)
    print("  [OK] 日期范围过滤验证成功")


def main() -> None:
    """主函数 - 运行所有测试."""
    print("\n" + "=" * 60)
    print("DataReader/DataWriter 数据流测试")
    print("=" * 60)

    try:
        # 运行各项测试
        test_etf_info_flow()
        test_daily_data_flow()
        test_adjustment_factors_flow()
        test_trading_calendar_flow()
        test_cross_symbol_data_consistency()

        # 总结
        print("\n" + "=" * 60)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 60)
        print("\n测试完成。数据文件保存在 data/test_*_flow 目录下。")

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
