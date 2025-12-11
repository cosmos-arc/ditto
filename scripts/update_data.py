#!/usr/bin/env python3
"""
数据更新脚本 - Phase 0.5 版本.

支持增量更新和 Golden Dataset 初始化
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

try:
    import polars as pl
    from ditto_core.data.services.data_reader import DataReader
    from ditto_core.data.services.data_writer import DataWriter
    from ditto_foundation.config.settings import get_settings
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/update_data.py")
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


def update_market_data() -> None:
    """更新市场数据."""
    logger.info("开始更新市场数据...")

    # 使用CSV适配器进行测试
    data_dir = Path("data/csv_test")
    csv_adapter = CSVAdapter(data_dir=data_dir)

    # 创建DataReader和DataWriter
    reader = DataReader(csv_adapter)
    writer = DataWriter(csv_adapter)

    # 1. 创建并更新ETF列表
    logger.info("更新ETF列表...")
    etf_data = pl.DataFrame(
        {
            "symbol": ["510300.SH", "516010.SH", "513100.SH", "000300.SH"],
            "name": ["沪深300ETF", "游戏ETF", "纳指ETF", "沪深300指数"],
            "list_date": ["2012-04-26", "2015-06-18", "2013-11-06", "2005-04-08"],
            "knowledge_date": [datetime.now() for _ in range(4)],
        }
    )
    writer.store_etf_info(etf_data)
    logger.info(f"[OK] ETF列表更新完成: {len(etf_data)} 条记录")

    # 2. 获取所有ETF代码
    etf_list = reader.get_etf_list()
    symbols = etf_list["symbol"].to_list()
    logger.info(f"获取到 {len(symbols)} 只ETF")

    # 3. 创建并更新日线数据（示例数据）
    logger.info(f"更新日线数据: {len(symbols)} 只ETF...")
    daily_records = []

    # 为每个ETF生成示例数据
    for i, symbol in enumerate(symbols):
        base_price = 3.0 + i * 0.5  # 基准价格
        for date_offset in range(10):  # 最近10天数据
            date = datetime(2024, 12, 1 + date_offset).strftime("%Y-%m-%d")
            # 生成随机价格变动
            price = base_price * (1 + (date_offset - 5) * 0.02)

            daily_records.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "open": price * 0.995,
                    "high": price * 1.01,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 1000000 + date_offset * 10000,
                }
            )

    # 存储日线数据
    daily_data = pl.DataFrame(daily_records)
    writer.store_daily_data(daily_data)

    # 4. 创建并存储复权因子
    logger.info("更新复权因子...")
    adj_records = []
    for symbol in symbols[:2]:  # 只为前两个ETF创建复权因子
        adj_records.append(
            {
                "symbol": symbol,
                "ex_date": "2024-06-01",
                "adj_factor": 1.05,
                "adj_type": "dividend",
                "description": "分红派息",
            }
        )

    if adj_records:
        adj_data = pl.DataFrame(adj_records)
        writer.store_adjustment_factors(adj_data)
        logger.info(f"[OK] 复权因子更新完成: {len(adj_records)} 条记录")

    # 5. 生成更新报告
    logger.info("\n=== 数据更新报告 ===")
    logger.info(f"ETF列表: {len(etf_list)} 只")
    logger.info(f"日线数据: {len(daily_data)} 条记录")
    logger.info(f"复权因子: {len(adj_records)} 条记录")

    # 验证数据
    logger.info("\n验证数据存储...")
    for symbol in symbols[:2]:  # 只验证前两个
        df = reader.get_daily_data(symbol, "2024-12-01", "2024-12-10")
        if len(df) > 0:
            logger.info(f"  [OK] {symbol}: {len(df)} 条记录")
        else:
            logger.info(f"  [ERROR] {symbol}: 无数据")

    logger.info("\n[OK] 数据更新完成！")
    logger.info(f"数据存储位置: {data_dir.absolute()}")


if __name__ == "__main__":
    update_market_data()
