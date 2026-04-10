# DataHub 数据集存储结构与 source 支持分析

> 生成时间: 2026-01-23
> 目的: 梳理所有数据集的存储结构，分析 source（数据源）接口支持情况

## 一、数据集总览

Ditto 系统共有 **8 个 Store 类**，管理 **11 个主要数据集**，分为 **Parquet 文件存储**和 **SQLite 数据库存储**两类。

---

## 二、Parquet 存储的数据集（按年份分区）

### 2.1 BarsStore - 市场行情数据

| 属性 | 值 |
|------|-----|
| **Store 类** | `BarsStore` |
| **存储类型** | Parquet |
| **存储路径** | `data_root/{dataset}/YYYY.parquet` |
| **数据集** | `stock_daily`, `etf_daily` |
| **键列** | `["sid", "trade_date", "source"]` |
| **数据列** | `sid`, `trade_date`, `source`, `open`, `high`, `low`, `close`, `volume`, `amount`, `turnover` |

**source 支持**:
- ✅ 包含 source 列
- ✅ read() 支持 source 参数
- ✅ write() 接受 source
- ✅ 键列包含 source

**状态**: 🟢 完善

---

### 2.2 AdjFactorStore - 复权因子数据

| 属性 | 值 |
|------|-----|
| **Store 类** | `AdjFactorStore` |
| **存储类型** | Parquet |
| **存储路径** | `data_root/adj_factor/YYYY.parquet` |
| **数据集** | `adj_factor` |
| **键列** | `["sid", "trade_date"]` |
| **数据列** | `sid`, `trade_date`, `adj_factor` |

**source 支持**:
- ❌ 不包含 source 列
- ❌ read() 不支持 source 参数
- ❌ write() 不接受 source
- ❌ 键列不包含 source

**状态**: 🔴 **需改进**

**问题**:
- 同一 sid 在不同数据源可能有不同的复权因子
- 当前无法区分数据来源

---

### 2.3 StockStatusStore - 股票状态数据

| 属性 | 值 |
|------|-----|
| **Store 类** | `StockStatusStore` |
| **存储类型** | Parquet |
| **存储路径** | `data_root/stock_status/YYYY.parquet` |
| **数据集** | `stock_status` |
| **键列** | `["sid", "trade_date"]` |
| **数据列** | `sid`, `trade_date`, `is_suspended`, `suspend_timing`, `is_st`, `st_type`, `list_status` |

**source 支持**:
- ❌ 不包含 source 列
- ❌ read() 不支持 source 参数
- ❌ write() 不接受 source

**状态**: 🟡 合理（股票状态来自交易所，单一权威源）

---

## 三、SQLite 存储的数据集

### 3.1 CalendarStore - 交易日历

| 属性 | 值 |
|------|-----|
| **Store 类** | `CalendarStore` |
| **存储类型** | SQLite |
| **表名** | `trading_calendar` |
| **键列** | `trade_date` (PRIMARY KEY) |
| **数据列** | `trade_date`, `is_open`, `prev_trade_date`, `next_trade_date`, `week_of_year`, `month`, `quarter`, `year`, `is_week_end`, `is_month_end`, `is_quarter_end` |

**source 支持**:
- ❌ 不包含 source 列

**状态**: 🟡 合理（交易日历是全局统一的）

---

### 3.2 SecurityStore - 证券主数据（含 PIT 支持）

| 属性 | 值 |
|------|-----|
| **Store 类** | `SecurityStore` |
| **存储类型** | SQLite |
| **表名** | `security` (主表), `security_mapping` (映射表) |
| **主表键列** | `sid` (PRIMARY KEY) |
| **映射表键列** | `(source, src_code, effective_from)` (PRIMARY KEY) |
| **主表数据列** | `sid`, `symbol`, `name`, `display_name`, `exchange`, `board`, `asset_class`, `list_date`, `delist_date`, `is_st`, `is_active` |
| **映射表数据列** | `sid`, `source`, `src_code`, `effective_from`, `effective_to`, `is_primary` |

