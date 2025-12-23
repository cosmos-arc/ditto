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
| `ditto.system.scheduler_jobs_total` | Counter | `job`, `status` | 调度任务执行数 |
| `ditto.system.scheduler_job_duration_seconds` | Histogram | `job` | 任务耗时 |
| `ditto.system.api_requests_total` | Counter | `endpoint`, `method`, `status` | API 请求数 |
| `ditto.system.api_duration_seconds` | Histogram | `endpoint`, `method` | API 耗时 |
| `ditto.system.db_query_duration_seconds` | Histogram | `db`, `operation` | 数据库查询耗时 |
| `ditto.system.heartbeat_timestamp` | Gauge | - | 最近心跳时间戳 |

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
packages/foundation/scr/ditto_foundation/
├── observability/
│   ├── __init__.py          # 统一导出
│   ├── config.py             # 配置
│   ├── logging.py            # Loguru 配置
│   ├── tracing.py            # OTel Tracing
│   ├── metrics.py            # OTel Metrics
│   └── testing.py            # 测试辅助
```

### 9.2 完整实现

```python
# packages/foundation/scr/ditto_foundation/observability/__init__.py
"""
Ditto 可观测性模块

使用方法：
    from ditto.observability import init, logger, span, traced, M

    # 初始化
    init()

    # 日志
    logger.info("Starting backtest", strategy="etf_rotation")

    # 追踪
    @traced("my_function")
    def my_function():
        with span("sub_operation", key="value"):
            ...

    # 指标
    M.backtest_total.add(1, {"strategy": "etf_rotation", "status": "success"})
"""

from .config import ObservabilityConfig, Mode
from .logging import configure_logging
from .tracing import (
    configure_tracing,
    span,
    traced,
    get_trace_id,
    get_tracer,
)
from .metrics import configure_metrics, get_meter, M
from .testing import (
    reset_for_testing,
    get_recorded_spans,
    clear_recorded_spans,
    get_recorded_metrics,
)

from loguru import logger

__all__ = [
    # 初始化
    "init",
    "shutdown",
    "ObservabilityConfig",
    "Mode",
    # Logging
    "logger",
    # Tracing
    "span",
    "traced",
    "get_trace_id",
    "get_tracer",
    # Metrics
    "get_meter",
    "M",
    # Testing
    "reset_for_testing",
    "get_recorded_spans",
    "clear_recorded_spans",
    "get_recorded_metrics",
]

_initialized = False


def init(
    service_name: str = "ditto",
    environment: str = "dev",
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics",
    mode: Mode | None = None,
) -> None:
    """一键初始化所有可观测性组件"""
    global _initialized

    if _initialized:
        return

    config = ObservabilityConfig(
        service_name=service_name,
        environment=environment,
        vm_otlp_endpoint=vm_endpoint,
    )

    actual_mode = mode or config.detect_mode()

    if actual_mode in (Mode.TESTING, Mode.TESTING_WITH_ASSERTIONS):
        configure_logging(config, silent=True)
    else:
        configure_logging(config)

    configure_tracing(config, actual_mode)
    configure_metrics(config, actual_mode)

    if actual_mode not in (Mode.TESTING, Mode.TESTING_WITH_ASSERTIONS):
        logger.info(
            f"Observability initialized: {service_name} ({actual_mode.value})",
            event="observability_init",
            service=service_name,
            environment=environment,
            mode=actual_mode.value,
        )

    _initialized = True


def shutdown() -> None:
    """优雅关闭"""
    from opentelemetry import trace, metrics

    for provider in [trace.get_tracer_provider(), metrics.get_meter_provider()]:
        if hasattr(provider, "shutdown"):
            provider.shutdown()
```

```python
# packages/foundation/scr/ditto_foundation/observability/config.py
"""可观测性配置"""

from __future__ import annotations

import os
from enum import Enum
from dataclasses import dataclass, field


class Mode(Enum):
    """运行模式"""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TESTING = "testing"
    TESTING_WITH_ASSERTIONS = "testing_assertions"


