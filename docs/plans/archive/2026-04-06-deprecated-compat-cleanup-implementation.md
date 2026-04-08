# 废弃与兼容代码全面清理 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除全库 15 个 re-export shim 文件、废弃类/参数/别名、legacy 迁移代码，消除约 500-800 行死代码。

**Architecture:** 按包分层清理（Engine/Analytics → Data → App → 全局），每 Task 独立验证。所有 shim 文件消费者更新为直接导入子模块。

**Tech Stack:** Python, pytest, basedpyright, ruff

**验证命令:** `pixi run -e dev check`（lint + fmt + type + test --fast）

**设计文档:** `docs/plans/2026-04-06-deprecated-compat-cleanup-design.md`

---

## Task 1: 删除 Engine 层 Shim 文件（零引用，纯删除）

**Files:**
- Delete: `packages/engine/src/ditto_engine/backtest/risk/__init__.py`
- Delete: `packages/engine/src/ditto_engine/backtest/risk/pre_trade.py`
- Delete: `packages/engine/src/ditto_engine/backtest/risk/post_trade.py`
- Delete: `packages/engine/src/ditto_engine/backtest/risk/` (整个目录)

**Context:** 这 3 个 shim 文件零引用。所有消费者已直接从 `ditto_engine.risk.pre_trade` 和 `ditto_engine.risk.post_trade` 导入。`backtest/risk/` 目录下只有这 3 个 shim 文件，可整体删除。

**Step 1: 删除 backtest/risk 目录**

```bash
rm -rf packages/engine/src/ditto_engine/backtest/risk/
```

**Step 2: 验证**

```bash
pixi run -e dev check
```

**Step 3: Commit**

```bash
git add -A packages/engine/
git commit -m "cleanup: 删除 engine 层 risk shim 文件（零引用）"
```

---

## Task 2: 删除 Analytics 层 Shim 文件（零引用，纯删除）

**Files:**
- Delete: `packages/analytics/src/ditto_analytics/models/research.py`

**Context:** `research.py` 是从 `ditto_kernel.research` 重导出的 shim。零引用——所有 11 个消费者已直接从 `ditto_kernel.research` 导入。`models/__init__.py` 也已直接从 `ditto_kernel.research` 导入，不经过 shim。

**Step 1: 删除 shim 文件**

```bash
rm packages/analytics/src/ditto_analytics/models/research.py
```

**Step 2: 验证**

```bash
pixi run -e dev check
```

**Step 3: Commit**

```bash
git add -A packages/analytics/
git commit -m "cleanup: 删除 analytics 层 research shim 文件（零引用）"
```

---

## Task 3: 删除 Data 层 6 个 Shim 文件

**Files:**
- Delete: `packages/data/src/ditto_data/services/ingestion_log_service.py`
- Delete: `packages/data/src/ditto_data/services/publication_safety_record_service.py`
- Delete: `packages/data/src/ditto_data/services/quality_record_service.py`
- Delete: `packages/data/src/ditto_data/services/late_arrival.py`
- Delete: `packages/data/src/ditto_data/services/ingestion_cursor_service.py`
- Delete: `packages/data/src/ditto_data/services/freeze_service.py`
- Modify: 5 个消费者文件（更新导入路径）

**Context:** 6 个 shim 文件都从 `ditto_data.ingestion.*` 重导出。`services/__init__.py` 已直接从 canonical 路径导入（不经过 shim）。仅 6 处直接导入需要更新。

**Step 1: 更新消费者导入（5 个文件）**

将所有 `from ditto_data.services.publication_safety_record_service import` 改为 `from ditto_data.ingestion.publication_safety_record_service import`：

