# 按股票维度摄取能力设计

> 创建日期: 2026-02-18
> 状态: ✅ 设计完成 (Ready for Implementation)

## 1. 背景与动机

### 1.1 当前限制

现有摄取流程**仅支持按交易日（trade_date）驱动**的批量获取模式：
- 每次摄取获取某一天所有股票的数据
- 不支持按单只股票+时间范围的精确摄取
- 修复个股数据异常时，需要重新拉取整天的数据

### 1.2 目标

1. **新增按股票+时间段摄取能力**：支持对单只股票的历史数据回填
2. **提供 Source API**：直接查询 Source 层（经过 Adapter 转换），用于验证 ETL 逻辑
3. **修复命名规范问题**：统一 `ticker` / `source_ticker` / `instrument_id` 命名

---

## 2. 需求确认

### 2.1 触发方式

| 方式 | 用途 | 状态 |
|------|------|------|
| **CLI 命令** | 手动触发回填 | 🆕 新增 |
| **Prefect 任务** | 临时修复个股异常数据 | 🆕 新增 |
| **REST API** | 直接查询 Source 层 | 🆕 新增 |

### 2.2 CLI 命令示例

```bash
# 按股票+时间段摄取
pixi run ingest ticker \
  --source-ticker 000001.SZ \
  --dataset stock_daily \
  --start 2024-01-01 \
  --end 2024-01-31

# 支持多种标识符
pixi run ingest ticker \
  --ticker 000001 \
  --dataset stock_daily \
  --start 2024-01-01 \
  --end 2024-01-31

pixi run ingest ticker \
  --instrument-id 1000001 \
  --dataset stock_daily \
  --start 2024-01-01 \
  --end 2024-01-31
```

### 2.3 REST API 设计

```
GET /api/source/{dataset}?source_ticker=000001.SZ&start=2024-01-01&end=2024-01-31

功能：直接查询 Source（经过 Adapter 转换）
返回：Source Schema 标准结构
用途：验证 ETL 逻辑、调试适配器、数据探索
```

**不在范围内**：
- ❌ 原始 Tushare 透传 API（用户直接调用 Tushare 接口）
- ❌ 自动检测异常数据
- ❌ 前端 UI

### 2.4 支持的数据类型

**全部数据集**：按股票维度支持所有相关数据集
- 行情：STOCK_DAILY, ETF_DAILY, INDEX_DAILY
- 复权：ADJ_FACTOR, FUND_ADJ
- 估值：VALUATION_METRICS, MARGIN_TRADING, PLEDGE_RATIO
- 财务：BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, DIVIDEND
- 状态：STOCK_STATUS

### 2.5 标识符支持

| 标识符 | 格式 | 示例 | 说明 |
|--------|------|------|------|
| `instrument_id` | 整数 | `1000001` | 系统内部唯一标识 |
| `source_ticker` | 字符串 | `000001.SZ` | 数据源原始代码（带交易所后缀） |
| `ticker` | 字符串 | `000001` | 裸代码（无后缀） |

---

## 3. 架构设计

### 3.0 数据流与映射关系

**关键映射：`source_ticker` → `instrument_id`**

```
┌─────────────────────────────────────────────────────────────┐
│  Source 层（TushareSource）                                 │
│  返回：source_ticker (如 "000001.SZ")                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Coordinator 层（IngestionCoordinator）                     │
│  映射：source_ticker → instrument_id                        │
│  通过：InstrumentMetadataStore.get_instrument_id()          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Store 层（ParquetStore）                                   │
│  写入：instrument_id (整数主键)                              │
└─────────────────────────────────────────────────────────────┘
```

**日期字段差异**：

| 数据类型 | 日期字段 | 说明 |
|---------|---------|------|
| 行情类（stock_daily, etf_daily, index_daily） | `trade_date` | 交易日期 |
| 复权类（adj_factor, fund_adj） | `trade_date` | 交易日期 |
| 估值类（valuation_metrics, margin_trading） | `trade_date` | 交易日期 |
| 财务类（balance_sheet, income_statement, cash_flow） | `ann_date` | 公告日期（PIT） |
| 分红类（dividend） | `ann_date` | 公告日期 |
| 状态类（stock_status） | `trade_date` | 交易日期 |