@dataclass
class ObservabilityConfig:
    """可观测性配置"""

    service_name: str = "ditto"
    environment: str = "dev"
    log_dir: str = "logs"
    log_level: str = "INFO"

    # VictoriaMetrics OTLP 端点
    vm_otlp_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics"
    metrics_export_interval_ms: int = 15_000

    # 功能开关
    tracing_enabled: bool = True
    metrics_enabled: bool = True

    def detect_mode(self) -> Mode:
        """自动检测运行模式"""
        # pytest 环境
        if "PYTEST_CURRENT_TEST" in os.environ:
            return Mode.TESTING

        # 显式指定
        mode = os.environ.get("DITTO_OBSERVABILITY_MODE", "").lower()
        if mode == "testing":
            return Mode.TESTING
        if mode == "testing_assertions":
            return Mode.TESTING_WITH_ASSERTIONS

        # 根据环境判断
        if self.environment == "production":
            return Mode.PRODUCTION
        return Mode.DEVELOPMENT
```

```python
# packages/foundation/scr/ditto_foundation/observability/logging.py
"""Loguru 日志配置"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from .config import ObservabilityConfig


def _json_formatter(record: dict) -> str:
    """JSON 格式化器 - VictoriaLogs 友好"""
    r = record
    log = {
        "_time": r["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": r["level"].name,
        "_msg": r["message"],
        "service": r["extra"].get("service", "ditto"),
        "file": f"{r['file'].name}:{r['line']}",
    }

    # 合并上下文字段（过滤 None 值）
    for k, v in r["extra"].items():
        if v is not None and k != "service":
            log[k] = v

    # 异常信息
    if r["exception"]:
        log["error"] = str(r["exception"].value)
        log["error_type"] = (
            r["exception"].type.__name__ if r["exception"].type else None
        )

    return json.dumps(log, ensure_ascii=False, default=str)


def _json_sink(message) -> None:
    """JSON sink"""
    print(_json_formatter(message.record), file=sys.stderr)


def configure_logging(config: ObservabilityConfig, silent: bool = False) -> None:
    """配置 Loguru"""
    logger.remove()

    if silent:
        # 测试模式：静默（可保留 WARNING 以上）
        # logger.add(sys.stderr, level="WARNING")
        return

    # 开发环境：彩色控制台
    if config.environment != "production":
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[trace_id]:-<8}</cyan> | "
                "<cyan>{file}:{line}</cyan> | "
                "<level>{message}</level>"
            ),
            level="DEBUG",
            colorize=True,
        )
    else:
        # 生产环境：JSON 格式
        logger.add(_json_sink, level=config.log_level)

    # 文件输出（JSON 格式，供 Vector 采集）
    log_path = Path(config.log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 主日志文件
    logger.add(
        log_path / "ditto_{time:YYYY-MM-DD}.jsonl",
        format="{message}",
        serialize=True,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        level="INFO",
    )

    # 错误日志单独文件
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="gz",
    )

    # 默认上下文
    logger.configure(
        extra={
            "service": config.service_name,
            "trace_id": None,
            "span": None,
        }
    )
```

```python
# packages/foundation/scr/ditto_foundation/observability/tracing.py
"""OTel Tracing - 轻量实现，通过 trace_id 关联日志"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable, TypeVar, Generator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from loguru import logger

if TYPE_CHECKING:
    from .config import ObservabilityConfig, Mode

F = TypeVar("F", bound=Callable)

_tracer: trace.Tracer | None = None
_in_memory_exporter: InMemorySpanExporter | None = None


def configure_tracing(config: "ObservabilityConfig", mode: "Mode") -> trace.Tracer:
    """配置 OTel Tracing"""
    global _tracer, _in_memory_exporter

    from .config import Mode

    resource = Resource.create({SERVICE_NAME: config.service_name})

    if mode == Mode.TESTING:
        # NoOp：不设置 provider
        _tracer = trace.get_tracer(config.service_name)
        return _tracer

    if mode == Mode.TESTING_WITH_ASSERTIONS:
        # InMemory：可断言
        _in_memory_exporter = InMemorySpanExporter()
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(config.service_name)
        return _tracer

    # 正常模式：暂不导出 traces，只用于生成 trace_id
    # 未来加 VictoriaTraces 时添加 OTLP exporter
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(config.service_name)

    return _tracer


def get_tracer() -> trace.Tracer:
    """获取 OTel Tracer"""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("ditto")
    return _tracer


def get_trace_id() -> str | None:
    """获取当前 trace_id（8 位）"""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")[:8]
    return None


def get_span_id() -> str | None:
    """获取当前 span_id（8 位）"""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.span_id, "016x")[:8]
    return None


