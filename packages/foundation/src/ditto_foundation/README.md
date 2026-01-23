# ditto-foundation

**版本**: v0.5.0
**最后更新**: 2026-01-23
**状态**: ✅ 稳定

## 概要

基础设施层，提供跨包共享的数据契约、系统配置管理、可观测性（日志/追踪/指标）和通用工具函数，是系统的基础依赖层。

## 核心功能

- **配置管理**: Pydantic Settings，环境变量优先级管理
- **可观测性**: 统一的日志（Loguru）、追踪（OTel）、指标（VictoriaMetrics）
- **并发控制**: 跨平台文件锁管理器
- **缓存层**: 基于 cachebox 的通用缓存封装
- **数据校验**: 文件校验和计算（SHA-256、MD5）
- **工具函数**: 日期规范化、原子写入

## 架构

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

## 目录结构

```
src/ditto_foundation/
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

## 使用示例

### 配置管理

```python
from ditto_foundation.config.settings import get_settings

# 获取配置
settings = get_settings()
print(settings.data_source.tushare_token)
```

### 可观测性

```python
from ditto_foundation import init, logger, span, M, Mode

# 初始化
init(mode=Mode.DEVELOPMENT)

# 日志 + 追踪 + 指标
@span("data.update")
def update_data(source: str):
    logger.info("Data updated", event="data_update", source=source)
    M.data_records.add(100, {"source": source})
    M.data_update_duration.record(1.5, {"source": source})
```

### 缓存

```python
from ditto_foundation import DataCache

cache = DataCache(ttl_seconds=300, max_size=10000)
cache.set("my_key", {"data": "value"})
value = cache.get("my_key")
```

### 并发控制

```python
from ditto_foundation import FileLockManager
from pathlib import Path

manager = FileLockManager(Path("/tmp/locks"))

with manager.acquire("my_resource", timeout=30.0):
    # 临界区代码
    process_data()
```

## 预定义指标

### 数据指标
- `M.data_update_duration` (Histogram) - 数据更新耗时
- `M.data_records` (Counter) - 数据记录总数
- `M.data_freshness` (Gauge) - 数据新鲜度（天数）
- `M.data_errors` (Counter) - 数据错误总数

### 因子指标
- `M.factor_calc_duration` (Histogram) - 因子计算耗时
- `M.factor_ic` (Gauge) - 因子 IC 值
- `M.factor_health` (Gauge) - 因子健康分数

### 策略指标
- `M.signal_total` (Counter) - 信号总数
- `M.rebalance_total` (Counter) - 调仓总数

### 组合指标
- `M.portfolio_value` (Gauge) - 组合价值
- `M.portfolio_drawdown` (Gauge) - 组合回撤
- `M.portfolio_drawdown_3d` (Gauge) - 3天滚动回撤

### 风控指标
- `M.kill_switch_level` (Gauge) - Kill Switch 等级 (0-3)
- `M.kill_switch_total` (Counter) - Kill Switch 触发总数

### 系统指标
- `M.scheduler_jobs` (Counter) - 调度任务总数
- `M.api_requests` (Counter) - API 请求总数
- `M.api_duration` (Histogram) - API 耗时

## 可观测性运行模式

| 模式 | 说明 | 日志输出 | 指标导出 |
|------|------|----------|----------|
| `PRODUCTION` | 生产模式 | 文件 (JSON) | VictoriaMetrics |
| `DEVELOPMENT` | 开发模式 | Console + 文件 | VictoriaMetrics |
| `TESTING` | 测试静默模式 | 无 | 无 |
| `TESTING_WITH_ASSERTIONS` | 测试断言模式 | 无 | 内存记录 |

## 外部依赖部署

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

### 访问地址

- **Grafana**: http://localhost:3000 (可视化仪表盘)
- **VictoriaMetrics**: http://localhost:8428 (Metrics 查询)
- **VictoriaLogs**: http://localhost:9428 (Logs 查询)
- **Vector**: http://localhost:8686 (日志采集状态)

### 详细部署文档

请参考 [deploy/observability/README.md](../../../../deploy/observability/README.md) 获取完整的部署指南、配置说明和故障排查。

## 相关文档

- [可观测性模块 README](observability/README.md)
- [工具函数 README](util/README.md)

## 变更记录

### v0.5.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善模块结构说明
- 重新组织预定义指标文档

### v0.4.0 (2025-12-27)
**新增**
- DataCache 缓存层实现
- SQLitePool 连接池实现
- FileLockManager 并发控制

### v0.1.0 (2025-12-08)
**新增**
- 初始模块结构
- 配置管理（Pydantic Settings）
- 可观测性基础（Loguru + OTel）
- 工具函数库
