# Ditto 数据摄取调度设计

**版本：v1.0**

**日期：2025-12-26**

---

## 1. 设计背景

### 1.1 需求

基于 Ditto 数据层设计（02_data_design.md），规划 Server 侧数据摄取定时任务：

- 支持定时自动执行
- 支持手动触发
- 支持失败重试
- 支持任务依赖编排
- 可观测（执行历史、日志、状态）

### 1.2 技术选型

**选择 Prefect 3 本地 Server 模式**

| 维度 | APScheduler | Prefect |
|------|-------------|---------|
| 可观测性 | ⭐⭐ 需自建 | ⭐⭐⭐⭐⭐ 内置 Dashboard |
| 手动触发 | ⭐⭐ 需开发 API | ⭐⭐⭐⭐⭐ CLI/UI/API |
| 重试机制 | ⭐⭐ 手动实现 | ⭐⭐⭐⭐⭐ 声明式指数退避 |
| DAG 支持 | ⭐ 无 | ⭐⭐⭐⭐⭐ 原生 |
| 历史记录 | ⭐⭐ 需自建 | ⭐⭐⭐⭐⭐ 内置 |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Server 层                                       │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Prefect Flows（编排逻辑）                         │   │
│   │                                                                      │   │
│   │   daily_ingest_flow ─→ ingest_calendar                              │   │
│   │         │             ─→ ingest_securities                          │   │
│   │         │             ─→ ingest_etf_bars (并行)                     │   │
│   │         │             ─→ ingest_index_bars (并行)                   │   │
│   │         │             ─→ ingest_adj_factor                          │   │
│   │         │                                                           │   │
│   │   dq_batch_flow ────→ dq_batch_check (L3 统计异常)                  │   │
│   │                                                                      │   │
│   │   heartbeat_flow ───→ send_heartbeat                                │   │
│   │                                                                      │   │
│   │   backfill_flow ────→ 批量补数据                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    │ 调用                                    │
│                                    ▼                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DataHub 层                                        │
│                                                                              │
│   hub.sources.tushare.fetch_xxx()  ──→  从外部获取数据                      │
│   hub.securities.resolve_sids()    ──→  SID 解析                           │
│   hub.bars.write()                 ──→  写入存储（自动触发 DQ L1+L2）       │
│   DQEngine.check_statistical()     ──→  L3 批量检查                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```
### 2.2. 数据流示意

```
                     Server (Prefect)                    DataHub
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
┌─────────┐        ┌─────────┐         ┌─────────┐
│ daily   │        │ backfill│         │heartbeat│
│ _ingest │        │  _flow  │         │  _flow  │
│  _flow  │        │         │         │         │
└────┬────┘        └────┬────┘         └─────────┘
     │                  │
     ├──────────────────┤
     ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Tasks                                    │
│  ingest_calendar │ ingest_bars │ ingest_adj │ dq_batch_check   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ 调用
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DataHub                                  │
│                                                                  │
│  hub.sources.tushare.fetch_xxx()  ──→  从外部获取数据            │
│                                                                  │
│  hub.securities.resolve_sids()    ──→  SID 解析                 │
│                                                                  │
│  hub.bars.write()                 ──→  写入存储                 │
│       │                                 │                        │
│       └── DQEngine.check(L1+L2) ────────┘                       │
│           自动执行，L1 失败阻断写入                               │
│                                                                  │
│  DQEngine.check_statistical(L3)   ──→  批量统计检查             │
│       由 Server dq_batch_check Task 触发                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2.3 职责边界

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Server (apps/server)                                  │
│                                                                              │
│   职责：应用层编排                                                           │
│   - Prefect Flows/Tasks：任务编排、调度、重试                                 │
│   - 触发 L3 批量检查（规则定义在 DataHub）                                    │
│   - API：手动触发、状态查询                                                  │
│                                                                              │
│   不包含：                                                                   │
│   - 数据获取逻辑（通过 hub.sources 调用）                                    │
│   - DQ 规则定义（在 DataHub）                                               │
│   - 独立的 Validator（规则统一在 DataHub）                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 调用
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DataHub (packages/ditto-data-hub)                       │
│                                                                              │
│   职责：统一数据入口                                                         │
│   - Sources：外部数据源适配（Tushare/AkShare），支持实时查询                   │
│   - Stores：本地存储读写（Parquet/SQLite）                                   │
│   - Repositories：业务聚合，PIT/复权等语义                                   │
│   - DQ Engine：统一的数据质量检查（L1/L2/L3 规则）                           │
└─────────────────────────────────────────────────────────────────────────────┘
```


| 层 | 职责 | 不做 |
|---|---|---|
| **Server/Flows** | 任务编排、调度、重试、告警 | 数据获取逻辑、DQ 规则定义 |
| **Server/Tasks** | 调用 DataHub API，处理结果 | 直接调用 Tushare API |
| **DataHub/Sources** | 外部数据源适配 | 存储逻辑 |
| **DataHub/DQ** | DQ 规则定义和执行 | 调度逻辑 |

---

## 3. 任务依赖关系

```
daily_ingest_flow
├── ingest_calendar        ← 首先执行（其他任务依赖交易日历）
├── ingest_securities      ← 依赖 calendar
├── ingest_bars (并行)     ← 依赖 securities（需 SID 解析）
│   ├── ingest_etf_bars
│   ├── ingest_stock_bars (Phase 2+)
│   └── ingest_index_bars
├── ingest_adj_factor      ← 依赖 securities
└── compute_derived        ← 依赖 bars + adj_factor
    └── compute_limit_status (涨跌停状态)

