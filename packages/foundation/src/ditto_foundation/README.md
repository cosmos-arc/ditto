# ditto-foundation

> 基础设施层 - 共享类型、配置管理、日志、可观测性与工具函数

## 一、核心功能

提供跨包共享的数据契约、系统配置管理、可观测性（日志/追踪/指标）和通用工具函数，是系统的基础依赖层。

## 二、架构定位

```
┌─────────────────────────────────────┐
│         ditto-datahub               │
├─────────────────────────────────────┤
│      ditto-foundation               │  ← 当前层
│  ┌──────────┐  ┌──────────┐         │
│  │ Config   │  │ Contract │         │
│  │Logging   │  │  Util    │         │
│  │Observability│           │         │
│  └──────────┘  └──────────┘         │
└─────────────────────────────────────┘
```

**依赖方向**: 零内部包依赖，仅依赖标准库和第三方库

## 三、目录结构

```
src/ditto_foundation/
├── bootstrap/              # 应用启动引导
│   ├── __init__.py
│   └── initializer.py      # AppInitializer, initialize_app()
├── cache/                  # 缓存能力
│   ├── __init__.py
│   └── core.py             # DataCache, CacheStats
├── checksum/               # 数据完整性校验
│   ├── __init__.py
│   └── file.py             # compute_checksum()
├── concurrency/            # 并发控制
│   ├── __init__.py
│   └── filelock.py         # FileLockManager, LockAcquisitionError
├── config/                 # 配置管理
│   ├── __init__.py
│   ├── settings.py         # Pydantic Settings (主配置)
│   ├── manager.py          # 配置管理器
│   ├── initializer.py      # 配置初始化
│   └── paths.py            # XDG 路径配置
├── db/                     # 数据库连接池
│   ├── __init__.py
│   └── sqlite_pool.py      # SQLitePool
├── observability/          # 可观测性模块
│   ├── __init__.py         # 主入口: init(), shutdown()
│   ├── config.py           # Mode, ObservabilityConfig
│   ├── logging.py          # Loguru 日志配置
│   ├── tracing.py          # OTel 追踪: span(), @traced, get_trace_id()
│   ├── metrics.py          # M 类 (预定义指标)
│   └── testing.py          # 测试辅助: reset_for_testing()
└── util/                   # 工具函数
    ├── __init__.py
    ├── checksum.py         # DataFrame 校验和计算
    ├── dates.py            # 日期规范化 (normalize_date)
    └── io.py               # IO 工具 (atomic_write, file_md5)
```

## 四、关键模块说明

### bootstrap/ - 应用启动引导

应用生命周期管理和初始化。

```python
from ditto_foundation import initialize_app, AppInitializer

# 快速初始化（单例模式）
result = initialize_app()
# {"status": "initialized", "observability_initialized": True, ...}

# 手动管理
initializer = AppInitializer()
result = initializer.initialize()
```

### cache/ - 缓存能力

基于 cachebox 的通用缓存封装，支持 TTL、LRU、OpenTelemetry 指标。

```python
from ditto_foundation import DataCache

# 创建缓存（5分钟TTL，最大10000条）
cache = DataCache(ttl_seconds=300, max_size=10000)

# 设置/获取
cache.set("my_key", {"data": "value"})
value = cache.get("my_key")

# 模式失效
cache.invalidate_pattern("sid:*")

# 统计
stats = cache.get_stats()
print(f"命中率: {stats.hit_rate:.2%}")
```

### checksum/ - 数据完整性校验

文件校验和计算工具（SHA-256）。

```python
from ditto_foundation import compute_checksum
from pathlib import Path

# 计算文件校验和
checksum = compute_checksum(Path("data.parquet"))
# 返回 64 字符的 SHA-256 hex string
```

### concurrency/ - 并发控制

跨平台文件锁管理器。

```python
from ditto_foundation import FileLockManager
from pathlib import Path

manager = FileLockManager(Path("/tmp/locks"))

with manager.acquire("my_resource", timeout=30.0):
    # 临界区代码
    process_data()
```

### observability/ - 可观测性模块

统一的日志、追踪和指标接口，支持多种运行模式。

#### 核心功能

**初始化与关闭**:
```python
from ditto_foundation import init, shutdown, Mode

# 自动检测模式
init()

# 显式指定模式
init(mode=Mode.TESTING)  # 静默模式 (测试最快)
init(mode=Mode.TESTING_WITH_ASSERTIONS)  # 断言模式 (可验证)
init(mode=Mode.PRODUCTION)  # 生产模式

# 优雅关闭
shutdown()
```

**日志**:
```python
from ditto_foundation import logger

logger.info("Processing data", event="data_process", count=100)
logger.error("Failed to connect", event="db_error", db="sqlite")
```

**追踪**:
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

# 获取 trace_id
trace_id = get_trace_id()  # 返回 UUID 格式字符串
```

**指标**:
```python
from ditto_foundation import M

# Counter
M.data_records.add(100, {"source": "tushare", "table": "etf_daily"})

# Gauge
M.kill_switch_level.set(2, {"strategy": "etf_rotation"})