@contextmanager
def span(name: str, **attributes) -> Generator[trace.Span, None, None]:
    """
    创建 OTel Span，同时自动注入日志上下文。

    用法：
        with span("load_data", source="tushare") as s:
            logger.info("Loading...")  # 自动带 trace_id
            s.set_attribute("rows", 10000)
    """
    tracer = get_tracer()

    with tracer.start_as_current_span(name) as s:
        # 设置属性
        for k, v in attributes.items():
            s.set_attribute(k, v)

        # 注入日志上下文
        trace_id = get_trace_id()

        with logger.contextualize(trace_id=trace_id, span=name):
            logger.debug(f"▶ {name}")
            try:
                yield s
                s.set_status(trace.StatusCode.OK)
                logger.debug(f"◀ {name}")
            except Exception as e:
                s.set_status(trace.StatusCode.ERROR, str(e))
                s.record_exception(e)
                logger.error(f"✖ {name}: {e}")
                raise


def traced(name: str | None = None, **default_attrs):
    """
    Trace 装饰器。

    用法：
        @traced("run_backtest")
        def run_backtest(strategy: str):
            ...
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            with span(span_name, **default_attrs):
                return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
```

```python
# packages/foundation/scr/ditto_foundation/observability/metrics.py
"""OTel Metrics - OTLP 直推 VictoriaMetrics"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
    InMemoryMetricReader,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from loguru import logger

if TYPE_CHECKING:
    from .config import ObservabilityConfig, Mode

_meter: metrics.Meter | None = None
_in_memory_reader: InMemoryMetricReader | None = None


def configure_metrics(config: "ObservabilityConfig", mode: "Mode") -> metrics.Meter:
    """配置 OTel Metrics"""
    global _meter, _in_memory_reader

    from .config import Mode

    resource = Resource.create({SERVICE_NAME: config.service_name})

    if mode == Mode.TESTING:
        # NoOp：不设置 provider
        _meter = metrics.get_meter(config.service_name)
        return _meter

    if mode == Mode.TESTING_WITH_ASSERTIONS:
        # InMemory：可断言
        _in_memory_reader = InMemoryMetricReader()
        provider = MeterProvider(resource=resource, metric_readers=[_in_memory_reader])
        metrics.set_meter_provider(provider)
        _meter = metrics.get_meter(config.service_name)
        M.setup()
        return _meter

    # 正常模式：OTLP 推送到 VictoriaMetrics
    exporter = OTLPMetricExporter(endpoint=config.vm_otlp_endpoint)
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=config.metrics_export_interval_ms,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    _meter = metrics.get_meter(config.service_name)
    M.setup()

    logger.info(f"Metrics → {config.vm_otlp_endpoint}")

    return _meter


def get_meter() -> metrics.Meter:
    """获取 OTel Meter"""
    global _meter
    if _meter is None:
        _meter = metrics.get_meter("ditto")
    return _meter


