# Server 层设计文档

**日期**: 2025-12-27
**Sprint**: Sprint 1 - 数据层与数据摄取
**任务**: 任务6 - Server 层骨架（Prefect 调度 + 数据摄取 Flow）
**状态**: ✅ 已完成（commit: 873c2b5）

---

## 1. 设计目标

搭建调度框架基础，实现数据从外部数据源（Tushare）流入 DataHub 的完整管道。

**核心目标**：
- ✅ 搭建 Prefect 调度框架（为未来所有调度任务提供基础）
- ✅ 实现完整的市场数据摄取（ETF + 股票 + 复权因子）
- ✅ 支持新证券自动注册
- ✅ 部分失败不阻断，但有监控预警和人工重试机制

---

## 2. 架构设计

### 2.1 整体架构（更新）

```
┌─────────────────────────────────────────────────────────────────┐
│                        Server 层                                 │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                    Prefect Flows                        │   │
│   │                                                          │   │
│   │   daily_ingest_flow (7 tasks, 并行执行)                  │   │
│   │                                                          │   │
│   │   Step 1 (可选):                                         │   │
│   │   ├─ ingest_stock_basic                                │   │
│   │                                                          │   │
│   │   Step 2 (并行):                                         │   │
│   │   ├─ ingest_etf_bars ───────────┐                        │   │
│   │   └─ ingest_stock_daily ────────┤                        │   │
│   │                               │ ↓                        │   │
│   │   Step 3 (并行):              │ fetch_xxx()              │   │
│   │   ├─ ingest_adj_factor ────────┤                        │   │
│   │   └─ ingest_fund_adj ─────────┘                        │   │
│   │                          ↓                               │   │
│   │                    hub.sources.tushare.fetch_xxx()      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                  ↓                              │
└──────────────────────────────────────────────────────────────────┘
                                   ↓ 调用
┌──────────────────────────────────────────────────────────────────┐
│                        DataHub 层                                │
│                                                                  │
│   Sources → Repositories → Stores → Runtime                     │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 职责边界

| 层级 | 职责 | 不做 |
|------|------|------|
| **Server/Flows** | 任务编排、依赖管理、并行执行 | 数据获取逻辑 |
| **Server/Tasks** | 调用 DataHub API、数据转换 | 直接调用 Tushare |
| **DataHub/Sources** | 数据源适配 | 调度逻辑 |

### 2.3 目录结构（更新）

```
apps/server/src/ditto_port/
├── main.py                    # FastAPI 应用（集成 Prefect Server）
├── ingestion/                 # 数据摄取模块
│   ├── config.py              # IngestionConfig 配置
│   ├── flows/                 # Prefect Flows（编排层）
│   │   └── daily_ingest.py    # 完整 daily_ingest_flow（7 tasks）
│   └── tasks/                 # Prefect Tasks（执行层）
│       ├── bars.py            # ingest_etf_bars
│       ├── stock.py           # ingest_stock_basic, ingest_stock_daily
│       └── adj_factor.py      # ingest_adj_factor, ingest_fund_adj
```

---

## 3. Prefect 集成设计

### 3.1 运行模式

**完整 Server 模式** + **嵌入 FastAPI 进程**

- 启动 Prefect Server（后台进程）
- 访问 UI: `http://localhost:4200`
- 通过 CLI/UI 触发 Flow

### 3.2 集成方式

**FastAPI lifespan**：
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    # 1. 初始化 observability（已有）
    # 2. 启动 Prefect Server（后台进程）
    yield
    # Shutdown
    # 1. 停止 Prefect Server
```

---

## 4. 数据流设计

### 4.1 ingest_etf_bars / ingest_stock_daily 数据流（相同模式）

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

### 4.2 新证券自动注册逻辑

```python
# 1. 尝试解析 SID
sid_mapping = hub.securities.resolve_identifiers_batch(
    identifiers=src_codes,
    source="tushare",
    asof=trade_date,
)

# 2. 找出未解析的证券
unresolved = [code for code in src_codes if code not in sid_mapping]

# 3. 获取完整的基本信息
basic_df = fetch_etf_basic() / fetch_stock_basic()

# 4. 过滤出未注册的证券
new_securities = basic_df.filter(pl.col("src_code").is_in(unresolved))

# 5. 逐个注册新证券
for row in new_securities.iter_rows(named=True):
    sid = hub.securities.register(
        src_code=row["src_code"],
        symbol=row["symbol"],
        name=row["name"],
        exchange=row["exchange"],
        asset_class="etf" / "stock",
        list_date=str(row["list_date"]),
        source="tushare",
    )
    sid_mapping[row["src_code"]] = sid
