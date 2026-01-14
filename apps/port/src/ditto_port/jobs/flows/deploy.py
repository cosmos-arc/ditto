"""
部署脚本。

该模块用于部署所有 Prefect Flows 到 Prefect Server。

使用 Prefect 3.x 新部署机制 (flow.deploy / prefect.deploy)。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ditto_foundation import logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from prefect import Flow


@dataclass(frozen=True)
class FlowDeploymentConfig:
    """Flow 部署配置 (Prefect 3.x)。"""

    flow: Callable[[], Flow[Any, Any]]
    """Flow 函数(延迟导入)"""
    deployment_name: str
    """部署名称"""
    description: str
    """描述"""
    parameters: dict[str, Any]
    """默认参数"""
    tags: list[str]
    """标签"""


def _get_flow(name: str) -> Flow[Any, Any]:
    """动态导入 flow。"""
    from ditto_port.jobs.flows import (
        backfill_flow,
        daily_ingestion_flow,
        daily_repair_flow,
        repair_holes_flow,
        retry_failed_flow,
    )

    flow_map: dict[str, Flow[Any, Any]] = {
        "daily_ingestion_flow": daily_ingestion_flow,
        "daily_repair_flow": daily_repair_flow,
        "retry_failed_flow": retry_failed_flow,
        "backfill_flow": backfill_flow,
        "repair_holes_flow": repair_holes_flow,
    }

    if name not in flow_map:
        raise ValueError(f"Unknown flow: {name}")
    return flow_map[name]


def _get_flow_configs() -> list[FlowDeploymentConfig]:
    """获取所有 flow 部署配置。"""
    return [
        FlowDeploymentConfig(
            flow=lambda: _get_flow("daily_ingestion_flow"),
            deployment_name="daily-ingestion-prod",
            description="每日增量数据摄取流程 (T0 → T1 → T3)",
            parameters={"trade_date": "{{ date }}", "data_root": "data"},
            tags=["production", "daily", "ingestion"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("daily_repair_flow"),
            deployment_name="daily-repair-prod",
            description="每日修补流程 (重试 + 空洞扫描)",
            parameters={"data_root": "data"},
            tags=["production", "daily", "repair"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("retry_failed_flow"),
            deployment_name="retry-failed-prod",
            description="重试失败的任务",
            parameters={"dataset": "stock_daily", "data_root": "data"},
            tags=["production", "retry", "repair"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("backfill_flow"),
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
            flow=lambda: _get_flow("repair_holes_flow"),
            deployment_name="repair-holes-prod",
            description="扫描并修补数据空洞",
            parameters={"dataset": "stock_daily", "data_root": "data"},
            tags=["production", "repair", "manual"],
        ),
    ]


def deploy_all_flows(
    work_pool_name: str = "my-work-pool",
    image: str | None = None,
    push: bool = False,
) -> None:
    """
    部署所有 Flows 到 Prefect (3.x)。

    Args:
        work_pool_name: 工作池名称
        image: Docker 镜像 (可选)
        push: 是否推送镜像到注册表

    该函数会：
    1. 部署每日增量摄取流程
    2. 部署每日修补流程
    3. 部署重试失败流程
    4. 部署全量回补流程
    5. 部署修补空洞流程

    注意: Prefect 3.x 移除了 Deployment API，改用 flow.deploy()。

    """
    from prefect import deploy

    logger.info("开始部署 Prefect Flows", event="deploy_start")

    # 准备部署列表 (使用 to_deployment 方法)
    deployments: list[Any] = []
    for config in _get_flow_configs():
        flow = config.flow()
        deployment = flow.to_deployment(
            name=config.deployment_name,
            description=config.description,
            tags=config.tags,
            parameters=config.parameters,
        )
        deployments.append(deployment)

    # 使用 prefect.deploy() 一次性部署所有 flows
    # 注意: 这会构建一个共享的 Docker 镜像
    deploy(
        *deployments,
        work_pool_name=work_pool_name,
        image=image,
        push=push,
    )

    logger.info("Prefect Flows 部署完成", event="deploy_complete")


def list_flows() -> dict[str, str]:
    """
    列出所有可用的 Flows。

    Returns:
        Flow 名称到描述的映射

    """
    flow_descriptions: dict[str, str] = {}
    for config in _get_flow_configs():
        # 从配置中提取 flow 名称
        flow = config.flow()
        flow_descriptions[flow.name] = config.description
    return flow_descriptions


def main() -> None:
    """主函数：部署所有 Flows。"""
    # 检查命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "list":
            # 列出所有 flows
            flows = list_flows()
            logger.info("Available flows", flows=list(flows.items()))
            return

    # 部署所有 flows
    # 注意: 实际部署时需要指定 work_pool_name 和 image
    deploy_all_flows()


if __name__ == "__main__":
    main()
