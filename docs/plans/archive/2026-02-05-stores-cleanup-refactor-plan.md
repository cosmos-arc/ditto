# DataHub stores 目录清理与重构计划

> **创建日期**: 2026-02-05
> **状态**: Draft
> **目标**: 完成 stores 到 domains 的迁移，清理废弃代码，更新上层依赖

---

## 一、当前状态总结

### 1.1 已完成迁移的域

| 域 | 状态 | 测试覆盖率 |
|----|------|-----------|
| **Market** | ✅ 完全迁移 | 93.48%+ |
| **Metadata** | ✅ 完全迁移 | 需验证 |
| **Fundamental** | ✅ 新域实现 | 需验证 |
| **Capital** | ✅ 新域实现 | 需验证 |
| **Macro** | ✅ 新域实现 | 需验证 |
| **Features** | ✅ 新域实现 | 需验证 |
| **Factors** | ✅ 新域实现 | 需验证 |

### 1.2 stores 目录现状

**保留的基础设施**（`stores/base/`）:
- `base_store.py` - 基类抽象
- `parquet_store.py` - Parquet 存储基类
- `sqlite_store.py` - SQLite 存储基类
- `partition_strategy.py` - 分区策略

**待清理的废弃文件**:
- `adj_factor_store.py` → 已迁移至 `domains/market/*/adj/`
- `bars_store.py` → 已迁移至 `domains/market/*/bars/`
- `calendar_store.py` → 已迁移至 `domains/metadata/calendar/`
- `parquet_store_base.py` → 功能已被 `base/parquet_store.py` 替代
- `universe_store.py` → 已迁移至 `domains/metadata/`

**待迁移的非域数据**:
- `index_weight_store.py` → 迁移至 `domains/market/index/`
- `ingestion_log.py` → 迁移至 `runtime/ingestion/`
- `quarantine_store.py` → 迁移至 `runtime/quality/`
- `quality/comparison_store.py` → 迁移至 `runtime/quality/`

**保留的基础设施**:
- `sqlite_client.py` - SQLite 客户端（基础设施）

### 1.3 上层依赖问题

**accessors/ 层**（7 个文件 - **完全移除**）:
- `adj_factor_accessor.py` → ❌ **移除**，Port 层直接使用 `StockAdjFactorStore` + FileLock
- `bars_accessor.py` → ❌ **移除**，使用 `MarketService.get_bars()`
- `index_accessor.py` → ❌ **移除**，使用 `MarketService.get_constituents()`
- `universe_accessor.py` → ❌ **移除**，使用 `MetadataService`
- `comparison_accessor.py` → ❌ **移除**，直接使用 `ComparisonStore`
- `quarantine_accessor.py` → ❌ **移除**，直接使用 `QuarantineStore`
- `ingestion_log_accessor.py` → ❌ **移除**，直接使用 `IngestionLogStore`

**Port 层注册** (`registry/datahub.py`):
- ❌ 移除所有 accessor provider
- ✅ 只保留 domain services + domain stores
- ✅ 写入操作：直接在 DataHub 中提供便捷方法（封装 FileLock）

---

## 二、重构计划

### 阶段 1: IndexWeightStore 迁移（1-2 天）

**目标**: 将 `index_weight_store.py` 迁移至 `domains/market/index/`

| 步骤 | 任务 | 文件 |
|------|------|------|
| 1.1 | 检查 `index_weight_store.py` 的使用情况 | `stores/index_weight_store.py` |
| 1.2 | 在 `domains/market/index/` 创建新实现 | `domains/market/index/weight/weight_store.py` |
| 1.3 | 更新 `IndexAccessor` 使用新 store | `accessors/index_accessor.py` |
| 1.4 | 运行测试验证 | `tests/unit/stores/test_index_weight_store_unit.py` |
| 1.5 | 删除旧文件 | `stores/index_weight_store.py` |

---

### 阶段 2: IngestionLog 和 QuarantineStore 迁移（1-2 天）

**目标**: 将非域数据迁移至 `runtime/` 目录