| 文件 | 旧行 | 新导入路径 |
|------|------|-----------|
| `packages/data/tests/unit/services/test_publication_safety_record_service.py:10` | `from ditto_data.services.publication_safety_record_service import` | `from ditto_data.ingestion.publication_safety_record_service import` |
| `packages/app/tests/unit/process/materialization/test_publication_facade_unit.py:34` | `from ditto_data.services.publication_safety_record_service import` | `from ditto_data.ingestion.publication_safety_record_service import` |
| `packages/app/tests/unit/process/materialization/test_derived_materialization_orchestrator_unit.py:36` | `from ditto_data.services.publication_safety_record_service import` | `from ditto_data.ingestion.publication_safety_record_service import` |
| `packages/data/tests/unit/services/test_quality_record_service.py:4` | `from ditto_data.services.quality_record_service import` | `from ditto_data.ingestion.quality_record_service import` |
| `packages/app/src/ditto_app/process/quality.py:24` | `from ditto_data.services.quality_record_service import` | `from ditto_data.ingestion.quality_record_service import` |
| `packages/data/tests/unit/services/test_late_arrival_unit.py:17` | `from ditto_data.services.late_arrival import` | `from ditto_data.ingestion.late_arrival import` |

**Step 2: 删除 6 个 shim 文件**

```bash
rm packages/data/src/ditto_data/services/ingestion_log_service.py
rm packages/data/src/ditto_data/services/publication_safety_record_service.py
rm packages/data/src/ditto_data/services/quality_record_service.py
rm packages/data/src/ditto_data/services/late_arrival.py
rm packages/data/src/ditto_data/services/ingestion_cursor_service.py
rm packages/data/src/ditto_data/services/freeze_service.py
```

