"""
质量对比结果读取器.

Provides read-only access to quality comparison data.
"""

from pathlib import Path

import polars as pl
from ditto_infra.foundation import logger


class ComparisonReader:
    """
    质量对比数据读取器.

    路径：data_root/quarantine/quality_comparison/
    保留：30 天自动清理

    职责：只读取 DataFrame，不依赖 Engine 层类型
    """

    def __init__(
        self,
        base_path: Path,
        retention_days: int = 30,
    ) -> None:
        """
        初始化读取器.

        Args:
            base_path: 基础路径（通常是 data_root）
            retention_days: 数据保留天数

        """
        self.base_path = Path(base_path) / "quarantine" / "quality_comparison"
        self.retention_days = retention_days

    def read_comparison(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> pl.DataFrame | None:
        """
        读取对比结果.

        Args:
            trade_date: 交易日期
            dataset: 数据集标识

        Returns:
            DataFrame or None if not found

        """
        year = trade_date[:4]
        month = trade_date[4:6]
        dataset_path = self.base_path / f"year={year}" / f"month={month}" / dataset
        file_path = dataset_path / f"{trade_date}.parquet"

        if not file_path.exists():
            return None

        df = pl.read_parquet(file_path)
        return df  # 路径已包含 dataset，无需过滤

    def get_stats(self) -> list[dict[str, str | int]]:
        """
        获取对比结果统计信息.

        Returns:
            统计信息列表，每个元素包含 trade_date, row_count, file_path

        """
        stats: list[dict[str, str | int]] = []
        for file_path in self.base_path.rglob("*.parquet"):
            try:
                stem = file_path.stem
                df = pl.read_parquet(file_path)
                stats.append(
                    {
                        "trade_date": stem,
                        "row_count": len(df),
                        "file_path": str(file_path.relative_to(self.base_path)),
                    }
                )
            except Exception as e:
                logger.warning(
                    "Failed to read comparison file for stats",
                    file_path=str(file_path),
                    error=str(e),
                )
                continue
        return stats