```

### 4.3 ingest_adj_factor / ingest_fund_adj 数据流（简化版）

```
1. fetch_adj_factor(trade_date) / fetch_fund_adj(trade_date)
   └─> DataFrame[src_code, trade_date, adj_factor]

2. resolve_identifiers_batch(src_codes, source)
   └─> {src_code: sid} 映射

3. 转换数据格式（src_code → sid）

4. adj_factor_store.write(dataset, df, year)
   └─> 写入 Parquet 文件（年分区）

5. 返回统计结果
```

---

## 5. 任务列表与特性

### 5.1 完整任务列表

| 任务 | 说明 | 数据集 | 可选 |
|------|------|--------|------|
| `ingest_stock_basic` | 股票基本信息 | - | ✅ 首次运行 |
| `ingest_etf_bars` | ETF 日线行情 | `etf_daily` | ❌ |
| `ingest_stock_daily` | 股票日线行情 | `stock_daily` | ❌ |
| `ingest_adj_factor` | 股票复权因子 | `adj_factor` | ❌ |
| `ingest_fund_adj` | ETF/基金复权因子 | `fund_adj` | ❌ |

### 5.2 任务特性

- **自动注册新证券**: 识别未解析的证券代码，自动获取基本信息并注册
- **部分失败容错**: 单个证券失败不阻断整体任务，记录 `skipped_list`
- **指数退避重试**: 网络波动自动重试（1min, 5min, 15min）
- **DQ 检查集成**: 写入数据前自动执行 L1+L2 数据质量检查
- **结构化日志**: 包含 `event` 字段，便于监控和告警

### 5.3 并行执行策略

```python
# Step 2: 日线数据并行
etf_bars_future = ingest_etf_bars.submit(trade_date, source, data_root)
stock_bars_future = ingest_stock_daily.submit(trade_date, source, data_root)

# Step 3: 复权因子并行
adj_factor_future = ingest_adj_factor.submit(trade_date, source, data_root)
fund_adj_future = ingest_fund_adj.submit(trade_date, source, data_root)
```

---

## 6. 错误处理策略

### 6.1 Task 级别重试

```python
@task(
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # 指数退避
)
def ingest_etf_bars(trade_date: str, source: str, data_root: str) -> dict:
    ...
```

### 6.2 错误分类处理

| 错误类型 | 处理方式 | 原因 |
|----------|----------|------|
| `SourceRateLimitError` | 重试（指数退避） | API 限流，短暂问题 |
| `SourceFetchError` | 重试 3 次后失败 | 网络波动 |
| `DataSourceError` | 失败，不重试 | 配置/认证错误 |
| 新证券注册失败 | 记录告警，跳过该证券 | 部分失败不应阻断全部 |

### 6.3 返回值设计

```python
{
    "trade_date": str,
    "source": str,
    "rows_fetched": int,
    "rows_written": int,
    "new_securities_registered": int,
    "failed_checks": int,
    "skipped_securities": int,
    "skipped_list": list[str],   # 具体跳过的证券代码
    "status": str,               # "success" | "warning" | "failed"
}
```

**adj_factor / fund_adj 特有字段**：
```python
{
    "trade_date": str,
    "source": str,
    "rows_fetched": int,
    "rows_written": int,
    "skipped_unresolved": int,
    "status": str,
}
```

---

## 7. 监控预警与人工重试

### 7.1 日志告警

**结构化日志**：
```python
# 部分失败时记录 WARNING
if skipped_securities > 0:
    logger.warning(
        "Partial ingestion failure",
        event="ingestion_partial_failure",
        trade_date=trade_date,
        skipped_securities=skipped_securities,
        skipped_list=skipped_codes,
    )
```

### 7.2 人工重试机制

**通过 Prefect UI**：
1. 打开 `http://localhost:4200`
2. 进入 Flow Runs 页面
3. 找到失败的运行，点击 "Retry"

**通过 Prefect CLI**：
```bash
# 查看失败的历史运行
prefect flow-run ls --state-names Failed

# 重试特定运行
prefect flow-run retry <flow-run-id>
```

---

## 8. Token 安全配置

### 8.1 采用方案

**keyring（主）+ ~/.ditto/secrets.toml（备）+ TUSHARE_TOKEN（开发）**

### 8.2 优先级

1. **keyring**（推荐）：Windows 凭据管理器 / macOS Keychain / Linux Secret Service
2. **~/.ditto/secrets.toml**（备用）：用户主目录配置文件
3. **TUSHARE_TOKEN 环境变量**（仅开发环境）

