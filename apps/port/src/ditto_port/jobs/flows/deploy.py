"""
部署脚本。

该模块用于部署所有 Prefect Flows 到 Prefect Server。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ditto_foundation import logger

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class FlowDeploymentConfig:
    """Flow 部署配置。"""

    flow_name: str
    """Flow 名称(用于导入)"""
    deployment_name: str
    """部署名称"""
    description: str
    """描述"""
    parameters: dict[str, Any]
    """参数"""
    tags: list[str]
    """标签"""
    is_task: bool = False
    """是否为 task(而非 flow)"""


# 部署配置列表
_DEPLOYMENT_CONFIGS: list[FlowDeploymentConfig] = [
    FlowDeploymentConfig(
        flow_name="daily_ingestion_flow",
        deployment_name="daily-ingestion-prod",
        description="每日增量数据摄取流程 (T0 → T1 → T3)",
        parameters={"trade_date": "{{ date }}", "data_root": "data"},
        tags=["production", "daily", "ingestion"],
    ),
    FlowDeploymentConfig(
        flow_name="daily_repair_flow",
        deployment_name="daily-repair-prod",
        description="每日修补流程 (重试 + 空洞扫描)",
        parameters={"data_root": "data"},
        tags=["production", "daily", "repair"],
    ),
    FlowDeploymentConfig(
        flow_name="retry_failed_flow",
        deployment_name="retry-failed-prod",
        description="重试失败的任务",
        parameters={"dataset": "stock_daily", "data_root": "data"},
        tags=["production", "retry", "repair"],
    ),
    FlowDeploymentConfig(
        flow_name="backfill_flow",
        deployment_name="backfill-prod",
        description="全量数据回补流程",
        parameters={
            "dataset": "stock_daily",
            "start_date": "2020-01-01",
            "end_date": "2024-12-31",
            "data_root": "data",
        },
        tags=["production", "backfill", "manual"],
    ),
    FlowDeploymentConfig(
        flow_name="repair_holes_flow",
        deployment_name="repair-holes-prod",
        description="扫描并修补数据空洞",
        parameters={"dataset": "stock_daily", "data_root": "data"},
        tags=["production", "repair", "manual"],
    ),
    FlowDeploymentConfig(
        flow_name="dq_batch_check",
        deployment_name="dq-batch-check-prod",
        description="批量数据质量检查",
        parameters={"trade_date": "{{ date }}"},
        tags=["production", "dq", "manual"],
        is_task=True,
    ),
]


def _get_flow(flow_name: str, is_task: bool = False) -> Callable:
    """动态导入 flow 或 task。"""
    if is_task and flow_name == "dq_batch_check":
        from ditto_port.jobs.tasks.dq_batch import dq_batch_check  # noqa: PLC0415

        return dq_batch_check.fn

    from ditto_port.jobs.flows import (  # noqa: PLC0415
        backfill_flow,
        daily_ingestion_flow,
        daily_repair_flow,
        repair_holes_flow,
        retry_failed_flow,
    )

    flow_map = {
        "daily_ingestion_flow": daily_ingestion_flow,
        "daily_repair_flow": daily_repair_flow,
        "retry_failed_flow": retry_failed_flow,
        "backfill_flow": backfill_flow,
        "repair_holes_flow": repair_holes_flow,
    }

    return flow_map[flow_name]


def deploy_all_flows() -> None:
    """
    部署所有 Flows 到 Prefect。

    该函数会：
    1. 部署每日增量摄取流程
    2. 部署每日修补流程
    3. 部署重试失败流程
    4. 部署全量回补流程
    5. 部署修补空洞流程
    6. 部署 DQC 检查流程

    """
    from prefect.deployments import Deployment  # noqa: PLC0415

    logger.info("开始部署 Prefect Flows", event="deploy_start")

    for config in _DEPLOYMENT_CONFIGS:
        flow = _get_flow(config.flow_name, config.is_task)
        Deployment.build_from_flow(  # type: ignore[attr-defined]
            flow=flow,
            name=config.deployment_name,
            parameters=config.parameters,
            schedule=None,
            description=config.description,
            tags=config.tags,
            version="1.0.0",
        )

    logger.info("Prefect Flows 部署完成", event="deploy_complete")


def list_flows() -> dict[str, str]:
    """
    列出所有可用的 Flows。

    Returns:
        Flow 名称到描述的映射

    """
    return {
        "daily_ingestion_flow": "每日增量数据摄取流程 (T0 → T1 → T3)",
        "daily_repair_flow": "每日修补流程 (重试 + 空洞扫描)",
        "retry_failed_flow": "重试失败的任务",
        "backfill_flow": "全量数据回补流程",
        "backfill_missing_flow": "回补缺失数据",
        "repair_holes_flow": "扫描并修补数据空洞",
        "dq_batch_check": "批量数据质量检查",
    }


def main() -> None:
    """主函数：部署所有 Flows。"""
    import sys  # noqa: PLC0415

    # 检查命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "list":
            # 列出所有 flows
            flows = list_flows()
            print("可用的 Flows:")
            for name, description in flows.items():
                print(f"  - {name}: {description}")
            return

    # 部署所有 flows
    deploy_all_flows()


if __name__ == "__main__":
    main()
