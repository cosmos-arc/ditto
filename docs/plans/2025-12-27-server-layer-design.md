# Server 层骨架设计文档

**日期**: 2025-12-27
**Sprint**: Sprint 1 - 数据层与数据摄取
**任务**: 任务6 - Server 层骨架（Prefect 调度 + 数据摄取 Flow）

---

## 1. 设计目标

搭建调度框架基础，实现数据从外部数据源（Tushare）流入 DataHub 的完整管道。

**核心目标**：
- 搭建 Prefect 调度框架（为未来所有调度任务提供基础）
- 实现 ETF 日线数据摄取（第一个用例，验证架构）
- 支持新证券自动注册
- 部分失败不阻断，但有监控预警和人工重试机制

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Server 层                                 │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                    Prefect Flows                        │   │
│   │                                                          │   │
│   │   daily_ingest_flow ──→ ingest_etf_bars                 │   │
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
| **Server/Flows** | 任务编排、依赖管理 | 数据获取逻辑 |
| **Server/Tasks** | 调用 DataHub API | 直接调用 Tushare |
| **DataHub/Sources** | 数据源适配 | 调度逻辑 |

### 2.3 目录结构

```
apps/server/src/ditto_server/
├── main.py                    # FastAPI 应用（集成 Prefect Server）
├── ingestion/                 # 数据摄取模块
│   ├── config.py              # IngestionConfig 配置
│   ├── flows/                 # Prefect Flows（编排层）
│   │   └── daily_ingest.py    # daily_ingest_flow
│   └── tasks/                 # Prefect Tasks（执行层）
│       └── bars.py            # ingest_etf_bars
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

### 4.1 ingest_etf_bars Task 数据流

```
1. fetch_etf_daily(trade_date)
   └─> DataFrame[src_code, trade_date, open, high, low, close, ...]

2. resolve_identifiers_batch(src_codes, source)
   └─> {src_code: sid} 映射

3. 识别未解析的证券（sid 为 None）

4. fetch_etf_basic() 获取完整 ETF 基本信息

5. securities.register() 批量注册新证券

6. 合并 SID 映射

7. 转换数据格式（src_code → sid）

8. bars.write(df, dataset="etf_daily", run_dq_check=True)
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

# 3. 获取完整的 ETF 基本信息
etf_basic_df = hub.sources.tushare.fetch_etf_basic()

# 4. 过滤出未注册的证券
new_securities = etf_basic_df.filter(
    pl.col("src_code").is_in(unresolved)
)

# 5. 批量注册
if not new_securities.is_empty():
    hub.securities.register(
        symbols=new_securities["symbol"].to_list(),
        names=new_securities["name"].to_list(),
        source="tushare",
        asof=trade_date,
    )
```

---

## 5. 错误处理策略

### 5.1 Task 级别重试

```python
@task(
    name="ingest_etf_bars",
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # 指数退避
)
def ingest_etf_bars(trade_date: str, source: str, data_root: str) -> dict:
    ...
```

### 5.2 错误分类处理

| 错误类型 | 处理方式 | 原因 |
|----------|----------|------|
| `SourceRateLimitError` | 重试（指数退避） | API 限流，短暂问题 |
| `SourceFetchError` | 重试 3 次后失败 | 网络波动 |
| `DataSourceError` | 失败，不重试 | 配置/认证错误 |
| 新证券注册失败 | 记录告警，跳过该证券 | 部分失败不应阻断全部 |

### 5.3 返回值设计

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
    "alert_triggered": bool,     # 是否触发告警
}
```

---

## 6. 监控预警与人工重试

### 6.1 日志告警

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

### 6.2 人工重试机制

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

## 7. Token 安全配置

### 7.1 采用方案

**keyring（主）+ ~/.ditto/secrets.toml（备）**

### 7.2 优先级

1. **keyring**（推荐）：Windows 凭据管理器 / macOS Keychain / Linux Secret Service
2. **~/.ditto/secrets.toml**（备用）：用户主目录配置文件

### 7.3 配置方式

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

### 7.4 代码实现

```python
def get_tushare_token() -> str:
    """Get Tushare token with graceful fallback."""
    import keyring
    from pathlib import Path
    import tomllib

    # 1. Try keyring (recommended)
    if token := keyring.get_password("ditto", "tushare"):
        logger.debug("Token loaded from keyring", event="token_loaded", source="keyring")
        return token

    # 2. Try user config file (fallback)
    config_file = Path.home() / ".ditto" / "secrets.toml"
    if config_file.exists():
        config = tomllib.loads(config_file.read_text())
        if token := config.get("tushare", {}).get("token"):
            logger.debug("Token loaded from config file", event="token_loaded", source="secrets.toml")
            return token

    raise ValueError("Tushare token未配置，请使用 keyring 或 ~/.ditto/secrets.toml 配置")
```

### 7.5 安全性要求

- 日志中不打印完整 token
- 错误消息不包含 token 值
- 使用最小够用的 Tushare 积分级别

---

## 8. 测试策略

### 8.1 单元测试

使用 mock 隔离 DataHub：
- `test_ingest_etf_bars_success`: 正常流程
- `test_ingest_etf_bars_with_new_securities`: 新证券注册
- `test_ingest_etf_bars_partial_failure`: 部分失败
- `test_ingest_etf_bars_empty_data`: 空数据

### 8.2 集成测试（可选）

使用临时 DataHub 测试完整数据流。

---

## 9. 验收标准

### 9.1 功能验收

- [ ] `pixi run -e dev server` 启动成功
- [ ] 访问 `http://localhost:4200` 显示 Prefect UI
- [ ] 手动触发 `daily_ingest_flow` 成功执行
- [ ] 数据成功写入 `data/bars/etf_daily/YYYY.parquet`
- [ ] 新证券自动注册，日志中有记录
- [ ] 部分失败时，日志中有 `skipped_list` 告警
- [ ] 可通过 UI 或 CLI 重试失败的运行

### 9.2 代码质量

- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 单元测试覆盖率 ≥80%
- [ ] 所有日志包含 `event` 字段
- [ ] 使用 `@traced` 装饰器记录关键操作

---

## 10. 关键文件清单

| 操作 | 文件路径 |
|------|----------|
| 修改 | `apps/server/src/ditto_server/main.py` |
| 新增 | `apps/server/src/ditto_server/ingestion/config.py` |
| 新增 | `apps/server/src/ditto_server/ingestion/tasks/bars.py` |
| 新增 | `apps/server/src/ditto_server/ingestion/flows/daily_ingest.py` |
| 新增 | `apps/server/tests/unit/ingestion/test_config.py` |
| 新增 | `apps/server/tests/unit/ingestion/test_tasks.py` |
| 新增 | `apps/server/tests/unit/ingestion/test_flows.py` |
| 修改 | `pixi.toml` (添加 prefect, keyring 依赖) |
| 修改 | `packages/datahub/src/ditto_datahub/sources/tushare/client.py` (keyring 集成) |

---

## 11. 后续优化（Sprint-02）

- 完整 Flows/Tasks（calendar, securities, adj_factor）
- 定时调度（CronSchedule）
- 告警集成（Telegram/钉钉）
- 回填 Flow（backfill_flow）
- DQ 批量检查（dq_batch_flow）