**Step 3: 验证**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add -A packages/data/ packages/app/
git commit -m "cleanup: 删除 data 层 6 个 ingestion shim 文件 + 更新 6 处导入"
```

---

## Task 4: 删除 App 层 coordinator + ingestion Shim

**Files:**
- Delete: `packages/app/src/ditto_app/process/coordinator.py`
- Delete: `packages/app/src/ditto_app/process/ingestion.py`
- Modify: `packages/app/src/ditto_app/process/__init__.py` — 改为直接导入子模块
- Modify: 约 25 个消费者文件的导入路径

**Context:**
- `coordinator.py` shim 重导出自 5 个子模块 + 1 个私有函数
- `ingestion.py` shim 重导出自 `coordinator.py` shim + 6 个子模块
- `process/__init__.py` 从 `ingestion.py` shim 导入所有符号
- 消费者文件通过 `ditto_app.process.ingestion` 或 `ditto_app.process` 包导入

**导入映射表：**

| shim 中的符号 | canonical 导入路径 |
|--------------|-------------------|
| `EXCHANGE_PREFIX_MAP`, `MARKET_INDEX_CODES`, `STYLE_INDEX_CODES`, `SUPPORTED_INSTRUMENT_DATASETS`, `SWIndustryProvider`, `create_coordinator`, `get_all_index_codes`, `get_default_index_codes`, `get_sw_index_codes` | `ditto_app.process.coordinator_factory` |
| `IngestionCoordinator` | `ditto_app.process.ingestion_coordinator` |
| `BackfillManager` | `ditto_app.process.backfill_manager` |
| `RetryManager` | `ditto_app.process.retry_manager` |
| `IngestionDataWriter` | `ditto_app.process.data_writer` |
| `IngestionConfig`, `IngestionCoordinatorConfig` | `ditto_app.process.ingestion_config` |
| `API_LIMITS`, `EARLIEST_LIST_DATE_INFERENCE`, `TRADING_DAYS_PER_YEAR`, `ListDateInferenceService` | `ditto_app.process.list_date_inference` |
| `MetadataManager` | `ditto_app.process.metadata_manager` |
| `IngestionResultHandler`, `count_results` | `ditto_app.process.result_handler` |

**Step 1: 更新 `process/__init__.py`**

将 `from ditto_app.process.ingestion import (...)` 改为直接从子模块导入。将所有 22 个符号的导入源替换为上表中的 canonical 路径。

**Step 2: 更新 `providers.py` — 无需修改**

`providers.py` 不从这两个 shim 导入。

**Step 3: 更新源码消费者（5 个文件）**

| 文件 | 变更 |
|------|------|
| `interfaces/src/ditto_interfaces/registry/contexts/ingestion.py` | `from ditto_app.process.ingestion` → 按符号分别导入 |
| `interfaces/src/ditto_interfaces/registry/contexts/bundle.py` | `from ditto_app.process.ingestion` → 按符号分别导入 |
| `interfaces/src/ditto_interfaces/jobs/flows/daily.py` | `from ditto_app.process.ingestion import count_results` → `from ditto_app.process.result_handler import count_results` |
| `interfaces/src/ditto_interfaces/cli/executor.py` | `from ditto_app.process.ingestion` → 按符号分别导入 |
| `packages/app/src/ditto_app/builders/service_factory.py` | 如有导入自 `ditto_app.process.strategy` 则保持（Task 5 处理） |

**Step 4: 更新测试消费者（约 15 个文件）**

所有 `from ditto_app.process.ingestion import Xxx` 改为从 canonical 子模块导入。

**注意：** `_infer_exchange_suffix` 的测试消费者（`test_coordinator_instrument_unit.py:403`）改为：
```python
from ditto_app.process.ingestion_coordinator import _infer_exchange_suffix
```

**Step 5: 删除 shim 文件**

```bash
rm packages/app/src/ditto_app/process/coordinator.py
rm packages/app/src/ditto_app/process/ingestion.py
```

**Step 6: 验证**

```bash
pixi run -e dev check
```

**Step 7: Commit**

```bash
git add -A packages/app/ interfaces/
git commit -m "cleanup: 删除 app 层 coordinator + ingestion shim + 更新所有导入"
```

---

## Task 5: 删除 App 层 materialization Shim

**Files:**
- Delete: `packages/app/src/ditto_app/process/materialization.py`
- Modify: `packages/app/src/ditto_app/process/__init__.py`
- Modify: `packages/app/src/ditto_app/providers.py:68-73`
- Modify: 约 20 个消费者文件

**Context:** materialization shim 从 5 个子模块重导出 25 个符号。

**导入映射表：**

| shim 中的符号 | canonical 导入路径 |
|--------------|-------------------|
| `CASCADE_MAX_RETRY_COUNT`, `REALTIME_CASCADE_MAX_DEPTH`, `CascadeDepthExceededError`, `CascadeStatus`, `InvalidationCascadeOrchestrator`, `RepairBatchResult` | `ditto_app.process.cascade_orchestrator` |
| `build_manifest_record`, `build_minimal_dq_record`, `dependency_refs`, `resolve_shadow_baseline` | `ditto_app.process.materialization_helpers` |
| `DerivedMaterializationOrchestrator`, `FactorOrthogonalizationService`, `RuntimeDerivedInputProvider`, `UniverseProvider`, `apply_cs_amplification` | `ditto_app.process.materialization_orchestrator` |
| `DerivedInputProvider`, `InMemoryDerivedInputProvider`, `InputContext`, `MissingDependencyError`, `UnavailableDerivedInputProvider`, `earliest_pending_start`, `hydrate_spec`, `prepare_input_frame` | `ditto_app.process.materialization_types` |
| `DerivedPublicationFacade`, `build_certification_checks` | `ditto_app.process.publication_facade` |

**Step 1: 更新 `process/__init__.py`**

将 `from ditto_app.process.materialization import (...)` 改为直接从 5 个子模块导入。

**Step 2: 更新 `providers.py`**

```python
# 旧（行 68-73）:
from ditto_app.process.materialization import (
    DerivedMaterializationOrchestrator,
    DerivedPublicationFacade,
    InvalidationCascadeOrchestrator,
    RuntimeDerivedInputProvider,
)
# 新:
from ditto_app.process.cascade_orchestrator import InvalidationCascadeOrchestrator
from ditto_app.process.materialization_orchestrator import (
    DerivedMaterializationOrchestrator,
    RuntimeDerivedInputProvider,
)
from ditto_app.process.publication_facade import DerivedPublicationFacade
```

**Step 3: 更新所有消费者文件**

按导入映射表，将所有 `from ditto_app.process.materialization import Xxx` 替换为正确的 canonical 路径。涉及约 20 个文件。

**Step 4: 删除 shim 文件**

```bash
rm packages/app/src/ditto_app/process/materialization.py
```

**Step 5: 验证**

```bash
pixi run -e dev check
```

**Step 6: Commit**

```bash
git add -A packages/app/ interfaces/
git commit -m "cleanup: 删除 app 层 materialization shim + 更新所有导入"
```

---

## Task 6: 删除 App 层 strategy + builders.strategy Shim

**Files:**
- Delete: `packages/app/src/ditto_app/process/strategy.py`
- Delete: `packages/app/src/ditto_app/builders/strategy.py`
- Modify: `packages/app/src/ditto_app/process/__init__.py`
- Modify: `packages/app/src/ditto_app/providers.py`
- Modify: 约 20 个消费者文件

**导入映射表 — strategy:**

| shim 中的符号 | canonical 导入路径 |
|--------------|-------------------|
| `BacktestService`, `BacktestServiceConfig`, `BacktestServiceOptions` | `ditto_app.process.backtest_service` |
| `StrategyFacade`, `StrategyRunMode`, `StrategyRunResult`, `StrategyRunService`, `StrategyRunServiceConfig` | `ditto_app.process.strategy_run_service` |
| `RunLifecycleService`, `StrategyInputAssembler`, `build_display_map`, `enrich_record_with_symbol`, `write_backtest_artifacts` | `ditto_app.process.strategy_types` |

**导入映射表 — builders.strategy:**

| shim 中的符号 | canonical 导入路径 |
|--------------|-------------------|
| `PublishedStrategyRuntime`, `StrategyRuntimeBuilder` | `ditto_app.builders.runtime_builder` |
| `BacktestRuntimeBuilder`, `PublishedBacktestRuntime`, `StrategyServiceFactory` | `ditto_app.builders.service_factory` |
| `StrategySliceBuilder` | `ditto_app.builders.slice_builder` |

**注意：** `builders/__init__.py` 已直接从子模块导入（不经过 shim），无需修改。

**Step 1: 更新 `process/__init__.py`**

将 `from ditto_app.process.strategy import (...)` 改为从 3 个子模块导入。

**Step 2: 更新 `providers.py`**

```python
# 旧（行 58-63）:
from ditto_app.builders.strategy import (
    BacktestRuntimeBuilder, StrategyRuntimeBuilder,
    StrategyServiceFactory, StrategySliceBuilder,
)
# 新:
from ditto_app.builders import (
    BacktestRuntimeBuilder, StrategyRuntimeBuilder,
    StrategyServiceFactory, StrategySliceBuilder,
)