**source 支持**:
- ✅ mapping 表包含 source 列
- ✅ read() 支持 source 参数
- ✅ write() 接受 source
- ✅ 键列包含 source

**状态**: 🟢 完善，设计良好

---

### 3.3 UniverseStore - 标的池管理（含 PIT 支持）

| 属性 | 值 |
|------|-----|
| **Store 类** | `UniverseStore` |
| **存储类型** | SQLite |
| **表名** | `universe`, `universe_constituent` |
| **池定义键列** | `universe_id` (PRIMARY KEY) |
| **成分股键列** | `(universe_id, sid, effective_from)` (PRIMARY KEY) |
| **成分股数据列** | `universe_id`, `sid`, `effective_from`, `effective_to`, `weight`, `source`, `src_code` |

**source 支持**:
- ✅ 成分股表包含 source 列
- ❌ read() 不支持 source 参数
- ✅ write() 接受 source
- ❌ 键列不包含 source

**状态**: 🟡 **需改进**

**问题**:
- `universe_constituent` 有 `source` 列但不在主键中
- 无法区分同一 sid 在同一 universe 中来自不同 source 的成分

---

### 3.4 IndexWeightStore - 指数成分股权重（含 PIT 支持）

| 属性 | 值 |
|------|-----|
| **Store 类** | `IndexWeightStore` |
| **存储类型** | SQLite |
| **表名** | `index_weight` |
| **键列** | `(index_id, sid, effective_from)` (PRIMARY KEY) |
| **数据列** | `index_id`, `sid`, `effective_from`, `effective_to`, `weight` |

**source 支持**:
- ❌ 不包含 source 列
- ❌ read() 不支持 source 参数
- ❌ write() 不接受 source

**状态**: 🟡 **需改进**

**问题**:
- 同一指数在不同数据源可能有不同的成分股权重
- 当前无法区分

---

### 3.5 IngestionLogStore - 数据摄入日志

| 属性 | 值 |
|------|-----|
| **Store 类** | `IngestionLogStore` |
| **存储类型** | SQLite |
| **表名** | `ingestion_log` |
| **键列** | `(dataset, source, trade_date)` (PRIMARY KEY) |
| **数据列** | `dataset`, `source`, `trade_date`, `status`, `checksum`, `rows`, `error_code`, `error_message`, `attempts`, `first_attempt_at`, `last_attempt_at` |

**source 支持**:
- ✅ 包含 source 列
- ✅ 所有查询方法都包含 source 参数
- ✅ 写入接受 source
- ✅ 键列包含 source

**状态**: 🟢 完善

---

### 3.6 QuarantineStore - 数据质量隔离区

| 属性 | 值 |
|------|-----|
| **Store 类** | `QuarantineStore` |
| **存储类型** | SQLite |
| **表名** | `quarantine_failed_data` |
| **键列** | `id` (AUTOINCREMENT PRIMARY KEY) |
| **数据列** | `dataset`, `rule_id`, `severity`, `failed_data` (JSON), `affected_rows`, `trade_date`, `created_at` |

**source 支持**:
- ❌ 不包含 source 列
- ❌ read() 不支持 source 参数
- ❌ write() 不接受 source

**状态**: 🟡 **需改进**

**问题**:
- 无法追踪失败数据来自哪个数据源
- 影响问题排查和重试

---

## 四、source 支持情况汇总表