> **注意**：财务数据按股票查询时，时间范围参数对应 `ann_date` 而非 `trade_date`。

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        触发层                                │
├──────────────────┬──────────────────────────────────────────┤
│   CLI            │   Prefect Flow                           │
│   ingest tick    │   backfill_single_stock                  │
│   --ticker       │   (临时修复个股)                          │
│   --dataset      │                                          │
│   --start --end  │                                          │
└──────────────────┴──────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  IngestionCoordinator                        │
├─────────────────────────────────────────────────────────────┤
│  ingest_by_date(dataset, trade_date)    # 现有              │
│  ingest_by_ticker(dataset, ticker_params) # 新增            │
│      ├─ 标识符解析（ticker/source_ticker/instrument_id）     │
│      ├─ 调用 Source.fetch_xxx()                             │
│      └─ 复用 DataWriter / ResultHandler                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     TushareSource                            │
├─────────────────────────────────────────────────────────────┤
│  fetch_xxx(trade_date=...)              # 现有：按日期       │
│  fetch_xxx(source_ticker=..., ...)      # 新增：按股票       │
│      └─ 同一方法，参数组合决定查询模式                         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 DataSource 接口扩展（已确认）

**设计决策**：通过**参数扩展复用现有方法**，而非新增方法系列。

```python
# 扩展前
def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:

# 扩展后（向后兼容）
def fetch_stock_daily(
    self,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
```

**调用模式**：
```python
# 模式1：按日期批量（现有，向后兼容）
source.fetch_stock_daily(trade_date="2024-01-15")

# 模式2：按股票+时间段（新增）
source.fetch_stock_daily(source_ticker="000001.SZ", start_date="2024-01-01", end_date="2024-01-31")
```

**参数校验规则**：
- `trade_date` 和 `source_ticker` 互斥，不能同时指定
- 必须指定其中之一

**需要扩展的方法**：

| 方法 | 按日期 | 按股票+时间段 | 备注 |
|------|--------|--------------|------|
| `fetch_stock_daily` | ✅ | 🆕 | |
| `fetch_etf_daily` | ✅ | 🆕 | |
| `fetch_index_daily` | ✅ | ✅ (已有) | 参数名改为 `source_tickers` |
| `fetch_adj_factor` | ✅ | 🆕 | |
| `fetch_fund_adj` | ✅ | 🆕 | |
| `fetch_stock_status` | ✅ | 🆕 | |
| `fetch_valuation_metrics` | ✅ | 🆕 | |
| `fetch_margin_trading` | ✅ | 🆕 | |
| `fetch_pledge_ratio` | ✅ | 🆕 | |
| `fetch_balance_sheet` | ✅ | 🆕 | 使用 `ann_date` |
| `fetch_income_statement` | ✅ | 🆕 | 使用 `ann_date` |
| `fetch_cash_flow` | ✅ | 🆕 | 使用 `ann_date` |
| `fetch_dividend` | ✅ | 🆕 | 使用 `ann_date` |

**不需要扩展**：
- `fetch_calendar` - 无股票维度
- `fetch_stock_basic` / `fetch_etf_basic` / `fetch_index_basic` - 元数据，无时间维度

---

## 4. 命名规范（已确认）

### 4.1 术语定义

| 术语 | 定义 | 格式 | 示例 |
|------|------|------|------|
| `instrument_id` | 系统内部唯一标识 | INTEGER | `1000001` |
| `source_ticker` | 数据源原始代码（带后缀） | `{code}.{exchange}` | `000001.SZ` |
| `ticker` | 裸代码（无后缀） | STRING | `000001` |
| `exchange` | 标准化交易所代码 | STRING | `SZSE`, `SSE` |

### 4.2 禁用术语

| 术语 | 原因 | 替代 |
|------|------|------|
| `symbol` | 语义不明确 | 使用 `ticker` |
| `ts_code` | 仅用于 Tushare API 边界 | 内部使用 `source_ticker` |
| `code` | 过于通用 | 明确使用 `ticker` 或 `source_ticker` |

