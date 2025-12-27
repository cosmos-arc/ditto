# Ditto 可观测性方案设计文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-23**

---

## 目录

1. [设计目标与原则](#1-设计目标与原则)
2. [技术栈选择](#2-技术栈选择)
3. [架构设计](#3-架构设计)
4. [日志规范](#4-日志规范)
5. [Trace 规范](#5-trace-规范)
6. [Metrics 规范](#6-metrics-规范)
7. [埋点清单](#7-埋点清单)
8. [告警规则](#8-告警规则)
9. [代码实现](#9-代码实现)
10. [部署方案](#10-部署方案)
11. [测试方案](#11-测试方案)
12. [运维手册](#12-运维手册)

---

## 1. 设计目标与原则

### 1.1 设计目标

| 目标 | 说明 | 验收标准 |
|------|------|----------|
| **问题可定位** | 出错时能快速找到原因 | 通过 trace_id 5 分钟内定位问题 |
| **状态可感知** | 随时了解系统运行状况 | Grafana 仪表盘实时展示 |
| **外部可验证** | 心跳机制证明系统存活 | /healthz 端点响应 < 100ms |
| **历史可追溯** | 关键操作有审计记录 | 审计日志永久保留 |

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **OTel 标准优先** | 使用 OpenTelemetry API，后端可插拔 |
| **轻量单机优化** | 资源占用 < 500MB RAM |
| **渐进式建设** | 先 Logs + Metrics，后 Traces |
| **测试友好** | 单测不依赖外部服务 |
| **业务语义清晰** | 指标/日志命名体现业务含义 |

---

## 2. 技术栈选择

### 2.1 SDK 层

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Logs | Loguru | ≥0.7 | Python 最佳日志库，开发体验好 |
| Traces | OTel API | ≥1.20 | 业界标准，通过日志 trace_id 关联 |
| Metrics | OTel API | ≥1.20 | 业界标准，OTLP 直推 |

### 2.2 后端层

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Metrics 存储 | VictoriaMetrics | ≥1.96 | 原生 OTLP 支持，单二进制 |
| Logs 存储 | VictoriaLogs | ≥1.0 | 超轻量，LogsQL 查询 |
| Logs 采集 | Vector | ≥0.34 | 高性能，配置简单 |
| 可视化 | Grafana | ≥10.2 | 统一仪表盘 |

### 2.3 依赖清单

```toml
# pyproject.toml
[project]
dependencies = [
    # OTel 核心
    "opentelemetry-api>=1.20",
    "opentelemetry-sdk>=1.20",
    "opentelemetry-exporter-otlp-proto-http>=1.20",

    # 日志
    "loguru>=0.7",
]
```

**安装大小：~15MB**

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Ditto Application                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Loguru     │    │  OTel Tracer │    │  OTel Meter  │       │
│  │              │◄───│  (trace_id)  │    │              │       │
│  └──────┬───────┘    └──────────────┘    └──────┬───────┘       │
│         │                                        │               │
│         ▼                                        ▼               │
│  ┌──────────────┐                        ┌──────────────┐       │
│  │  JSON Files  │                        │ OTLP Exporter│       │
│  │  (.jsonl)    │                        │              │       │
│  └──────┬───────┘                        └──────┬───────┘       │
│         │                                        │               │
└─────────┼────────────────────────────────────────┼───────────────┘
          │                                        │
          ▼                                        ▼
   ┌──────────────┐                    ┌────────────────────┐
   │    Vector    │                    │  VictoriaMetrics   │
   │              │                    │  :8428/otlp/v1     │
   └──────┬───────┘                    └─────────┬──────────┘
          │                                      │
          ▼                                      │
   ┌──────────────┐                              │
   │ VictoriaLogs │                              │
   │    :9428     │                              │
   └──────┬───────┘                              │
          │                                      │
          └──────────────┬───────────────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   Grafana    │
                  │    :3000     │
                  └──────────────┘
```

### 3.2 数据流

| 数据类型 | 流向 | 格式 |
|----------|------|------|
| Logs | App → JSON File → Vector → VictoriaLogs | JSON Lines |
| Metrics | App → OTLP HTTP → VictoriaMetrics | OTLP/HTTP |
| Traces | 通过 trace_id 关联日志（暂不独立存储） | - |

### 3.3 端口规划

| 服务 | 端口 | 用途 |
|------|------|------|
| Ditto API | 8000 | 业务 API |
| VictoriaMetrics | 8428 | Metrics 存储 + OTLP 接收 |
| VictoriaLogs | 9428 | Logs 存储 + 查询 |
| Vector | 8686 | 日志采集状态 |
| Grafana | 3000 | 可视化仪表盘 |

---

## 4. 日志规范

### 4.1 日志级别

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| **DEBUG** | 开发调试信息 | 函数入参、中间计算结果、span 开始/结束 |
| **INFO** | 正常业务流程 | 任务开始/完成、数据更新成功、调仓执行 |
| **WARNING** | 异常但可恢复 | 数据源降级、因子健康度警告、Kill Switch L1 |
| **ERROR** | 错误但系统可继续 | 单个标的数据获取失败、API 调用失败 |
| **CRITICAL** | 严重错误需人工介入 | Kill Switch L2/L3、数据库损坏 |

### 4.2 日志字段规范

#### 4.2.1 必选字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `_time` | string | ISO8601 时间戳 | `2024-12-23T14:30:01.123Z` |
| `level` | string | 日志级别 | `INFO` |
| `_msg` | string | 日志消息 | `Data update completed` |
| `service` | string | 服务名 | `ditto` |

#### 4.2.2 Trace 上下文字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `trace_id` | string | 追踪 ID（8位） | `a1b2c3d4` |
| `span` | string | 当前 Span 名称 | `run_backtest` |
| `span_path` | string | Span 调用路径 | `run_backtest > load_data` |

#### 4.2.3 业务上下文字段

| 字段名 | 类型 | 使用场景 | 示例 |
|--------|------|----------|------|
| `event` | string | 事件类型（用于搜索） | `data_update`, `rebalance` |
| `strategy` | string | 策略名称 | `etf_rotation` |
| `trade_date` | string | 交易日期 | `2024-12-23` |
| `symbol` | string | 标的代码 | `510300.SH` |
| `source` | string | 数据源 | `tushare`, `akshare` |
| `duration_ms` | float | 操作耗时（毫秒） | `1234.5` |
| `error` | string | 错误信息 | `Connection timeout` |
| `error_type` | string | 错误类型 | `ValueError` |

### 4.3 事件类型（event 字段）

统一使用 `snake_case`，格式：`{domain}_{action}`

| 领域 | 事件类型 | 说明 |
|------|----------|------|
| **数据** | `data_update_start` | 数据更新开始 |
| | `data_update_complete` | 数据更新完成 |
| | `data_update_failed` | 数据更新失败 |
| | `data_validation_error` | 数据校验错误 |
| **因子** | `factor_calc_start` | 因子计算开始 |
| | `factor_calc_complete` | 因子计算完成 |
| | `factor_health_warning` | 因子健康度警告 |
| **策略** | `signal_generated` | 信号生成 |
| | `rebalance_plan_created` | 调仓计划创建 |
| | `rebalance_executed` | 调仓执行 |
| **风控** | `kill_switch_triggered` | Kill Switch 触发 |
| | `kill_switch_deactivated` | Kill Switch 解除 |
| | `drawdown_warning` | 回撤警告 |
| **系统** | `scheduler_job_start` | 调度任务开始 |
| | `scheduler_job_complete` | 调度任务完成 |
| | `api_request` | API 请求 |
| | `health_check` | 健康检查 |
| **数据摄取** | `ingest_flow_start` | Prefect Flow 开始 |
| | `ingest_flow_complete` | Prefect Flow 完成 |
| | `ingest_flow_failed` | Prefect Flow 失败 |
| | `ingest_task_start` | Prefect Task 开始 |
| | `ingest_task_complete` | Prefect Task 完成 |
| | `ingest_task_retry` | Prefect Task 重试 |
| **DQ** | `dq_l1_failed` | L1 技术校验失败 |
| | `dq_l2_warning` | L2 业务规则警告 |
| | `dq_l3_alert` | L3 统计异常告警 |

### 4.4 日志示例

```python
# INFO - 正常业务流程
logger.info(
    "Daily data update completed",
    event="data_update_complete",
    trade_date="2024-12-23",
    source="tushare",
    duration_ms=45000,
    records_inserted=1250,
    symbols_updated=50,
)

# WARNING - 可恢复异常
logger.warning(
    "Primary data source unavailable, using fallback",
    event="data_source_degraded",
    primary_source="tushare",
    fallback_source="akshare",
)

# ERROR - 错误但可继续
logger.error(
    "Failed to fetch data for symbol",
    event="data_update_failed",
    symbol="510300.SH",
    source="tushare",
    error="Connection timeout",
    error_type="TimeoutError",
    retry_count=3,
)

# CRITICAL - 需人工介入
logger.critical(
    "Kill Switch Level 2 triggered",
    event="kill_switch_triggered",
    level=2,
    current_drawdown=0.185,
    threshold=0.18,
    action="REDUCE_50PCT",
)
```

### 4.5 敏感信息处理

```python
# ❌ 错误：记录完整敏感信息
logger.info("API call", api_key="sk-1234567890abcdef")

# ✅ 正确：脱敏处理
logger.info("API call", api_key="sk-12****ef")

# ❌ 错误：记录密码
logger.info("Login", password="my_password")

# ✅ 正确：不记录密码
logger.info("Login", user="admin")
```

**禁止记录的信息：**
- 完整 API Key / Token
- 账户密码
- 券商账号信息
- 身份证号、手机号等个人信息

---

## 5. Trace 规范

### 5.1 Trace ID 生成规则

- **格式**：8 位十六进制字符（UUID 前 8 位）
- **生成时机**：每个顶层操作开始时自动生成
- **传递方式**：通过 `contextvars` 在调用链中传递

### 5.2 Span 命名规范

格式：`{domain}.{operation}` 或 `{operation}`（简单场景）

| 领域 | Span 名称 | 说明 |
|------|-----------|------|
| **数据** | `data.update` | 数据更新主流程 |
| | `data.fetch` | 从数据源获取数据 |
| | `data.validate` | 数据校验 |
| | `data.store` | 数据存储 |
| **因子** | `factor.calculate` | 因子计算主流程 |
| | `factor.{name}` | 单个因子计算 |
| **策略** | `strategy.generate_signal` | 信号生成 |
| | `strategy.create_plan` | 创建调仓计划 |
| | `strategy.execute` | 执行调仓 |
| **回测** | `backtest.run` | 回测主流程 |
| | `backtest.load_data` | 加载回测数据 |
| | `backtest.simulate` | 模拟交易 |
| | `backtest.calculate_metrics` | 计算回测指标 |

### 5.3 Span 属性规范

| 属性名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `strategy` | string | 策略名称 | `etf_rotation` |
| `trade_date` | string | 交易日期 | `2024-12-23` |
| `symbol` | string | 标的代码 | `510300.SH` |
| `source` | string | 数据源 | `tushare` |
| `rows` | int | 数据行数 | `10000` |
| `duration_ms` | float | 耗时 | `1234.5` |

### 5.4 使用示例

```python
from ditto.observability import span, traced, logger

# 装饰器方式
@traced("backtest.run")
def run_backtest(strategy: str, start_date: str, end_date: str) -> dict:
    logger.info(f"Starting backtest: {strategy}")

    with span("backtest.load_data", source="duckdb") as s:
        df = load_data(start_date, end_date)
        s.set_attribute("rows", len(df))
        logger.info("Data loaded", rows=len(df))

    with span("backtest.simulate"):
        result = simulate(df, strategy)
        logger.info("Simulation complete", orders=result.order_count)

    return result
```

---

## 6. Metrics 规范

### 6.1 命名规范

格式：`ditto.{domain}.{metric_name}`

- 使用 `snake_case`
- 单位后缀：`_seconds`, `_bytes`, `_total`, `_ratio`, `_percent`
- Counter 以 `_total` 结尾
- Gauge 描述当前状态
- Histogram 用于分布统计

### 6.2 Label 规范

| Label 名 | 说明 | 示例值 |
|----------|------|--------|
| `strategy` | 策略名称 | `etf_rotation` |
| `source` | 数据源 | `tushare`, `akshare` |
| `table` | 数据表名 | `etf_daily`, `index_daily` |
| `factor` | 因子名称 | `rs_20d`, `vol_20d` |
| `status` | 状态 | `success`, `failed` |
| `level` | 级别 | `1`, `2`, `3` |
| `direction` | 方向 | `buy`, `sell` |
| `regime` | 市场状态 | `bull`, `bear`, `oscillation` |

**Label 使用原则：**
- 控制基数：每个 label 的值不超过 20 个
- 避免高基数：不使用 `symbol`、`order_id` 等高基数字段作为 label
- 相关指标使用一致的 label

### 6.3 指标清单

#### 6.3.1 数据指标

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `ditto.data.update_duration_seconds` | Histogram | `source`, `table` | 数据更新耗时 |
| `ditto.data.records_total` | Counter | `source`, `table`, `status` | 数据记录数 |
| `ditto.data.freshness_seconds` | Gauge | `source`, `table` | 数据新鲜度（距最新数据的秒数） |
| `ditto.data.quality_ratio` | Gauge | `source`, `table` | 数据完整率 |
| `ditto.data.errors_total` | Counter | `source`, `error_type` | 数据错误数 |
| `ditto.dq.check_duration_seconds` | Histogram | dataset, level | DQ 检查耗时 |
| `ditto.dq.issues_total` | Counter | dataset, level, severity | DQ 问题数 |

#### 6.3.2 因子指标

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `ditto.factor.calc_duration_seconds` | Histogram | `factor` | 因子计算耗时 |
| `ditto.factor.ic_value` | Gauge | `factor`, `period` | 因子 IC 值 |
| `ditto.factor.health_status` | Gauge | `factor` | 健康状态（0=健康,1=警告,2=严重） |

#### 6.3.3 策略指标

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `ditto.strategy.signal_total` | Counter | `strategy`, `direction` | 信号生成数 |
| `ditto.strategy.rebalance_total` | Counter | `strategy`, `status` | 调仓执行数 |

#### 6.3.4 组合指标

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `ditto.portfolio.value_yuan` | Gauge | `strategy` | 组合净值（元） |
| `ditto.portfolio.return_ratio` | Gauge | `strategy`, `period` | 收益率 |
| `ditto.portfolio.drawdown_ratio` | Gauge | `strategy` | 当前回撤 |
| `ditto.portfolio.drawdown_3d_ratio` | Gauge | `strategy` | 3 日回撤（速度） |
| `ditto.portfolio.position_ratio` | Gauge | `strategy` | 仓位比例 |
| `ditto.portfolio.position_count` | Gauge | `strategy` | 持仓数量 |

#### 6.3.5 风控指标

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `ditto.risk.kill_switch_level` | Gauge | `strategy` | Kill Switch 当前级别 |
| `ditto.risk.kill_switch_total` | Counter | `strategy`, `level` | Kill Switch 触发次数 |
| `ditto.risk.alerts_total` | Counter | `strategy`, `alert_type` | 告警次数 |

#### 6.3.6 系统指标

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `ditto.system.api_requests_total` | Counter | `endpoint`, `method`, `status` | API 请求数 |
| `ditto.system.api_duration_seconds` | Histogram | `endpoint`, `method` | API 耗时 |
| `ditto.system.db_query_duration_seconds` | Histogram | `db`, `operation` | 数据库查询耗时 |
| `ditto.system.heartbeat_timestamp` | Gauge | - | 最近心跳时间戳 |

#### 6.3.7 任务指标
| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `ditto.ingest.flow_duration_seconds` | Histogram | flow, source | Flow 执行耗时 |
| `ditto.ingest.task_duration_seconds` | Histogram | task, source | Task 执行耗时 |
| `ditto.ingest.records_total` | Counter | dataset, source, status | 摄取记录数 |

### 6.4 Histogram Buckets

```python
# 耗时类（秒）
DURATION_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300]

# 数据量类
SIZE_BUCKETS = [100, 500, 1000, 5000, 10000, 50000, 100000]
```

---

## 7. 埋点清单

### 7.1 数据模块

| 位置 | Span | Metrics | Logs |
|------|------|---------|------|
| 数据更新入口 | `data.update` | `update_duration_seconds` | INFO: 开始/完成 |
| 数据源获取 | `data.fetch` | `records_total` | DEBUG: 获取中 |
| 数据校验 | `data.validate` | `quality_ratio` | WARNING: 校验失败 |
| 数据存储 | `data.store` | - | DEBUG: 存储中 |
| 数据源切换 | - | `errors_total` | WARNING: 降级 |

```python
# 示例：数据更新埋点
@traced("data.update")
def update_daily_data(trade_date: str) -> None:
    logger.info("Starting daily data update", event="data_update_start", trade_date=trade_date)

    for source in ["tushare", "akshare"]:
        with span("data.fetch", source=source) as s:
            try:
                df = fetch_from_source(source, trade_date)
                s.set_attribute("rows", len(df))
                M.data_records.add(len(df), {"source": source, "table": "etf_daily", "status": "success"})
                logger.debug(f"Fetched {len(df)} records", source=source, rows=len(df))
            except Exception as e:
                M.data_errors.add(1, {"source": source, "error_type": type(e).__name__})
                logger.error("Data fetch failed", event="data_update_failed", source=source, error=str(e))
                raise

    M.data_freshness.set(0, {"source": "tushare", "table": "etf_daily"})
    logger.info("Daily data update completed", event="data_update_complete", trade_date=trade_date)
```

### 7.2 因子模块

| 位置 | Span | Metrics | Logs |
|------|------|---------|------|
| 因子计算入口 | `factor.calculate` | `calc_duration_seconds` | INFO: 开始/完成 |
| 单因子计算 | `factor.{name}` | - | DEBUG: 计算中 |
| IC 计算 | `factor.ic` | `ic_value` | INFO: IC 结果 |
| 健康检查 | - | `health_status` | WARNING: 健康度下降 |

```python
# 示例：因子计算埋点
@traced("factor.calculate")
def calculate_factors(trade_date: str) -> None:
    logger.info("Starting factor calculation", event="factor_calc_start", trade_date=trade_date)

    for factor_name in FACTORS:
        with span(f"factor.{factor_name}") as s:
            with M.factor_calc_duration.labels(factor=factor_name).time():
                result = calculate_single_factor(factor_name, trade_date)
                s.set_attribute("symbols", len(result))

    logger.info("Factor calculation completed", event="factor_calc_complete", trade_date=trade_date)
```

### 7.3 策略模块

| 位置 | Span | Metrics | Logs |
|------|------|---------|------|
| 信号生成 | `strategy.generate_signal` | `signal_total` | INFO: 信号详情 |
| 调仓计划 | `strategy.create_plan` | - | INFO: 计划创建 |
| 调仓执行 | `strategy.execute` | `rebalance_total` | INFO: 执行结果 |

### 7.4 风控模块

| 位置 | Span | Metrics | Logs |
|------|------|---------|------|
| Kill Switch 检查 | - | `kill_switch_level` | DEBUG: 检查结果 |
| Kill Switch 触发 | - | `kill_switch_total` | CRITICAL: L2/L3, WARNING: L1 |
| 回撤计算 | - | `drawdown_ratio`, `drawdown_3d_ratio` | WARNING: 超阈值 |

```python
# 示例：Kill Switch 埋点
def check_kill_switch(drawdown: float, drawdown_3d: float) -> int:
    level = 0

    if drawdown >= 0.20:
        level = 3
        logger.critical(
            "Kill Switch Level 3 triggered - Full liquidation",
            event="kill_switch_triggered",
            level=3,
            current_drawdown=drawdown,
            threshold=0.20,
            action="LIQUIDATE_ALL",
        )
    elif drawdown >= 0.18:
        level = 2
        logger.critical(
            "Kill Switch Level 2 triggered - Reduce 50%",
            event="kill_switch_triggered",
            level=2,
            current_drawdown=drawdown,
            threshold=0.18,
            action="REDUCE_50PCT",
        )
    elif drawdown >= 0.15 or drawdown_3d >= 0.05:
        level = 1
        logger.warning(
            "Kill Switch Level 1 triggered - No new positions",
            event="kill_switch_triggered",
            level=1,
            current_drawdown=drawdown,
            drawdown_3d=drawdown_3d,
            action="STOP_NEW_POSITIONS",
        )

    M.kill_switch_level.set(level, {"strategy": "etf_rotation"})
    if level > 0:
        M.kill_switch_total.add(1, {"strategy": "etf_rotation", "level": str(level)})

    return level
```

### 7.5 调度模块

| 位置 | Span | Metrics | Logs |
|------|------|---------|------|
| 任务开始 | `scheduler.{job}` | `scheduler_jobs_total` | INFO: 任务开始 |
| 任务完成 | - | `scheduler_job_duration_seconds` | INFO: 任务完成 |
| 任务失败 | - | - | ERROR: 任务失败 |

### 7.6 API 模块

| 位置 | Span | Metrics | Logs |
|------|------|---------|------|
| 请求入口 | `api.{endpoint}` | `api_requests_total` | DEBUG: 请求详情 |
| 请求完成 | - | `api_duration_seconds` | DEBUG: 响应详情 |
| 请求错误 | - | - | ERROR: 错误详情 |

---

## 8. 告警规则

### 8.1 告警级别

| 级别 | 名称 | 响应时间 | 通知方式 |
|------|------|----------|----------|
| **P0** | 紧急 | 立即 | Telegram + 钉钉 + 邮件 + 短信 |
| **P1** | 严重 | 1 小时内 | Telegram + 钉钉 + 邮件 |
| **P2** | 警告 | 当日 | Telegram + 钉钉 |
| **P3** | 通知 | 下次检查 | 仅日志 |

### 8.2 告警规则清单

#### P0 - 紧急

| 规则名 | 条件 | 消息模板 |
|--------|------|----------|
| `kill_switch_level3` | `kill_switch_level >= 3` | 🚨 紧急：Kill Switch L3 触发！回撤 {drawdown:.1%}，已强制清仓 |

#### P1 - 严重

| 规则名 | 条件 | 消息模板 |
|--------|------|----------|
| `kill_switch_level2` | `kill_switch_level == 2` | ⚠️ 严重：Kill Switch L2 触发，回撤 {drawdown:.1%}，已减仓 50% |
| `all_data_sources_failed` | 所有数据源失败 | ⚠️ 严重：所有数据源不可用，数据更新暂停 |
| `heartbeat_missing` | 心跳超过 6 小时 | ⚠️ 严重：系统心跳丢失超过 6 小时 |

#### P2 - 警告

| 规则名 | 条件 | 消息模板 |
|--------|------|----------|
| `kill_switch_level1` | `kill_switch_level == 1` | ⚡ 警告：Kill Switch L1 触发，回撤 {drawdown:.1%}，已停止新开仓 |
| `fast_drawdown` | `drawdown_3d > 0.05` | ⚡ 警告：3 日回撤 {drawdown_3d:.1%}，触发速度保护 |
| `factor_critical` | 因子健康状态为 CRITICAL | ⚡ 警告：因子 {factor} IC 为负，建议移除 |
| `data_stale` | 数据新鲜度 > 24 小时 | ⚡ 警告：{table} 数据已超过 24 小时未更新 |

#### P3 - 通知

| 规则名 | 条件 | 消息模板 |
|--------|------|----------|
| `data_source_degraded` | 主数据源不可用 | 📝 通知：主数据源 {source} 不可用，已降级到备用源 |
| `factor_warning` | 因子健康状态为 WARNING | 📝 通知：因子 {factor} IC 低于阈值，建议观察 |
| `scheduler_job_failed` | 调度任务失败 | 📝 通知：任务 {job} 执行失败：{error} |

### 8.3 Grafana 告警配置示例

```yaml
# grafana/provisioning/alerting/rules.yaml
apiVersion: 1
groups:
  - name: ditto_critical
    folder: Ditto
    interval: 1m
    rules:
      - uid: kill_switch_l2
        title: Kill Switch Level 2
        condition: B
        data:
          - refId: A
            datasourceUid: victoriametrics
            model:
              expr: ditto_risk_kill_switch_level{strategy="etf_rotation"} >= 2
          - refId: B
            datasourceUid: "-100"
            model:
              type: threshold
              conditions:
                - evaluator:
                    type: gt
                    params: [0]
        for: 0s
        annotations:
          summary: "Kill Switch Level 2 triggered"
        labels:
          severity: critical

```

---

## 9. 代码实现

### 9.1 目录结构

```
packages/foundation/src/ditto_foundation/
├── observability/
│   ├── __init__.py          # 统一导出接口
│   ├── config.py            # 运行模式枚举和配置类
│   ├── logging.py           # Loguru 日志配置
│   ├── tracing.py           # OTel Tracing 实现
│   ├── metrics.py           # OTel Metrics 实现
│   ├── testing.py           # 测试辅助函数
│   └── README.md           # 模块使用文档
```

### 9.2 模块说明

**实际实现采用多文件模块结构**，各文件职责如下：

- `__init__.py`: 统一导出 `init()`, `shutdown()`, `logger`, `span`, `traced`, `M` 等公共接口
- `config.py`: 定义 `Mode` 枚举（PRODUCTION/DEVELOPMENT/TESTING/TESTING_WITH_ASSERTIONS）和 `ObservabilityConfig` 配置类
- `logging.py`: Loguru 配置，支持 JSON 格式输出和多种运行模式
- `tracing.py`: OTel Tracing 配置，实现 `span` 上下文管理器和 `traced` 装饰器
- `metrics.py`: OTel Metrics 配置，定义 `M` 类包含所有预定义业务指标
- `testing.py`: 测试辅助函数，提供 `reset_for_testing()`, `get_recorded_spans()`, `get_recorded_metrics()`

### 9.3 使用方式

```python
# 从 ditto_foundation 导入可观测性接口
from ditto_foundation import init, logger, span, traced, M

# 初始化
init()

# 日志
logger.info("Starting backtest", event="backtest_start", strategy="etf_rotation")

# 追踪
@traced("my_function")
def my_function():
    with span("sub_operation", key="value"):
        ...

# 指标
M.data_records.add(100, {"source": "tushare", "table": "etf_daily", "status": "success"})
```

> **注**: 完整的代码实现请参考 `packages/foundation/src/ditto_foundation/observability/README.md` 模块文档。

---

## 10. 部署方案

### 10.1 目录结构

```
deploy/observability/
├── docker-compose.yml          # Docker Compose 配置
├── README.md                   # 部署说明文档
├── vector.toml                 # Vector 日志采集配置
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── datasources.yml      # 数据源配置
        └── dashboards/
            ├── dashboard.yml         # 仪表盘提供者配置
            └── ditto-overview.json   # Ditto 概览仪表盘

scripts/observability/
├── start.ps1                   # 启动服务脚本
├── stop.ps1                    # 停止服务脚本
├── health_check.ps1            # 健康检查脚本
└── test_observability.py       # 测试脚本
```

### 10.2 服务版本

| 服务 | 版本 | 发布日期 | 端口 | 内存限制 | 保留期 | 用途 |
|------|------|----------|------|----------|--------|------|
| VictoriaMetrics | v1.104.0 | 2024-10-02 | 8428 | 256M | 90天 | Metrics 存储 + OTLP 接收 |
| VictoriaLogs | v1.37.0 | 2024-10-18 | 9428 | 256M | 30天 | Logs 存储 + 查询 |
| Vector | v0.52.0-debian | 2024-12-16 | 8686 | 128M | - | 日志采集 |
| Grafana | 11.1.0 | 2024-06-21 | 3000 | 256M | - | 可视化仪表盘 |

**总资源占用**: ~400MB RAM, ~2.6GB 磁盘 (30天)

### 10.3 部署拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│                      Ditto Application                           │
├─────────────────────────────────────────────────────────────────┤
│  Loguru → logs/ditto.jsonl → Vector → VictoriaLogs             │
│  OTel Metrics → OTLP HTTP → VictoriaMetrics                     │
│  Traces → 通过 trace_id 关联日志（暂不独立存储）                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                        ┌──────────────┐
                        │   Grafana    │
                        │    :3000     │
                        └──────────────┘
```

### 10.4 快速开始

#### 前置要求
- Docker Desktop 已安装并运行
- Windows PowerShell 5.1+
- 端口 8428, 9428, 3000, 8686 未被占用

#### 启动服务

```powershell
# 从项目根目录
.\scripts\observability\start.ps1
```

#### 检查服务状态

```powershell
.\scripts\observability\health_check.ps1
```

#### 访问服务

| 服务 | URL | 用途 |
|------|-----|------|
| Grafana | http://localhost:3000 | 可视化仪表盘 |
| VictoriaMetrics | http://localhost:8428 | Metrics 查询 UI |
| VictoriaLogs | http://localhost:9428 | Logs 查询 UI |
| Vector | http://localhost:8686 | 日志采集状态 |

#### 停止服务

```powershell
.\scripts\observability\stop.ps1
```

### 10.5 关键配置

#### VictoriaMetrics
- OTLP HTTP 端点: `http://localhost:8428/otlp/v1/metrics`
- 数据保留: 90 天
- 内存限制: 256MB

#### VictoriaLogs
- HTTP 接收端点: `http://localhost:9428/insert/jsonline`
- 查询语言: LogsQL
- 数据保留: 30 天
- 内存限制: 256MB

#### Vector
- 日志源: `/logs/ditto*.jsonl` (JSON Lines 格式)
- 目标: VictoriaLogs HTTP 端点
- 内存限制: 128MB

#### Grafana
- 插件: victoriametrics-logs-datasource
- 数据源: VictoriaMetrics (Prometheus 兼容), VictoriaLogs
- 预配置仪表盘: Ditto Observability Overview
- 内存限制: 256MB

### 10.6 资源占用

| 组件 | 内存 | 磁盘（30天） |
|------|------|--------------|
| VictoriaMetrics | ~100MB | ~500MB |
| VictoriaLogs | ~100MB | ~2GB |
| Vector | ~50MB | - |
| Grafana | ~150MB | ~100MB |
| **总计** | **~400MB** | **~2.6GB** |

### 10.7 故障排查

#### Docker Desktop 未启动

```powershell
docker version
```

#### 端口占用

```powershell
netstat -an | findstr "8428 9428 3000 8686"
```

#### 服务日志

```powershell
# 查看所有服务日志
docker-compose -f deploy/observability/docker-compose.yml logs -f

# 查看特定服务日志
docker logs ditto-grafana
docker logs ditto-vector
```

### 10.8 维护操作

#### 更新服务版本

编辑 `deploy/observability/docker-compose.yml` 中的镜像版本，然后：

```powershell
docker-compose -f deploy/observability/docker-compose.yml pull
docker-compose -f deploy/observability/docker-compose.yml up -d
```

#### 清理数据（警告：删除所有数据）

```powershell
docker-compose -f deploy/observability/docker-compose.yml down -v
```

#### 备份数据

```powershell
# 备份 VictoriaMetrics 数据
docker cp ditto-vm:/vmdata ./backup/vmdata

# 备份 VictoriaLogs 数据
docker cp ditto-vl:/vldata ./backup/vldata

# 备份 Grafana 配置
docker cp ditto-grafana:/var/lib/grafana ./backup/grafana
```

### 10.9 生产环境注意事项

当前配置为本地开发环境，生产环境部署需要：

1. **启用认证**
   - Grafana: 配置用户名/密码或 OAuth
   - VictoriaMetrics: 配置基本认证或反向代理

2. **启用 TLS**
   - 使用反向代理 (Nginx/Traefik) 提供 HTTPS
   - 配置有效的 SSL 证书

3. **网络隔离**
   - 限制外部访问 VictoriaMetrics/VictoriaLogs
   - 仅通过 Grafana 访问数据

4. **数据备份**
   - 定期备份数据卷
   - 配置远程存储

5. **监控告警**
   - 配置服务健康检查
   - 设置磁盘空间告警

---

## 11. 测试方案

### 11.1 pytest 配置

```python
# tests/conftest.py
"""pytest 配置"""

import pytest
import os

os.environ["PYTEST_CURRENT_TEST"] = "true"


@pytest.fixture(autouse=True, scope="function")
def reset_observability():
    """每个测试自动重置"""
    from ditto.observability import reset_for_testing
    reset_for_testing()
    yield
    reset_for_testing()


@pytest.fixture
def obs_noop():
    """NoOp 模式 - 静默，最快"""
    from ditto.observability import init, Mode
    init(mode=Mode.TESTING)
    yield


@pytest.fixture
def obs_assertions():
    """断言模式 - 记录到内存"""
    from ditto.observability import init, Mode
    init(mode=Mode.TESTING_WITH_ASSERTIONS)
    yield
```

### 11.2 测试示例

```python
# tests/test_observability.py
import pytest
from ditto.observability import (
    span, traced, logger, M,
    get_recorded_spans, get_recorded_metrics,
)


class TestSpan:
    """Span 测试"""

    def test_span_created(self, obs_assertions):
        """验证 span 正确创建"""
        with span("test_operation", key="value"):
            pass

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_operation"
        assert spans[0].attributes["key"] == "value"

    def test_nested_spans(self, obs_assertions):
        """验证嵌套 span"""
        with span("parent"):
            with span("child"):
                pass

        spans = get_recorded_spans()
        assert len(spans) == 2

        child, parent = spans
        assert child.name == "child"
        assert parent.name == "parent"

    def test_span_records_exception(self, obs_assertions):
        """验证异常记录"""
        with pytest.raises(ValueError):
            with span("failing_op"):
                raise ValueError("test error")

        spans = get_recorded_spans()
        from opentelemetry import trace
        assert spans[0].status.status_code == trace.StatusCode.ERROR


class TestMetrics:
    """Metrics 测试"""

    def test_counter_incremented(self, obs_assertions):
        """验证 counter 递增"""
        M.data_records.add(100, {"source": "test", "table": "test", "status": "success"})

        metrics = get_recorded_metrics()
        assert "ditto.data.records_total" in metrics


class TestTraced:
    """@traced 装饰器测试"""

    def test_traced_decorator(self, obs_assertions):
        """验证装饰器创建 span"""

        @traced("my_operation")
        def my_func():
            return 42

        result = my_func()
        assert result == 42

        spans = get_recorded_spans()
        assert len(spans) == 1
        assert spans[0].name == "my_operation"
```

---

## 12. 运维手册

### 12.1 常用命令

```bash
# 启动可观测性服务
cd deploy/observability
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f victorialogs

# 停止服务
docker-compose down

# 清理数据（谨慎！）
docker-compose down -v
```

### 12.2 VictoriaLogs 查询

```sql
-- 查询某次操作的完整链路
{service="ditto"} trace_id="a1b2c3d4"

-- 查询错误日志
{service="ditto", level="ERROR"}

-- 按事件类型查询
{service="ditto"} event="kill_switch_triggered"

-- 时间范围查询
{service="ditto", level="ERROR"} _time:1h

-- 统计每分钟错误数
{service="ditto", level="ERROR"} | stats count() by (_time:1m)

-- 查询慢操作
{service="ditto"} duration_ms:>1000
```

### 12.3 VictoriaMetrics 查询

```promql
# 当前 Kill Switch 级别
ditto_risk_kill_switch_level{strategy="etf_rotation"}

# 当前回撤
ditto_portfolio_drawdown_ratio{strategy="etf_rotation"}

# 数据更新 P95 耗时
histogram_quantile(0.95,
  sum(rate(ditto_data_update_duration_seconds_bucket[1h])) by (le, source)
)

# 最近 1 小时错误数
sum(increase(ditto_data_errors_total[1h])) by (source, error_type)

# Kill Switch 触发次数趋势
sum(increase(ditto_risk_kill_switch_total[1d])) by (level)
```

### 12.4 健康检查

```bash
# VictoriaMetrics 健康检查
curl http://localhost:8428/health

# VictoriaLogs 健康检查
curl http://localhost:9428/health

# Grafana 健康检查
curl http://localhost:3000/api/health

# Ditto 应用健康检查
curl http://localhost:8000/healthz
```

### 12.5 日志保留策略

| 日志类型 | 保留期 | 存储位置 |
|----------|--------|----------|
| 运行日志（文件） | 30 天 | `logs/ditto_*.jsonl.gz` |
| 错误日志（文件） | 90 天 | `logs/error_*.log.gz` |
| VictoriaLogs | 30 天 | Docker volume |
| VictoriaMetrics | 90 天 | Docker volume |
| 审计日志 | 永久 | SQLite |

### 12.6 故障排查流程

```
1. 查看告警信息
   └─► Grafana Dashboard / Telegram 通知

2. 确定 trace_id
   └─► 从告警或日志中获取

3. 查询完整链路
   └─► VictoriaLogs: {service="ditto"} trace_id="xxx"

4. 分析指标
   └─► Grafana: 查看相关指标趋势

5. 定位根因
   └─► 结合日志 + 指标确定问题

6. 修复 & 验证
   └─► 修复后观察指标恢复
```

---

## 附录 A：快速开始

```bash
# 1. 安装依赖
pip install opentelemetry-api opentelemetry-sdk \
            opentelemetry-exporter-otlp-proto-http loguru

# 2. 启动后端服务
cd deploy/observability
docker-compose up -d

# 3. 在代码中初始化
from ditto.observability import init, logger, span, M

init(service_name="ditto", environment="dev")

# 4. 开始使用
logger.info("Hello Ditto!", event="startup")

with span("my_operation"):
    logger.info("Processing...")
    M.data_records.add(100, {"source": "test", "table": "test", "status": "success"})

# 5. 查看结果
# Grafana: http://localhost:3000
# VictoriaMetrics: http://localhost:8428
# VictoriaLogs: http://localhost:9428
```

---
