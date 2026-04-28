"""
质量对比结果写入器.

Provides write access to quality comparison data.
"""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl


class ComparisonWriter:
    """
    质量对比数据写入器.

    路径：data_root/quarantine/quality_comparison/
    保留：30 天自动清理

    职责：只存储 DataFrame，不依赖 Engine 层类型
    转换逻辑由 Port 层处理
    """

    def __init__(
        self,
        base_path: Path,
        retention_days: int = 30,
    ) -> None:
        """
        初始化写入器.

        Args:
            base_path: 基础路径（通常是 data_root）
            retention_days: 数据保留天数

        """
        self.base_path = Path(base_path) / "quarantine" / "quality_comparison"
        self.retention_days = retention_days
        self.base_path.mkdir(parents=True, exist_ok=True)

    def write_comparison(
        self,
        trade_date: str,
        comparison_df: pl.DataFrame,
        dataset: str = "stock_daily",
    ) -> None:
        """
        存储对比结果 DataFrame.

        Args:
            trade_date: 交易日期
            comparison_df: 对比结果 DataFrame（由 Port 层转换）
            dataset: 数据集标识

        """
        if comparison_df.height == 0:
            return  # 无数据，不存储

        # 按日期和数据集分区存储（避免多数据集覆盖）
        year = trade_date[:4]
        month = trade_date[4:6]
        dataset_path = self.base_path / f"year={year}" / f"month={month}" / dataset
        file_path = dataset_path / f"{trade_date}.parquet"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        comparison_df.write_parquet(file_path)

        # 清理过期数据
        self._cleanup_old_data()

    def _cleanup_old_data(self) -> None:
        """清理过期数据."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        for file_path in self.base_path.rglob("*.parquet"):
            # 从文件名提取日期
            try:
                stem = file_path.stem
                file_date = datetime.strptime(stem, "%Y%m%d")
                if file_date < cutoff_date:
                    file_path.unlink()
            except ValueError:
                continue