### 4.3 转换规则

```
Tushare API (ts_code)  ──rename──>  source_ticker (内部使用)
                                               │
                                               ├── split(".")[0] ──> ticker
                                               │
                                               └── split(".")[1] ──> exchange（需转换）
```

### 4.4 需要修复的位置

| 文件 | 问题 | 修复 |
|------|------|------|
| `apps/port/tests/conftest.py` | 使用 `symbol` | 改为 `ticker` 或 `source_ticker` |
| `.claude/rules/python-test.md` | 示例使用 `symbol` | 改为 `ticker` |
| `docs/sprints/sprint-04-backtest-risk.md` | 使用 `symbol` | 改为 `ticker` |

---

## 5. 存储层分析（已确认）

### 5.1 现有存储机制

| 维度 | 设计 |
|------|------|
| **分区策略** | `YearlyPartition` - 按年分区（2024.parquet） |
| **写入模式** | **合并写入** - `_merge_with_existing()` |
| **主键** | `["instrument_id", "trade_date"]` |
| **去重策略** | `OnDuplicate` 枚举：`ERROR` / `KEEP_FIRST` / `KEEP_LAST` |

### 5.2 关键结论

**无需新增写入模式**！现有 `ParquetStore.write()` 已正确处理合并逻辑：
- 读取现有分区数据
- 按主键合并去重
- 原子写入

### 5.3 Coordinator 写入方式

```python
def ingest_by_ticker(
    self,
    dataset: Dataset,
    params: TickerIngestParams,
) -> IngestionResult:
    """按股票+时间段摄取数据."""

    # 1. 获取数据（可能跨多年）
    df = self._fetch_by_ticker(dataset, params)

    # 2. 映射 source_ticker → instrument_id
    df = self._map_to_instrument_id(df, params.source_ticker)

    # 3. 按年份分组写入（复用现有逻辑）
    results: list[WriteResult] = []
    for (year,), year_df in df.group_by(pl.col("trade_date").dt.year()):
        result = self._writer.write(
            dataset=dataset,
            df=year_df,
            year=int(year),  # year 是 int 类型
            on_duplicate=OnDuplicate.KEEP_LAST,  # 新数据覆盖旧数据
        )
        results.append(result)

    return self._aggregate_results(results)

def _map_to_instrument_id(
    self,
    df: pl.DataFrame,
    source_ticker: str,
) -> pl.DataFrame:
    """将 source_ticker 映射为 instrument_id."""
    instrument_id = self._metadata_store.get_instrument_id(source_ticker)
    return df.with_columns(
        pl.lit(instrument_id).alias("instrument_id")
    )
```

---

## 6. 标识符解析与冲突处理（已确认）

### 6.1 解析优先级

```
instrument_id > source_ticker > ticker
```

### 6.2 Ticker 歧义处理

当裸 `ticker`（如 `000001`）匹配多个标的时，抛出 `AmbiguousTickerError`：

```python
class AmbiguousTickerError(Exception):
    """Ticker 不唯一异常."""

    def __init__(self, ticker: str, matches: list[dict]) -> None:
        self.ticker = ticker
        self.matches = matches  # [{source_ticker, instrument_id, name}, ...]
        ...
```

### 6.3 CLI 错误输出示例

```bash
$ pixi run ingest ticker --ticker 000001 --dataset stock_daily --start 2024-01-01 --end 2024-01-31

❌ 错误: Ticker '000001' 存在歧义，匹配到 2 个标的：
  - 000001.SZ (ID: 1000001, 名称: 平安银行)
  - 000001.SH (ID: 1000002, 名称: 上证指数)

请使用 --source-ticker 或 --instrument-id 明确指定。
示例：
  pixi run ingest ticker --source-ticker 000001.SZ ...
  pixi run ingest ticker --instrument-id 1000001 ...
```

### 6.4 解析函数