# 旧（行 75）:
from ditto_app.process.strategy import StrategyFacade
# 新:
from ditto_app.process.strategy_run_service import StrategyFacade
```

**Step 3: 更新所有消费者文件**

涉及约 20 个文件。每个文件的 `from ditto_app.process.strategy import` 和 `from ditto_app.builders.strategy import` 按映射表替换。

**Step 4: 删除 shim 文件**

```bash
rm packages/app/src/ditto_app/process/strategy.py
rm packages/app/src/ditto_app/builders/strategy.py
```

**Step 5: 验证**

```bash
pixi run -e dev check
```

**Step 6: Commit**

```bash
git add -A packages/app/ interfaces/
git commit -m "cleanup: 删除 app 层 strategy + builders shim + 更新所有导入"
```

---

## Task 7: 删除 SimpleGauge 废弃类

**Files:**
- Modify: `packages/infra/src/ditto_infra/foundation/observability/metrics.py`
  - 删除 `SimpleGauge` 类定义（lines 327-352）
  - 从 `__all__` 中删除 `"SimpleGauge"`（line 514）
- Delete: `packages/infra/tests/unit/observability/test_simple_gauge_unit.py`
- Modify: `packages/infra/tests/integration/observability/test_metrics_setup_integration.py`
  - 删除 `SimpleGauge` 导入（line 12）
  - 删除/修复 `isinstance(..., SimpleGauge)` 断言（lines 122-125）
  - 删除 `TestSimpleGaugeCreation` 类（line 179+）
- Modify: `packages/infra/tests/integration/observability/test_metrics_integration.py`
  - 更新注释 `# data_freshness 应该是 SimpleGauge` → `SafeGauge`（line 939）

