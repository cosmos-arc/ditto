"""
部署脚本。

该模块用于部署所有 Prefect Flows 到 Prefect Server。

使用 Prefect 3.x 新部署机制 (flow.deploy / prefect.deploy)。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ditto_foundation import logger
from prefect import Flow, deploy

from ditto_port.jobs.flows import (
    backfill_flow,
    daily_ingestion_flow,
    daily_repair_flow,
    repair_holes_flow,
    retry_failed_flow,
)


@dataclass(frozen=True)
class FlowDeploymentConfig:
    """Flow 部署配置 (Prefect 3.x)。"""

    flow: Flow[Any, Any] | Callable[[], Flow[Any, Any]]
    """Flow 对象或返回 Flow 对象的函数"""
    deployment_name: str
    """部署名称"""
    description: str
    """描述"""
    parameters: dict[str, Any]
    """默认参数"""
    tags: list[str]
    """标签"""


def _get_flow(name: str) -> Flow[Any, Any]:
    """
    动态导入 flow 对象.

    注意: 在 Prefect 3.x 中，flow 装饰器直接返回 Flow 对象，无需调用.
    """
    flow_map: dict[str, Flow[Any, Any]] = {
        "daily_ingestion_flow": daily_ingestion_flow,
        "daily_repair_flow": daily_repair_flow,
        "retry_failed_flow": retry_failed_flow,
        "backfill_flow": backfill_flow,
        "repair_holes_flow": repair_holes_flow,
    }

    if name not in flow_map:
        raise ValueError(f"Unknown flow: {name}")
    # Flow 对象已经由装饰器返回，直接返回即可
    return flow_map[name]


def _resolve_flow(
    flow: Flow[Any, Any] | Callable[[], Flow[Any, Any]],
) -> Flow[Any, Any]:
    """
    解析 flow 对象（处理 Flow 对象或返回 Flow 的函数）.

    Args:
        flow: Flow 对象或返回 Flow 对象的函数

    Returns:
        Flow 对象

    """
    # 检查是否已经是 Flow 对象（通过检查 Flow 对象的特征属性）
    # Flow 对象有 name, description, to_deployment 等属性
    if hasattr(flow, "name") and hasattr(flow, "to_deployment"):
        return flow  # type: ignore[return-value]

    # 如果是可调用对象（lambda 或函数），调用它获取 Flow
    if callable(flow):
        result = flow()
        if hasattr(result, "name") and hasattr(result, "to_deployment"):
            return result  # type: ignore[return-value]

    # 如果都不是，尝试直接返回（可能会失败，但至少抛出明确的错误）
    return flow  # type: ignore[return-value]


def _get_flow_configs() -> list[FlowDeploymentConfig]:
    """获取所有 flow 部署配置。"""
    return [
        FlowDeploymentConfig(
            flow=lambda: _get_flow("daily_ingestion_flow"),
            deployment_name="daily-ingestion-prod",
            description="每日增量数据摄取流程 (T0 → T1 → T3)",
            parameters={"trade_date": "{{ date }}"},
            tags=["production", "daily", "ingestion"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("daily_repair_flow"),
            deployment_name="daily-repair-prod",
            description="每日修补流程 (重试 + 空洞扫描)",
            parameters={},
            tags=["production", "daily", "repair"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("retry_failed_flow"),
            deployment_name="retry-failed-prod",
            description="重试失败的任务",
            parameters={"dataset": "stock_daily"},
            tags=["production", "retry", "repair"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("backfill_flow"),
            deployment_name="backfill-prod",
            description="全量数据回补流程",
            parameters={
                "backfill_config": {
                    "dataset": "stock_daily",
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31",
                }
            },
            tags=["production", "backfill", "manual"],
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("repair_holes_flow"),
            deployment_name="repair-holes-prod",
            description="扫描并修补数据空洞",
            parameters={"dataset": "stock_daily"},
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
    logger.info("开始部署 Prefect Flows", event="deploy_start")

    # 准备部署列表 (使用 to_deployment 方法)
    deployments: list[Any] = []
    for config in _get_flow_configs():
        flow = _resolve_flow(config.flow)
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
        flow = _resolve_flow(config.flow)
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