dq_batch_flow (独立 Flow，晚于 ingest 执行)
└── dq_batch_check         ← 执行 L3 统计异常检测
```

---

## 4. 代码结构

```
apps/
  server/
    pyproject.toml

    src/
      ditto_server/
        __init__.py
        main.py                     # FastAPI 入口

        # ============ API 层 ============
        api/
          __init__.py
          router.py                 # 主路由
          health.py                 # 健康检查（含 Prefect 状态）
          ingestion.py              # 摄取触发 API

        # ============ 数据摄取模块 ============
        ingestion/
          __init__.py
          config.py                 # 摄取配置

          # Prefect Flows（编排逻辑）
          flows/
            __init__.py
            daily_ingest.py         # 每日摄取主 Flow
            backfill.py             # 补数据 Flow
            heartbeat.py            # 心跳 Flow

          # Prefect Tasks（调用 DataHub）
          tasks/
            __init__.py
            calendar.py             # 日历摄取
            securities.py           # 证券主数据摄取
            bars.py                 # K线摄取（ETF/Stock/Index）
            adj_factor.py           # 复权因子摄取
            derived.py              # 衍生数据计算（涨跌停状态）
            dq_batch.py             # L3 批量 DQ 检查（触发 DataHub DQEngine）

          # 调度配置
          schedules.py              # Prefect Deployment 定义
          hooks.py                  # Flow/Task 状态变化钩子（告警）

        # ============ 其他服务 ============
        services/
          __init__.py
          notification.py           # 告警通知（钉钉/Telegram）
```

---

## 5. Flow 实现

### 5.1 每日摄取 Flow

```python
# flows/daily_ingest.py

from prefect import flow, get_run_logger
from typing import Literal

from ditto_data_hub import DataHub

from ..tasks.calendar import ingest_calendar
from ..tasks.securities import ingest_securities
from ..tasks.bars import ingest_etf_bars, ingest_index_bars
from ..tasks.adj_factor import ingest_adj_factor
from ..tasks.derived import compute_limit_status
from ..hooks import on_flow_failure


@flow(
    name="daily-ingest",
    description="每日数据摄取主流程",
    retries=2,
    retry_delay_seconds=300,
    log_prints=True,
    on_failure=[on_flow_failure],
)
def daily_ingest_flow(
    trade_date: str | None = None,
    source: Literal["tushare", "akshare"] = "tushare",
    skip_calendar: bool = False,
    skip_securities: bool = False,
) -> dict:
    """
    每日数据摄取

    Args:
        trade_date: 摄取日期，None 则自动获取最近交易日
        source: 数据源
        skip_calendar: 跳过日历摄取（补数据时使用）
        skip_securities: 跳过证券主数据（补数据时使用）
    """
    logger = get_run_logger()
    hub = DataHub()

    # 确定摄取日期
    if trade_date is None:
        trade_date = hub.calendar.get_last_trading_day()

    logger.info(f"开始摄取: {trade_date}, source={source}")

    results = {}

    # Step 1: 日历摄取
    if not skip_calendar:
        results["calendar"] = ingest_calendar(source=source)

    # Step 2: 证券主数据
    if not skip_securities:
        results["securities"] = ingest_securities(source=source)

    # Step 3: K线数据（并行）
    etf_future = ingest_etf_bars.submit(trade_date, source)
    index_future = ingest_index_bars.submit(trade_date, source)

    # Step 4: 复权因子
    adj_future = ingest_adj_factor.submit(trade_date, source)

    # 等待并行任务
    results["etf"] = etf_future.result()
    results["index"] = index_future.result()
    results["adj"] = adj_future.result()

    # Step 5: 衍生数据计算
    results["limit_status"] = compute_limit_status(trade_date)

    logger.info(f"摄取完成: {results}")
    return results
