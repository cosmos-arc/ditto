---
paths: **/*.py
---

# Ditto 可观测性编码规范

> 本规范指导如何在 Ditto 项目中正确添加日志、追踪和指标埋点。

---

## 核心原则

1. **使用 OTel API** — 指标和追踪使用 OpenTelemetry 标准接口
2. **Loguru 处理日志** — 通过 `trace_id` 关联追踪上下文
3. **业务语义清晰** — 命名体现业务含义，非技术实现
4. **测试友好** — 单测不依赖外部服务，使用 NoOp/InMemory 模式

---

## 导入规范

```python
# ✅ 正确：统一从 observability 模块导入
from ditto.observability import init, logger, span, traced, M

# ❌ 错误：直接导入底层库
from loguru import logger
from opentelemetry import trace
```

---

## 日志规范

### 日志级别

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| `DEBUG` | 开发调试、span 开始/结束 | 函数入参、中间状态 |
| `INFO` | 正常业务流程 | 任务开始/完成、数据更新成功 |
| `WARNING` | 异常但可恢复 | 数据源降级、Kill Switch L1 |
| `ERROR` | 错误但系统可继续 | 单个标的获取失败 |
| `CRITICAL` | 需人工介入 | Kill Switch L2/L3、数据库损坏 |

### 必选字段

每条业务日志必须包含 `event` 字段：

```python
# ✅ 正确
logger.info("Daily data update completed", event="data_update_complete", records=1250)

# ❌ 错误：缺少 event
logger.info("Daily data update completed", records=1250)
```

### event 命名规范

格式：`{domain}_{action}`，使用 `snake_case`

| 领域 | event 示例 |
|------|------------|
| 数据 | `data_update_start`, `data_update_complete`, `data_update_failed` |
| 因子 | `factor_calc_start`, `factor_calc_complete`, `factor_health_warning` |
| 策略 | `signal_generated`, `rebalance_plan_created`, `rebalance_executed` |
| 风控 | `kill_switch_triggered`, `kill_switch_deactivated`, `drawdown_warning` |
| 系统 | `scheduler_job_start`, `scheduler_job_complete`, `api_request` |

### 常用字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `event` | str | 事件类型（必选） |
| `duration_ms` | float | 操作耗时（毫秒） |
| `strategy` | str | 策略名称 |
| `trade_date` | str | 交易日期 |
| `symbol` | str | 标的代码 |
| `source` | str | 数据源 |
| `error` | str | 错误信息 |
| `error_type` | str | 错误类型 |

### 日志示例

```python
# INFO - 正常流程
logger.info(
    "Daily data update completed",
    event="data_update_complete",
    trade_date="2024-12-23",
    source="tushare",
    duration_ms=45000,
    records_inserted=1250,
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

### 敏感信息

```python
# ❌ 禁止
logger.info("API call", api_key="sk-1234567890abcdef")
logger.info("Login", password="my_password")

# ✅ 正确：脱敏
logger.info("API call", api_key="sk-12****ef")
logger.info("Login", user="admin")
```

**禁止记录：** 完整 API Key、密码、券商账号、身份证、手机号

---

## Trace 规范

### 使用方式

```python
# 方式 1：装饰器（推荐用于函数入口）
@traced("backtest.run")
def run_backtest(strategy: str) -> dict:
    ...

# 方式 2：上下文管理器（推荐用于代码块）
with span("data.fetch", source="tushare") as s:
    df = fetch_data()
    s.set_attribute("rows", len(df))
```

### Span 命名规范

格式：`{domain}.{operation}` 或 `{operation}`

| 领域 | Span 名称 |
|------|-----------|
| 数据 | `data.update`, `data.fetch`, `data.validate`, `data.store` |
| 因子 | `factor.calculate`, `factor.{name}` |
| 策略 | `strategy.generate_signal`, `strategy.create_plan`, `strategy.execute` |
| 回测 | `backtest.run`, `backtest.load_data`, `backtest.simulate` |
| 调度 | `scheduler.{job_name}` |
| API | `api.{endpoint}` |

### Span 属性

```python
with span("data.fetch", source="tushare") as s:
    df = fetch_data()
    # 动态添加属性
    s.set_attribute("rows", len(df))
    s.set_attribute("symbols", df["symbol"].nunique())
```

常用属性：`strategy`, `trade_date`, `symbol`, `source`, `rows`, `duration_ms`

### 嵌套 Span

```python
@traced("backtest.run")
def run_backtest(strategy: str) -> dict:
    logger.info(f"Starting backtest: {strategy}")

    with span("backtest.load_data", source="duckdb") as s:
        df = load_data()
        s.set_attribute("rows", len(df))
        logger.info("Data loaded", rows=len(df))

    with span("backtest.simulate"):
        with span("backtest.calculate_signals"):
            signals = calc_signals(df)

        with span("backtest.execute_trades"):
            result = execute(signals)

    return result
```

---

## Metrics 规范

### 命名规范

格式：`ditto.{domain}.{metric_name}`

- 使用 `snake_case`
- Counter 以 `_total` 结尾
- 时间类以 `_seconds` 结尾
- 比例类以 `_ratio` 结尾

### Label 规范

| Label | 说明 | 值示例 |
|-------|------|--------|
| `strategy` | 策略名 | `etf_rotation` |
| `source` | 数据源 | `tushare`, `akshare` |
| `table` | 数据表 | `etf_daily` |
| `status` | 状态 | `success`, `failed` |
| `level` | 级别 | `1`, `2`, `3` |

**注意：** 每个 label 值不超过 20 个，避免高基数（不用 `symbol`, `order_id` 作为 label）

### 使用预定义指标

```python
from ditto.observability import M

# Counter - 计数
M.data_records.add(100, {"source": "tushare", "table": "etf_daily", "status": "success"})
M.kill_switch_total.add(1, {"strategy": "etf_rotation", "level": "2"})

# Gauge - 当前值
M.portfolio_drawdown.set(0.15, {"strategy": "etf_rotation"})
M.kill_switch_level.set(2, {"strategy": "etf_rotation"})
M.data_freshness.set(0, {"source": "tushare", "table": "etf_daily"})

# Histogram - 耗时分布
M.data_update_duration.record(45.5, {"source": "tushare", "table": "etf_daily"})
```

### 可用指标清单

| 指标 | 类型 | Labels |
|------|------|--------|
| `M.data_update_duration` | Histogram | `source`, `table` |
| `M.data_records` | Counter | `source`, `table`, `status` |
| `M.data_freshness` | Gauge | `source`, `table` |
| `M.data_errors` | Counter | `source`, `error_type` |
| `M.factor_calc_duration` | Histogram | `factor` |
| `M.factor_ic` | Gauge | `factor`, `period` |
| `M.factor_health` | Gauge | `factor` |
| `M.signal_total` | Counter | `strategy`, `direction` |
| `M.rebalance_total` | Counter | `strategy`, `status` |
| `M.portfolio_value` | Gauge | `strategy` |
| `M.portfolio_drawdown` | Gauge | `strategy` |
| `M.portfolio_drawdown_3d` | Gauge | `strategy` |
| `M.kill_switch_level` | Gauge | `strategy` |
| `M.kill_switch_total` | Counter | `strategy`, `level` |
| `M.scheduler_jobs` | Counter | `job`, `status` |
| `M.api_requests` | Counter | `endpoint`, `method`, `status` |

---

## 埋点模式

### 标准函数埋点

```python
@traced("data.update")
def update_daily_data(trade_date: str) -> int:
    """更新每日数据"""
    logger.info("Starting daily data update", event="data_update_start", trade_date=trade_date)

    start_time = time.time()
    total_records = 0

    try:
        with span("data.fetch", source="tushare") as s:
            df = fetch_from_tushare(trade_date)
            s.set_attribute("rows", len(df))
            total_records = len(df)

            M.data_records.add(len(df), {
                "source": "tushare",
                "table": "etf_daily",
                "status": "success",
            })

        with span("data.store"):
            store_to_db(df)

        duration_ms = (time.time() - start_time) * 1000
        M.data_update_duration.record(duration_ms / 1000, {
            "source": "tushare",
            "table": "etf_daily",
        })
        M.data_freshness.set(0, {"source": "tushare", "table": "etf_daily"})

        logger.info(
            "Daily data update completed",
            event="data_update_complete",
            trade_date=trade_date,
            duration_ms=duration_ms,
            records=total_records,
        )

        return total_records

    except Exception as e:
        M.data_errors.add(1, {"source": "tushare", "error_type": type(e).__name__})
        logger.error(
            "Daily data update failed",
            event="data_update_failed",
            trade_date=trade_date,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
```

### 风控埋点

```python
def check_kill_switch(drawdown: float, drawdown_3d: float) -> int:
    """检查 Kill Switch"""
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

    # 更新指标
    M.kill_switch_level.set(level, {"strategy": "etf_rotation"})
    if level > 0:
        M.kill_switch_total.add(1, {"strategy": "etf_rotation", "level": str(level)})

    return level
```

### API 埋点

```python
@router.get("/api/v1/portfolio")
async def get_portfolio():
    """获取组合信息"""
    with span("api.portfolio") as s:
        start = time.time()

        try:
            result = await portfolio_service.get_current()

            M.api_requests.add(1, {
                "endpoint": "/api/v1/portfolio",
                "method": "GET",
                "status": "success",
            })

            duration = time.time() - start
            M.api_duration.record(duration, {
                "endpoint": "/api/v1/portfolio",
                "method": "GET",
            })

            return result

        except Exception as e:
            M.api_requests.add(1, {
                "endpoint": "/api/v1/portfolio",
                "method": "GET",
                "status": "error",
            })
            logger.error("API error", event="api_error", endpoint="/api/v1/portfolio", error=str(e))
            raise
```

---

## 测试中的可观测性

### 单测 fixture

```python
import pytest
from ditto.observability import init, Mode, reset_for_testing

@pytest.fixture(autouse=True)
def reset_obs():
    reset_for_testing()
    yield
    reset_for_testing()

@pytest.fixture
def obs_noop():
    """静默模式 - 最快"""
    init(mode=Mode.TESTING)
    yield

@pytest.fixture
def obs_assertions():
    """断言模式 - 可验证"""
    init(mode=Mode.TESTING_WITH_ASSERTIONS)
    yield
```

### 断言 Span

```python
from ditto.observability import span, get_recorded_spans

def test_span_created(obs_assertions):
    with span("test_op", key="value"):
        pass

    spans = get_recorded_spans()
    assert len(spans) == 1
    assert spans[0].name == "test_op"
    assert spans[0].attributes["key"] == "value"
```

### 断言 Metrics

```python
from ditto.observability import M, get_recorded_metrics

def test_counter(obs_assertions):
    M.data_records.add(100, {"source": "test", "table": "test", "status": "success"})

    metrics = get_recorded_metrics()
    assert "ditto.data.records_total" in metrics
```

---

## 常见错误

### ❌ 缺少 event 字段

```python
# 错误
logger.info("Data updated", records=100)

# 正确
logger.info("Data updated", event="data_update_complete", records=100)
```

### ❌ 日志级别错误

```python
# 错误：Kill Switch L2 应该是 CRITICAL
logger.warning("Kill Switch L2 triggered", ...)

# 正确
logger.critical("Kill Switch L2 triggered", ...)
```

### ❌ 高基数 Label

```python
# 错误：symbol 是高基数字段
M.data_records.add(1, {"symbol": "510300.SH"})

# 正确：使用低基数 label
M.data_records.add(1, {"source": "tushare", "table": "etf_daily"})
```

### ❌ 直接导入 loguru

```python
# 错误
from loguru import logger

# 正确
from ditto.observability import logger
```

### ❌ span 不设置属性

```python
# 错误：span 没有业务上下文
with span("data.fetch"):
    df = fetch()

# 正确：添加有意义的属性
with span("data.fetch", source="tushare") as s:
    df = fetch()
    s.set_attribute("rows", len(df))
```

### ❌ 异常时不记录错误

```python
# 错误：异常被吞掉，没有日志
try:
    fetch_data()
except Exception:
    pass

# 正确：记录错误
try:
    fetch_data()
except Exception as e:
    logger.error("Fetch failed", event="data_update_failed", error=str(e))
    raise
```

---

## 检查清单

添加新功能时，确认以下埋点：

- [ ] 入口函数使用 `@traced` 装饰器
- [ ] 关键代码块使用 `with span()` 包装
- [ ] INFO 日志包含 `event` 字段
- [ ] 异常路径有 ERROR 日志
- [ ] 耗时操作记录 `duration_ms`
- [ ] 计数类指标使用 Counter
- [ ] 状态类指标使用 Gauge
- [ ] Label 值控制在 20 个以内
- [ ] 敏感信息已脱敏
- [ ] 单测使用 `obs_noop` 或 `obs_assertions` fixture
