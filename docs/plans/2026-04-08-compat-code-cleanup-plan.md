# 兼容代码全面清理计划

> **日期**: 2026-04-08
> **分支**: `refactor/phase4-app-layer-extraction`
> **前置条件**: 无（独立任务）
> **验证命令**: `pixi run -e dev check && pixi run -e dev arch-check`

## 背景

项目处于开发阶段未上线，**零向后兼容需求**。全库扫描发现 11 处 re-export shim、
1 个废弃函数、1 个兼容别名、12 行过期 pyproject.toml 配置、~90 行 legacy schema
逻辑。本次清理使每个符号只有唯一的权威导入路径。

## 审计发现总览

| 类别 | 数量 | 本次处理 |
|------|------|----------|
| Re-export shim（零消费者） | 3 处 | 全部删除 |
| Re-export hub（TECH-DEBT barrel） | 2 处 | 全部清除 |
| 兼容别名/废弃函数 | 2 处 | 全部删除 |
| Re-export（有消费者，需迁移） | 4 处 | 迁移后删除 |
| Legacy schema 逻辑 | 1 处（~90 行） | 直接删除 |
| 过期 pyproject.toml 配置 | 12 行 | 全部删除 |
| `# type: ignore` (156 处) | — | **不处理**（后续专项） |
| `# noqa` (86 处) | — | **不处理**（大部分合理豁免） |

---

## Group A — 零消费者，直接删除

### A1. 删除 `ditto_data.models.enums` re-export

**文件**: `packages/data/src/ditto_data/models/enums.py`（整个文件）

**现状**: 纯 re-export `AssetClass, Exchange` from `ditto_kernel.enums`，无任何 `.py` 文件导入。

**操作**:
1. 删除 `packages/data/src/ditto_data/models/enums.py`
2. 检查 `packages/data/src/ditto_data/models/__init__.py` 是否 re-export 之，如有则移除

**验证**: `grep -r "from ditto_data.models.enums import" packages/ interfaces/` → 零结果

---

### A2. 清除 `registry/__init__.py` Provider re-export

**文件**: `interfaces/src/ditto_interfaces/registry/__init__.py` L18-29

**现状**: 从 `ditto_data.di` re-export 10 个 Provider（`CapitalProvider, DerivedProvider, ...`）。
所有消费者已直接 `from ditto_data.di import ...`，零代码通过 registry 导入。

**操作**:
1. 删除 L17-29（注释 + 10 个 Provider import）
2. 从 `__all__` 中移除对应 10 个条目：`CapitalProvider, DerivedProvider, FundamentalProvider, GoldenDatasetProvider, MacroProvider, MarketProvider, MetadataProvider, QualityProvider, RuntimeProvider, SourcesProvider`

**验证**: `grep -r "from ditto_interfaces.registry import.*Provider" packages/ interfaces/` → 零结果

---

### A3. 清除 `interfaces.models` TECH-DEBT barrel

**文件**: `interfaces/src/ditto_interfaces/models/__init__.py` L3-34

**现状**: re-export 16+ 符号 from `ditto_app.config`, `ditto_app.query.derived`, `ditto_app.types`, `ditto_kernel.enums`。
无代码通过 barrel 形式 `from ditto_interfaces.models import ...` 导入这些符号。

**操作**:
1. 删除 L3-4（TECH-DEBT 注释）
2. 删除 L8-34（`ditto_app` / `ditto_kernel` 的 import 语句）
3. 从 `__all__` 中移除对应的 16 个条目（`INGESTION_SPECS, AssetClass, Dataset, DatasetSpec, ...` 等）
4. 保留所有 `ditto_interfaces.models.<submodule>` 的 import（这些是 canonical）

需移除的 `__all__` 条目:
```
INGESTION_SPECS, AssetClass, Dataset, DatasetSpec,
DerivedCompareResult, DerivedLatestResult, DerivedSeriesResult,
InstrumentIngestParams, LatestDerivedRequest, MacroCategory, MacroFrequency,
SeriesDerivedRequest, SourceCompareRequest, T1ConfigSpec, TaskTier,
create_t0_config, create_t1_config, get_all_datasets, get_dataset_config,
get_datasets_by_tier, get_parallel_datasets, iter_tier_datasets
```

**验证**: `grep -r "from ditto_interfaces.models import" packages/ interfaces/` → 仅剩 submodule 级导入

---

### A4. 删除废弃函数 `create_cli_host()`

**文件**: `interfaces/src/ditto_interfaces/cli/context.py` L14-33