```

### 5.2 L3 批量校验 Flow

```python
# flows/dq_batch.py

from prefect import flow, get_run_logger

from ditto_data_hub import DataHub
from ditto_data_hub.dq import get_dq_engine

from ..hooks import on_flow_failure, send_dq_alert


@flow(
    name="dq-batch",
    description="L3 批量数据质量检查",
    log_prints=True,
    on_failure=[on_flow_failure],
)
def dq_batch_flow(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
) -> dict:
    """
    L3 批量 DQ 检查

    规则定义在 DataHub 的 dq_rules.yaml
    """
    logger = get_run_logger()
    hub = DataHub()
    engine = get_dq_engine()

    if trade_date is None:
        trade_date = hub.calendar.get_last_trading_day()

    if datasets is None:
        datasets = ["etf_daily", "index_daily", "adj_factor"]

    logger.info(f"开始 L3 检查: {trade_date}, datasets={datasets}")

    all_issues = []

    for dataset in datasets:
        result = engine.check_statistical(
            dataset=dataset,
            trade_date=trade_date,
            hub=hub,
        )
        all_issues.extend(result.issues)

        if result.issues:
            logger.warning(f"{dataset}: 发现 {len(result.issues)} 个异常")

    summary = {
        "trade_date": trade_date,
        "datasets_checked": len(datasets),
        "total_issues": len(all_issues),
        "alerts": sum(1 for i in all_issues if i.severity.value == "alert"),
    }

    # 发送告警
    if all_issues:
        send_dq_alert(trade_date, all_issues)

    logger.info(f"L3 检查完成: {summary}")
    return summary
```

### 5.3 补数据 Flow

```python
# flows/backfill.py

from prefect import flow, get_run_logger
import time

from ditto_data_hub import DataHub

from .daily_ingest import daily_ingest_flow


@flow(
    name="backfill",
    description="批量补数据",
    log_prints=True,
)
def backfill_flow(
    start_date: str,
    end_date: str,
    source: str = "tushare",
    batch_size: int = 5,
    batch_interval: int = 60,
) -> dict:
    """
    批量补数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
        source: 数据源
        batch_size: 每批处理天数
        batch_interval: 批次间隔秒数（避免限流）
    """
    logger = get_run_logger()
    hub = DataHub()

    trading_days = hub.calendar.list_trading_days(start_date, end_date)
    logger.info(f"需要补 {len(trading_days)} 个交易日")

    results = []

    for i, trade_date in enumerate(trading_days):
        logger.info(f"[{i+1}/{len(trading_days)}] 补数据: {trade_date}")

        result = daily_ingest_flow(
            trade_date=trade_date,
            source=source,
            skip_calendar=True,
            skip_securities=True,
        )
        results.append(result)

        # 批次间隔
        if (i + 1) % batch_size == 0 and i < len(trading_days) - 1:
            logger.info(f"休息 {batch_interval} 秒...")
            time.sleep(batch_interval)

    return {
        "total_days": len(trading_days),
        "success_days": len(results),
    }
```

---

## 6. Task 实现

### 6.1 K线摄取 Task

```python
# tasks/bars.py

from prefect import task, get_run_logger
from typing import Literal
import polars as pl

from ditto_data_hub import DataHub
from ditto_data_hub.sources.base import DataSourceError


