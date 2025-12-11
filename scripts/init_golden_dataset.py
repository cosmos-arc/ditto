#!/usr/bin/env python3
"""
Golden Dataset 初始化脚本.

收集 Phase 0.5 需要的验证数据
"""

import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import polars as pl
    from ditto_core.data.services.data_reader import DataReader
    from ditto_core.data.services.data_writer import DataWriter
    from ditto_foundation.config.settings import get_settings
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/init_golden_dataset.py")
    sys.exit(1)

# Import CSV adapter for testing
sys.path.append(str(Path(__file__).parent))
from csv_adapter import CSVAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Golden Dataset 标的
GOLDEN_SYMBOLS = [
    "510300.SH",  # 沪深300ETF
    "516010.SH",  # 游戏ETF
    "513100.SH",  # 纳指ETF
    "000300.SH",  # 沪深300指数
]


def init_golden_dataset() -> None:
    """初始化 Golden Dataset."""
    logger.info("初始化 Golden Dataset...")

    # 使用CSV适配器存储Golden Dataset
    data_dir = Path("data/golden_dataset")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 确保ETF列表是最新的
    logger.info("1. 更新ETF列表...")
    etf_data = pl.DataFrame(
        {
            "symbol": GOLDEN_SYMBOLS,
            "name": ["沪深300ETF", "游戏ETF", "纳指ETF", "沪深300指数"],
            "list_date": ["2012-04-26", "2015-06-18", "2013-11-06", "2005-04-08"],
            "knowledge_date": [datetime.now() for _ in GOLDEN_SYMBOLS],
        }
    )
    writer.store_etf_info(etf_data)
    logger.info(f"[OK] ETF列表更新完成: {len(etf_data)} 条记录")

    # 2. 生成历史数据(2022-2024年)
    logger.info("2. 生成历史数据(2022-2024年)...")
    daily_records = []
    trading_days = []

    # 为每个Golden标的生成3年历史数据
    for symbol in GOLDEN_SYMBOLS:
        # 设置基准价格
        if symbol == "510300.SH":
            base_price = 4.0
        elif symbol == "516010.SH":
            base_price = 1.5
        elif symbol == "513100.SH":
            base_price = 50.0
        else:  # 000300.SH (指数)
            base_price = 4000.0

        # 生成3年数据（每年约250个交易日）
        current_price = base_price
        for year in range(2022, 2025):
            for day in range(250):
                # 跳过周末（简化处理）
                date = datetime(year, 1, 1) + timedelta(days=day)
                if date.weekday() >= 5:
                    continue

                # 生成随机价格变动（模拟真实市场波动）
                price_change = random.uniform(-0.03, 0.03)
                current_price *= 1 + price_change

                # 记录交易日
                if year == 2022 and symbol == GOLDEN_SYMBOLS[0]:
                    trading_days.append(
                        {
                            "date": date.strftime("%Y-%m-%d"),
                            "is_trading_day": True,
                            "market": "all",
                        }
                    )

                # 记录日线数据
                daily_records.append(
                    {
                        "symbol": symbol,
                        "date": date.strftime("%Y-%m-%d"),
                        "open": current_price * 0.998,
                        "high": current_price * 1.02,
                        "low": current_price * 0.98,
                        "close": current_price,
                        "volume": random.randint(1000000, 10000000),
                    }
                )

    # 存储日线数据
    daily_data = pl.DataFrame(daily_records)
    writer.store_daily_data(daily_data)
    daily_result = {
        "total_records": len(daily_data),
        "symbols_updated": GOLDEN_SYMBOLS,
        "validation_errors": [],
        "status": "completed",
    }
    logger.info(f"[OK] 日线数据生成完成: {daily_result['total_records']} 条记录")

    # 3. 生成复权因子
    logger.info("3. 生成复权因子...")
    adj_records = []

    # 为每只ETF在每年生成一次分红复权
    for symbol in GOLDEN_SYMBOLS[:3]:  # 不包括指数
        for year in range(2022, 2025):
            # 模拟分红复权
            adj_records.append(
                {
                    "symbol": symbol,
                    "ex_date": f"{year}-06-01",
                    "adj_factor": 0.95 + random.uniform(-0.02, 0.02),
                    "adj_type": "dividend",
                    "description": f"{year}年分红派息",
                }
            )

            # 偶尔发生拆股
            if year == 2023 and symbol == "513100.SH":
                adj_records.append(
                    {
                        "symbol": symbol,
                        "ex_date": f"{year}-12-01",
                        "adj_factor": 0.5,
                        "adj_type": "split",
                        "description": f"{year}年拆股",
                    }
                )

    if adj_records:
        adj_data = pl.DataFrame(adj_records)
        writer.store_adjustment_factors(adj_data)
        logger.info(f"[OK] 复权因子生成完成: {len(adj_records)} 条记录")

    # 4. 存储交易日历
    if trading_days:
        calendar_data = pl.DataFrame(trading_days)
        writer.store_trading_calendar(calendar_data)

    # 5. 生成报告
    logger.info("\n=== Golden Dataset 初始化报告 ===")
    logger.info(f"ETF列表: {len(etf_data)} 只")
    logger.info(f"日线数据: {daily_result['total_records']} 条记录")
    logger.info(f"成功更新: {len(daily_result['symbols_updated'])} 只标的")
    logger.info(f"复权因子: {len(adj_records)} 条记录")
    logger.info(f"交易日历: {len(trading_days)} 天")

    # 验证数据完整性
    logger.info("\n验证数据完整性...")
    for symbol in GOLDEN_SYMBOLS:
        df = reader.get_daily_data(symbol, "2022-01-01", "2024-12-31")
        if len(df) > 0:
            logger.info(f"  [OK] {symbol}: {len(df)} 条记录")

            # 验证日期范围
            min_date = df["date"].min()
            max_date = df["date"].max()
            logger.info(f"    数据范围: {min_date} 至 {max_date}")

            # 检查是否有复权因子
            adj_df = reader.get_adjustment_factors(symbol)
            if not adj_df.empty:
                logger.info(f"    复权因子: {len(adj_df)} 条记录")
        else:
            logger.error(f"  [ERROR] {symbol}: 无数据")

    logger.info("\n[OK] Golden Dataset 初始化完成！")
    logger.info(f"数据存储位置: {data_dir.absolute()}")
    logger.info(f"Golden Dataset 标的: {', '.join(GOLDEN_SYMBOLS)}")


if __name__ == "__main__":
    init_golden_dataset()