class M:
    """Ditto 业务指标（延迟初始化）"""

    _initialized: bool = False

    # === 数据指标 ===
    data_update_duration: metrics.Histogram
    data_records: metrics.Counter
    data_freshness: metrics.Gauge
    data_quality: metrics.Gauge
    data_errors: metrics.Counter

    # === 因子指标 ===
    factor_calc_duration: metrics.Histogram
    factor_ic: metrics.Gauge
    factor_health: metrics.Gauge

    # === 策略指标 ===
    signal_total: metrics.Counter
    rebalance_total: metrics.Counter

    # === 组合指标 ===
    portfolio_value: metrics.Gauge
    portfolio_return: metrics.Gauge
    portfolio_drawdown: metrics.Gauge
    portfolio_drawdown_3d: metrics.Gauge
    portfolio_position_ratio: metrics.Gauge
    portfolio_position_count: metrics.Gauge

    # === 风控指标 ===
    kill_switch_level: metrics.Gauge
    kill_switch_total: metrics.Counter
    alerts_total: metrics.Counter

    # === 系统指标 ===
    scheduler_jobs: metrics.Counter
    scheduler_duration: metrics.Histogram
    api_requests: metrics.Counter
    api_duration: metrics.Histogram
    db_query_duration: metrics.Histogram
    heartbeat_timestamp: metrics.Gauge

    @classmethod
    def setup(cls) -> None:
        """初始化所有指标"""
        if cls._initialized:
            return

        m = get_meter()

        # === 数据指标 ===
        cls.data_update_duration = m.create_histogram(
            name="ditto.data.update_duration_seconds",
            description="Data update duration in seconds",
            unit="s",
        )
        cls.data_records = m.create_counter(
            name="ditto.data.records_total",
            description="Total data records processed",
            unit="1",
        )
        cls.data_freshness = m.create_gauge(
            name="ditto.data.freshness_seconds",
            description="Seconds since last data update",
            unit="s",
        )
        cls.data_quality = m.create_gauge(
            name="ditto.data.quality_ratio",
            description="Data completeness ratio",
            unit="1",
        )
        cls.data_errors = m.create_counter(
            name="ditto.data.errors_total",
            description="Total data errors",
            unit="1",
        )

        # === 因子指标 ===
        cls.factor_calc_duration = m.create_histogram(
            name="ditto.factor.calc_duration_seconds",
            description="Factor calculation duration",
            unit="s",
        )
        cls.factor_ic = m.create_gauge(
            name="ditto.factor.ic_value",
            description="Factor IC value",
            unit="1",
        )
        cls.factor_health = m.create_gauge(
            name="ditto.factor.health_status",
            description="Factor health status (0=healthy, 1=warning, 2=critical)",
            unit="1",
        )

        # === 策略指标 ===
        cls.signal_total = m.create_counter(
            name="ditto.strategy.signal_total",
            description="Total signals generated",
            unit="1",
        )
        cls.rebalance_total = m.create_counter(
            name="ditto.strategy.rebalance_total",
            description="Total rebalances executed",
            unit="1",
        )

        # === 组合指标 ===
        cls.portfolio_value = m.create_gauge(
            name="ditto.portfolio.value_yuan",
            description="Portfolio value in CNY",
            unit="CNY",
        )
        cls.portfolio_return = m.create_gauge(
            name="ditto.portfolio.return_ratio",
            description="Portfolio return ratio",
            unit="1",
        )
        cls.portfolio_drawdown = m.create_gauge(
            name="ditto.portfolio.drawdown_ratio",
            description="Current drawdown ratio",
            unit="1",
        )
        cls.portfolio_drawdown_3d = m.create_gauge(
            name="ditto.portfolio.drawdown_3d_ratio",
            description="3-day drawdown ratio",
            unit="1",
        )
        cls.portfolio_position_ratio = m.create_gauge(
            name="ditto.portfolio.position_ratio",
            description="Position ratio",
            unit="1",
        )
        cls.portfolio_position_count = m.create_gauge(
            name="ditto.portfolio.position_count",
            description="Number of positions",
            unit="1",
        )

        # === 风控指标 ===
        cls.kill_switch_level = m.create_gauge(
            name="ditto.risk.kill_switch_level",
            description="Current Kill Switch level",
            unit="1",
        )
        cls.kill_switch_total = m.create_counter(
            name="ditto.risk.kill_switch_total",
            description="Total Kill Switch triggers",
            unit="1",
        )
        cls.alerts_total = m.create_counter(
            name="ditto.risk.alerts_total",
            description="Total alerts triggered",
            unit="1",
        )

        # === 系统指标 ===
        cls.scheduler_jobs = m.create_counter(
            name="ditto.system.scheduler_jobs_total",
            description="Total scheduler jobs",
            unit="1",
        )
        cls.scheduler_duration = m.create_histogram(
            name="ditto.system.scheduler_job_duration_seconds",
            description="Scheduler job duration",
            unit="s",
        )
        cls.api_requests = m.create_counter(
            name="ditto.system.api_requests_total",
            description="Total API requests",
            unit="1",
        )
        cls.api_duration = m.create_histogram(
            name="ditto.system.api_duration_seconds",
            description="API request duration",
            unit="s",
        )
        cls.db_query_duration = m.create_histogram(
            name="ditto.system.db_query_duration_seconds",
            description="Database query duration",
            unit="s",
        )
        cls.heartbeat_timestamp = m.create_gauge(
            name="ditto.system.heartbeat_timestamp",
            description="Last heartbeat timestamp",
            unit="s",
        )

        cls._initialized = True
```

```python
# packages/foundation/scr/ditto_foundation/observability/testing.py
"""测试辅助工具"""

from __future__ import annotations

from opentelemetry import trace, metrics