| 步骤 | 任务 | 文件 |
|------|------|------|
| 2.1 | 将 `ingestion_log.py` 迁移至 `runtime/ingestion/` | `runtime/ingestion/ingestion_log_store.py` |
| 2.2 | 将 `quarantine_store.py` 迁移至 `runtime/quality/` | `runtime/quality/quarantine_store.py` |
| 2.3 | 将 `quality/comparison_store.py` 迁移至 `runtime/quality/` | `runtime/quality/comparison_store.py` |
| 2.4 | 更新 accessor 导入路径 | `accessors/*.py` |
| 2.5 | 更新 Port 层注册 | `registry/datahub.py` |
| 2.6 | 运行测试验证 | `tests/unit/stores/test_*_unit.py` |
| 2.7 | 删除旧文件 | `stores/ingestion_log.py`, `stores/quarantine_store.py`, `stores/quality/` |

---

### 阶段 3: 完全移除 Accessor 层（2-3 天）

**目标**: Port 层直接使用 Domain Services 和 Stores，移除 Accessor 中间层

**设计决策**：
- ✅ **读取操作**: 直接使用 Domain Services（`MarketService`, `MetadataService`）
- ✅ **写入操作**: 直接使用 Domain Stores（带 FileLockManager）
- ❌ **移除**: 所有 Accessor 层文件

| 步骤 | 任务 | 替换方案 |
|------|------|----------|
| 3.1 | 在 `MarketService` 中添加写入方法 | `write_bars()`, `write_adj_factor()` |
| 3.2 | 在 `RuntimeService` 中添加写入方法 | `save_ingestion_log()` |
| 3.3 | 移除 `BarsAccessor` | → `MarketService.get_bars()` / `write_bars()` |
| 3.4 | 移除 `AdjFactorAccessor` | → `MarketService.write_adj_factor()` |
| 3.5 | 移除 `UniverseAccessor` | → `MetadataService` |
| 3.6 | 移除 `IndexAccessor` | → `MarketService.get_constituents()` |
| 3.7 | 移除 `QuarantineAccessor` | → 直接使用 `QuarantineStore` |
| 3.8 | 移除 `ComparisonAccessor` | → 直接使用 `ComparisonStore` |
| 3.9 | 移除 `IngestionLogAccessor` | → `RuntimeService.save_ingestion_log()` |
| 3.10 | 更新 DataHub Facade 方法 | 转发到对应 Service |
| 3.11 | 更新 Port 层注册 | 移除 accessor provider |
| 3.12 | 更新 `data_writer.py` | 使用 Service 的写入方法 |
| 3.13 | 运行 Port 层集成测试 | 验证无破坏 |

**实现细节**：

#### 3.2 实现细节：Accessor 移除方案

**当前架构** (需要移除 Accessor 中间层):
```
Port 层调用 → DataHub → Accessor → Store
                     ↓
                  (多余的中间层)
```

**读取操作** - 直接使用 Domain Services:

当前 `DataHub.get_bars()` 实现：
```python
# hub.py - 当前代码
def get_bars(self, params: BarsQuerySpec) -> pl.DataFrame:
    # ... 解析标识符 ...
    return self.bars.get(query)  # ← 委托给 BarsAccessor
```

替换为：
```python
# hub.py - 新实现
def get_bars(self, params: BarsQuerySpec) -> pl.DataFrame:
    # ... 解析标识符 ...

    # 直接使用 MarketService，移除 BarsAccessor 中间层
    query = MarketBarsQuery(
        sids=resolved_sids,
        start=params.start,
        end=params.end,
        adj=AdjType(params.adj),
        asof=params.asof,
        asset_class=params.asset_class,
        with_symbol=params.with_symbol,
        with_status=params.with_status,
        raw=params.raw,
    )
    return self.market.get_bars(query)  # ← 直接使用 MarketService
```

**写入操作** - 在对应 Service 中提供写入方法:

```python
# domains/market/market_service.py - 新增写入方法
class MarketService:
    """Market 域统一服务（读 + 写）。"""

    def __init__(
        self,
        # ... stores ...
        file_lock: FileLockManager,  # 新增：用于并发写入保护
    ) -> None:
        # ...
        self._file_lock = file_lock

    @traced("market.write_adj_factor")
    def write_adj_factor(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        写入复权因子数据（替代 AdjFactorAccessor）。

        内部使用 StockAdjFactorStore + FileLock 保护。
        """
        store = self._stock_adj_store if dataset == "adj_factor" else self._etf_adj_store
        lock_name = f"adj_factor_write_{dataset}_{year}"

        with self._file_lock.acquire(lock_name, timeout=60.0):
            result = store.write(dataset, df, year, on_duplicate=on_duplicate)

        M.data_records.add(len(df), {"dataset": dataset, "operation": "write"})
        return result

    @traced("market.write_bars")
    def write_bars(
        self,
        df: pl.DataFrame,
        year: int,
        dataset: str = "stock_daily",
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """写入 K 线数据（替代 BarsAccessor.write）。"""
        store_map = {
            "stock_daily": self._stock_bars_store,
            "etf_daily": self._etf_bars_store,
            "index_daily": self._index_bars_store,
        }
        store = store_map.get(dataset)
        if store is None:
            raise ValueError(f"Unknown dataset: {dataset}")

        lock_name = f"bars_write_{dataset}_{year}"

        with self._file_lock.acquire(lock_name, timeout=60.0):
            result = store.write(dataset, df, year, on_duplicate=on_duplicate)

        M.data_records.add(len(df), {"dataset": dataset, "operation": "write"})
        return result
```

**DataHub 只作为 Facade 转发**:
```python
# hub.py - DataHub 只转发到 Service
def write_adj_factor(self, dataset, df, year, on_duplicate):
    """写入复权因子（转发到 MarketService）。"""
    return self.market.write_adj_factor(dataset, df, year, on_duplicate)

def write_bars(self, df, year, dataset, on_duplicate):
    """写入 K 线（转发到 MarketService）。"""
    return self.market.write_bars(df, year, dataset, on_duplicate)

def save_ingestion_log(self, log):
    """保存摄取日志（转发到 RuntimeService 或直接 Store）。"""
    # ingestion_log 可能单独放在 runtime/ 模块
    return self._ingestion_log_store.save_log(log)
```

**Service 依赖更新**:
```python
# registry/datahub.py - Provider 更新
@provide
def market_query_service(
    self,
    # ... stores ...
    file_lock: FileLockManager,  # 新增：注入 FileLock
) -> MarketService:
    """Market 查询服务（支持读写）。"""
    return MarketService(
        # ... stores ...
        file_lock=file_lock,
    )
```

---

### 阶段 4: Port 层注册清理（1 天）

**目标**: 移除 `registry/datahub.py` 中废弃 stores 的注册

| 步骤 | 任务 | 说明 |
|------|------|------|
| 4.1 | 移除 `bars_store` 注册 | 已被 `stock_bars_store` 等替代 |
| 4.2 | 移除 `adj_factor_store` 注册 | 已被 `stock_adj_store` 等替代 |
| 4.3 | 移除 `calendar_store` 注册 | 已被 `calendar_store` (metadata) 替代 |
| 4.4 | 移除 `universe_store` 注册 | 已被 `universe_store` (metadata) 替代 |
| 4.5 | 移除 `index_weight_store` 注册 | 已迁移至 domains |
| 4.6 | 更新 `datahub` provider 依赖注入 | 只保留 domains 相关的 stores |
| 4.7 | 运行 Port 层完整测试 | 验证无破坏 |

---

### 阶段 5: 废弃文件清理（1 天）

**目标**: 删除 stores 目录下所有废弃文件

| 文件 | 状态 | 操作 |
|------|------|------|
| `stores/adj_factor_store.py` | 🔴 废弃 | **删除** |
| `stores/bars_store.py` | 🔴 废弃 | **删除** |
| `stores/calendar_store.py` | 🔴 废弃 | **删除** |
| `stores/index_weight_store.py` | 🔴 已迁移 | **删除** |
| `stores/ingestion_log.py` | 🔴 已迁移 | **删除** |
| `stores/parquet_store_base.py` | 🔴 废弃 | **删除** |
| `stores/quarantine_store.py` | 🔴 已迁移 | **删除** |
| `stores/universe_store.py` | 🔴 废弃 | **删除** |
| `stores/quality/` | 🔴 已迁移 | **删除目录** |

