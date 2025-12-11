#!/usr/bin/env python3
"""
Golden Dataset 初始化脚本.

收集 Phase 0.5 需要的验证数据
"""

import logging
import sys
from typing import Any

try:
    from ditto_core.data.collector import DataCollector
    from ditto_core.data.service import DataService
    from ditto_foundation.config.settings import get_settings
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/init_golden_dataset.py")
    sys.exit(1)

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

    settings = get_settings()

    with DataService(
        duckdb_path=settings.database.duckdb_path,
        sqlite_path=settings.database.sqlite_path,
    ) as data_service:
        # 创建Mock适配器
        class MockAdapter:
            def store_etf_info(self, df: Any) -> None:
                logger.info(f"Mock存储ETF信息: {len(df)}条记录")

            def store_daily_data(self, df: Any) -> None:
                logger.info(f"Mock存储日线数据: {len(df)}条记录")

            def update_adj_factors(
                self, symbols: list[str], start_date: str, end_date: str
            ) -> dict[str, Any]:
                logger.info(f"Mock更新复权因子: {len(symbols)}只标的")
                return {"status": "completed", "records": 50}

        collector = DataCollector(data_service)
        collector._analytics_adapter = MockAdapter()

        # 1. 确保ETF列表是最新的
        logger.info("1. 更新ETF列表...")
        # Mock更新
        logger.info("✅ ETF列表更新完成(M)")

        # 2. 下载历史数据(2022-2024年)
        logger.info("2. 下载历史数据...")
        daily_result: dict[str, Any] = {
            "total_records": 2000,  # Mock: 3年 * 4个标的 * ~166天/年
            "symbols_updated": GOLDEN_SYMBOLS[:3],  # Mock更新了前3个
            "validation_errors": [],  # Mock无错误
            "status": "completed",
        }

        # 3. 下载复权因子
        logger.info("3. 下载复权因子...")
        collector._analytics_adapter.update_adj_factors(
            symbols=GOLDEN_SYMBOLS, start_date="20220101", end_date="20241231"
        )

        # 4. 生成报告
        logger.info("\n=== Golden Dataset 初始化报告 ===")
        logger.info("ETF列表: 已更新(M)")
        logger.info(f"日线数据: {daily_result['total_records']} 条记录")
        logger.info(f"成功更新: {len(daily_result['symbols_updated'])} 只标的")
        if daily_result["validation_errors"]:
            logger.info(f"验证错误: {len(daily_result['validation_errors'])} 个")
            for error in daily_result["validation_errors"][:5]:
                logger.info(f"  - {error}")

        logger.info(
            "\n注意: 这是Mock运行(M), 需要配置真实的Tushare Token才能获取真实数据"
        )
        logger.info(f"Golden Dataset 标的: {', '.join(GOLDEN_SYMBOLS)}")


if __name__ == "__main__":
    init_golden_dataset()
