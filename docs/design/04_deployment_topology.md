# Ditto 部署拓扑文档

**版本：v2.1（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-26**

---

## 1. 部署目标与约束

### 1.1 核心目标

1. **单机闭环**：Windows 10/11 本地完整运行，不依赖云服务
2. **简单可靠**：最小化运维负担，故障恢复简单
3. **可证明存活**：心跳机制证明系统正常运行
4. **可观测调度**：数据摄取任务可视化、可手动触发

### 1.2 关键约束

- **硬件**：普通 PC（8GB+ RAM，100GB+ SSD）
- **网络**：仅需外网访问数据源，无需内网服务
- **运维**：个人开发者，无专职运维
- **监控**：外部心跳（Telegram/钉钉），不依赖本机监控

---

## 2. 整体部署架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Windows 10/11 本地主机                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Pixi 环境管理                                │   │
│  │  Python 3.12+ / Node.js 20+ / 所有依赖                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌───────────────────────┐    ┌───────────────────────┐                │
│  │    DittoServer        │    │    DittoWeb           │                │
│  │    (FastAPI)          │    │    (Next.js)          │                │
│  │    Port: 8000         │    │    Port: 3000         │                │
│  │                       │    │                       │                │
│  │  + Prefect Worker     │    │  + Dev Server         │                │
│  │  + HeartbeatService   │    │    (or Static Build)  │                │
│  └───────────┬───────────┘    └───────────┬───────────┘                │
│              │                            │                             │
│              │                            │                             │
│  ┌───────────┴───────────┐                │                             │
│  │   Prefect Server      │                │                             │
│  │   Port: 4200 (UI)     │                │                             │
│  │   SQLite 持久化       │                │                             │
│  └───────────────────────┘                │                             │
│              │                            │                             │
│              │ HTTP/WS                    │ HTTP                        │
│              ▼                            ▼                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      数据存储层                                  │   │
│  │                                                                  │   │
│  │  ┌─────────────────────┐    ┌─────────────────────┐             │   │
│  │  │  Parquet + DuckDB   │    │  SQLite             │             │   │
│  │  │  data/              │    │  data/meta.db       │             │   │
│  │  │                     │    │  (WAL Mode)         │             │   │
│  │  │  - K线/因子/Regime  │    │  - 元数据/映射      │             │   │
│  │  │  - 回测结果         │    │  - 调仓计划/持仓    │             │   │
│  │  └─────────────────────┘    └─────────────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      外部通信                                    │   │
│  │                                                                  │   │
│  │  → Tushare Pro API (数据采集)                                   │   │
│  │  → AkShare API (降级备选)                                       │   │
│  │  → Telegram/钉钉 Webhook (心跳通知)                             │   │
│  │  → 邮件 SMTP (备用通知)                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
D:\Ditto\                              # 项目根目录
├── apps/
│   ├── server/                        # FastAPI 后端
│   │   ├── src/
│   │   │   ├── ditto_port/
│   │   │   │   ├── api/               # HTTP 接口
│   │   │   │   ├── services/          # 应用服务
│   │   │   │   ├── ingestion/         # Prefect 数据摄取（新）
│   │   │   │   │   ├── flows/         #   Flows
│   │   │   │   │   ├── tasks/         #   Tasks
│   │   │   │   │   └── schedules.py   #   调度配置
│   │   │   │   └── main.py
│   │   └── pyproject.toml
│   │
│   └── web/                           # Next.js 前端
│       ├── src/
│       └── package.json
│
├── packages/
│   ├── ditto-core/                    # 核心引擎库
│   └── ditto-data-hub/                # 数据层库
│
├── data/                              # 数据目录
│   ├── parquet/                       # Parquet 年分区数据
│   │   ├── etf_daily/
│   │   ├── index_daily/
│   │   └── adj_factor/
│   ├── meta.db                        # SQLite 元数据
│   └── golden/                        # Golden Dataset
│
├── backups/                           # 备份目录
│   ├── data_YYYYMMDD/
│   └── meta_YYYYMMDD.db
│
├── logs/                              # 日志目录
│   ├── ditto_YYYYMMDD.jsonl
│   └── archived/
│
├── config/                            # 配置目录
│   ├── settings.toml                  # 主配置
│   ├── secrets.toml                   # 敏感配置（Git 忽略）
│   └── strategies/                    # 策略配置
│       └── etf_rotation.toml
│
├── scripts/                           # 运维脚本
│   ├── start_all.ps1                  # 一键启动
│   ├── stop_all.ps1                   # 一键停止
│   ├── start_prefect.ps1              # 启动 Prefect（新）
│   ├── backup.ps1                     # 备份脚本
│   └── health_check.ps1               # 健康检查
│
├── pixi.toml                          # Pixi 项目配置
└── .gitignore
```

---

## 4. 任务调度（Prefect）

### 4.1 技术选型

**选择 Prefect 3 本地 Server 模式（SQLite 持久化）**

| 维度 | APScheduler | Prefect |
|------|-------------|---------|
| 复杂度 | ⭐⭐ 简单 | ⭐⭐⭐ 中等 |
| 可观测性 | ⭐⭐ 需自建 | ⭐⭐⭐⭐⭐ 内置 Dashboard |
| 手动触发 | ⭐⭐ 需开发 | ⭐⭐⭐⭐⭐ CLI/UI/API |
| 重试机制 | ⭐⭐ 手动 | ⭐⭐⭐⭐⭐ 声明式指数退避 |
| DAG 支持 | ⭐ 无 | ⭐⭐⭐⭐⭐ 原生 |
| 历史记录 | ⭐⭐ 需自建 | ⭐⭐⭐⭐⭐ 内置 |

**结论**：Prefect 的可观测性和手动触发能力带来的运维便利性，超过了其额外复杂度带来的成本。

### 4.2 调度任务清单

| 任务 | 触发时间 | 职责 |
|------|----------|------|
| `daily_ingest_flow` | 交易日 17:00 | 日历 + 证券 + K线 + 复权因子 |
| `dq_batch_check` | 交易日 18:00 | L3 统计异常检测 |
| `heartbeat_flow` | 每小时整点 | 发送心跳到 Telegram/钉钉 |
| `daily_backup` | 每天 22:00 | Parquet + SQLite 备份 |
| `factor_health_check` | 每周一 9:00 | 因子健康度检查 |

### 4.3 Prefect 部署配置

```python
# apps/server/src/ditto_port/ingestion/schedules.py