| 数据集 | Store 类 | 存储类型 | 键列含 source | read 支持 source | write 接受 source | 数据列含 source | 状态 |
|--------|----------|----------|--------------|------------------|------------------|----------------|------|
| stock_daily | BarsStore | Parquet | ✅ | ✅ | ✅ | ✅ | 🟢 完善 |
| etf_daily | BarsStore | Parquet | ✅ | ✅ | ✅ | ✅ | 🟢 完善 |
| adj_factor | AdjFactorStore | Parquet | ❌ | ❌ | ❌ | ❌ | 🔴 **需改进** |
| stock_status | StockStatusStore | Parquet | ❌ | ❌ | ❌ | ❌ | 🟡 合理 |
| trading_calendar | CalendarStore | SQLite | ❌ | ❌ | ❌ | ❌ | 🟡 合理 |
| security | SecurityStore | SQLite | ❌ (主表) | ✅ | ✅ | ❌ | 🟢 完善 |
| security_mapping | SecurityStore | SQLite | ✅ | ✅ | ✅ | ✅ | 🟢 完善 |
| universe | UniverseStore | SQLite | ❌ | ❌ | N/A | ❌ | 🟡 合理 |
| universe_constituent | UniverseStore | SQLite | ❌ | ❌ | ✅ | ✅ | 🟡 **需改进** |
| index_weight | IndexWeightStore | SQLite | ❌ | ❌ | ❌ | ❌ | 🟡 **需改进** |
| ingestion_log | IngestionLogStore | SQLite | ✅ | ✅ | ✅ | ✅ | 🟢 完善 |
| quarantine | QuarantineStore | SQLite | ❌ | ❌ | ❌ | ❌ | 🟡 **需改进** |

---

## 五、优先级改进建议

### 🔴 高优先级

#### AdjFactorStore 应支持 source

**问题**:
- 键列为 `["sid", "trade_date"]`，不包含 `source`
- 无法区分同一 sid 来自不同数据源的复权因子

**建议**:
1. 键列改为 `["sid", "trade_date", "source"]`
2. read() 方法添加 `source` 参数
3. write() 方法接受 source 参数

---

### 🟡 中优先级

#### UniverseStore constituent 添加 source 到键列

**问题**:
- 有 `source` 列但不在主键中
- 无法区分同一 sid 在同一 universe 中来自不同 source 的成分

**建议**:
- 主键改为 `(universe_id, sid, source, effective_from)`

#### IndexWeightStore 应支持 source

**问题**:
- 同一指数在不同数据源可能有不同的成分股权重

**建议**:
- 主键改为 `(index_id, sid, source, effective_from)`

#### QuarantineStore 添加 source 列

**问题**:
- 无法追踪失败数据来源

**建议**:
- 添加 `source` 列
- save_failed_data() 方法接受 source 参数

---

## 六、设计原则

### 标准 source 支持模式

参考 **BarsStore** 和 **SecurityStore** 的完善设计:

1. **多数据源数据**: 键列必须包含 source
2. **单数据源数据**: 不需要 source
3. **元数据/日志**: 必须包含 source 以便追溯
4. **PIT 支持**: `effective_from`, `effective_to` 与 source 配合

### 不需要 source 的数据集

- **trading_calendar**: 交易日历是全局统一的
- **stock_status**: 股票状态数据来自交易所，单一权威源
- **security (主表)**: SID 是全局唯一标识符，与 source 无关
- **universe (定义表)**: 标的池定义与数据源无关

---

## 七、相关文件

### Store 实现
- `packages/data/src/ditto_data/stores/bars_store.py`
- `packages/data/src/ditto_data/stores/adj_factor_store.py`
- `packages/data/src/ditto_data/stores/stock_status_store.py`
- `packages/data/src/ditto_data/stores/calendar_store.py`
- `packages/data/src/ditto_data/stores/security_store.py`
- `packages/data/src/ditto_data/stores/universe_store.py`
- `packages/data/src/ditto_data/stores/index_weight_store.py`
- `packages/data/src/ditto_data/stores/ingestion_log_store.py`
- `packages/data/src/ditto_data/stores/quarantine_store.py`

### Accessor 实现
- `packages/data/src/ditto_data/accessors/bars_accessor.py`
- `packages/data/src/ditto_data/accessors/adj_factor_accessor.py`
- `packages/data/src/ditto_data/accessors/calendar_accessor.py`
- `packages/data/src/ditto_data/accessors/security_accessor.py`
- `packages/data/src/ditto_data/accessors/universe_accessor.py`
- `packages/data/src/ditto_data/accessors/index_accessor.py`
- `packages/data/src/ditto_data/accessors/ingestion_log_accessor.py`
- `packages/data/src/ditto_data/accessors/quarantine_accessor.py`