### 8.3 配置方式

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

**方式 3 - 环境变量（仅开发）**：
```bash
export TUSHARE_TOKEN="YOUR_TOKEN"
```

### 8.4 代码实现

已在 `packages/data/src/ditto_data/sources/tushare/client.py` 中实现 `_get_tushare_token()` 函数，自动按优先级获取 token。

### 8.5 安全性要求

- 日志中不打印完整 token
- 错误消息不包含 token 值
- 使用最小够用的 Tushare 积分级别

---

## 9. 测试策略

### 9.1 单元测试

使用 mock 隔离 DataHub：
- `test_ingest_etf_bars_success`: 正常流程
- `test_ingest_etf_bars_with_new_securities`: 新证券注册
- `test_ingest_etf_bars_partial_failure`: 部分失败
- `test_ingest_etf_bars_empty_data`: 空数据

**Stock 任务**：
- `test_ingest_stock_basic_success`: 股票基本信息
- `test_ingest_stock_daily_success`: 股票日线
- `test_ingest_stock_daily_with_new_securities`: 新股票注册

**AdjFactor 任务**：
- `test_ingest_adj_factor_success`: 股票复权因子
- `test_ingest_fund_adj_success`: ETF 复权因子
- `test_ingest_adj_factor_unresolved`: 部分 sid 未解析

### 9.2 集成测试（可选）

使用临时 DataHub 测试完整数据流。

---

## 10. 验收标准

### 10.1 功能验收

- ✅ `pixi run -e dev server` 启动成功
- ✅ 访问 `http://localhost:4200` 显示 Prefect UI
- ✅ 手动触发 `daily_ingest_flow` 成功执行
- ✅ 7 个任务全部实现，并行执行正常
- ✅ 数据成功写入 `data/bars/etf_daily/YYYY.parquet`
- ✅ 数据成功写入 `data/bars/stock_daily/YYYY.parquet`
- ✅ 数据成功写入 `data/adj_factor/adj_factor/YYYY.parquet`
- ✅ 数据成功写入 `data/adj_factor/fund_adj/YYYY.parquet`
- ✅ 新证券自动注册，日志中有记录
- ✅ 部分失败时，日志中有 `skipped_list` 告警
- ✅ 可通过 UI 或 CLI 重试失败的运行

### 10.2 代码质量

- ✅ `pixi run -e dev ci-check` 全部通过
- ✅ Pre-commit hooks 通过
- ✅ 所有日志包含 `event` 字段
- ✅ 提交 commit: `873c2b5`

---

## 11. 关键文件清单（更新）

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 修改 | `apps/server/src/ditto_port/main.py` | FastAPI + Prefect 启动 |
| 修改 | `packages/data/src/ditto_data/sources/tushare/client.py` | Token fallback 链 |
| 修改 | `packages/data/src/ditto_data/sources/base.py` | 新增 4 个抽象方法 |
| 修改 | `packages/data/src/ditto_data/sources/tushare/source.py` | 新增 4 个 fetch 方法 |
| 新增 | `apps/server/src/ditto_port/ingestion/tasks/stock.py` | 股票摄取任务 |
| 新增 | `apps/server/src/ditto_port/ingestion/tasks/adj_factor.py` | 复权因子摄取任务 |
| 新增 | `apps/server/src/ditto_port/ingestion/flows/daily_ingest.py` | 完整摄取流程（7 tasks） |
| 新增 | `apps/server/README.md` | Server 模块说明 |
| 新增 | `packages/data/src/ditto_data/sources/README.md` | Sources 模块说明 |
| 修改 | `docs/sprints/sprint-01-data-layer.md` | Sprint 文档更新 |
| 修改 | `pixi.toml` | 添加 prefect, keyring 依赖 |

---

## 12. 实现状态（更新）

### 12.1 已完成 ✅

- [x] Prefect 基础设施集成
- [x] ingest_etf_bars 任务
- [x] ingest_stock_basic 任务
- [x] ingest_stock_daily 任务
- [x] ingest_adj_factor 任务
- [x] ingest_fund_adj 任务
- [x] daily_ingest_flow 完整实现
- [x] Token 安全配置（keyring + secrets.toml + env var）
- [x] 并行执行优化

### 12.2 后续优化（Sprint-02）

- calendar / securities 摄取任务
- 定时调度（CronSchedule）
- 告警集成（Telegram/钉钉）
- 回填 Flow（backfill_flow）
- DQ 批量检查（dq_batch_flow）
- AkShare 数据源集成