**保留的文件**:
- `stores/base/` - 基础存储基类（保留）
- `stores/sqlite_client.py` - SQLite 客户端（保留）
- `stores/__init__.py` - 更新导出列表

---

### 阶段 6: 验证与测试（1-2 天）

**目标**: 确保重构后所有功能正常

| 步骤 | 任务 | 验证方式 |
|------|------|----------|
| 6.1 | 运行 datahub 单元测试 | `pixi run -e dev pytest packages/data/tests/unit/` |
| 6.2 | 运行 datahub 集成测试 | `pixi run -e dev pytest packages/data/tests/integration/` |
| 6.3 | 运行 Port 层测试 | `pixi run -e dev pytest apps/port/tests/` |
| 6.4 | 类型检查 | `pixi run -e dev type` |
| 6.5 | Lint 检查 | `pixi run -e dev lint` |
| 6.6 | 更新文档 | 更新 `stores/README.md` |

---

## 三、重构后的架构

### 3.1 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                       Port 层 (应用层)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DataHub (Facade - 转发到对应 Service):                       │
│  ├─ hub.get_bars()          → market.get_bars()              │
│  ├─ hub.write_bars()        → market.write_bars()            │
│  ├─ hub.write_adj_factor()  → market.write_adj_factor()      │
│  ├─ hub.get_securities()    → metadata.get_securities()      │
│  └─ hub.save_ingestion_log() → runtime.save_ingestion_log()  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Services 层 (读 + 写)              │
├─────────────────────────────────────────────────────────────┤
│  MarketService                                               │
│  ├─ get_bars()           读取 K线                            │
│  ├─ write_bars()         写入 K线 (封装 FileLock)            │
│  ├─ write_adj_factor()   写入复权因子 (封装 FileLock)        │
│  └─ get_constituents()   读取指数成分股                      │
│                                                              │
│  MetadataService                                             │
│  ├─ get_securities()     读取证券数据                        │
│  └─ resolve_sid()        标识符解析                          │
│                                                              │
│  RuntimeService (新增)                                        │
│  └─ save_ingestion_log() 保存摄取日志                        │
│                                                              │
│  FundamentalService │ CapitalService │ MacroService │ ...    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Stores 层                          │
├─────────────────────────────────────────────────────────────┤
│  domains/market/stock/bars/bars_store.py                    │
│  domains/market/stock/adj/adj_factor_store.py               │
│  domains/metadata/calendar/calendar_store.py                │
│  runtime/ingestion/ingestion_log_store.py                   │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    基础设施 (stores/)                        │
├─────────────────────────────────────────────────────────────┤
│  stores/base/parquet_store.py    ← Parquet 基类              │
│  stores/base/sqlite_store.py     ← SQLite 基类               │
│  stores/sqlite_client.py         ← SQLite 客户端             │
│  FileLockManager                 ← 并发写入保护               │
└─────────────────────────────────────────────────────────────┘
```

**设计原则**：
- ✅ **Service 职责完整**: 每个域的 Service 提供该域的**读 + 写**操作
- ✅ **FileLock 封装**: Service 内部封装 FileLock，对外简化接口
- ✅ **DataHub 薄 Facade**: 只做转发，不包含业务逻辑
- ✅ **职责清晰**: Port → Service → Store，层次分明

### 3.2 清理后的目录结构

```
packages/data/src/ditto_data/
├── stores/                              # 只保留基础设施
│   ├── base/
│   │   ├── __init__.py
│   │   ├── base_store.py               # 基类抽象
│   │   ├── parquet_store.py            # Parquet 存储基类
│   │   ├── sqlite_store.py             # SQLite 存储基类
│   │   └── partition_strategy.py       # 分区策略
│   ├── sqlite_client.py                # SQLite 客户端
│   └── __init__.py                     # 只导出基础设施
│
├── domains/                            # 所有域数据存储
│   ├── market/
│   │   ├── stock/bars/bars_store.py
│   │   ├── stock/adj/adj_factor_store.py
│   │   ├── stock/status/status_store.py
│   │   ├── etf/bars/bars_store.py
│   │   ├── etf/adj/adj_factor_store.py
│   │   ├── etf/nav/nav_store.py
│   │   ├── etf/status/status_store.py
│   │   ├── index/bars/bars_store.py
│   │   ├── index/constituent/constituent_store.py
│   │   ├── index/weight/weight_store.py    # ← 新增
│   │   └── market_service.py               # Market 域服务
│   ├── metadata/
│   │   ├── calendar/calendar_store.py
│   │   ├── identity/identity_store.py
│   │   ├── industry/industry_basic_store.py
│   │   ├── industry/industry_mapping_store.py
│   │   ├── instrument/instrument_store.py
│   │   └── metadata_service.py             # Metadata 域服务
│   ├── fundamental/
│   │   └── fundamental_service.py          # Fundamental 域服务
│   ├── capital/
│   │   └── capital_service.py              # Capital 域服务
│   ├── macro/
│   │   └── macro_service.py                # Macro 域服务
│   ├── features/
│   │   └── feature_service.py              # Features 域服务
│   └── factors/
│       └── factor_service.py               # Factors 域服务
│
├── runtime/                            # 非域数据（新增）
│   ├── ingestion/ingestion_log_store.py    # ← 从 stores/ 迁移
│   └── quality/
│       ├── quarantine_store.py            # ← 从 stores/ 迁移
│       └── comparison_store.py            # ← 从 stores/ 迁移
│
└── accessors/                         # ❌ 完全删除此目录
    ├── (已删除)
    └── ...