**Step 1: 删除 SimpleGauge 类和测试文件**

从 `metrics.py` 删除 `SimpleGauge` 类定义和 `__all__` 条目。删除 `test_simple_gauge_unit.py`。

**Step 2: 修复集成测试**

从 `test_metrics_setup_integration.py` 删除 `SimpleGauge` 导入和相关断言。`Metrics` 属性实际是 `SafeGauge` 实例。

**Step 3: 验证**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add -A packages/infra/
git commit -m "cleanup: 删除已废弃的 SimpleGauge 类及相关测试"
```

---

## Task 8: 移除 value_std 兼容参数

**Files:**
- Modify: `packages/app/src/ditto_app/process/materialization_helpers.py`
  - 从 `_compute_value_jump_rate` 签名删除 `value_std: float` 参数
  - 删除 `_ = value_std` 行
  - 更新内部调用方（line 130）删除 `value_stats["std"]` 参数
- Modify: `packages/app/tests/unit/process/test_materialization_unit.py`
  - 从所有测试调用中删除 `value_std=...` 参数
  - 删除 `test_compute_value_jump_rate_value_std_ignored` 测试（lines 151-162）

**Step 1: 修改函数签名和调用方**

`_compute_value_jump_rate` 签名变为：
```python
def _compute_value_jump_rate(frame: pl.DataFrame) -> float:
```

内部调用方（line 130）变为：
```python
value_jump_rate = _compute_value_jump_rate(frame)
```

**Step 2: 更新测试**

所有测试调用删除 `value_std=...` 关键字参数。删除 `test_compute_value_jump_rate_value_std_ignored` 测试用例。

**Step 3: 验证**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add packages/app/
git commit -m "cleanup: 移除 value_std 兼容参数"
```

---

## Task 9: 移除 ts_diff 兼容别名

**Files:**
- Modify: `packages/analytics/src/ditto_analytics/expression/codegen.py:501` — 删除 `"ts_diff": _ts_delta`
- Modify: `packages/analytics/src/ditto_analytics/expression/registry.py:84-89` — 删除 `"ts_diff"` spec
- Modify: `packages/analytics/src/ditto_analytics/expression/analyzer.py` — 从 3 个 frozenset 删除 `"ts_diff"`（lines 36, 76, 107），更新注释（line 298）
- Modify: `packages/analytics/tests/unit/test_operator_golden_data.py` — 删除 `TestTsDiff` 类（lines 411-418），更新 docstring（line 13）

**Step 1: 删除 ts_diff 注册**

从 `codegen.py` 的 `_TS_SPECIAL_DISPATCH` 删除 `"ts_diff"` 条目。
从 `registry.py` 的 `P0_OPERATOR_SPECS` 删除 `"ts_diff"` 条目。
从 `analyzer.py` 的 3 个 frozenset 删除 `"ts_diff"`。

**Step 2: 更新/删除测试**

删除 `TestTsDiff` 测试类。更新 docstring 移除 `ts_diff` 提及。