def reset_for_testing() -> None:
    """重置所有可观测性状态（测试 fixture 用）"""
    from . import tracing, metrics as metrics_module

    # 清除 spans
    if tracing._in_memory_exporter:
        tracing._in_memory_exporter.clear()

    # 重置全局状态
    trace._TRACER_PROVIDER = None
    metrics._METER_PROVIDER = None

    tracing._tracer = None
    tracing._in_memory_exporter = None
    metrics_module._meter = None
    metrics_module._in_memory_reader = None
    metrics_module.M._initialized = False


def get_recorded_spans() -> list:
    """获取记录的 spans（测试用）"""
    from . import tracing

    if tracing._in_memory_exporter:
        return list(tracing._in_memory_exporter.get_finished_spans())
    return []


def clear_recorded_spans() -> None:
    """清除记录的 spans"""
    from . import tracing

    if tracing._in_memory_exporter:
        tracing._in_memory_exporter.clear()


def get_recorded_metrics() -> dict:
    """获取记录的 metrics（测试用）"""
    from . import metrics as metrics_module

    if metrics_module._in_memory_reader:
        data = metrics_module._in_memory_reader.get_metrics_data()
        result = {}
        for resource_metric in data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    result[metric.name] = metric
        return result
    return {}
```

---

## 10. 部署方案

### 10.1 目录结构

```
deploy/
└── observability/
    ├── docker-compose.yml
    ├── vector.toml
    └── grafana/
        ├── datasources.yml
        └── dashboards/
            ├── overview.json
            └── risk.json
```

### 10.2 Docker Compose

```yaml
# deploy/observability/docker-compose.yml
version: '3.8'

services:
  # VictoriaMetrics - Metrics 存储
  victoriametrics:
    image: victoriametrics/victoria-metrics:v1.96.0
    container_name: ditto-vm
    ports:
      - "8428:8428"
    command:
      - "-storageDataPath=/data"
      - "-retentionPeriod=90d"
      - "-selfScrapeInterval=10s"
    volumes:
      - vm-data:/data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M  # 锁死内存上限

  # VictoriaLogs - Logs 存储
  victorialogs:
    image: victoriametrics/victoria-logs:v1.0.0-victorialogs
    container_name: ditto-vl
    ports:
      - "9428:9428"
    command:
      - "-storageDataPath=/data"
      - "-retentionPeriod=30d"
    volumes:
      - vl-data:/data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M  # 锁死内存上限

  # Vector - 日志采集
  vector:
    image: timberio/vector:0.34.0-debian
    container_name: ditto-vector
    volumes:
      - ./vector.toml:/etc/vector/vector.toml:ro
      - ../../logs:/logs:ro
    depends_on:
      - victorialogs
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 128M  # 锁死内存上限

  # Grafana - 可视化
  grafana:
    image: grafana/grafana:10.2.2
    container_name: ditto-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_INSTALL_PLUGINS=victoriametrics-datasource,victorialogs-datasource
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml:ro
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    depends_on:
      - victoriametrics
      - victorialogs
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M  # 锁死内存上限

volumes:
  vm-data:
  vl-data:
  grafana-data:
```

### 10.3 Vector 配置

```toml
# deploy/observability/vector.toml

# ============ Sources ============

[sources.ditto_logs]
type = "file"
include = ["/logs/ditto_*.jsonl"]
read_from = "end"

# ============ Transforms ============

[transforms.parse_json]
type = "remap"
inputs = ["ditto_logs"]
source = '''
. = parse_json!(.message)
'''

# ============ Sinks ============

[sinks.victorialogs]
type = "http"
inputs = ["parse_json"]
uri = "http://victorialogs:9428/insert/jsonline?_stream_fields=service,level,event"
encoding.codec = "json"
framing.method = "newline_delimited"
request.headers.Content-Type = "application/stream+json"
```

### 10.4 Grafana 数据源配置

```yaml
# deploy/observability/grafana/datasources.yml
apiVersion: 1

datasources:
  - name: VictoriaMetrics
    type: prometheus
    access: proxy
    url: http://victoriametrics:8428
    isDefault: true
    editable: false

  - name: VictoriaLogs
    type: victorialogs-datasource
    access: proxy
    url: http://victorialogs:9428
    editable: false
```

### 10.5 资源占用

| 组件 | 内存 | 磁盘（30天） |
|------|------|--------------|
| VictoriaMetrics | ~100MB | ~500MB |
| VictoriaLogs | ~100MB | ~2GB |
| Vector | ~50MB | - |
| Grafana | ~150MB | ~100MB |
| **总计** | **~400MB** | **~2.6GB** |

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