# Histogram
M.data_update_duration.record(1.5, {"source": "tushare"})
```

#### 运行模式

| 模式 | 说明 | 日志输出 | 指标导出 |
|------|------|----------|----------|
| `PRODUCTION` | 生产模式 | 文件 (JSON) | VictoriaMetrics |
| `DEVELOPMENT` | 开发模式 | Console + 文件 | VictoriaMetrics |
| `TESTING` | 测试静默模式 | 无 | 无 |
| `TESTING_WITH_ASSERTIONS` | 测试断言模式 | 无 | 内存记录 |

#### 预定义指标

**数据指标**:
- `M.data_update_duration` (Histogram) - 数据更新耗时
- `M.data_records` (Counter) - 数据记录总数
- `M.data_freshness` (Gauge) - 数据新鲜度（天数）
- `M.data_errors` (Counter) - 数据错误总数

**因子指标**:
- `M.factor_calc_duration` (Histogram) - 因子计算耗时
- `M.factor_ic` (Gauge) - 因子 IC 值
- `M.factor_health` (Gauge) - 因子健康分数

**策略指标**:
- `M.signal_total` (Counter) - 信号总数
- `M.rebalance_total` (Counter) - 调仓总数

**组合指标**:
- `M.portfolio_value` (Gauge) - 组合价值
- `M.portfolio_drawdown` (Gauge) - 组合回撤
- `M.portfolio_drawdown_3d` (Gauge) - 3天滚动回撤

**风控指标**:
- `M.kill_switch_level` (Gauge) - Kill Switch 等级 (0-3)
- `M.kill_switch_total` (Counter) - Kill Switch 触发总数

**系统指标**:
- `M.scheduler_jobs` (Counter) - 调度任务总数
- `M.api_requests` (Counter) - API 请求总数
- `M.api_duration` (Histogram) - API 耗时

### config/ - 配置管理
- `Settings`: 主配置类
  - `DatabaseSettings`: DuckDB/SQLite 配置
  - `ObservabilitySettings`: 可观测性配置
  - `DataSourceSettings`: Tushare/AkShare 配置
  - `APISettings`: FastAPI 服务配置
  - `SystemSettings`: 系统基础配置
  - `FileStorageSettings`: 文件存储配置
- `get_settings()`: 全局配置单例

### util/ - 工具函数
- `ChecksumCompute`: 统一的 Checksum 计算工具（MD5 算法，确定性排序）
  - `from_dataframe()`: 计算 DataFrame 的确定性 checksum
  - `get_sort_keys()`: 获取数据集的排序键配置
- `atomic_write()`: 原子写入 Parquet
- `file_md5()`: 文件 MD5 校验
- `normalize_date()`: 日期格式规范化

## 五、注意事项

1. **零依赖原则**: 本包不依赖其他 ditto 包
2. **配置热加载**: 使用 `reload_settings()` 可重新加载配置
3. **环境变量**: 配置优先级: 环境变量 > .env 文件 > 默认值
4. **可观测性模式**: 测试环境自动使用 `TESTING` 模式，可通过 `DITTO_OBSERVABILITY_MODE` 环境变量显式指定
5. **外部依赖部署**: 生产/开发模式需要部署外部服务（VictoriaMetrics、VictoriaLogs、Vector、Grafana）

## 六、外部依赖部署

生产环境和开发环境需要部署以下可观测性服务：

### 快速开始

```powershell
# 启动服务
.\scripts\observability\start.ps1

# 检查服务状态
.\scripts\observability\health_check.ps1

# 停止服务
.\scripts\observability\stop.ps1
```

### 服务说明

| 服务 | 版本 | 端口 | 用途 |
|------|------|------|------|
| VictoriaMetrics | v1.104.0 | 8428 | Metrics 存储 + OTLP 接收 |
| VictoriaLogs | v1.37.0 | 9428 | Logs 存储 + 查询 |
| Vector | v0.52.0-debian | 8686 | 日志采集 |
| Grafana | 11.1.0 | 3000 | 可视化仪表盘 |

### 数据流向

```
Application
    Loguru -> logs/ditto.jsonl -> Vector -> VictoriaLogs
    OTel Metrics -> OTLP HTTP -> VictoriaMetrics
                              |
                              v
                        Grafana :3000
```

### 访问地址

- **Grafana**: http://localhost:3000 (可视化仪表盘)
- **VictoriaMetrics**: http://localhost:8428 (Metrics 查询)
- **VictoriaLogs**: http://localhost:9428 (Logs 查询)
- **Vector**: http://localhost:8686 (日志采集状态)

### 详细部署文档

请参考 `deploy/observability/README.md` 获取完整的部署指南、配置说明和故障排查。

## 七、使用示例

### 基础使用

```python
from ditto_foundation.config.settings import get_settings
from ditto_foundation.util.io import atomic_write

# 获取配置
settings = get_settings()
print(settings.data_source.tushare_token)

# 原子写入
from pathlib import Path
atomic_write(df, Path("data/output.parquet"))
```

### 可观测性使用

```python
from ditto_foundation import init, logger, span, traced, M, Mode

# 初始化
init(mode=Mode.DEVELOPMENT)

# 日志 + 追踪 + 指标
@traced("data.update")
def update_data(source: str):
    with span("data.fetch", source=source):
        data = fetch_data(source)

    M.data_records.add(len(data), {"source": source})
    M.data_update_duration.record(elapsed, {"source": source})

    logger.info("Data updated", event="data_update", source=source, count=len(data))

    return data
```

### 测试中使用可观测性

```python
import pytest
from ditto_foundation import init, reset_for_testing, Mode, get_recorded_spans

def test_my_function():
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS)

    # 执行测试...

    # 验证 spans
    spans = get_recorded_spans()
    assert len(spans) == 2
    assert spans[0].name == "my_operation"
```