**Step 3: 验证**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add packages/analytics/
git commit -m "cleanup: 移除 ts_diff 兼容别名（保留 ts_delta）"
```

---

## Task 10: 清理私有符号重导出

**Files:**
- Modify: `packages/analytics/src/ditto_analytics/evaluation/metrics/__init__.py` — 删除 `_scalar_to_float` 和 `_two_sided_p_value` 的重导出和 `__all__` 条目（lines 16-17, 45-46）
- Modify: `packages/analytics/tests/unit/evaluation/test_metrics_unit.py` — 更新导入（line 1047+）从 `ditto_analytics.evaluation.metrics._math` 导入

**Step 1: 删除重导出**

从 `metrics/__init__.py` 删除两行私有函数重导出和 `__all__` 中的条目。

**Step 2: 更新测试导入**

将测试中的 `from ditto_analytics.evaluation.metrics import _two_sided_p_value` 改为 `from ditto_analytics.evaluation.metrics._math import two_sided_p_value`。

**Step 3: 验证**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add packages/analytics/
git commit -m "cleanup: 移除 metrics 私有符号重导出"
```

---

## Task 11: 清理 Legacy Schema 迁移代码

**Files:**
- Modify: `packages/infra/src/ditto_infra/foundation/db/sqlite_pool.py`
  - 简化 `_handle_legacy_schema`：开发期直接重建，删除 env var 检查
  - 可选：简化 `LegacySchemaError` 或删除（改为 logging warning）
- Modify: `packages/infra/src/ditto_infra/foundation/db/__init__.py` — 同步清理 `LegacySchemaError` 导出
- Modify: `packages/infra/tests/unit/db/test_db_unit.py` — 删除 `TestLegacySchemaProtection` 类（lines 423-527）
- Modify: `packages/data/src/ditto_data/services/audit/execution_audit_service.py` — 删除 instrument_scope 列迁移（lines 99-108）
- Modify: `packages/data/tests/unit/services/test_execution_audit_service_unit.py` — 删除 `test_migrates_legacy_table_missing_instrument_scope`（lines 123-166）

**Step 1: 简化 sqlite_pool.py legacy schema 处理**

将 `_handle_legacy_schema` 简化为直接重建（开发期）：
```python
def _handle_legacy_schema(self, conn: sqlite3.Connection) -> None:
    logger.warning("Legacy schema detected, rebuilding all user tables")
    self._reset_all_user_tables(conn)
```

删除 `LegacySchemaError` 类定义和 `__init__.py` 中的导出。

**Step 2: 删除 legacy schema 测试**

删除 `TestLegacySchemaProtection` 类。

**Step 3: 删除 execution_audit 列迁移**

从 `execution_audit_service.py` 删除 lines 99-108（ALTER TABLE instrument_scope 迁移）。
删除对应测试。

**Step 4: 验证**

```bash
pixi run -e dev check
```

**Step 5: Commit**

```bash
git add packages/infra/ packages/data/
git commit -m "cleanup: 移除 legacy schema 迁移代码（开发期无旧数据）"
```

---

## Task 12: 清理 TYPE_CHECKING 块 + Vector 配置 + 其他废弃测试

**Files:**
- Modify: `packages/data/tests/unit/sources/test_exchange_transformers_unit.py` — 删除空 TYPE_CHECKING 块（lines 3, 9-10）
- Modify: `packages/infra/tests/integration/observability/conftest.py` — 改为直接导入
- Modify: `interfaces/tests/e2e/reporter.py` — 改为直接导入
- Modify: `interfaces/tests/e2e/test_quality.py` — 改为直接导入
- Modify: `deploy/observability/vector.toml` — 删除 legacy_logs 配置
- Delete deprecated tests:
  - `test_backward_compatibility_md5_raises_error` in `packages/data/tests/integration/runtime/test_freeze_manager_checksum_integration.py:50`
  - `test_backward_compatible` in `packages/analytics/tests/unit/factors/test_factor_context_unit.py:80`
  - `test_sharpe_zero_rf_backward_compat` in `packages/analytics/tests/unit/evaluation/test_evaluation_metrics_unit.py:101`
  - `TestMacroTushareAdapterLegacyMethod` in `packages/data/tests/unit/sources/tushare/adapters/test_macro_adapter_unit.py:312`
  - `test_find_series_defaults_to_non_streaming` in `packages/data/tests/unit/services/test_derived_query_service.py:713`
  - `test_find_latest_defaults_to_non_streaming` in `packages/data/tests/unit/services/test_derived_query_service.py:787`

