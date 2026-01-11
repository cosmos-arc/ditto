# observability

> 统一的可观测性接口 - 日志、追踪、指标

## 一、概述

本模块提供统一的可观测性功能，整合了日志（Loguru）、分布式追踪（OpenTelemetry）和指标收集（OpenTelemetry Metrics），支持多种运行模式。

## 二、核心功能

### 1. 日志 (Logging)

基于 Loguru 的结构化日志，支持 JSON 格式输出和上下文注入。

```python
from ditto_foundation import logger

logger.info("Processing data", event="data_process", count=100)
logger.error("Failed to connect", event="db_error", db="sqlite")
```

### 2. 追踪 (Tracing)

基于 OpenTelemetry 的分布式追踪，支持 span 管理和 trace_id 生成。

```python
from ditto_foundation import span, traced, get_trace_id

# 上下文管理器
with span("data.load", source="tushare"):
    data = load_data()

# 装饰器
@traced("backtest.run")
def run_backtest(start_date, end_date):
    # 自动创建名为 "backtest.run" 的 span
    ...

# 获取 trace_id (UUID 格式)
trace_id = get_trace_id()
span_id = get_span_id()
```

### 3. 指标 (Metrics)

基于 OpenTelemetry 的指标收集，提供预定义的业务指标。

```python
from ditto_foundation import M

# Counter - 计数器
M.data_records.add(100, {"source": "tushare", "table": "etf_daily"})

# Gauge - 仪表
M.kill_switch_level.set(2, {"strategy": "etf_rotation"})

# Histogram - 直方图
M.data_update_duration.record(1.5, {"source": "tushare"})
```

## 三、运行模式

| 模式 | 说明 | 日志输出 | 指标导出 | 用途 |
|------|------|----------|----------|------|
| `PRODUCTION` | 生产模式 | 文件 (JSON) | VictoriaMetrics | 生产环境 |
| `DEVELOPMENT` | 开发模式 | Console + 文件 | VictoriaMetrics | 开发环境 |
| `TESTING` | 测试静默模式 | 无 | 无 | 单元测试 (最快) |
| `TESTING_WITH_ASSERTIONS` | 测试断言模式 | 无 | 内存记录 | 单元测试 (可验证) |

### 模式检测

自动检测顺序：
1. `DITTO_OBSERVABILITY_MODE` 环境变量 (显式指定)
2. `PYTEST_CURRENT_TEST` 环境变量 (pytest 测试)
3. `environment` 配置参数 ("production" → PRODUCTION, 其他 → DEVELOPMENT)

## 四、API 参考

### 初始化与关闭

```python
from ditto_foundation import init, shutdown, Mode

# 自动检测模式
init()

# 显式指定模式
init(mode=Mode.TESTING)
init(mode=Mode.PRODUCTION, service_name="my_service")

# 优雅关闭 (刷新缓冲数据)
shutdown()
```

### 日志 API

```python
from ditto_foundation import logger

logger.debug("Debug message", key=value)
logger.info("Info message", event="event_name")
logger.warning("Warning message")
logger.error("Error message", event="error", error_code=500)
logger.critical("Critical message")

# 绑定上下文
logger.bind(trace_id="xxx-xxx-xxx").info("Message with context")
```

### 追踪 API

```python
from ditto_foundation import span, traced, get_trace_id, get_span_id

# Span 上下文管理器
with span("operation_name", key1=value1):
    # 操作代码
    pass

# Span 装饰器
@traced("operation_name")
def my_function(arg1, arg2):
    # 函数代码
    pass

# 获取 trace/span ID
trace_id = get_trace_id()  # UUID 格式字符串
span_id = get_span_id()    # 16位十六进制
```

### 指标 API

```python
from ditto_foundation import M

# Counter (单调递增)
M.data_records.add(delta, attributes)
M.signal_total.increment(attributes)

# Gauge (可增减)
M.kill_switch_level.set(value, attributes)
M.kill_switch_level.inc(delta, attributes)

# Histogram (记录分布)
M.data_update_duration.record(value, attributes)
```

### 测试辅助 API

```python
from ditto_foundation import reset_for_testing, get_recorded_spans, get_recorded_metrics

# 重置状态
reset_for_testing()

# 获取记录的 spans
spans = get_recorded_spans()
assert len(spans) == 1
assert spans[0].name == "operation_name"

# 获取记录的指标
metrics = get_recorded_metrics()
assert metrics["metrics_recorded"] is True
```