```python
def resolve_source_ticker(
    ticker: str | None,
    source_ticker: str | None,
    instrument_id: int | None,
    metadata_store: InstrumentMetadataStore,
) -> str:
    """
    将任意标识符解析为 source_ticker.

    Raises:
        ValueError: 未提供任何标识符
        AmbiguousTickerError: ticker 不唯一
        NotFoundError: 标识符无效
    """
    if instrument_id is not None:
        return metadata_store.get_source_ticker(instrument_id)

    if source_ticker is not None:
        return source_ticker

    if ticker is not None:
        matches = metadata_store.find_by_ticker(ticker)
        if len(matches) == 0:
            raise NotFoundError(f"未找到 ticker '{ticker}'")
        elif len(matches) == 1:
            return matches[0]["source_ticker"]
        else:
            raise AmbiguousTickerError(ticker=ticker, matches=matches)

    raise ValueError("必须指定 ticker / source_ticker / instrument_id 之一")
```

---

## 7. CLI 命令详细设计（已确认）

### 7.1 命令结构

```bash
pixi run ingest ticker [OPTIONS]
```

### 7.2 参数定义

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--ticker` | str | * | 裸代码，如 `000001` |
| `--source-ticker` | str | * | 数据源代码，如 `000001.SZ` |
| `--instrument-id` | int | * | 内部 ID，如 `1000001` |
| `--dataset` | str | ✅ | 数据集名称 |
| `--start` | date | ✅ | 开始日期 (YYYY-MM-DD) |
| `--end` | date | ✅ | 结束日期 (YYYY-MM-DD) |
| `--dry-run` | flag | | 仅获取数据，不写入 |

> *三选一，优先级：`--instrument-id` > `--source-ticker` > `--ticker`

### 7.3 使用示例

```bash
# 按裸代码回填
pixi run ingest ticker --ticker 000001 --dataset stock_daily --start 2024-01-01 --end 2024-01-31

# 按 source_ticker 回填
pixi run ingest ticker --source-ticker 000001.SZ --dataset valuation_metrics --start 2024-01-01 --end 2024-06-30

# 预览模式（不写入）
pixi run ingest ticker --ticker 600519 --dataset stock_daily --start 2024-01-01 --end 2024-01-31 --dry-run
```

---

## 8. REST API 详细设计（已确认）

### 8.1 端点

```
GET /api/source/{dataset}
```

### 8.2 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `dataset` | path | ✅ | 数据集名称，如 `stock_daily` |
| `source_ticker` | query | * | 数据源代码，如 `000001.SZ` |
| `ticker` | query | * | 裸代码，如 `000001` |
| `instrument_id` | query | * | 内部 ID |
| `start_date` | query | ✅ | 开始日期 (YYYY-MM-DD) |
| `end_date` | query | ✅ | 结束日期 (YYYY-MM-DD) |

> *三选一

### 8.3 响应格式

```python
class SourceDataResponse(BaseModel):
    """Source API 响应."""
    dataset: str
    source_ticker: str
    start_date: date
    end_date: date
    records: list[dict[str, Any]]  # Source Schema 数据
    row_count: int
    query_time_ms: float
    source: str = "tushare"
```

### 8.4 限流

Tushare 底层已有限流，上层暂不额外处理。

---

## 9. Prefect 任务设计（已确认）

### 9.0 模块位置

```python
# apps/port/src/ditto_port/flows/backfill.py

from datetime import date

from prefect import flow

from ditto_datahub.models import Dataset
from ditto_port.services.ingestion.coordinator import (
    IngestionCoordinator,
    TickerIngestParams,
    get_coordinator,
)
```

### 9.1 单股票回填

```python
@flow(name="backfill_single_stock")
def backfill_single_stock(
    source_ticker: str,
    dataset: str,
    start_date: str,
    end_date: str,
) -> dict:
    """回填单只股票数据."""
    coordinator = get_coordinator()
    params = TickerIngestParams(
        source_ticker=source_ticker,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
    )
    result = coordinator.ingest_by_ticker(Dataset(dataset), params)
    return result.to_dict()
