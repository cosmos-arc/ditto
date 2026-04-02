"""
T0 元数据摄取任务工厂.

该模块提供 T0 层级（元数据）摄取任务的工厂函数。
任务是轻量 wrapper，真正逻辑在 IngestionCoordinator。
"""

from typing import Any

from ditto_app.config import INGESTION_SPECS
from ditto_data.models import Dataset
from prefect import task

from ditto_interfaces.registry import create_ingestion_bundle


# Prefect Task 返回类型是复杂的泛型，使用 Any 简化类型注解
def create_ingest_task(dataset: Dataset) -> Any:
    """
    创建摄取任务的工厂函数。

    根据给定的数据集创建一个 Prefect Task，该任务：
    1. 从 INGESTION_SPECS 读取配置（重试次数、超时等）
    2. 创建 DataHub 实例
    3. 调用 IngestionCoordinator 执行摄取
    4. 确保 DataHub 正确关闭

    Args:
        dataset: 数据集枚举值

    Returns:
        Prefect Task 函数

    Examples:
        >>> task_func = create_ingest_task(Dataset.CALENDAR)
        >>> result = task_func.fn(
        ...     trade_date="2024-01-02",
        ...     source="tushare",
        ...     data_root="data",
        ...     force=False,
        ... )

    """
    config = INGESTION_SPECS[dataset]

    @task(
        name=f"ingest_{dataset.value}",
        description=config.description,
        retries=config.retry_limit,
        timeout_seconds=config.timeout_seconds,
        tags=[dataset.value, "ingestion"],
    )
    def ingest_task(
        trade_date: str,
        source: str = "tushare",
        force: bool = False,
    ) -> dict[str, object]:
        """
        摄取指定交易日数据。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            source: 数据源名称
            force: 是否强制重新摄取（忽略缓存）

        Returns:
            摄取结果字典，包含：
            - dataset: 数据集名称
            - trade_date: 交易日期
            - status: 状态 (success/skipped/failed)
            - row_count: 行数
            - checksum: 校验和
            - message: 消息
            - error: 错误信息（如果失败）

        Raises:
            Exception: 摄取失败时抛出异常

        """
        with create_ingestion_bundle(source=source) as bundle:
            result = bundle.coordinator.ingest_date(
                dataset=dataset.value,
                trade_date=trade_date,
                force=force,
            )

            # 转换为字典返回
            return {
                "dataset": result.dataset,
                "trade_date": result.trade_date,
                "status": result.status,
                "row_count": result.row_count,
                "checksum": result.checksum,
                "message": result.message,
                "error": result.error,
            }

    return ingest_task


# 预定义任务实例（可选使用）
# 推荐使用工厂函数动态创建，以便统一管理配置
