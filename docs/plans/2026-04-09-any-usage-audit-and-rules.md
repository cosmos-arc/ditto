# Any 使用审计与规范

> 审计日期：2026-04-09 | 范围：`packages/*/src/**/*.py` + `interfaces/src/**/*.py`（排除 tests + typings）

## 1. 总览

| 分类 | 源码命中数 | 占比 | 判定 |
|------|-----------|------|------|
| A. 合理使用（IO/外部边界） | ~120 | 55% | ✅ 保留 |
| B. 可改进（有更精确类型） | ~30 | 14% | ⚠️ 应修复 |
| C. 底层库限制（无法避免） | ~15 | 7% | ✅ 保留 + 注释 |
| D. `dict[str, Any]` 返回值 | ~50 | 23% | ⚠️ 分批收敛 |

---

## 2. Any 使用分类规范

### A 类：合理使用（允许）

适用于 **IO/外部边界**，数据在进入领域逻辑前已完成解析/校验/收敛。

| 子类 | 典型场景 | 示例 | 理由 |
|------|---------|------|------|
| **A1: SQL 参数** | SQLite 参数/结果 | `params: list[Any]`, `fetchone() -> tuple[Any, ...]` | SQL 参数天然异构（str/int/float/bytes 混排） |
| **A2: 通用缓存** | 泛型容器内部 | `VTTLCache[str, Any]`, `_TTLEntry.value: Any` | 缓存存储不同类型值是刻意设计 |
| **A3: 日志/指标 attributes** | 上下文字段 | `dict[str, Any]`（日志记录、OTel attributes） | 键值对异构，业界标准做法 |
| **A4: 事件 payload** | 领域事件 | `DomainEvent.payload: dict[str, Any]` | 事件系统核心价值是松耦合 |
| **A5: 第三方库适配** | Prefect/httpx 等动态对象 | `Flow[Any, Any]`, `PrefectFuture[dict[str, Any]]` | 第三方库类型不完整或设计为动态 |
| **A6: 环境配置** | env 文件加载 | `dict[str, Any]`（环境变量值） | 环境变量天然是字符串，类型在 Pydantic 解析时收敛 |

### B 类：可改进（应修复）

存在更精确的类型替代方案，使用 `Any` 是偷懒行为。

| # | 位置 | 当前 | 应改为 | 类型 |
|----|------|------|--------|------|
| B1 | `packages/infra/src/ditto_infra/foundation/observability/tracing.py:65` | `self._span: Any = None` | `Span \| None` | Union |
| B2 | `packages/infra/src/ditto_infra/foundation/observability/metrics.py:300` | `self._gauge: Any = None` | `Gauge \| None` | Union |
| B3 | `packages/infra/src/ditto_infra/foundation/observability/logging.py:65` | `_json_log_format: Any = _json_formatter` | `Callable[[LogRecord], str]` | 具体类型 |
| B4 | `data/quality/golden.py:102` | `ticker_val: Any = item_dict.get("ticker", "")` | `str \| None` | Union |
| B5 | `data/quality/golden.py:154` | `tickers_raw: Any = data_dict.get("tickers", [])` | `str \| list[str] \| None` | Union |
| B6 | `data/quality/golden.py:124` | `items: list[Any]` | `list[str \| Mapping[str, Any]]` | Union |
| B7 | `data/quality/golden.py:166` | `items_list: list[Any] = cast(...)` | 同 B6 | Union |
| B8 | `interfaces/api/routes/source.py:168` | `-> Any` | 具体数据源 Protocol 类型 | Protocol |
| B9 | `interfaces/api/routes/source.py:181` | `source: Any` | `SupportsStockDailyFetch` Protocol | Protocol |
| B10 | `engine/risk/post_trade.py:39` | `bars: dict[InstrumentId, Any]` | `dict[InstrumentId, MarketSnapshot]` 或 `Mapping` | 具体类型 |
| B11 | `data/runtime/sql_engine.py:231` | `cast(Any, table_df.to_arrow())` | `cast(pyarrow.Table, ...)` | 具体类型 |
| B12 | `engine/events.py:67` | `details: dict[str, Any]` | `dict[str, str \| int \| float]` 或 TypedDict | 收窄上界 |

### C 类：底层库限制（保留 + 注释）

`Any` 无法避免，但必须附带注释说明原因。

| 子类 | 典型场景 | 要求 |
|------|---------|------|
| **C1: cachebox 内部** | `VTTLCache[str, Any]`（泛型 DataCache 内部） | 注释：`# cachebox 不支持异构值，Any 是类型擦除妥协` |
| **C2: Polars-DuckDB 转换** | `cast(Any, ...)` 桥接类型不匹配 | 注释：`# pyarrow ↔ duckdb 类型签名不兼容` |
| **C3: 第三方 stub 不完整** | Prefect Flow/Task 返回值 | 注释：`# prefect 类型 stub 不完整` |

### D 类：`dict[str, Any]` 返回值（分批收敛）

这是项目中最大的 `Any` 聚集区。分两档处理：

#### D1：高层应收敛（Service 层对外 API）