from prefect.client.schemas.schedules import CronSchedule

# 每日数据摄取：交易日 17:00
daily_ingest_deployment = daily_ingest_flow.to_deployment(
    name="daily-ingest-scheduled",
    schedules=[
        CronSchedule(cron="0 17 * * 1-5", timezone="Asia/Shanghai")
    ],
    parameters={"source": "tushare"},
)

# L3 批量校验：交易日 18:00
dq_batch_deployment = dq_batch_flow.to_deployment(
    name="dq-batch-scheduled",
    schedules=[
        CronSchedule(cron="0 18 * * 1-5", timezone="Asia/Shanghai")
    ],
)

# 心跳：每小时整点
heartbeat_deployment = heartbeat_flow.to_deployment(
    name="heartbeat-scheduled",
    schedules=[
        CronSchedule(cron="0 * * * *", timezone="Asia/Shanghai")
    ],
)
```

### 4.4 Flow 实现示例

```python
# apps/server/src/ditto_port/ingestion/flows/daily_ingest.py

from prefect import flow, get_run_logger
from ditto_data_hub import DataHub

from ..tasks.calendar import ingest_calendar
from ..tasks.securities import ingest_securities
from ..tasks.bars import ingest_etf_bars, ingest_index_bars
from ..tasks.adj_factor import ingest_adj_factor


@flow(
    name="daily-ingest",
    description="每日数据摄取",
    retries=2,
    retry_delay_seconds=300,
    log_prints=True,
)
def daily_ingest_flow(
    trade_date: str | None = None,
    source: str = "tushare",
) -> dict:
    """
    每日数据摄取主流程

    DAG 依赖：
    calendar → securities → bars (并行) + adj_factor
    """
    logger = get_run_logger()
    hub = DataHub()

    if trade_date is None:
        trade_date = hub.calendar.get_last_trading_day()

    logger.info(f"开始摄取: {trade_date}, source={source}")

    # Step 1: 日历（其他任务依赖）
    ingest_calendar(source=source)

    # Step 2: 证券主数据
    ingest_securities(source=source)

    # Step 3: K线数据（并行）
    etf_future = ingest_etf_bars.submit(trade_date, source)
    index_future = ingest_index_bars.submit(trade_date, source)

    # Step 4: 复权因子
    adj_future = ingest_adj_factor.submit(trade_date, source)

    # 等待并行任务
    results = {
        "etf": etf_future.result(),
        "index": index_future.result(),
        "adj": adj_future.result(),
    }

    logger.info(f"摄取完成: {results}")
    return results
```

### 4.5 手动触发方式

```bash
# 1. CLI 方式
prefect deployment run "daily-ingest/daily-ingest-scheduled" \
    --param trade_date="2024-12-20"