**现状**: 注释标注"保留用于向后兼容，推荐使用 create_executor()"。

**操作**:
1. 删除 `create_cli_host()` 函数及其 docstring
2. 删除不再需要的 `Any` import（如仅此函数使用）
3. 保留 `create_executor()` 函数不变

**验证**: `grep -r "create_cli_host" packages/ interfaces/` → 零结果

---

### A5. 删除兼容别名 `_compute_calendar_enrichment`

**文件**: `packages/data/src/ditto_data/services/metadata_service.py` L51-52, L55

**现状**: `_compute_calendar_enrichment = compute_calendar_enrichment`（带下划线的别名）。
唯一消费者: 1 个测试文件。

**操作**:
1. 删除 `metadata_service.py` L51-52（别名定义 + 注释）
2. 从 `__all__` 中移除 `"_compute_calendar_enrichment"`
3. 迁移测试文件 `packages/data/tests/unit/services/test_metadata_service_calendar.py`:
   - 新增 `from ditto_data.services.metadata.calendar import compute_calendar_enrichment`
   - 将测试中所有 `_compute_calendar_enrichment` 调用改为 `compute_calendar_enrichment`

**验证**: `grep -r "_compute_calendar_enrichment" packages/ interfaces/` → 零结果

---

### A6. 清理 `pyproject.toml` 过期文件引用

**文件**: `pyproject.toml`

**现状**: 12 行引用已删除的旧 `stores/`/`domains/` 目录结构和旧 `interfaces/services/` 路径。

**操作**:

删除 `[tool.ruff.lint.per-file-ignores]` 中 3 条过期规则:
```toml
# 删除 L103（metadata_writer.py — 文件已删除）
"packages/data/src/ditto_data/stores/macro/indicator/metadata_writer.py" = ["PLR0913"]
# 删除 L105（macro metadata_store.py — 文件已删除）
"packages/data/src/ditto_data/domains/macro/indicator/metadata_store.py" = ["S608"]
# 删除 L106（features metadata_store.py — 文件已删除）
"packages/data/src/ditto_data/domains/features/technical/indicator_metadata_store.py" = ["S608"]
# 删除 L107（factors metadata_store.py — 文件已删除）
"packages/data/src/ditto_data/domains/factors/factor_metadata_store.py" = ["S608"]
# 删除 L109（services/derived/research.py — 文件已删除）
"interfaces/src/ditto_interfaces/services/derived/research.py" = ["S608"]
```

删除 `[tool.basedpyright] ignore` 中 6 条过期路径:
```toml
# 删除 L222-228（全部引用已删除的 domains/ 文件）
"packages/data/src/ditto_data/domains/market/stock/adj/adj_factor_store.py",
"packages/data/src/ditto_data/domains/market/etf/bars/bars_store.py",
"packages/data/src/ditto_data/domains/market/etf/status/status_store.py",
"packages/data/src/ditto_data/domains/market/etf/nav/nav_store.py",
"packages/data/src/ditto_data/domains/market/etf/adj/adj_factor_store.py",
"packages/data/src/ditto_data/domains/market/market_query_service.py",
```

**验证**: `pixi run -e dev lint` — 配置无报错

---

## Group B — 少量消费者，迁移后删除

### B1. 迁移 `RunStatus` re-export（3 个文件）

**源文件**: `packages/data/src/ditto_data/models/strategy_run.py` L11-14

**消费者**:
| 文件 | 当前 import | 迁移后 |
|------|-------------|--------|
| `packages/data/src/ditto_data/services/strategy/strategy_run_service.py` | `from ditto_data.models.strategy_run import (RunStatus, StrategyRunRecord)` | 拆分: `from ditto_kernel.enums import RunStatus` + `from ditto_data.models.strategy_run import StrategyRunRecord` |
| `packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py` | 同上 | 同上 |
| `packages/data/tests/unit/storage/metadata/test_strategy_run_store_unit.py` | `from ditto_data.models.strategy_run import RunStatus, StrategyRunRecord` | 同上 |

**操作**:
1. 迁移 3 个文件的 import
2. 删除 `strategy_run.py` 中的别名: `from ditto_kernel.enums import RunStatus as _KernelRunStatus` + `RunStatus = _KernelRunStatus`
3. 更新 `strategy_run.py` L38: `status: str = RunStatus.PENDING` → `status: str = _KernelRunStatus.PENDING`（或直接 import `RunStatus` 供内部使用）

**验证**: `grep -r "from ditto_data.models.strategy_run import.*RunStatus" packages/ interfaces/` → 零结果