Service 层对外返回 `dict[str, Any]` 等于放弃了类型安全。应逐步替换为 Pydantic model / dataclass / TypedDict。

| 位置 | 当前返回类型 | 建议 |
|------|------------|------|
| `MetadataService.get_instrument()` | `dict[str, Any] \| None` | → `InstrumentInfo` dataclass |
| `MetadataService.get_symbol()` | `dict[str, Any] \| None` | → `SymbolInfo` dataclass |
| `MetadataService.list_instruments()` | `list[dict[str, Any]]` | → `list[InstrumentInfo]` |
| `MetadataService.list_rebalances()` | `list[dict[str, Any]]` | → `list[RebalanceRecord]` |
| `CalendarService.save_calendar()` 参数 | `list[dict[str, Any]]` | → `list[CalendarRecord]` |
| `QualityRecordService.get_quarantine_stats()` | `list[dict[str, Any]]` | → `list[QuarantineStat]` |
| `App Quality.build_report()` | `dict[str, Any]` | → `QualityReport` dataclass |
| `App MetadataQuery.get_instrument()` | `dict[str, Any] \| None` | → `InstrumentInfo` |

#### D2：低层可容忍（Storage 内部 / Row 转换）

Storage 层从数据库读取原始行，`dict[str, Any]` 是合理中间表示，**前提是上层 Service 已做收敛**。

| 位置 | 判定 |
|------|------|
| `SQLiteClient.query_dict()` → `dict[str, Any] \| None` | ✅ Storage 内部，可保留 |
| `SQLiteClient.query_dicts()` → `list[dict[str, Any]]` | ✅ Storage 内部，可保留 |
| `_to_spec_record(row: dict[str, Any])` | ✅ Row→Model 转换函数，可保留 |
| `to_bar(row: dict[str, Any])` | ✅ Row→Model 转换函数，可保留 |

---

## 3. Any 使用决策流程

```
需要用 Any？
  │
  ├─ 是 SQL 参数/结果？
  │   └─ ✅ A1 允许
  │
  ├─ 是通用缓存/日志/指标 attributes？
  │   └─ ✅ A2/A3 允许
  │
  ├─ 是领域事件 payload？
  │   └─ ✅ A4 允许
  │
  ├─ 是第三方库适配？
  │   └─ ✅ A5 允许（附注释）
  │
  ├─ 是底层库类型不兼容？
  │   └─ ✅ C 类允许（必须注释原因）
  │
  ├─ 是延迟初始化（先 None 后赋值）？
  │   └─ ⚠️ 用 Union：`X | None`
  │
  ├─ 是 dict[str, Any] 返回值？
  │   ├─ Service 层对外 API？
  │   │   └─ ⚠️ D1 应定义为 TypedDict/dataclass
  │   └─ Storage 层内部？
  │       └─ ✅ D2 可保留
  │
  ├─ 是中间变量 .get() 结果？
  │   └─ ⚠️ 用 Union：`str | None`
  │
  ├─ 是函数参数/返回值？
  │   ├─ 有已知行为约束？
  │   │   └─ ⚠️ 用 Protocol
  │   └─ 有已知类型候选？
  │       └─ ⚠️ 用 Union
  │
  └─ 以上都不满足？
      └─ ❌ 禁止使用 Any
```

---

## 4. 替代方案速查表

| 你想表达 | 用这个 | 不用 Any |
|---------|--------|---------|
| "可能是 A 或 B" | `A \| B` | ❌ `Any` |
| "可能是某个值或空" | `T \| None` | ❌ `Any = None` |
| "有这些方法" | `Protocol` | ❌ `Any` |
| "有这些字段" | `TypedDict` | ❌ `dict[str, Any]` |
| "是这几个值之一" | `Literal["a", "b"]` | ❌ `Any` |
| "是同一种类型" | `TypeVar` | ❌ `Any` |
| "外部数据结构已知" | `Pydantic` / `dataclass` | ❌ `dict[str, Any]` |
| "数据库行" | `dict[str, Any]`（Storage 内部） | ✅ 仅限 Storage 层 |
| "日志字段" | `dict[str, Any]` | ✅ 仅限 observability |
| "SQL 参数" | `list[Any]` | ✅ 仅限 SQLite 调用 |

---

## 5. 实施建议

### 优先级 P0（立即修复，零风险）

- B1-B3：OTel 延迟初始化 + 日志 workaround（3 处，改 Union/具体类型即可）
- B4-B7：golden.py 中间变量（4 处，改 Union 即可）

### 优先级 P1（短中期，需新建类型）

- B8-B9：API 路由数据源类型（定义 Protocol）
- B10-B12：Engine 层具体类型（定义 dataclass 或 TypedDict）

### 优先级 P2（中期，分批收敛）

- D1：Service 层 `dict[str, Any]` 返回值 → TypedDict / dataclass
  - 建议按模块分批：先 MetadataService，再 QualityService，最后其他
  - 每次收敛一个 Service，确保测试通过

### 不建议改

- A 类全部（合理使用）
- C 类全部（底层限制）
- D2 类全部（Storage 内部）
- 测试代码中的 `Any`（灵活性需求）