## 五、预定义指标

### Histogram Buckets 配置

所有 `duration` 类型的 Histogram 指标使用统一的 buckets 配置（单位：秒）：

```python
buckets = [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
```

适用于以下指标：
- `ditto.data.update.duration`
- `ditto.factor.calc.duration`
- `ditto.api.duration`

### 数据指标

| 指标名 | 类型 | 属性示例 | 说明 |
|--------|------|----------|------|
| `ditto.data.update.duration` | Histogram | source, table | 数据更新耗时 (秒) |
| `ditto.data.records_total` | Counter | source, table, status | 数据记录总数 |
| `ditto.data.freshness_days` | Gauge | - | 数据新鲜度 (天) |
| `ditto.data.errors_total` | Counter | source, table, error_type | 数据错误总数 |

### 因子指标

| 指标名 | 类型 | 属性示例 | 说明 |
|--------|------|----------|------|
| `ditto.factor.calc.duration` | Histogram | factor_name | 因子计算耗时 (秒) |
| `ditto.factor.ic` | Gauge | factor_name, window | 因子 IC 值 |
| `ditto.factor.health` | Gauge | factor_name | 因子健康分数 (0-100) |

### 策略指标

| 指标名 | 类型 | 属性示例 | 说明 |
|--------|------|----------|------|
| `ditto.signal.total` | Counter | strategy, signal_type | 信号总数 |
| `ditto.rebalance.total` | Counter | strategy | 调仓总数 |

### 组合指标

| 指标名 | 类型 | 属性示例 | 说明 |
|--------|------|----------|------|
| `ditto.portfolio.value` | Gauge | strategy | 组合价值 |
| `ditto.portfolio.drawdown` | Gauge | strategy | 组合回撤 |
| `ditto.portfolio.drawdown_3d` | Gauge | strategy | 3天滚动回撤 |

### 风控指标

| 指标名 | 类型 | 属性示例 | 说明 |
|--------|------|----------|------|
| `ditto.risk.kill_switch_level` | Gauge | strategy | Kill Switch 等级 (0-3) |
| `ditto.risk.kill_switch_total` | Counter | strategy, level | Kill Switch 触发总数 |

### 系统指标

| 指标名 | 类型 | 属性示例 | 说明 |
|--------|------|----------|------|
| `ditto.scheduler.jobs_total` | Counter | job_name, status | 调度任务总数 |
| `ditto.api.requests_total` | Counter | endpoint, status | API 请求总数 |
| `ditto.api.duration` | Histogram | endpoint, status | API 耗时 (秒) |

## 六、测试示例

### 基础测试

```python
import pytest
from ditto_foundation import init, reset_for_testing, Mode

def test_my_function():
    reset_for_testing()
    init(mode=Mode.TESTING)

    # 测试代码 (无日志输出)
    result = my_function()
    assert result is not None
```

### 带 Span 验证的测试

```python
from ditto_foundation import init, span, Mode, get_recorded_spans, reset_for_testing

def test_span_creation():
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS)

    with span("test_operation", key="value"):
        pass

    spans = get_recorded_spans()
    assert len(spans) == 1
    assert spans[0].name == "test_operation"
    assert spans[0].attributes.get("key") == "value"
```

### 带指标验证的测试

```python
from ditto_foundation import init, M, Mode, get_recorded_metrics, reset_for_testing

def test_metrics():
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS)

    M.data_records.add(100, {"source": "test"})

    metrics = get_recorded_metrics()
    assert metrics is not None
```

## 七、配置

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DITTO_OBSERVABILITY_MODE` | 显式指定模式 (production/development/testing/testing_assertions) | 自动检测 |
| `OBSERVABILITY_LOG_LEVEL` | 日志级别 | INFO |
| `OBSERVABILITY_VM_ENDPOINT` | VictoriaMetrics OTLP 端点 | http://localhost:8428/opentelemetry/v1/metrics |

### 配置类

```python
from ditto_foundation import ObservabilityConfig

