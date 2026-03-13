# ADR-018: 监控与告警

**状态**: 已决策（2026-03-05）

---

## 背景

因子系统需要完整的可观测性支持，包括运行状态监控、数据延迟告警、数据质量追踪。

---

## 架构决策

| 决策点 | 选择 | 理由 |
|-------|------|------|
| **指标后端** | VictoriaMetrics | 复用现有基础设施 |
| **可视化** | Grafana | 复用现有基础设施 |
| **告警管理** | AlertManager | 复用现有基础设施 |
| **通知渠道** | 全局配置 | 减少配置复杂度 |

---

## 指标体系

**命名规范**: `ditto.derived.*` 前缀

### 运行状态

| 指标名 | 类型 | 说明 |
|-------|------|------|
| `ditto.derived.materialization.total` | Counter | 物化任务计数 |
| `ditto.derived.materialization.duration` | Histogram | 物化耗时（秒） |
| `ditto.derived.materialization.running` | Gauge | 当前运行任务数 |

### 数据延迟

| 指标名 | 类型 | 说明 |
|-------|------|------|
| `ditto.derived.data.lag_hours` | Gauge | Watermark 延迟（小时） |
| `ditto.derived.data.freshness_days` | Gauge | 数据新鲜度（天） |

### 数据质量

| 指标名 | 类型 | 说明 |
|-------|------|------|
| `ditto.derived.data.coverage` | Gauge | 覆盖率（0-1） |
| `ditto.derived.data.gaps` | Gauge | 缺口数量 |
| `ditto.derived.data.rows_total` | Counter | 行数统计 |
| `ditto.derived.data.null_ratio` | Gauge | NULL 比例 |

### 依赖健康

| 指标名 | 类型 | 说明 |
|-------|------|------|
| `ditto.derived.dependency.ready` | Gauge | 依赖就绪状态 |

### 在线查询边界（详见 ADR-030）

| 指标名 | 类型 | 说明 |
|-------|------|------|
| `ditto.online_parquet_reads_total` | Counter | ONLINE 模式下 Parquet 读取次数（按 runtime_mode, factor_id 标签） |
| `ditto.parquet_read_latency_seconds` | Histogram | Parquet 读取延迟 |
| `ditto.runtime_mode_changes_total` | Counter | 运行时模式切换次数（按 from_mode, to_mode 标签） |

---

## 告警规则

### Critical 级别

| 告警 | 条件 | 说明 |
|-----|------|------|
| MaterializationFailed | `status="failed"` | 物化失败 |
| DataLagCritical | `lag_hours > 4` | 数据延迟 > 4 小时 |
| AllMaterializationStuck | 24h 无完成 | 全系统停滞 |

### Warning 级别

| 告警 | 条件 | 说明 |
|-----|------|------|
| DataLagWarning | `lag_hours > 1` | 数据延迟 > 1 小时 |
| LowCoverage | `coverage < 0.95` | 覆盖率 < 95% |
| DataGaps | `gaps > 0` | 存在数据缺口 |
| MaterializationSlow | P95 > 300s | 物化耗时过长 |
| DependencyNotReady | `ready == 0` | 依赖未就绪 |

### 在线查询边界告警（详见 ADR-030）

| 告警 | 级别 | 条件 | 说明 |
|-----|------|------|------|
| OnlineParquetRead | Critical | `rate(online_parquet_reads_total{runtime_mode="ONLINE"}[5m]) > 0` | ONLINE 模式下访问 Parquet |
| FrequentDegradedMode | Warning | `rate(runtime_mode_changes_total{to_mode="DEGRADED"}[1h]) > 3` | 频繁切换到降级模式 |

---

## 监控服务

```python
# packages/core/src/ditto_core/derived/monitoring.py

class DerivedMonitor:
    """因子系统监控服务"""

    def record_materialization_start(entity_id, mode) -> None
    def record_materialization_complete(entity_id, mode, duration, rows, success, error) -> None
    def record_watermark(entity_id, watermark, expected) -> None
    def record_coverage(entity_id, coverage, gaps) -> None
```

---

## Grafana Dashboard 面板

| 面板 | 类型 | 说明 |
|-----|------|------|
| 活跃因子数 | Stat | 当前 is_active=true 的因子 |
| 运行中任务 | Stat | 当前 materialization_running |
| 今日成功率 | Gauge | success / total |
| 任务状态分布 | Pie | success/failed/running |
| 耗时分布 | Histogram | P50/P95/P99 |
| 延迟热力图 | Heatmap | 各因子延迟分布 |
| Watermark 时间线 | Time Series | 各因子 watermark 变化 |
| 覆盖率表格 | Table | 各因子覆盖率、缺口数 |

---

## 告警通知

复用全局 AlertManager 配置：
- **Critical** → 邮件 + Webhook
- **Warning** → 邮件

告警模板位置：
```
packages/infra/src/ditto_infra/services/notification/templates/alerts/derived.py
```
