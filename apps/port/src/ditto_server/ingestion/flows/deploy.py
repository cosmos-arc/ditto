"""
部署脚本。

该模块用于部署所有 Prefect Flows 到 Prefect Server。
"""

from __future__ import annotations

from ditto_foundation import logger


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

    from ditto_server.ingestion.flows import (  # noqa: PLC0415
        backfill_flow,
        daily_ingestion_flow,
        daily_repair_flow,
        repair_holes_flow,
        retry_failed_flow,
    )
    from ditto_server.ingestion.tasks.dq_batch import dq_batch_check  # noqa: PLC0415

    logger.info("开始部署 Prefect Flows", event="deploy_start")

    # 1. 每日增量摄取流程（交易日 18:00）
    Deployment.build_from_flow(  # type: ignore[attr-defined]
        flow=daily_ingestion_flow,
        name="daily-ingestion-prod",
        parameters={"trade_date": "{{ date }}", "data_root": "data"},
        schedule=None,  # 手动触发或通过 cron
        description="每日增量数据摄取流程 (T0 → T1 → T3)",
        tags=["production", "daily", "ingestion"],
        version="1.0.0",
    )

    # 2. 每日修补流程（每日凌晨 2:00）
    Deployment.build_from_flow(  # type: ignore[attr-defined]
        flow=daily_repair_flow,
        name="daily-repair-prod",
        parameters={"data_root": "data"},
        schedule=None,  # 手动触发或通过 cron
        description="每日修补流程 (重试 + 空洞扫描)",
        tags=["production", "daily", "repair"],
        version="1.0.0",
    )

    # 3. 重试失败流程（每 4 小时）
    Deployment.build_from_flow(  # type: ignore[attr-defined]
        flow=retry_failed_flow,
        name="retry-failed-prod",
        parameters={"dataset": "stock_daily", "data_root": "data"},
        schedule=None,  # 手动触发或通过 cron
        description="重试失败的任务",
        tags=["production", "retry", "repair"],
        version="1.0.0",
    )

    # 4. 全量回补流程（手动触发）
    Deployment.build_from_flow(  # type: ignore[attr-defined]
        flow=backfill_flow,
        name="backfill-prod",
        parameters={
            "dataset": "stock_daily",
            "start_date": "2020-01-01",
            "end_date": "2024-12-31",
            "data_root": "data",
        },
        schedule=None,  # 手动触发
        description="全量数据回补流程",
        tags=["production", "backfill", "manual"],
        version="1.0.0",
    )

    # 5. 修补空洞流程（手动触发）
    Deployment.build_from_flow(  # type: ignore[attr-defined]
        flow=repair_holes_flow,
        name="repair-holes-prod",
        parameters={"dataset": "stock_daily", "data_root": "data"},
        schedule=None,  # 手动触发
        description="扫描并修补数据空洞",
        tags=["production", "repair", "manual"],
        version="1.0.0",
    )

    # 6. DQC 检查流程（手动触发）
    Deployment.build_from_flow(  # type: ignore[attr-defined]
        flow=dq_batch_check.fn,
        name="dq-batch-check-prod",
        parameters={"trade_date": "{{ date }}"},
        schedule=None,  # 手动触发
        description="批量数据质量检查",
        tags=["production", "dq", "manual"],
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