config = ObservabilityConfig(
    service_name="my_service",
    environment="production",
    log_level="INFO",
    log_dir="logs",
    vm_endpoint="http://localhost:8428/opentelemetry/v1/metrics",
)
```

## 八、外部依赖部署

### 生产环境部署

在 PRODUCTION/DEVELOPMENT 模式下，需要部署外部可观测性服务来接收日志和指标。

#### 使用 Docker Compose 部署

1. **启动服务**
   ```powershell
   # 从项目根目录运行
   .\scripts\observability\start.ps1
   ```

2. **验证服务**
   ```powershell
   .\scripts\observability\health_check.ps1
   ```

3. **访问服务**
   | 服务 | URL | 用途 |
   |------|-----|------|
   | Grafana | http://localhost:3000 | 可视化仪表盘 |
   | VictoriaMetrics | http://localhost:8428 | Metrics 查询 UI |
   | VictoriaLogs | http://localhost:9428 | Logs 查询 UI |

#### 服务组件

| 组件 | 版本 | 端口 | 内存限制 | 保留期 |
|------|------|------|----------|--------|
| VictoriaMetrics | v1.104.0 | 8428 | 256M | 90天 |
| VictoriaLogs | v0.37.0 | 9428 | 256M | 30天 |
| Vector | v0.52.0 | 8686 | 128M | - |
| Grafana | 11.1.0 | 3000 | 256M | - |

**总资源占用**: ~400MB RAM, ~2.6GB 磁盘 (30天)

#### 数据流向

```
App (Loguru) → logs/ditto.jsonl → Vector → VictoriaLogs
App (OTel) → OTLP HTTP → VictoriaMetrics
                                      ↓
                                  Grafana
```

#### 停止服务

```powershell
.\scripts\observability\stop.ps1
```

详细部署指南请参考：[deploy/observability/README.md](../../../../deploy/observability/README.md)

### 配置端点

默认配置下，应用会向以下端点推送数据：

- **Metrics**: `http://localhost:8428/opentelemetry/v1/metrics`
- **Logs**: 通过 Vector 采集 `logs/ditto.jsonl`

如需修改端点，设置环境变量：

```powershell
$env:OBSERVABILITY_VM_ENDPOINT="http://your-vm-endpoint:8428/opentelemetry/v1/metrics"
```

## 九、内部实现

### Tracing 状态管理

Tracing 模块使用 `TracingState` dataclass 封装全局状态：

```python
@dataclass
class TracingState:
    """封装所有 tracing 全局状态."""
    tracer: trace.Tracer | None = None
    in_memory_exporter: InMemorySpanExporter | None = None

    def reset(self) -> None:
        """重置所有状态."""
        ...
```

- **单一状态对象**: 所有全局状态封装在 `_state` 单例中
- **简化重置**: `reset_tracing()` 调用 `_state.reset()` 清理所有状态
- **无手动 Span 管理**: 完全依赖 OpenTelemetry 的 `trace.get_current_span()`

### 重置函数

| 函数 | 用途 | 使用场景 |
|------|------|----------|
| `reset_tracing()` | 重置 tracing 状态 | 测试间清理 |
| `reset_metrics()` | 重置 metrics 状态 | 测试间清理 |
| `reset_for_testing()` | 重置所有可观测性状态 | 测试前置操作 |

## 十、注意事项

1. **测试隔离**: 每个测试前应调用 `reset_for_testing()` 重置状态
2. **shutdown 限制**: `shutdown()` 后无法重新初始化，测试中应使用 `reset_for_testing()` 代替
3. **属性值**: 指标属性值必须是字符串，数字会被自动转换
4. **force 参数**: `init(force=True)` 可强制重新初始化 (仅用于测试)
5. **trace_id 格式**: 返回标准 UUID 格式字符串 (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
6. **ObservableGauge 限制**: 预定义的 Gauge 指标（如 `M.kill_switch_level`）当前实现不支持多标签 attributes。`set(attributes)` 中的 attributes 参数会被忽略，仅保留 API 兼容性。如需带标签的 Gauge，请直接使用 meter API 创建。
7. **生产环境日志格式**: 生产模式下日志文件为 `ditto.jsonl` (JSON Lines 格式)，便于 Vector 采集和分析。
8. **Docker Desktop 依赖**: 部署外部依赖需要 Docker Desktop 运行，建议使用 WSL 2 后端。
