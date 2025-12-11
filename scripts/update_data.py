#!/usr/bin/env python3
"""
数据更新脚本 - Phase 0.5 版本.

支持增量更新和 Golden Dataset 初始化
"""

import logging
import sys
from typing import Any

try:
    import polars as pl
    from ditto_core.data.collector import DataCollector
    from ditto_core.data.service import DataService
    from ditto_foundation.config.settings import get_settings
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/update_data.py")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def update_market_data() -> None:
    """更新市场数据."""
    logger.info("开始更新市场数据...")

    settings = get_settings()

    with DataService(
        duckdb_path=settings.database.duckdb_path,
        sqlite_path=settings.database.sqlite_path,
    ) as data_service:
        # 创建一个简单的Mock对象来测试脚本
        class MockAdapter:
            def store_etf_info(self, df: Any) -> None:
                logger.info(f"Mock存储ETF信息: {len(df)}条记录")

            def store_daily_data(self, df: Any) -> None:
                logger.info(f"Mock存储日线数据: {len(df)}条记录")

            def get_etf_list(self) -> pl.DataFrame:
                return pl.DataFrame(
                    {
                        "symbol": ["510300.SH", "516010.SH", "513100.SH"],
                        "name": ["沪深300ETF", "游戏ETF", "纳指ETF"],
                    }
                )

        collector = DataCollector(data_service)
        collector._analytics_adapter = MockAdapter()

        # 1. 更新ETF列表 (Mock)
        logger.info("更新ETF列表...")
        # 由于没有真实的token, 这里只是模拟更新
        logger.info("✅ ETF列表更新完成(M)")

        # 2. 获取所有ETF代码
        etf_list = MockAdapter().get_etf_list()
        symbols = etf_list["symbol"].to_list()

        # 3. 更新日线数据(Mock)
        logger.info(f"更新日线数据: {len(symbols)} 只ETF...")
        daily_result: dict[str, Any] = {
            "total_records": 100,
            "symbols_updated": symbols[:2],  # Mock更新了前2个
            "validation_errors": ["符号1: 验证错误示例(M)"],  # Mock错误
            "status": "completed",
        }

        logger.info("✅ 日线数据更新完成(M):")
        logger.info(f"   - 总记录数: {daily_result['total_records']}")
        logger.info(f"   - 更新成功: {len(daily_result['symbols_updated'])} 只")
        if daily_result["validation_errors"]:
            logger.info(f"   - 验证错误: {len(daily_result['validation_errors'])} 个")

        logger.info(
            "\n注意: 这是Mock运行(M), 需要配置真实的Tushare Token才能获取真实数据"
        )


if __name__ == "__main__":
    update_market_data()