@task(
    name="ingest-etf-bars",
    description="摄取 ETF K线数据",
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # 指数退避
    tags=["etf", "bars", "critical"],
)
def ingest_etf_bars(
    trade_date: str,
    source: Literal["tushare", "akshare"] = "tushare",
) -> dict:
    """
    摄取 ETF K线

    数据流：
    1. hub.sources.{source}.fetch_etf_daily() 获取数据
    2. hub.securities.resolve_sids_batch() 解析 SID
    3. hub.bars.write() 写入（自动触发 DQ L1+L2）
    """
    logger = get_run_logger()
    hub = DataHub()

    try:
        # Step 1: 从数据源获取
        data_source = hub.sources.get(source)
        raw_df = data_source.fetch_etf_daily(trade_date=trade_date)

        if raw_df.is_empty():
            logger.warning(f"无 ETF 数据: {trade_date}")
            return {"status": "empty", "row_count": 0}

        logger.info(f"获取 {raw_df.height} 条 ETF 数据")

        # Step 2: 解析 SID
        src_codes = raw_df["src_code"].unique().to_list()
        sid_map = hub.securities.resolve_sids_batch(src_codes, source=source)

        raw_df = raw_df.with_columns(
            pl.col("src_code").replace(sid_map).alias("sid")
        ).filter(pl.col("sid").is_not_null())

        # Step 3: 写入（DQ L1+L2 自动执行）
        write_result = hub.bars.write(
            df=raw_df,
            dataset="etf_daily",
            source=source,
        )

        logger.info(
            f"ETF K线摄取完成: rows={write_result.row_count}, "
            f"dq_passed={write_result.dq_passed}"
        )

        return {
            "status": "success" if write_result.dq_passed else "dq_warning",
            "row_count": write_result.row_count,
            "dq_failures": write_result.dq_failures,
        }

    except DataSourceError as e:
        logger.error(f"数据源错误: {e}")
        # 尝试降级到 AkShare
        if source == "tushare":
            logger.warning("尝试 AkShare 降级")
            return ingest_etf_bars(trade_date, source="akshare")
        raise
```

### 6.2 L3 批量检查 Task

```python
# tasks/dq_batch.py

from prefect import task, get_run_logger

from ditto_data_hub import DataHub
from ditto_data_hub.dq import get_dq_engine


@task(
    name="dq-batch-check",
    description="L3 统计异常检查",
    tags=["dq", "batch"],
)
def dq_batch_check(
    trade_date: str,
    dataset: str,
) -> dict:
    """
    执行单个数据集的 L3 检查

    规则定义在 DataHub 的 dq_rules.yaml
    """
    logger = get_run_logger()
    hub = DataHub()
    engine = get_dq_engine()

    result = engine.check_statistical(
        dataset=dataset,
        trade_date=trade_date,
        hub=hub,
    )

    if result.issues:
        logger.warning(f"发现 {len(result.issues)} 个异常")
        for issue in result.issues:
            logger.warning(f"  - {issue.rule_name}: {issue.message}")

    return {
        "dataset": dataset,
        "issues": len(result.issues),
        "details": [i.to_dict() for i in result.issues],
    }
```

---

## 7. 调度配置

```python
# schedules.py

from prefect.client.schemas.schedules import CronSchedule

from .flows.daily_ingest import daily_ingest_flow
from .flows.dq_batch import dq_batch_flow
from .flows.heartbeat import heartbeat_flow
from .flows.backfill import backfill_flow


def create_deployments():
    """创建所有 Deployments"""

    deployments = []

    # 每日数据摄取：交易日 17:00
    deployments.append(
        daily_ingest_flow.to_deployment(
            name="daily-ingest-scheduled",
            schedules=[
                CronSchedule(cron="0 17 * * 1-5", timezone="Asia/Shanghai")
            ],
            parameters={"source": "tushare"},
        )
    )

    # L3 批量校验：交易日 18:00
    deployments.append(
        dq_batch_flow.to_deployment(
            name="dq-batch-scheduled",
            schedules=[
                CronSchedule(cron="0 18 * * 1-5", timezone="Asia/Shanghai")
            ],
        )
    )

    # 心跳：每小时整点
    deployments.append(
        heartbeat_flow.to_deployment(
            name="heartbeat-scheduled",
            schedules=[
                CronSchedule(cron="0 * * * *", timezone="Asia/Shanghai")
            ],
        )
    )

    # 补数据：手动触发
    deployments.append(
        backfill_flow.to_deployment(
            name="backfill-manual",
            schedules=[],  # 无定时，只手动触发
        )
    )

    return deployments
