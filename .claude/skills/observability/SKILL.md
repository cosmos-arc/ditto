---
name: observability
description: |
  【必读】可观测性指南。
  触发条件: logger、logging、日志、span、trace、追踪、metrics、指标、埋点、OpenTelemetry、监控。
  核心规则: 必须包含 event 字段、命名规范 domain_action、敏感信息脱敏。
globs:
  - "**/*.py"
---

# 可观测性指南

## 导入

```python
from ditto_foundation import logger, span, traced, M
```

---

## 日志级别

| 级别 | 场景 |
|------|------|
| DEBUG | 开发调试 |
| INFO | 正常业务流程 |
| WARNING | 异常但可恢复、Kill Switch L1 |
| ERROR | 错误但系统可继续 |
| CRITICAL | Kill Switch L2/L3 |

---

## 必须包含 event

```python
# ✅ 正确
logger.info("Update done", event="data_update_complete", records=100)

# ❌ 错误
logger.info("Update done", records=100)  # 缺少 event
```

---

## Trace

```python
# 装饰器
@traced("backtest.run")
def run_backtest(): ...

# 上下文管理器
with span("data.fetch", source="tushare") as s:
    df = fetch_data()
    s.set_attribute("rows", len(df))
```

---

## Metrics

```python
# Counter
M.data_records.add(100, {"source": "tushare"})

# Gauge
M.portfolio_drawdown.set(0.15)
M.kill_switch_level.set(2)

# Histogram
M.data_update_duration.record(45.5)
```

---

## 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| event | `{domain}_{action}` | `data_update_complete` |
| span | `{domain}.{op}` | `backtest.run` |
| metric | `ditto.{domain}.{name}` | `ditto.data.records` |

---

## 禁止

| 禁止 | 替代 |
|------|------|
| 记录 API Key/密码 | 脱敏 |
| 高基数 label | 限制 ≤20 个值 |
| 缺少 event 字段 | 必须包含 |