---

### B2. 迁移 Mapping re-export（5 个文件）

**源文件**: `packages/data/src/ditto_data/sources/tushare/processors/transformer.py` L10-29

**消费者**:
| 文件 | 需迁移的符号 | 保留在 transformer 的符号 |
|------|-------------|--------------------------|
| `adapters/etf.py` | `ETF_BASIC_MAPPING, FUND_ADJ_MAPPING` | `TushareDataTransformer` |
| `adapters/calendar.py` | `CALENDAR_MAPPING` | `TushareDataTransformer` |
| `adapters/index.py` | `INDEX_BASIC_MAPPING` | `TushareDataTransformer` |
| `adapters/industry.py` | （无 Mapping，只有 `ColumnMapping`） | `ColumnMapping, TushareDataTransformer` |
| `tests/unit/sources/tushare/test_transformer_unit.py` | `ADJ_FACTOR_MAPPING, CALENDAR_MAPPING, DAILY_OHLCV_MAPPING, ETF_BASIC_MAPPING` | `ColumnMapping, TushareDataTransformer` |

**操作**:
1. 4 个 adapter 文件: 新增 `from ditto_data.sources.tushare.processors.mappings import XXX_MAPPING`，从 transformer import 中移除 Mapping 符号
2. 1 个测试文件: 同上
3. `adapters/industry.py` 无 Mapping 符号需迁移（ColumnMapping 来自 column_mapping.py），确认后跳过
4. 删除 `transformer.py` 中的 re-export 代码（L10-29 的 import + `__all__` 中的 Mapping 条目）
5. 删除 `transformer.py` 中 `from .mappings import (...)` 整个 import 块

**验证**: `grep -r "from.*transformer import.*MAPPING" packages/ interfaces/` → 零结果

---

### B3. 迁移 `FillEvent` re-export（4 个文件）

**源文件**: `packages/engine/src/ditto_engine/execution/fills.py` L8-18

**消费者**:
| 文件 | 需迁移的符号 | 保留在 fills.py 的符号 |
|------|-------------|----------------------|
| `execution/reality/fill.py` | `FillEvent` | `Filled, FillOutcome, NoFill` |
| `execution/brokerage.py` | `FillEvent` | `Filled, NoFill` |
| `execution/__init__.py` | `FillEvent` | `Filled, FillOutcome, NoFill` |
| `tests/unit/execution/test_fills_unit.py` | `FillEvent` | `Filled, FillOutcome, NoFill` |

**操作**:
1. 4 个文件: 新增 `from ditto_engine.accounting.fills import FillEvent`，从 `from ditto_engine.execution.fills import` 中移除 `FillEvent`
2. 删除 `fills.py` 中的 re-export: `from ditto_engine.accounting.fills import FillEvent` + 对应注释
3. 更新 `fills.py` 的 `__all__` 移除 `"FillEvent"`
4. 更新 `execution/__init__.py` 的 `__all__` 移除 `"FillEvent"`（如有）

**验证**: `grep -r "from ditto_engine.execution.fills import.*FillEvent" packages/ interfaces/` → 零结果

---

### B4. 迁移 `ditto_app.types` re-export hub（14 个文件）

**源文件**: `packages/app/src/ditto_app/types.py`（整个文件）