# 2. Prefect UI
# 访问 http://localhost:4200，点击 Run 按钮

# 3. Python API
from prefect.deployments import run_deployment
run_deployment(name="daily-ingest/daily-ingest-scheduled", parameters={"trade_date": "2024-12-20"})

# 4. HTTP API（通过 FastAPI）
curl -X POST http://localhost:8000/api/v1/ingestion/trigger \
    -H "Content-Type: application/json" \
    -d '{"flow": "daily_ingest", "params": {"trade_date": "2024-12-20"}}'
```

---

## 5. 心跳机制

### 5.1 设计原则

> **"死人不会说话"** —— 监控系统本身挂了无法报警

因此心跳必须发送到**外部系统**（Telegram/钉钉/邮件），而非本机监控。

### 5.2 心跳内容

```
🤖 Ditto Heartbeat
Time: 2024-12-26 15:00
Status: ✅ OK | Data: 2024-12-25
Kill Switch: Inactive
Prefect: 3 flows healthy
```

### 5.3 异常时发送详情

```
🤖 Ditto Heartbeat
Time: 2024-12-26 15:00
Status: ❌ ERROR
Kill Switch: ACTIVE Level 2 - Drawdown 18.5%
Last Flow Run: daily-ingest FAILED
Action Required: Review and manually confirm
```

### 5.4 Prefect 告警 Hook

```python
# apps/server/src/ditto_port/ingestion/hooks.py

from prefect import flow
from prefect.blocks.notifications import SlackWebhook


async def on_flow_failure(flow, flow_run, state):
    """Flow 失败时发送告警"""
    message = f"""
🚨 **Ditto 任务失败告警**

Flow: {flow.name}
Run ID: {flow_run.id}
State: {state.name}
Error: {state.message}

请及时检查处理！
"""
    # 发送到 Telegram/钉钉
    webhook = await SlackWebhook.load("ditto-alerts")
    await webhook.notify(message)


@flow(name="daily-ingest", on_failure=[on_flow_failure])
def daily_ingest_flow(...):
    ...
```

---

## 6. Prefect 启动与运维

### 6.1 启动脚本

```powershell
# scripts/start_prefect.ps1

# 启动 Prefect Server（后台运行）
Start-Process -NoNewWindow -FilePath "prefect" -ArgumentList "server", "start", "--host", "0.0.0.0"

# 等待 Server 就绪
Start-Sleep -Seconds 5

# 启动 Prefect Worker
Start-Process -NoNewWindow -FilePath "prefect" -ArgumentList "worker", "start", "--pool", "default-agent-pool"

Write-Host "Prefect Server: http://localhost:4200"
```

### 6.2 一键启动

```powershell
# scripts/start_all.ps1

Write-Host "Starting Ditto services..."

# 1. 启动 Prefect
& "$PSScriptRoot\start_prefect.ps1"

# 2. 启动 FastAPI Server
Start-Process -NoNewWindow -FilePath "pixi" -ArgumentList "run", "server"

# 3. 启动 Web UI（可选）
# Start-Process -NoNewWindow -FilePath "pixi" -ArgumentList "run", "web"

Write-Host "All services started!"
Write-Host "  - API: http://localhost:8000"
Write-Host "  - Prefect UI: http://localhost:4200"
Write-Host "  - Web UI: http://localhost:3000"
```

### 6.3 日常命令

```bash
# 查看所有 Deployments
prefect deployment ls

# 查看最近运行
prefect flow-run ls --limit 10

# 手动触发
prefect deployment run "daily-ingest/daily-ingest-scheduled"

# 取消运行
prefect flow-run cancel <run-id>

# 查看日志
prefect flow-run logs <run-id>

# 补数据
prefect deployment run "backfill/backfill-scheduled" \
    --param start_date="2024-01-01" \
    --param end_date="2024-12-20"
```

---

## 7. 数据库并发控制

### 7.1 核心原则

**"任何时刻只有一个写 Parquet/SQLite 的进程"**

### 7.2 实现方式

- Prefect Worker 单实例运行（`max_instances=1`）
- 使用文件锁 (`msvcrt.locking` on Windows)
- SQLite WAL 模式

### 7.3 SQLite 配置

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
```

---

## 8. 健康检查

### 8.1 检查项

| 组件 | 检查内容 | 健康标准 |
|------|----------|----------|
| sqlite | 连接 + 查询 | 可查询 |
| parquet | 文件可读 | 可读取 |
| data_freshness | 最新数据日期 | ≤ 1 天 |
| prefect_server | API 响应 | 可访问 |
| prefect_worker | 运行状态 | 正在运行 |
| kill_switch | 触发状态 | 未触发 |

