"""
部署脚本。

该模块用于部署 Prefect Flows 到 Prefect Server。

使用 Prefect 3.x 新部署机制 (flow.deploy / prefect.deploy)。
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from ditto_platform.foundation import logger
from prefect import Flow, deploy
from prefect.schedules import Cron, Schedule
from prefect.types.entrypoint import EntrypointType

from ditto_apps.jobs.flows import (
    backfill_flow,
    daily_ingestion_flow,
    daily_repair_flow,
    eod_flow,
    repair_holes_flow,
    retry_failed_flow,
)
from ditto_apps.jobs.flows.backtest import run_backtest_flow

# ---------------------------------------------------------------------------
# Cron 调度定义
#
# 时区统一使用 Asia/Shanghai，与 A 股市场交易时间对齐。
# Cron 表达式遵循标准 5 字段格式: 分 时 日 月 周。
# ---------------------------------------------------------------------------

# EOD: 交易日 19:45 — EOD 编排流程 (摄取 → 物化 → 策略)。
# #613 数据-only 先行：仅 scope=all 部署（EOD sleeve 环境门槛只在此时生效）。
SCHEDULE_EOD: Schedule = Cron("45 19 * * 1-5", timezone="Asia/Shanghai")

# T1 摄取: 交易日 21:55 — 全量日频数据集一次跑完。
# #583 实测（issue 评论）：stock_status 支配端点 bak_basic 当日终值 ~21:50 才可用。
# EOD 编排后续接管摄取时需重新裁决此独立调度去留（#613 切片 6）。
SCHEDULE_DAILY_INGESTION: Schedule = Cron("55 21 * * 1-5", timezone="Asia/Shanghai")

# T2: 每日 02:00 — 空洞扫描 + 回补（非交易日亦可运行，无副作用）
SCHEDULE_DAILY_REPAIR: Schedule = Cron("0 2 * * *", timezone="Asia/Shanghai")

# 部署范围：all=全部（含 EOD/backtest）；ingestion=数据-only（#613，不含 EOD/backtest）
_DEPLOY_SCOPES = frozenset({"all", "ingestion"})


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
    schedule: Schedule | None = None
    """可选的 cron 调度, None 表示仅手动触发"""


def _get_flow(name: str) -> Flow[Any, Any]:
    """
    动态导入 flow 对象.

    注意: 在 Prefect 3.x 中，flow 装饰器直接返回 Flow 对象，无需调用.
    """
    flow_map: dict[str, Flow[Any, Any]] = {
        "daily_ingestion_flow": daily_ingestion_flow,
        "daily_repair_flow": daily_repair_flow,
        "eod_flow": eod_flow,
        "retry_failed_flow": retry_failed_flow,
        "backfill_flow": backfill_flow,
        "repair_holes_flow": repair_holes_flow,
        "run_backtest_flow": run_backtest_flow,
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
    if hasattr(flow, "name") and hasattr(flow, "to_deployment"):
        return cast(Flow[Any, Any], flow)

    # 如果是可调用对象（lambda 或函数），调用它获取 Flow
    if callable(flow):
        result = flow()
        if hasattr(result, "name") and hasattr(result, "to_deployment"):
            return cast(Flow[Any, Any], result)

    # 如果都不是，尝试直接返回（可能会失败，但至少抛出明确的错误）
    return cast(Flow[Any, Any], flow)


def _get_backfill_date_range() -> tuple[str, str]:
    """
    获取全量回补的日期范围。

    通过环境变量 DITTO_BACKFILL_START_DATE / DITTO_BACKFILL_END_DATE
    外部化配置，未设置时保留与原硬编码一致的默认值。

    Returns:
        (start_date, end_date) 字符串元组，格式 YYYY-MM-DD。

    """
    start = os.environ.get("DITTO_BACKFILL_START_DATE", "2020-01-01")
    end = os.environ.get("DITTO_BACKFILL_END_DATE", "2024-12-31")
    return start, end


_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off"})
_REQUIRED_EOD_ENV_VARS = (
    "DITTO_EOD_STRATEGY_ID",
    "DITTO_EOD_ACCOUNT_ID",
)


def _parse_boolean_env(name: str, *, default: bool) -> bool:
    """解析部署边界的布尔环境变量，拒绝有歧义的值。"""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in _TRUE_ENV_VALUES:
        return True
    if normalized in _FALSE_ENV_VALUES:
        return False
    valid_values = "1/0, true/false, yes/no, or on/off"
    raise ValueError(
        f"EOD_DEPLOYMENT_CONFIG_INVALID: {name} must be one of {valid_values}"
    )


def _get_eod_deployment_parameters() -> dict[str, Any]:
    """
    读取每日 EOD 的显式 execution sleeve，缺失时禁止部署。

    trade_date 不在部署参数中：Prefect 3.6 对纯字符串参数原样透传
    （`{{ date }}` 不再运行时渲染），由 eod_flow 运行时自取当日。
    """
    raw_values = {name: os.environ.get(name) for name in _REQUIRED_EOD_ENV_VARS}
    missing_names = [
        name
        for name, raw_value in raw_values.items()
        if raw_value is None or not raw_value.strip()
    ]
    if missing_names:
        names = ", ".join(missing_names)
        detail = f"required non-blank environment variables: {names}"
        raise ValueError(f"EOD_DEPLOYMENT_CONFIG_MISSING: {detail}")

    return {
        "strategy_id": cast(str, raw_values["DITTO_EOD_STRATEGY_ID"]).strip(),
        "account_id": cast(str, raw_values["DITTO_EOD_ACCOUNT_ID"]).strip(),
        "allow_experimental_data": _parse_boolean_env(
            "DITTO_EOD_ALLOW_EXPERIMENTAL_DATA",
            default=False,
        ),
    }


def _get_flow_configs(
    scope: str = "all",
    *,
    include_backtest: bool = False,
) -> list[FlowDeploymentConfig]:
    """
    获取 flow 部署配置。

    Args:
        scope: "all"=全部部署（含 EOD，需 EOD sleeve 环境门槛）；
            "ingestion"=数据-only（无 EOD/backtest，不受 EOD 门槛拦截）。
        include_backtest: ingestion 范围下追加 backtest 部署（scope=all 恒含）。

    """
    if scope not in _DEPLOY_SCOPES:
        valid = ", ".join(sorted(_DEPLOY_SCOPES))
        raise ValueError(f"DEPLOY_SCOPE_INVALID: {scope}; expected one of {valid}")

    backfill_start, backfill_end = _get_backfill_date_range()
    configs: list[FlowDeploymentConfig] = [
        FlowDeploymentConfig(
            flow=lambda: _get_flow("daily_ingestion_flow"),
            deployment_name="daily-ingestion-prod",
            description="每日增量数据摄取流程 (T0 → T1 → T3)",
            parameters={},
            tags=["production", "daily", "ingestion"],
            schedule=SCHEDULE_DAILY_INGESTION,
        ),
        FlowDeploymentConfig(
            flow=lambda: _get_flow("daily_repair_flow"),
            deployment_name="daily-repair-prod",
            description="每日修补流程 (重试 + 空洞扫描)",
            parameters={},
            tags=["production", "daily", "repair"],
            schedule=SCHEDULE_DAILY_REPAIR,
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
                "config": {
                    "dataset": "stock_daily",
                    "start_date": backfill_start,
                    "end_date": backfill_end,
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
    if scope == "all":
        configs.insert(
            0,
            FlowDeploymentConfig(
                flow=lambda: _get_flow("eod_flow"),
                deployment_name="eod-pipeline-prod",
                description="EOD 编排流程 (摄取 → 物化 → 策略运行)",
                parameters=_get_eod_deployment_parameters(),
                tags=["production", "daily", "eod"],
                schedule=SCHEDULE_EOD,
            ),
        )
    if scope == "all" or include_backtest:
        configs.append(
            FlowDeploymentConfig(
                flow=lambda: _get_flow("run_backtest_flow"),
                deployment_name="backtest-prod",
                description="异步回测执行 (R3 — Prefect Worker 调度)",
                parameters={},
                tags=["backtest", "manual"],
            ),
        )
    return configs


def deploy_all_flows(
    work_pool_name: str = "my-work-pool",
    image: str | None = None,
    push: bool = False,
    scope: str = "all",
    *,
    include_backtest: bool = False,
) -> None:
    """
    部署 Flows 到 Prefect (3.x)。

    Args:
        work_pool_name: 工作池名称
        image: Docker 镜像 (可选)
        push: 是否推送镜像到注册表
        scope: "all"=全部部署（EOD 门槛生效）；"ingestion"=数据-only（无 EOD/backtest）
        include_backtest: ingestion 范围下追加 backtest 部署

    该函数会：
    1. scope=all 时部署 EOD 编排流程（定时: 交易日 19:45，需 EOD sleeve 环境变量）
    2. 部署每日增量摄取流程（定时: 交易日 21:55，日期由 flow 运行时自取）
    3. 部署每日修补流程（定时: 每日 02:00）
    4. 部署重试失败流程（手动触发）
    5. 部署全量回补流程（手动触发）
    6. 部署修补空洞流程（手动触发）
    7. 部署异步回测流程（手动触发，R3；scope=all 或 include_backtest）

    注意: Prefect 3.x 移除了 Deployment API，改用 flow.deploy()。

    """
    logger.info("开始部署 Prefect Flows", event="deploy_start", scope=scope)

    # 准备部署列表 (使用 to_deployment 方法)
    # entrypoint_type=MODULE_PATH: worker 以本机 venv 按模块导入 flow，
    # 无需 Docker 镜像或远端存储（process work pool 的本地部署形态）
    deployments: list[Any] = []
    for config in _get_flow_configs(scope, include_backtest=include_backtest):
        flow_obj = _resolve_flow(config.flow)
        deployment = flow_obj.to_deployment(
            name=config.deployment_name,
            description=config.description,
            tags=config.tags,
            parameters=config.parameters,
            schedule=config.schedule,
            entrypoint_type=EntrypointType.MODULE_PATH,
        )
        deployments.append(deployment)

    # 使用 prefect.deploy() 一次性部署所有 flows
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
        flow_obj = _resolve_flow(config.flow)
        flow_descriptions[flow_obj.name] = config.description
    return flow_descriptions


def main() -> None:
    """主函数：部署 Flows（默认全量；`--only ingestion` 数据-only）。"""
    parser = argparse.ArgumentParser(description="部署 Ditto Prefect Flows")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["list", "deploy"],
        default="deploy",
        help="list=仅列出 flows; deploy=执行部署",
    )
    parser.add_argument(
        "--only",
        dest="scope",
        choices=sorted(_DEPLOY_SCOPES),
        default="all",
        help="部署范围: ingestion=数据-only(无 EOD/backtest); all=全量",
    )
    parser.add_argument(
        "--with-backtest",
        action="store_true",
        help="ingestion 范围下追加 backtest 部署",
    )
    parser.add_argument(
        "--work-pool",
        default="my-work-pool",
        help="目标 work pool 名称(须预先创建)",
    )
    args = parser.parse_args()

    if args.command == "list":
        flows = list_flows()
        logger.info("Available flows", flows=list(flows.items()))
        return

    # 注意: 实际部署时需要指定 work_pool_name 和 image
    deploy_all_flows(
        work_pool_name=args.work_pool,
        scope=args.scope,
        include_backtest=args.with_backtest,
    )


if __name__ == "__main__":
    main()