```

---

## 四、风险评估

| 风险项 | 风险等级 | 缓解措施 |
|--------|---------|----------|
| Accessor 层依赖复杂 | 🟡 中 | 先验证每个 accessor 的使用情况，逐步替换 |
| Port 层注册破坏 | 🟡 中 | 保留旧注册一段时间，使用 deprecation warning |
| 测试覆盖不足 | 🟢 低 | 每个阶段运行相关测试 |
| 历史数据兼容性 | 🟢 低 | 存储格式不变，只是代码位置变化 |

---

## 五、时间估算

| 阶段 | 预计时间 | 依赖 |
|------|---------|------|
| 阶段 1: IndexWeightStore 迁移 | 1-2 天 | 无 |
| 阶段 2: IngestionLog/Quarantine 迁移 | 1-2 天 | 阶段 1 |
| 阶段 3: Accessor 层重构 | 2-3 天 | 阶段 2 |
| 阶段 4: Port 层注册清理 | 1 天 | 阶段 3 |
| 阶段 5: 废弃文件清理 | 1 天 | 阶段 4 |
| 阶段 6: 验证与测试 | 1-2 天 | 阶段 5 |

**总计**: 7-12 天

---

## 六、验收标准

- [ ] 所有 stores 目录下的废弃文件已删除
- [ ] 所有域数据存储都在 `domains/` 目录下
- [ ] 所有非域数据都在 `runtime/` 目录下
- [ ] `stores/` 只保留基础设施（base 基类、sqlite_client）
- [ ] Port 层不再依赖废弃的 stores
- [ ] 所有测试通过（单元测试 + 集成测试）
- [ ] 类型检查通过（basedpyright）
- [ ] Lint 检查通过（ruff）

---

## 七、后续优化建议

1. **完全移除 Accessor 层**: 考虑是否需要 accessor 层，还是直接使用 domain services
2. **stores 目录重命名**: 考虑将 `stores/base/` 重命名为 `storage/` 或 `infrastructure/`
3. **统一 ParquetStore**: 确保所有 ParquetStore 都继承自同一个基类
4. **测试覆盖率提升**: 确保所有域的测试覆盖率达到 80%+

---

**文档版本**: v1.0
**创建日期**: 2026-02-05
**状态**: Draft