### 8.2 API 端点

```python
# apps/server/src/ditto_port/api/health.py

@router.get("/healthz")
async def healthz():
    """简单存活检查"""
    return {"status": "ok"}


@router.get("/health")
async def health():
    """详细健康报告"""
    return {
        "status": "healthy",
        "components": {
            "sqlite": check_sqlite(),
            "parquet": check_parquet(),
            "data_freshness": check_data_freshness(),
            "prefect": await check_prefect(),
            "kill_switch": check_kill_switch(),
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/health/prefect")
async def prefect_health():
    """Prefect 健康检查"""
    async with get_client() as client:
        deployments = await client.read_deployments()
        recent_runs = await client.read_flow_runs(limit=5)

        return {
            "status": "healthy",
            "deployments": len(deployments),
            "recent_runs": [
                {
                    "name": r.name,
                    "state": r.state.type.value,
                    "started": r.start_time.isoformat() if r.start_time else None,
                }
                for r in recent_runs
            ],
        }
```

---

## 9. 备份策略

### 9.1 备份内容

| 数据 | 频率 | 保留期 |
|------|------|--------|
| Parquet 数据 | 每日 | 30 天 |
| SQLite 元数据 | 每日 | 30 天 |
| 配置文件 | 每日 | 30 天 |
| Prefect 数据库 | 每周 | 30 天 |
| 日志文件 | 每周 | 90 天 |

### 9.2 备份脚本

```powershell
# scripts/backup.ps1

$date = Get-Date -Format "yyyyMMdd"
$backupDir = "D:\Ditto\backups\$date"

New-Item -ItemType Directory -Force -Path $backupDir

# 备份 Parquet 数据
Copy-Item -Recurse "D:\Ditto\data\parquet" "$backupDir\parquet"

# 备份 SQLite
Copy-Item "D:\Ditto\data\meta.db" "$backupDir\meta.db"

# 备份配置
Copy-Item -Recurse "D:\Ditto\config" "$backupDir\config"

# 清理旧备份（保留 30 天）
Get-ChildItem "D:\Ditto\backups" -Directory |
    Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Recurse -Force

Write-Host "Backup completed: $backupDir"
```

---

## 10. Runbook（故障处理手册）

### 10.1 收不到心跳

```
1. 检查网络连接
2. 远程登录主机
3. 检查 Prefect Worker 进程：
   Get-Process python | Where CommandLine -like "*prefect*"
4. 查看 Prefect UI：http://localhost:4200
5. 查看最近日志：Get-Content logs\ditto_*.jsonl -Tail 100
6. 如果 Worker 不存在，重启：.\scripts\start_prefect.ps1
```

### 10.2 数据摄取失败

```
1. 查看 Prefect UI 中的 Flow Run 详情
2. 检查具体 Task 的错误信息
3. 检查 Tushare 积分和 API 状态
4. 如果 Tushare 不可用，手动触发 AkShare 降级：
   prefect deployment run "daily-ingest/..." --param source="akshare"
5. 修复后手动重跑：
   prefect deployment run "daily-ingest/..." --param trade_date="2024-12-20"
```

### 10.3 Prefect Server 无响应

```
1. 检查进程：Get-Process python | Where CommandLine -like "*prefect server*"
2. 检查端口：netstat -an | findstr "4200"
3. 查看日志：Get-Content ~/.prefect/prefect.log -Tail 100
4. 重启 Prefect：
   Stop-Process -Name python -Force  # 停止所有 Python 进程
   .\scripts\start_prefect.ps1       # 重新启动
```

### 10.4 补数据流程

```
1. 确定需要补的日期范围
2. 运行 backfill Flow：
   prefect deployment run "backfill/backfill-scheduled" \
       --param start_date="2024-01-01" \
       --param end_date="2024-01-31"
3. 在 Prefect UI 监控进度
4. 完成后验证数据完整性
```

---

## 11. 资源需求

| 组件 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| FastAPI Server | 1 核 | 512MB | - |
| Prefect Server | 1 核 | 256MB | 100MB |
| Prefect Worker | 1 核 | 512MB | - |
| SQLite | - | 256MB | 1GB |
| Parquet 数据 | - | - | 10GB+ |
| **总计** | 2-4 核 | 2GB | 15GB+ |

---

*本部署拓扑文档定义了 Ditto Phase 0–1 的完整部署架构，使用 Prefect 替代 APScheduler 进行任务调度。*