**Step 1: 修复 TYPE_CHECKING 块**

4 个文件分别处理：
- `test_exchange_transformers_unit.py`：删除 `from typing import TYPE_CHECKING` 和 `if TYPE_CHECKING: pass` 块
- `conftest.py`：将 `if TYPE_CHECKING: from opentelemetry.metrics import Meter` 改为顶层导入
- `reporter.py`：将 `if TYPE_CHECKING: from ditto_data.quality import GoldenDatasetSpec` 改为顶层导入
- `test_quality.py`：同上

**Step 2: 清理 Vector legacy 配置**

从 `vector.toml` 删除：
- `[sources.legacy_logs]` 块（lines 18-22）
- `[transforms.legacy_logs_transform]` 块（lines 45-49）
- `[sinks.victorialogs]` 的 inputs 中删除 `"legacy_logs_transform"`

**Step 3: 删除废弃测试**

删除上述 6 个测试函数/类。注意 `FactorSpec` 的 `test_backward_compatible` 测试的是 `calendar_context` 可选参数——确认该参数已不是可选的后再删除。

**Step 4: 验证**

```bash
pixi run -e dev check
```

**Step 5: Commit**

```bash
git add -A
git commit -m "cleanup: 修复 TYPE_CHECKING 块 + 清理 vector legacy 配置 + 删除废弃测试"
```

---

## Task 13: 消除 CLI 重复代码

**Files:**
- Create: `interfaces/src/ditto_interfaces/cli/commands/ingest/_shared.py`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ingest/market.py` — 删除 `_run_instrument_ingest`，导入 shared
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ingest/capital.py` — 同上
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ingest/fundamental.py` — 同上

**Step 1: 创建共享模块**

```python
# interfaces/src/ditto_interfaces/cli/commands/ingest/_shared.py
"""CLI 摄取命令共享工具。"""

from __future__ import annotations

import typer

from ditto_interfaces.cli.context import create_executor
from ditto_interfaces.cli.utils.output import print_ingestion_result


def run_instrument_ingest(  # noqa: PLR0913
    ctx: typer.Context,
    dataset: str,
    ticker: str | None,
    standard_ticker: str | None,
    instrument_id: int | None,
    start: str | None,
    end: str | None,
    force: bool,
) -> None:
    """执行按标的摄取."""
    with create_executor() as executor:
        result = executor.ingest_by_instrument(
            dataset=dataset,
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            start_date=start or "",
            end_date=end or "",
            force=force,
        )
        print_ingestion_result(result, ctx.obj["verbose"])
```

**Step 2: 更新 3 个 CLI 文件**

每个文件删除 `_run_instrument_ingest` 函数定义，改为 `from ditto_interfaces.cli.commands.ingest._shared import run_instrument_ingest`。

**Step 3: 验证**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add interfaces/
git commit -m "cleanup: 提取 _run_instrument_ingest 到共享模块，消除 3 份重复"
```

---

## Task 14: 最终验证

**Step 1: 完整 CI 检查**

```bash
pixi run -e dev ci
```

**Step 2: 确认架构约束**

```bash
pixi run -e dev arch-check
```

**Step 3: 确认无残留**

搜索确认无残留 shim / deprecated 引用：
```bash
grep -r "re-export shim\|backward.compat\|已废弃" packages/ interfaces/ --include="*.py" -l
```

预期：空结果。

**Step 4: Final commit**

如有格式化修正：
```bash
pixi run -e dev fmt
git add -A
git commit -m "style: 最终格式化"
```
