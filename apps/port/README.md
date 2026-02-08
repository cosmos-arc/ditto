# ditto-port

**版本**: v0.3.0
**最后更新**: 2026-01-23
**状态**: ✅ 稳定

## 概要

数据摄取调度服务，基于 Prefect 的任务编排与数据摄取流程，支持从 Tushare 等数据源自动摄取 T0/T1 全矩阵数据集（行情、元数据、财务、资金面、宏观）。

## 核心功能

- **任务编排**: 基于 Prefect 3 的本地 Server 模式
- **数据摄取**: 支持 T0/T1 全矩阵（market/metadata/fundamental/capital/macro）
- **自动注册**: 识别未解析证券代码，自动获取基本信息并注册
- **容错机制**: 部分失败容错、指数退避重试
- **数据质量**: 自动执行 L1+L2 数据质量检查
- **结构化日志**: 包含 `event` 字段，便于监控和告警

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
│                                                              │
│  - 健康检查端点  - Prefect Server 集成  - 自动启动管理      │
└─────────────────────────────────────────────────────────────┘
                          △
┌─────────────────────────────────────────────────────────────┐
│                  Prefect Flows (编排层)                      │
│                                                              │
│  daily_ingest_flow                                          │
│    ├─ T0 元数据层（calendar/stock_basic/etf_basic）          │
│    ├─ T1 第 0 层（stock_daily/etf_daily/macro_indicators）  │
│    └─ T1 后续层（adj/status/fundamental/capital 等）         │
└─────────────────────────────────────────────────────────────┘
                          △
┌─────────────────────────────────────────────────────────────┐
│                  Prefect Tasks (执行层)                      │
│                                                              │
│  - fetch from DataHub sources                               │
│  - resolve and register securities                          │
│  - transform and write to DataHub                           │
│  - retry with exponential backoff                           │
└─────────────────────────────────────────────────────────────┘
                          △
┌─────────────────────────────────────────────────────────────┐
│                      DataHub Layer                           │
│                                                              │
│  Sources → Repositories → Stores → Runtime                 │
└─────────────────────────────────────────────────────────────┘
```

**依赖规则**:
- `jobs/` → `models/` ✅
- `services/` → `models/` ✅
- `jobs/` → `services/` ✅
- `models/` → 任何模块 ❌ (独立的模型层)

## 目录结构

```
apps/port/src/ditto_port/
├── models/                    # 模型层
│   ├── common.py              # ErrorResponse (API 响应)
│   ├── config.py              # DatasetSpec, T1ConfigSpec, DATASET_REGISTRY
│   └── ingestion.py           # IngestionResult, ResultCounts, BackfillResult, RetryResult
├── jobs/                      # 任务编排层
│   ├── flows/                 # Prefect Flows
│   │   ├── daily.py           # 每日摄取 Flow
│   │   ├── backfill.py        # 历史数据回补
│   │   ├── repair.py          # 数据修补
│   │   └── helpers.py         # Flow 辅助函数
│   └── tasks/                 # Prefect Tasks
│       ├── t0_meta.py         # T0 元数据任务
│       └── dq_batch.py        # DQ 批量检查
└── services/                  # 业务逻辑层
    └── ingestion/             # 数据摄取服务
        ├── coordinator.py     # 统一摄取协调器
        ├── backfill.py        # 回补管理器
        ├── data_writer.py     # 数据写入器
        ├── metadata.py        # 元数据服务
        ├── result_utils.py    # 结果统计工具
        ├── result_handler.py  # 结果处理器
        ├── retry.py           # 重试管理器
        ├── quality/           # 数据质量服务
        │   └── service.py     # DQ 检查与隔离
        └── protocols.py       # 服务接口协议
```

## 摄取任务

| 层级 | 说明 | 数据集 |
|------|------|--------|
| `T0_META` | 元数据基础层 | `calendar`, `stock_basic`, `etf_basic` |
| `T1_INCREMENTAL` | 日增量层 | `stock_daily`, `etf_daily`, `stock_status`, `adj_factor`, `fund_adj`, `balance_sheet`, `income_statement`, `cash_flow`, `dividend`, `valuation_metrics`, `margin_trading`, `pledge_ratio`, `macro_indicators` |

说明：实际执行由 `DATASET_REGISTRY` 动态生成任务，README 仅列出当前默认矩阵。

### 任务特性

- **自动注册新证券**: 识别未解析的证券代码，自动获取基本信息并注册
- **部分失败容错**: 单个证券失败不阻断整体任务，记录 `skipped_list`
- **指数退避重试**: 网络波动自动重试（1min, 5min, 15min）
- **DQ 检查集成**: 写入数据前自动执行 L1+L2 数据质量检查
- **结构化日志**: 包含 `event` 字段，便于监控和告警

## 使用示例

### 启动服务

```bash
# 开发环境
pixi run -e dev server

# 访问健康检查
curl http://localhost:8000/health

# 访问 Prefect UI
open http://localhost:4200
```

### 手动触发 Flow

```bash
# 首次运行（包含股票基本信息）
prefect flow-run run daily_ingest_flow \
    --json '{"trade_date": "2024-01-02", "run_stock_basic": true}'

# 日常运行（不含股票基本信息）
prefect flow-run run daily_ingest_flow \
    --json '{"trade_date": "2024-01-03"}'
```

### 查看 Flow 执行历史

```bash
# 通过 Prefect CLI
prefect flow-run ls --limit 10

# 查看特定运行的详情
prefect flow-run inspect <flow-run-id>
```

## 错误处理策略

### Task 级别重试

```python
@task(
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # 指数退避
)
def ingest_etf_bars(trade_date, source, data_root):
    ...
```

### 错误分类处理

| 错误类型 | 处理方式 | 原因 |
|----------|----------|------|
| `SourceRateLimitError` | 重试（指数退避） | API 限流，短暂问题 |
| `SourceFetchError` | 重试 3 次后失败 | 网络波动 |
| `DataSourceError` | 失败，不重试 | 配置/认证错误 |
| 新证券注册失败 | 记录告警，跳过该证券 | 部分失败不应阻断全部 |

## Token 安全配置

### 配置优先级

1. **keyring**（推荐）：Windows 凭据管理器 / macOS Keychain / Linux Secret Service
2. **~/.ditto/secrets.toml**（备用）：用户主目录配置文件
3. **TUSHARE_TOKEN** 环境变量（仅开发）

### 配置方式

**方式 1 - keyring（推荐）**：
```bash
python -c "import keyring; keyring.set_password('ditto', 'tushare', 'YOUR_TOKEN')"
```

**方式 2 - 备用文件**：
```toml
# ~/.ditto/secrets.toml
[tushare]
token = "YOUR_TOKEN"
```

## 相关文档

- [设计文档](../../docs/plans/2025-12-27-server-layer-design.md)
- [Sprint 文档](../../docs/sprints/sprint-01-data-layer.md)
- [Sources 文档](../../packages/datahub/src/ditto_datahub/sources/README.md)

## 变更记录

### v0.3.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善架构说明
- 重新组织文档结构

### v0.2.0 (2025-12-30)
**新增**
- 数据摄取调度服务实现
- Prefect 3 本地 Server 模式
- IngestionCoordinator 统一摄取协调器

### v0.1.0 (2025-12-27)
**新增**
- 初始应用结构
- FastAPI 基础框架