```

### 9.2 批量回填

```python
@flow(name="backfill_multiple_stocks")
def backfill_multiple_stocks(
    source_tickers: list[str],
    dataset: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """批量回填多只股票数据（并行）."""
    results = []
    for ticker in source_tickers:
        result = backfill_single_stock.submit(
            source_ticker=ticker,
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
        )
        results.append(result)
    return [r.result() for r in results]
```

---

## 10. 测试策略（已确认）

### 10.1 测试层次

| 层次 | 测试类型 | 重点 |
|------|---------|------|
| **Unit** | 单元测试 | 标识符解析、参数校验、冲突处理 |
| **Integration** | 集成测试 | Source 层按股票查询、合并写入 |
| **E2E** | 端到端测试 | CLI → Coordinator → Source → Store 完整链路 |

### 10.2 关键测试用例

**单元测试 - 标识符解析**：
- `test_resolve_by_instrument_id` - instrument_id 优先级最高
- `test_resolve_by_source_ticker` - source_ticker 直接返回
- `test_resolve_by_unique_ticker` - 唯一 ticker 正常解析
- `test_ambiguous_ticker_raises_error` - 歧义 ticker 抛出异常
- `test_no_identifier_raises_error` - 无标识符抛出错误

**集成测试 - 合并写入**：
- `test_merge_write_preserves_other_stocks` - 合并写入不影响其他股票

### 10.3 覆盖率要求

| 模块 | 目标覆盖率 |
|------|-----------|
| 标识符解析 | 100%（分支覆盖） |
| Coordinator `ingest_by_ticker` | ≥ 90% |
| Source 按股票查询 | ≥ 80% |

---

## 11. 实现任务清单

### 依赖关系

```
Phase 1 (命名规范) ─────────────────────────────────────────┐
                                                              │
Phase 2 (DataSource 接口) ───────────────────────────────────┤
                                                              │
Phase 3 (Coordinator) ◄──────────────────────────────────────┤
         │                                                    │
         ├─► Phase 4 (CLI 命令)                               │
         │                                                    │
         ├─► Phase 5 (REST API)                               │
         │                                                    │
         └─► Phase 6 (Prefect 任务)                           │
                                                              │
Phase 7 (测试) ◄─────────────────────────────────────────────┘
```

> **并行可能**：Phase 4/5/6 可以并行开发，都依赖 Phase 3 完成。

### 11.1 Phase 1: 命名规范修复

- [ ] 修复 `apps/port/tests/conftest.py` 中的 `symbol` 使用
- [ ] 更新 `.claude/rules/python-test.md` 示例
- [ ] 添加命名规范到 `.claude/rules/naming.md`

### 11.2 Phase 2: DataSource 接口扩展

- [ ] 扩展 `DataSource` 基类方法签名
- [ ] 实现 `TushareSource` 按股票查询
- [ ] 更新各 Adapter 实现参数路由

### 11.3 Phase 3: Coordinator 扩展

- [ ] 新增 `TickerIngestParams` 数据类
- [ ] 新增 `ingest_by_ticker()` 方法
- [ ] 新增 `_map_to_instrument_id()` 方法（source_ticker → instrument_id 映射）
- [ ] 新增 `AmbiguousTickerError` 异常
- [ ] 在 `InstrumentMetadataStore` 新增 `get_instrument_id()` 和 `find_by_ticker()` 方法

### 11.4 Phase 4: CLI 命令

- [ ] 新增 `pixi run ingest ticker` 命令
- [ ] 实现 `--dry-run` 预览模式
- [ ] 添加错误输出格式化

### 11.5 Phase 5: REST API

- [ ] 新增 `/api/source/{dataset}` 端点
- [ ] 实现 `SourceDataResponse` 模型
- [ ] 添加 API 文档

### 11.6 Phase 6: Prefect 任务

- [ ] 新增 `backfill_single_stock` Flow
- [ ] 新增 `backfill_multiple_stocks` Flow

### 11.7 Phase 7: 测试

- [ ] 单元测试：标识符解析
- [ ] 集成测试：Source 按股票查询
- [ ] 集成测试：合并写入
- [ ] E2E 测试：CLI 完整链路

---

## 12. 参考资料

- [Index Ingestion Design](./2026-02-18-index-ingestion-design.md)
- [E2E Validation Design](./2026-02-17-e2e-validation-design.md)