**消费者及迁移映射**:
| 文件 | 当前 import | canonical 路径 |
|------|-------------|---------------|
| `interfaces/src/ditto_interfaces/models/__init__.py` | `from ditto_app.types import Dataset, InstrumentIngestParams, MacroCategory, MacroFrequency` | `from ditto_data.models import Dataset, MacroCategory, MacroFrequency` + `from ditto_data.models.ingestion import InstrumentIngestParams` |
| `interfaces/src/ditto_interfaces/models/macro.py` | `from ditto_app.types import MacroCategory, MacroFrequency` | `from ditto_data.models import MacroCategory, MacroFrequency` |
| `interfaces/src/ditto_interfaces/api/utils/identifier.py` | `from ditto_app.types import AmbiguousTickerError, NoIdentifierProvidedError` | `from ditto_data.errors import AmbiguousTickerError, NoIdentifierProvidedError` |
| `interfaces/src/ditto_interfaces/jobs/tasks/t0_meta.py` | `from ditto_app.types import Dataset` | `from ditto_data.models import Dataset` |
| `interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py` | `from ditto_app.types import Dataset, DQIssue` | `from ditto_data.models import Dataset` + `from ditto_data.quality.spec import DQIssue` |
| `interfaces/src/ditto_interfaces/jobs/tasks/monitoring.py` | `from ditto_app.types import DQResult` | `from ditto_data.quality.spec import DQResult` |
| `interfaces/src/ditto_interfaces/jobs/context.py` | `from ditto_app.types import QualityEngine` | `from ditto_data.quality import QualityEngine` |
| `interfaces/src/ditto_interfaces/jobs/flows/daily.py` | `from ditto_app.types import Dataset` | `from ditto_data.models import Dataset` |
| `interfaces/src/ditto_interfaces/jobs/flows/backfill.py` | `from ditto_app.types import InstrumentIngestParams` | `from ditto_data.models.ingestion import InstrumentIngestParams` |
| `interfaces/src/ditto_interfaces/cli/executor.py` | `from ditto_app.types import InstrumentIngestParams` | `from ditto_data.models.ingestion import InstrumentIngestParams` |
| `interfaces/tests/unit/api/utils/test_identifier_unit.py` | `from ditto_app.types import AmbiguousTickerError, NoIdentifierProvidedError` | `from ditto_data.errors import ...` |
| `interfaces/tests/unit/api/routes/test_fundamental_identifier_query_unit.py` | `from ditto_app.types import AmbiguousTickerError` | `from ditto_data.errors import ...` |
| `interfaces/tests/unit/api/routes/test_capital_identifier_query_unit.py` | `from ditto_app.types import AmbiguousTickerError` | `from ditto_data.errors import ...` |
| 1 个 app test | （如有） | canonical |

**操作**:
1. 迁移 14 个文件的 import 到 canonical 路径
2. 删除 `packages/app/src/ditto_app/types.py`
3. 检查 `packages/app/src/ditto_app/__init__.py` 是否 re-export types，如有则移除
4. 检查是否有其他文件引用 `from ditto_app.types import`（`grep -r "from ditto_app.types" packages/ interfaces/`）

**验证**: `grep -r "from ditto_app.types" packages/ interfaces/` → 零结果

---

## Group C — 逻辑简化

### C1. 删除 SQLite legacy schema 检测/重建逻辑

**文件**: `packages/infra/src/ditto_infra/foundation/db/sqlite_pool.py`

**删除范围**:
- `_needs_schema_rebuild()` 方法（L204-243）
- `_reset_all_user_tables()` 方法（L245-271）
- `_handle_legacy_schema()` 方法（L273-280）
- `init_schema()` 中 L193-194 的条件调用: `if self._needs_schema_rebuild(conn): self._handle_legacy_schema(conn)`

**简化后 `init_schema()` 逻辑**:
```python
def init_schema(self, schema: str) -> None:
    """Initialize database schema."""
    conn = self.get_connection()
    conn.executescript(schema)
    conn.commit()
    logger.info(
        "Database schema initialized successfully",
        event="schema_init_complete",
        status="success",
    )
```

**同步清理测试**:
- `packages/infra/tests/unit/db/test_db_unit.py` 中的 `test_init_schema_rebuilds_legacy` 测试删除
- 对应的 `ENG-004` 测试类/注释清理

**验证**: `pixi run -e dev test packages/infra/tests/unit/db/`

---

## 执行顺序

```
A6 (pyproject.toml) ─── 独立，可最先执行
    │
A1 (enums.py) ─── 独立
A2 (registry) ─── 独立
A3 (models barrel) ─── 独立
A4 (create_cli_host) ─── 独立
A5 (_compute_calendar_enrichment) ─── 独立
    │
B1 (RunStatus) ─── 依赖 A1 完成（确保 enums.py 已删除，无歧义）
B2 (Mapping) ─── 独立
B3 (FillEvent) ─── 独立
B4 (types.py) ─── 依赖 A3 完成（models barrel 先清除）
    │
C1 (SQLite legacy) ─── 独立
    │
最终验证: pixi run -e dev check && pixi run -e dev arch-check
```

**建议并行分组**:
- Round 1: A1-A6（全部独立，可并行）
- Round 2: B1-B4（A 组完成后）
- Round 3: C1
- Round 4: 全量验证

---

## 不在范围内

| 项目 | 原因 |
|------|------|
| `# type: ignore` (156 处) | 工作量大，需专项处理 |
| `# noqa` (86 处) | 大部分为合理豁免（S608 SQL 字面量等） |
| `from __future__ import annotations` (252 文件) | 标准 Python 实践 |
| ABC `pass` / `NotImplementedError` | 正常 OOP 模式 |
| `storage/__init__.py` CQRS 迁移历史注释 | 纯文档，无代码影响 |
