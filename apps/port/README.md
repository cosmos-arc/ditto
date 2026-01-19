# ditto-server

> 数据摄取调度服务 - 基于 Prefect 的任务编排与数据摄取流程

## 一、核心功能

提供统一的数据摄取调度服务，使用 Prefect 进行任务编排，支持从 Tushare 等数据源自动摄取 ETF、股票行情和复权因子数据。

## 二、架构设计

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
│    ├─ ingest_stock_basic (可选)                             │
│    ├─ ingest_etf_bars + ingest_stock_daily (并行)           │
│    └─ ingest_adj_factor + ingest_fund_adj (并行)           │
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

### 2.2 依赖关系

```
                    ┌─────────────┐
                    │  models/    │  模型层
                    │ (config.py) │
                    │(ingestion.py)│
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
        ┌──────────┐              ┌──────────┐
        │  jobs/   │              │services/ │
        │ (编排层) │              │(逻辑层)  │
        └────┬─────┘              └─────┬────┘
             │                          │
             └──────────┬───────────────┘
                        ▼
                 ┌──────────────┐
                 │  datahub/    │
                 │  (数据层)    │
                 └──────────────┘
```

**依赖规则**:
- `jobs/` → `models/` ✅
- `services/` → `models/` ✅
- `jobs/` → `services/` ✅
- `models/` → 任何模块 ❌ (独立的模型层)

**关键设计**: `models/` 作为共享模型层消除了 `jobs/` 和 `services/` 之间的循环依赖。

## 三、目录结构

```
apps/port/src/ditto_port/
├── models/                    # 模型层
│   ├── __init__.py
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
        ├── result_utils.py    # 结果统计工具
        ├── retry.py           # 重试管理器
        └── security_mapper.py # 证券映射器
```

## 四、摄取任务

### 4.1 任务列表

| 任务 | 说明 | 数据集 |
|------|------|--------|
| `ingest_stock_basic` | 股票基本信息（可选） | - |
| `ingest_etf_bars` | ETF 日线行情 | `etf_daily` |
| `ingest_stock_daily` | 股票日线行情 | `stock_daily` |
| `ingest_adj_factor` | 股票复权因子 | `adj_factor` |
| `ingest_fund_adj` | ETF/基金复权因子 | `fund_adj` |

### 4.2 任务特性

- **自动注册新证券**: 识别未解析的证券代码，自动获取基本信息并注册
- **部分失败容错**: 单个证券失败不阻断整体任务，记录 `skipped_list`
- **指数退避重试**: 网络波动自动重试（1min, 5min, 15min）
- **DQ 检查集成**: 写入数据前自动执行 L1+L2 数据质量检查
- **结构化日志**: 包含 `event` 字段，便于监控和告警

### 4.3 返回值格式

```python
{
    "trade_date": str,
    "source": str,
    "rows_fetched": int,
    "rows_written": int,
    "new_securities_registered": int,
    "skipped_securities": int,
    "skipped_list": list[str],
    "failed_checks": int,
    "status": str,  # "success" | "warning" | "failed"
}
```

## 五、数据流设计

### 5.1 ingest_etf_bars / ingest_stock_daily 数据流

```
1. fetch_etf_daily(trade_date) / fetch_stock_daily(trade_date)
   └─> DataFrame[src_code, trade_date, open, high, low, close, ...]

2. resolve_identifiers_batch(src_codes, source)
   └─> {src_code: sid} 映射

3. 识别未解析的证券（sid 为 None）

4. fetch_etf_basic() / fetch_stock_basic() 获取完整基本信息

5. securities.register() 批量注册新证券

6. 合并 SID 映射

7. 转换数据格式（src_code → sid）

8. bars.write(df, dataset="etf_daily"/"stock_daily", run_dq_check=True)
   └─> 自动触发 DQ L1+L2 检查

9. 返回统计结果
```

### 5.2 ingest_adj_factor / ingest_fund_adj 数据流

```
1. fetch_adj_factor(trade_date) / fetch_fund_adj(trade_date)
   └─> DataFrame[src_code, trade_date, adj_factor]

2. resolve_identifiers_batch(src_codes, source)

3. 转换数据格式（src_code → sid）

4. adj_factor_store.write(dataset, df, year)
   └─> 写入 Parquet 文件（年分区）

5. 返回统计结果
```

## 六、使用示例

### 6.1 启动服务

```bash
# 开发环境
pixi run -e dev server

# 访问健康检查
curl http://localhost:8000/health

# 访问 Prefect UI
open http://localhost:4200
```

### 6.2 手动触发 Flow

```bash
# 首次运行（包含股票基本信息）
prefect flow-run run daily_ingest_flow \
    --json '{"trade_date": "2024-01-02", "run_stock_basic": true}'

# 日常运行（不含股票基本信息）
prefect flow-run run daily_ingest_flow \
    --json '{"trade_date": "2024-01-03"}'
```

### 6.3 查看 Flow 执行历史

```bash
# 通过 Prefect CLI
prefect flow-run ls --limit 10

# 查看特定运行的详情
prefect flow-run inspect <flow-run-id>
```

## 七、错误处理策略

### 7.1 Task 级别重试

```python
@task(
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # 指数退避
)
def ingest_etf_bars(trade_date, source, data_root):
    ...
```

### 7.2 错误分类处理

| 错误类型 | 处理方式 | 原因 |
|----------|----------|------|
| `SourceRateLimitError` | 重试（指数退避） | API 限流，短暂问题 |
| `SourceFetchError` | 重试 3 次后失败 | 网络波动 |
| `DataSourceError` | 失败，不重试 | 配置/认证错误 |
| 新证券注册失败 | 记录告警，跳过该证券 | 部分失败不应阻断全部 |

### 7.3 人工重试机制

**通过 Prefect UI**:
1. 打开 `http://localhost:4200`
2. 进入 Flow Runs 页面
3. 找到失败的运行，点击 "Retry"

**通过 Prefect CLI**:
```bash
# 重试特定运行
prefect flow-run retry <flow-run-id>
```

## 八、Token 安全配置

### 8.1 配置优先级

1. **keyring**（推荐）：Windows 凭据管理器 / macOS Keychain / Linux Secret Service
2. **~/.ditto/secrets.toml**（备用）：用户主目录配置文件
3. **TUSHARE_TOKEN** 环境变量（仅开发）

### 8.2 配置方式

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

### 8.3 安全性要求

- 日志中不打印完整 token
- 错误消息不包含 token 值
- 使用最小够用的 Tushare 积分级别

## 九、依赖项

```toml
[dependencies]
fastapi = ">=0.100"
uvicorn = ">=0.23"
prefect = ">=3.0"
keyring = ">=25.0"
ditto-data-hub = ">=0.1.0"
```

## 十、注意事项

1. **并行执行**: etf_bars + stock_bars 并行，adj_factor + fund_adj 并行
2. **新证券注册**: 首次运行时设置 `run_stock_basic=True`
3. **数据质量**: 所有写入操作自动执行 DQ L1+L2 检查
4. **日志规范**: 所有日志包含 `event` 字段
5. **监控告警**: 部分失败时记录 WARNING 级别日志

## 十一、相关文档

- 设计文档：`docs/plans/2025-12-27-server-layer-design.md`
- Sprint 文档：`docs/sprints/sprint-01-data-layer.md`
- Sources 文档：`packages/datahub/src/ditto_datahub/sources/README.md`