```

---

## 8. 告警 Hook

```python
# hooks.py

from prefect import flow
from prefect.blocks.notifications import SlackWebhook
import httpx


async def on_flow_failure(flow, flow_run, state):
    """Flow 失败时发送告警"""
    message = f"""
🚨 **Ditto 任务失败告警**

**Flow**: {flow.name}
**Run ID**: {flow_run.id}
**State**: {state.name}
**Error**: {state.message}

请及时检查处理！
"""
    await send_notification(message)


def send_dq_alert(trade_date: str, issues: list):
    """发送 DQ 告警"""
    issue_summary = "\n".join(
        f"- {i.rule_name}: {i.message} ({i.affected_rows} 条)"
        for i in issues[:10]
    )

    message = f"""
⚠️ **Ditto 数据质量告警**

**日期**: {trade_date}
**问题数**: {len(issues)}

**详情**:
{issue_summary}
"""
    send_notification_sync(message)


async def send_notification(message: str):
    """异步发送通知"""
    # Telegram
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat_id:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            })

    # 钉钉
    dingtalk_webhook = os.environ.get("DINGTALK_WEBHOOK")
    if dingtalk_webhook:
        async with httpx.AsyncClient() as client:
            await client.post(dingtalk_webhook, json={
                "msgtype": "markdown",
                "markdown": {"title": "Ditto 告警", "text": message},
            })
```

---

## 9. FastAPI 集成

```python
# apps/server/src/ditto_server/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from prefect.client import get_client

from .ingestion.schedules import create_deployments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup: 注册 Prefect Deployments
    async with get_client() as client:
        deployments = create_deployments()
        for deployment in deployments:
            await deployment.apply()

    yield

    # Shutdown: 清理资源


app = FastAPI(
    title="Ditto API",
    lifespan=lifespan,
)


# 手动触发 API
@app.post("/api/v1/ingestion/trigger")
async def trigger_flow(request: TriggerRequest):
    """手动触发摄取任务"""
    from prefect.deployments import run_deployment

    deployment_map = {
        "daily_ingest": "daily-ingest/daily-ingest-scheduled",
        "dq_batch": "dq-batch/dq-batch-scheduled",
        "backfill": "backfill/backfill-manual",
    }

    deployment_name = deployment_map.get(request.flow)
    if not deployment_name:
        raise HTTPException(400, f"Unknown flow: {request.flow}")

    flow_run = await run_deployment(
        name=deployment_name,
        parameters=request.params,
    )

    return {
        "flow_run_id": str(flow_run.id),
        "status": "triggered",
    }
```

---

## 10. 手动操作

### 10.1 CLI 触发

```bash
# 每日摄取
prefect deployment run "daily-ingest/daily-ingest-scheduled"

# 指定日期
prefect deployment run "daily-ingest/daily-ingest-scheduled" \
    --param trade_date="2024-12-20"

# L3 检查
prefect deployment run "dq-batch/dq-batch-scheduled"

# 补数据
prefect deployment run "backfill/backfill-manual" \
    --param start_date="2024-01-01" \
    --param end_date="2024-01-31"
```

### 10.2 查看状态

```bash
# 查看所有 Deployments
prefect deployment ls

# 查看最近运行
prefect flow-run ls --limit 10

# 查看日志
prefect flow-run logs <run-id>

# 取消运行
prefect flow-run cancel <run-id>
```

### 10.3 Prefect UI

访问 http://localhost:4200：

- 查看 Flow Runs 列表
- DAG 可视化
- 日志查看
- 手动触发 Run
- 查看参数

---

## 11. 迁移计划

### Phase 0（MVP）

1. 安装 Prefect：`pip install prefect`
2. 本地启动 Prefect Server
3. 实现 `daily_ingest_flow` 基础版本
4. 实现 `ingest_calendar` + `ingest_etf_bars` Tasks
5. 验证手动触发和定时调度

### Phase 0.5

1. 完善所有 Tasks
2. 实现 `heartbeat_flow`
3. 集成告警（Telegram/钉钉）
4. 与 DataHub PipelineStore 集成

### Phase 1

1. 实现 `dq_batch_flow`
2. 实现 `backfill_flow`
3. 集成 OpenTelemetry Trace

---

*本文档定义了 Ditto 数据摄取的调度设计，使用 Prefect 3 作为任务调度框架。*
