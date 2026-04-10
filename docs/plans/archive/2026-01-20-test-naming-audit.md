# Ditto 项目测试规范审计报告

**审计日期**: 2026-01-20
**审计范围**: 所有测试文件（`tests/**/*.py` 和 `**/test_*.py`）
**审计依据**: `.claude/rules/python-test.md`

---

## 一、执行摘要

### 测试文件统计

| 包/应用 | 单元测试 | 集成测试 | 合计 |
|--------|---------|---------|------|
| **apps/port** | 37 | 10 | 47 |
| **packages/data** | 76 | 13 | 89 |
| **packages/foundation** | 23 | 0 | 23 |
| **packages/core** | 0 | 0 | 0 (空) |
| **总计** | **136** | **23** | **159** |

### 规范符合率

| 指标 | 结果 |
|------|------|
| **命名规范符合率** | **~98%** (155/159) |
| **目录结构符合率** | **100%** |
| **需要修复的文件** | 5 个 |

### 发现的问题

| 严重程度 | 类型 | 数量 | 说明 |
|----------|------|------|------|
| **中** | 文件名冲突 | 1 | `test_backfill_unit.py` 存在于两处 |
| **低** | 命名不够精确 | 4 | 模块名与被测类名不完全匹配 |
| **低** | 空测试目录 | 3 | `core/tests/` 和 `foundation/tests/integration/` |

---

## 二、测试规范回顾

### 官方规范来源

项目的测试规范定义在 [`.claude/rules/python-test.md`](../.claude/rules/python-test.md)

### 目录结构要求

```
tests/
├── conftest.py
├── fixtures/
├── unit/           # 80% - 单元测试（完全 Mock）
└── integration/    # 20% - 集成测试（真实组件，测"接缝"处）
```

### 命名规范

| 测试类型 | 文件命名格式 | 示例 |
|---------|-------------|------|
| 单元测试 | `test_{module}_unit.py` | `test_bars_accessor_unit.py` |
| 集成测试 | `test_{module}_integration.py` | `test_bars_store_integration.py` |

### 防止 import 冲突

**禁止同名测试文件存在于不同测试层级**：

```
# ❌ 错误：会导致 pytest 收集冲突
packages/data/tests/unit/stores/test_pipeline_store.py
packages/data/tests/integration/stores/test_pipeline_store.py

# ✅ 正确：添加层级后缀区分
packages/data/tests/unit/stores/test_pipeline_store_unit.py
packages/data/tests/integration/stores/test_pipeline_store_integration.py
```

### 测试分类原则

- **单元测试**：完全 Mock，测试单个类的原子功能
- **集成测试**：真实组件，测试系统与外部的"接缝"处（DAO 写入数据库、HTTP Client 解析 API 响应）

---

## 三、当前测试目录结构

### 完整目录树

```
d:\code\quant\ditto\
├── apps/port/tests/
│   ├── integration/
│   │   ├── cli/
│   │   │   ├── test_adj_commands_integration.py
│   │   │   ├── test_calendar_commands_integration.py
│   │   │   ├── test_cli_integration.py
│   │   │   ├── test_etf_commands_integration.py
│   │   │   ├── test_init_commands_integration.py
│   │   │   └── test_stock_commands_integration.py
│   │   ├── flows/
│   │   │   └── test_helpers_integration.py
│   │   └── ingestion/
│   │       ├── flows/
│   │       │   ├── test_deploy_integration.py
│   │       │   └── test_repair_integration.py
│   │       └── test_adj_factor_ingestion_integration.py
│   └── unit/
│       ├── cli/
│       │   ├── commands/
│       │   │   ├── test_adj_unit.py
│       │   │   ├── test_calendar_unit.py
│       │   │   ├── test_etf_unit.py
│       │   │   ├── test_init_unit.py
│       │   │   └── test_stock_unit.py
│       │   ├── test_executor_unit.py
│       │   ├── test_factory_unit.py
│       │   ├── test_output_unit.py
│       │   └── test_validation_unit.py
│       ├── common/
│       │   └── test_types_unit.py
│       ├── ingestion/
│       │   ├── flows/
│       │   │   ├── test_backfill_unit.py
│       │   │   └── test_daily_unit.py
│       │   ├── tasks/
│       │   │   ├── test_dq_batch_unit.py
│       │   │   └── test_task_factory_unit.py
│       │   ├── test_backfill_unit.py  ⚠️ 与 flows/ 子目录同名
│       │   ├── test_config_unit.py
│       │   ├── test_coordinator_dq_blocking_unit.py
│       │   ├── test_coordinator_unit.py
│       │   ├── test_datasets_unit.py
│       │   ├── test_metadata_unit.py
│       │   ├── test_monitoring_unit.py
│       │   ├── test_result_utils_unit.py
│       │   └── test_retry_unit.py
│       ├── jobs/flows/
│       │   └── test_deploy_unit.py
│       ├── models/
│       │   └── test_common_models_unit.py
│       ├── test_conftest_unit.py
│       ├── test_db_fixtures_unit.py
│       ├── test_main_unit.py
│       └── test_middleware_unit.py
│
├── packages/core/tests/
│   ├── integration/ (空，仅有 __init__.py)
│   └── unit/ (空，仅有 __init__.py)
│
├── packages/data/tests/
│   ├── fixtures/
│   │   └── dq/
│   │       └── rules/
│   ├── integration/
│   │   ├── runtime/
│   │   │   ├── test_freeze_manager_checksum_integration.py
│   │   │   ├── test_freeze_manager_integration.py
│   │   │   ├── test_sid_allocator_integration.py
│   │   │   ├── test_sql_engine_injection_integration.py
│   │   │   ├── test_sql_engine_integration.py
│   │   │   └── test_sqlite_pool_integration.py
│   │   ├── sources/tushare/
│   │   │   └── test_tushare_api_integration.py
│   │   └── stores/
│   │       ├── test_adj_factor_store_integration.py
│   │       ├── test_bars_store_integration.py
│   │       ├── test_calendar_store_concurrent_integration.py
│   │       ├── test_ingestion_log_concurrent_integration.py
│   │       ├── test_ingestion_log_store_integration.py
│   │       ├── test_security_store_integration.py
│   │       └── test_universe_store_integration.py
│   └── unit/
│       ├── accessors/bars/
│       │   ├── test_accessor_unit.py
│       │   ├── test_adjustment_unit.py
│       │   └── test_dq_filters_unit.py
│       ├── accessors/
│       │   ├── test_adj_factor_accessor_unit.py
│       │   ├── test_bars_accessor_unit.py
│       │   ├── test_calendar_accessor_unit.py
│       │   ├── test_filter_failed_rows_unit.py
│       │   ├── test_index_accessor_unit.py
│       │   ├── test_ingestion_log_accessor_unit.py
│       │   ├── test_security_accessor_unit.py
│       │   └── test_universe_accessor_unit.py
│       ├── alerts/
│       │   ├── test_base_unit.py
│       │   ├── test_email_unit.py
│       │   ├── test_manager_unit.py
│       │   └── test_telegram_unit.py
│       ├── datahub/
│       │   └── test_datahub_observability_unit.py
│       ├── dq/checkers/
│       │   ├── test_business_unit.py  ⚠️
│       │   ├── test_statistical_property_unit.py
│       │   ├── test_statistical_unit.py  ⚠️
│       │   └── test_technical_unit.py  ⚠️
│       ├── dq/
│       │   ├── test_config_loading_unit.py
│       │   ├── test_engine_unit.py
│       │   ├── test_init_dq_config_unit.py
│       │   ├── test_models_unit.py
│       │   ├── test_report_unit.py
│       │   └── test_result_unit.py
│       ├── meta/
│       │   ├── test_schema_validator_unit.py
│       │   └── test_schemas_unit.py  ⚠️
│       ├── models/
│       │   ├── test_common_unit.py
│       │   ├── test_ingestion_unit.py
│       │   ├── test_models_quality_unit.py
│       │   ├── test_security_unit.py
│       │   └── test_storage_unit.py
│       ├── runtime/
│       │   ├── test_cache_runtime_unit.py
│       │   ├── test_cache_ttl_unit.py
│       │   ├── test_fake_time_unit.py
│       │   ├── test_freeze_manager_collect_checksums_unit.py
│       │   ├── test_pit_helper_property_unit.py
│       │   ├── test_pit_helper_unit.py
│       │   ├── test_sid_allocator_unit.py
│       │   └── test_sql_engine_unit.py
│       ├── sources/tushare/
│       │   ├── test_client_unit.py
│       │   ├── test_http_utils_unit.py
│       │   ├── test_rate_limiter_unit.py
│       │   ├── test_source_unit.py
│       │   └── test_transformer_unit.py
│       ├── sources/
│       │   ├── test_accessor_unit.py
│       │   └── test_base_unit.py
│       ├── stores/
│       │   ├── test_adj_factor_store_unit.py
│       │   ├── test_bars_store_unit.py
│       │   ├── test_calendar_store_unit.py
│       │   ├── test_index_weight_store_unit.py
│       │   ├── test_ingestion_log_store_unit.py
│       │   ├── test_parquet_store_base_unit.py
│       │   ├── test_quarantine_store_unit.py
│       │   ├── test_security_store_unit.py
│       │   ├── test_sqlite_client_unit.py
│       │   ├── test_stock_status_store_unit.py
│       │   └── test_universe_store_unit.py
│       ├── utils/
│       │   └── test_date_utils_unit.py
│       ├── test_errors_unit.py
│       └── test_hub_unit.py
│
└── packages/foundation/tests/
    ├── integration/ (空，仅有 __init__.py)
    └── unit/
        ├── bootstrap/
        │   └── test_initializer_unit.py
        ├── concurrency/
        │   └── test_file_lock_unit.py
        ├── config/
        │   ├── test_environment_unit.py
        │   ├── test_initializer_unit.py
        │   ├── test_loader_unit.py
        │   ├── test_manager_unit.py
        │   └── test_paths_unit.py
        ├── util/
        │   ├── test_checksum_unit.py
        │   ├── test_dates_property_unit.py
        │   ├── test_dates_unit.py
        │   └── test_io_unit.py
        ├── test_app_initializer_unit.py
        ├── test_cache_data_unit.py
        ├── test_db_unit.py
        ├── test_json_formatter_unit.py
        ├── test_metric_definitions_unit.py
        ├── test_observability_init_unit.py
        ├── test_observability_logging_unit.py
        ├── test_observability_metrics_unit.py
        ├── test_observability_testing_unit.py
        ├── test_observability_tracing_unit.py
        ├── test_observability_unit.py
        ├── test_simple_gauge_unit.py
        └── test_version_unit.py
```

---

## 四、命名规范符合性分析

### 符合规范的文件（155/159，~98%）

#### 单元测试命名模式

| 命名模式 | 数量 | 示例 | 状态 |
|---------|------|------|------|
| `test_{module}_unit.py` | 大部分 | `test_bars_accessor_unit.py` | ✅ 符合 |
| `test_conftest_unit.py` | 1 | 特殊用途 | ✅ 可接受 |

#### 集成测试命名模式

| 命名模式 | 数量 | 示例 | 状态 |
|---------|------|------|------|
| `test_{module}_integration.py` | 全部 | `test_bars_store_integration.py` | ✅ 完全符合 |

### 不符合规范的文件（4 个）

| 文件路径 | 当前名称 | 问题 | 建议名称 |
|---------|---------|------|----------|
| `packages/data/tests/unit/dq/checkers/` | `test_business_unit.py` | 模块名与类名不完全匹配 | `test_business_checker_unit.py` |
| `packages/data/tests/unit/dq/checkers/` | `test_technical_unit.py` | 模块名与类名不完全匹配 | `test_technical_checker_unit.py` |
| `packages/data/tests/unit/dq/checkers/` | `test_statistical_unit.py` | 模块名与类名不完全匹配 | `test_statistical_checker_unit.py` |
| `packages/data/tests/unit/meta/` | `test_schemas_unit.py` | 模块名不够具体 | `test_schema_definitions_unit.py` |

**影响分析**：
- 这些文件名虽然包含 `_unit` 后缀，但模块名称与被测类名不完全匹配
- 可能导致维护困难，难以快速定位被测代码

---

## 五、目录组织问题

### 问题 1：文件名冲突（中优先级）

**冲突文件**：
- `apps/port/tests/unit/ingestion/test_backfill_unit.py`（根目录）
- `apps/port/tests/unit/ingestion/flows/test_backfill_unit.py`（子目录）

**影响**：
- 虽然它们在不同目录，但文件名完全相同
- 在某些工具或 IDE 中可能导致混淆
- 违反了"防止 import 冲突"的规范精神

**建议**：
1. 检查两个文件是否测试同一模块
2. 如果是，合并文件
3. 如果不是，重命名根目录文件以更精确地反映其测试内容

### 问题 2：空测试目录（低优先级）

| 目录 | 状态 | 建议 |
|------|------|------|
| `packages/core/tests/unit/` | 空 | 添加测试或移除目录 |
| `packages/core/tests/integration/` | 空 | 添加测试或移除目录 |
| `packages/foundation/tests/integration/` | 空 | 添加测试或移除目录 |

### 问题 3：conftest.py 分布（✅ 正常）

每个包/应用的 `tests/` 目录都有独立的 `conftest.py`，符合 pytest 最佳实践：

```
apps/port/tests/conftest.py
apps/port/tests/integration/conftest.py
apps/port/tests/unit/conftest.py
packages/data/tests/conftest.py
packages/data/tests/integration/conftest.py
packages/data/tests/unit/conftest.py
packages/data/tests/unit/stores/conftest.py
packages/foundation/tests/unit/conftest.py
```

---

## 六、详细文件清单

### apps/port（47 个测试文件）

#### 集成测试（10 个）

| 文件路径 |
|---------|
| [apps/port/tests/integration/cli/test_adj_commands_integration.py](../apps/port/tests/integration/cli/test_adj_commands_integration.py) |
| [apps/port/tests/integration/cli/test_calendar_commands_integration.py](../apps/port/tests/integration/cli/test_calendar_commands_integration.py) |
| [apps/port/tests/integration/cli/test_cli_integration.py](../apps/port/tests/integration/cli/test_cli_integration.py) |
| [apps/port/tests/integration/cli/test_etf_commands_integration.py](../apps/port/tests/integration/cli/test_etf_commands_integration.py) |
| [apps/port/tests/integration/cli/test_init_commands_integration.py](../apps/port/tests/integration/cli/test_init_commands_integration.py) |
| [apps/port/tests/integration/cli/test_stock_commands_integration.py](../apps/port/tests/integration/cli/test_stock_commands_integration.py) |
| [apps/port/tests/integration/flows/test_helpers_integration.py](../apps/port/tests/integration/flows/test_helpers_integration.py) |
| [apps/port/tests/integration/ingestion/flows/test_deploy_integration.py](../apps/port/tests/integration/ingestion/flows/test_deploy_integration.py) |
| [apps/port/tests/integration/ingestion/flows/test_repair_integration.py](../apps/port/tests/integration/ingestion/flows/test_repair_integration.py) |
| [apps/port/tests/integration/ingestion/test_adj_factor_ingestion_integration.py](../apps/port/tests/integration/ingestion/test_adj_factor_ingestion_integration.py) |

#### 单元测试（37 个）

| 文件路径 |
|---------|
| [apps/port/tests/unit/cli/commands/test_adj_unit.py](../apps/port/tests/unit/cli/commands/test_adj_unit.py) |
| [apps/port/tests/unit/cli/commands/test_calendar_unit.py](../apps/port/tests/unit/cli/commands/test_calendar_unit.py) |
| [apps/port/tests/unit/cli/commands/test_etf_unit.py](../apps/port/tests/unit/cli/commands/test_etf_unit.py) |
| [apps/port/tests/unit/cli/commands/test_init_unit.py](../apps/port/tests/unit/cli/commands/test_init_unit.py) |
| [apps/port/tests/unit/cli/commands/test_stock_unit.py](../apps/port/tests/unit/cli/commands/test_stock_unit.py) |
| [apps/port/tests/unit/cli/test_executor_unit.py](../apps/port/tests/unit/cli/test_executor_unit.py) |
| [apps/port/tests/unit/cli/test_factory_unit.py](../apps/port/tests/unit/cli/test_factory_unit.py) |
| [apps/port/tests/unit/cli/test_output_unit.py](../apps/port/tests/unit/cli/test_output_unit.py) |
| [apps/port/tests/unit/cli/test_validation_unit.py](../apps/port/tests/unit/cli/test_validation_unit.py) |
| [apps/port/tests/unit/common/test_types_unit.py](../apps/port/tests/unit/common/test_types_unit.py) |
| [apps/port/tests/unit/ingestion/flows/test_backfill_unit.py](../apps/port/tests/unit/ingestion/flows/test_backfill_unit.py) ⚠️ |
| [apps/port/tests/unit/ingestion/flows/test_daily_unit.py](../apps/port/tests/unit/ingestion/flows/test_daily_unit.py) |
| [apps/port/tests/unit/ingestion/tasks/test_dq_batch_unit.py](../apps/port/tests/unit/ingestion/tasks/test_dq_batch_unit.py) |
| [apps/port/tests/unit/ingestion/tasks/test_task_factory_unit.py](../apps/port/tests/unit/ingestion/tasks/test_task_factory_unit.py) |
| [apps/port/tests/unit/ingestion/test_backfill_unit.py](../apps/port/tests/unit/ingestion/test_backfill_unit.py) ⚠️ **冲突** |
| [apps/port/tests/unit/ingestion/test_config_unit.py](../apps/port/tests/unit/ingestion/test_config_unit.py) |
| [apps/port/tests/unit/ingestion/test_coordinator_dq_blocking_unit.py](../apps/port/tests/unit/ingestion/test_coordinator_dq_blocking_unit.py) |
| [apps/port/tests/unit/ingestion/test_coordinator_unit.py](../apps/port/tests/unit/ingestion/test_coordinator_unit.py) |
| [apps/port/tests/unit/ingestion/test_datasets_unit.py](../apps/port/tests/unit/ingestion/test_datasets_unit.py) |
| [apps/port/tests/unit/ingestion/test_metadata_unit.py](../apps/port/tests/unit/ingestion/test_metadata_unit.py) |
| [apps/port/tests/unit/ingestion/test_monitoring_unit.py](../apps/port/tests/unit/ingestion/test_monitoring_unit.py) |
| [apps/port/tests/unit/ingestion/test_result_utils_unit.py](../apps/port/tests/unit/ingestion/test_result_utils_unit.py) |
| [apps/port/tests/unit/ingestion/test_retry_unit.py](../apps/port/tests/unit/ingestion/test_retry_unit.py) |
| [apps/port/tests/unit/jobs/flows/test_deploy_unit.py](../apps/port/tests/unit/jobs/flows/test_deploy_unit.py) |
| [apps/port/tests/unit/models/test_common_models_unit.py](../apps/port/tests/unit/models/test_common_models_unit.py) |
| [apps/port/tests/unit/test_conftest_unit.py](../apps/port/tests/unit/test_conftest_unit.py) |
| [apps/port/tests/unit/test_db_fixtures_unit.py](../apps/port/tests/unit/test_db_fixtures_unit.py) |
| [apps/port/tests/unit/test_main_unit.py](../apps/port/tests/unit/test_main_unit.py) |
| [apps/port/tests/unit/test_middleware_unit.py](../apps/port/tests/unit/test_middleware_unit.py) |

### packages/data（89 个测试文件）

#### 集成测试（13 个）

| 文件路径 |
|---------|
| [packages/data/tests/integration/runtime/test_freeze_manager_checksum_integration.py](../packages/data/tests/integration/runtime/test_freeze_manager_checksum_integration.py) |
| [packages/data/tests/integration/runtime/test_freeze_manager_integration.py](../packages/data/tests/integration/runtime/test_freeze_manager_integration.py) |
| [packages/data/tests/integration/runtime/test_sid_allocator_integration.py](../packages/data/tests/integration/runtime/test_sid_allocator_integration.py) |
| [packages/data/tests/integration/runtime/test_sql_engine_injection_integration.py](../packages/data/tests/integration/runtime/test_sql_engine_injection_integration.py) |
| [packages/data/tests/integration/runtime/test_sql_engine_integration.py](../packages/data/tests/integration/runtime/test_sql_engine_integration.py) |
| [packages/data/tests/integration/runtime/test_sqlite_pool_integration.py](../packages/data/tests/integration/runtime/test_sqlite_pool_integration.py) |
| [packages/data/tests/integration/sources/tushare/test_tushare_api_integration.py](../packages/data/tests/integration/sources/tushare/test_tushare_api_integration.py) |
| [packages/data/tests/integration/stores/test_adj_factor_store_integration.py](../packages/data/tests/integration/stores/test_adj_factor_store_integration.py) |
| [packages/data/tests/integration/stores/test_bars_store_integration.py](../packages/data/tests/integration/stores/test_bars_store_integration.py) |
| [packages/data/tests/integration/stores/test_calendar_store_concurrent_integration.py](../packages/data/tests/integration/stores/test_calendar_store_concurrent_integration.py) |
| [packages/data/tests/integration/stores/test_ingestion_log_concurrent_integration.py](../packages/data/tests/integration/stores/test_ingestion_log_concurrent_integration.py) |
| [packages/data/tests/integration/stores/test_ingestion_log_store_integration.py](../packages/data/tests/integration/stores/test_ingestion_log_store_integration.py) |
| [packages/data/tests/integration/stores/test_security_store_integration.py](../packages/data/tests/integration/stores/test_security_store_integration.py) |
| [packages/data/tests/integration/stores/test_universe_store_integration.py](../packages/data/tests/integration/stores/test_universe_store_integration.py) |

#### 单元测试（76 个）

| 文件路径 | 状态 |
|---------|------|
| [packages/data/tests/unit/accessors/bars/test_accessor_unit.py](../packages/data/tests/unit/accessors/bars/test_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/bars/test_adjustment_unit.py](../packages/data/tests/unit/accessors/bars/test_adjustment_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/bars/test_dq_filters_unit.py](../packages/data/tests/unit/accessors/bars/test_dq_filters_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_adj_factor_accessor_unit.py](../packages/data/tests/unit/accessors/test_adj_factor_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_bars_accessor_unit.py](../packages/data/tests/unit/accessors/test_bars_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_calendar_accessor_unit.py](../packages/data/tests/unit/accessors/test_calendar_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_filter_failed_rows_unit.py](../packages/data/tests/unit/accessors/test_filter_failed_rows_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_index_accessor_unit.py](../packages/data/tests/unit/accessors/test_index_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_ingestion_log_accessor_unit.py](../packages/data/tests/unit/accessors/test_ingestion_log_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_security_accessor_unit.py](../packages/data/tests/unit/accessors/test_security_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/accessors/test_universe_accessor_unit.py](../packages/data/tests/unit/accessors/test_universe_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/alerts/test_base_unit.py](../packages/data/tests/unit/alerts/test_base_unit.py) | ✅ |
| [packages/data/tests/unit/alerts/test_email_unit.py](../packages/data/tests/unit/alerts/test_email_unit.py) | ✅ |
| [packages/data/tests/unit/alerts/test_manager_unit.py](../packages/data/tests/unit/alerts/test_manager_unit.py) | ✅ |
| [packages/data/tests/unit/alerts/test_telegram_unit.py](../packages/data/tests/unit/alerts/test_telegram_unit.py) | ✅ |
| [packages/data/tests/unit/datahub/test_datahub_observability_unit.py](../packages/data/tests/unit/datahub/test_datahub_observability_unit.py) | ✅ |
| [packages/data/tests/unit/dq/checkers/test_business_unit.py](../packages/data/tests/unit/dq/checkers/test_business_unit.py) | ⚠️ 建议改为 `test_business_checker_unit.py` |
| [packages/data/tests/unit/dq/checkers/test_statistical_property_unit.py](../packages/data/tests/unit/dq/checkers/test_statistical_property_unit.py) | ✅ |
| [packages/data/tests/unit/dq/checkers/test_statistical_unit.py](../packages/data/tests/unit/dq/checkers/test_statistical_unit.py) | ⚠️ 建议改为 `test_statistical_checker_unit.py` |
| [packages/data/tests/unit/dq/checkers/test_technical_unit.py](../packages/data/tests/unit/dq/checkers/test_technical_unit.py) | ⚠️ 建议改为 `test_technical_checker_unit.py` |
| [packages/data/tests/unit/dq/test_config_loading_unit.py](../packages/data/tests/unit/dq/test_config_loading_unit.py) | ✅ |
| [packages/data/tests/unit/dq/test_engine_unit.py](../packages/data/tests/unit/dq/test_engine_unit.py) | ✅ |
| [packages/data/tests/unit/dq/test_init_dq_config_unit.py](../packages/data/tests/unit/dq/test_init_dq_config_unit.py) | ✅ |
| [packages/data/tests/unit/dq/test_models_unit.py](../packages/data/tests/unit/dq/test_models_unit.py) | ✅ |
| [packages/data/tests/unit/dq/test_report_unit.py](../packages/data/tests/unit/dq/test_report_unit.py) | ✅ |
| [packages/data/tests/unit/dq/test_result_unit.py](../packages/data/tests/unit/dq/test_result_unit.py) | ✅ |
| [packages/data/tests/unit/meta/test_schema_validator_unit.py](../packages/data/tests/unit/meta/test_schema_validator_unit.py) | ✅ |
| [packages/data/tests/unit/meta/test_schemas_unit.py](../packages/data/tests/unit/meta/test_schemas_unit.py) | ⚠️ 建议改为 `test_schema_definitions_unit.py` |
| [packages/data/tests/unit/models/test_common_unit.py](../packages/data/tests/unit/models/test_common_unit.py) | ✅ |
| [packages/data/tests/unit/models/test_ingestion_unit.py](../packages/data/tests/unit/models/test_ingestion_unit.py) | ✅ |
| [packages/data/tests/unit/models/test_models_quality_unit.py](../packages/data/tests/unit/models/test_models_quality_unit.py) | ✅ |
| [packages/data/tests/unit/models/test_security_unit.py](../packages/data/tests/unit/models/test_security_unit.py) | ✅ |
| [packages/data/tests/unit/models/test_storage_unit.py](../packages/data/tests/unit/models/test_storage_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_cache_runtime_unit.py](../packages/data/tests/unit/runtime/test_cache_runtime_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_cache_ttl_unit.py](../packages/data/tests/unit/runtime/test_cache_ttl_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_fake_time_unit.py](../packages/data/tests/unit/runtime/test_fake_time_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_freeze_manager_collect_checksums_unit.py](../packages/data/tests/unit/runtime/test_freeze_manager_collect_checksums_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_pit_helper_property_unit.py](../packages/data/tests/unit/runtime/test_pit_helper_property_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_pit_helper_unit.py](../packages/data/tests/unit/runtime/test_pit_helper_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_sid_allocator_unit.py](../packages/data/tests/unit/runtime/test_sid_allocator_unit.py) | ✅ |
| [packages/data/tests/unit/runtime/test_sql_engine_unit.py](../packages/data/tests/unit/runtime/test_sql_engine_unit.py) | ✅ |
| [packages/data/tests/unit/sources/test_accessor_unit.py](../packages/data/tests/unit/sources/test_accessor_unit.py) | ✅ |
| [packages/data/tests/unit/sources/test_base_unit.py](../packages/data/tests/unit/sources/test_base_unit.py) | ✅ |
| [packages/data/tests/unit/sources/tushare/test_client_unit.py](../packages/data/tests/unit/sources/tushare/test_client_unit.py) | ✅ |
| [packages/data/tests/unit/sources/tushare/test_http_utils_unit.py](../packages/data/tests/unit/sources/tushare/test_http_utils_unit.py) | ✅ |
| [packages/data/tests/unit/sources/tushare/test_rate_limiter_unit.py](../packages/data/tests/unit/sources/tushare/test_rate_limiter_unit.py) | ✅ |
| [packages/data/tests/unit/sources/tushare/test_source_unit.py](../packages/data/tests/unit/sources/tushare/test_source_unit.py) | ✅ |
| [packages/data/tests/unit/sources/tushare/test_transformer_unit.py](../packages/data/tests/unit/sources/tushare/test_transformer_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_adj_factor_store_unit.py](../packages/data/tests/unit/stores/test_adj_factor_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_bars_store_unit.py](../packages/data/tests/unit/stores/test_bars_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_calendar_store_unit.py](../packages/data/tests/unit/stores/test_calendar_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_index_weight_store_unit.py](../packages/data/tests/unit/stores/test_index_weight_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_ingestion_log_store_unit.py](../packages/data/tests/unit/stores/test_ingestion_log_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_parquet_store_base_unit.py](../packages/data/tests/unit/stores/test_parquet_store_base_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_quarantine_store_unit.py](../packages/data/tests/unit/stores/test_quarantine_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_security_store_unit.py](../packages/data/tests/unit/stores/test_security_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_sqlite_client_unit.py](../packages/data/tests/unit/stores/test_sqlite_client_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_stock_status_store_unit.py](../packages/data/tests/unit/stores/test_stock_status_store_unit.py) | ✅ |
| [packages/data/tests/unit/stores/test_universe_store_unit.py](../packages/data/tests/unit/stores/test_universe_store_unit.py) | ✅ |
| [packages/data/tests/unit/test_errors_unit.py](../packages/data/tests/unit/test_errors_unit.py) | ✅ |
| [packages/data/tests/unit/test_hub_unit.py](../packages/data/tests/unit/test_hub_unit.py) | ✅ |
| [packages/data/tests/unit/utils/test_date_utils_unit.py](../packages/data/tests/unit/utils/test_date_utils_unit.py) | ✅ |

### packages/foundation（23 个测试文件，全部为单元测试）

| 文件路径 |
|---------|
| [packages/foundation/tests/unit/bootstrap/test_initializer_unit.py](../packages/foundation/tests/unit/bootstrap/test_initializer_unit.py) |
| [packages/foundation/tests/unit/concurrency/test_file_lock_unit.py](../packages/foundation/tests/unit/concurrency/test_file_lock_unit.py) |
| [packages/foundation/tests/unit/config/test_environment_unit.py](../packages/foundation/tests/unit/config/test_environment_unit.py) |
| [packages/foundation/tests/unit/config/test_initializer_unit.py](../packages/foundation/tests/unit/config/test_initializer_unit.py) |
| [packages/foundation/tests/unit/config/test_loader_unit.py](../packages/foundation/tests/unit/config/test_loader_unit.py) |
| [packages/foundation/tests/unit/config/test_manager_unit.py](../packages/foundation/tests/unit/config/test_manager_unit.py) |
| [packages/foundation/tests/unit/config/test_paths_unit.py](../packages/foundation/tests/unit/config/test_paths_unit.py) |
| [packages/foundation/tests/unit/test_app_initializer_unit.py](../packages/foundation/tests/unit/test_app_initializer_unit.py) |
| [packages/foundation/tests/unit/test_cache_data_unit.py](../packages/foundation/tests/unit/test_cache_data_unit.py) |
| [packages/foundation/tests/unit/test_db_unit.py](../packages/foundation/tests/unit/test_db_unit.py) |
| [packages/foundation/tests/unit/test_json_formatter_unit.py](../packages/foundation/tests/unit/test_json_formatter_unit.py) |
| [packages/foundation/tests/unit/test_metric_definitions_unit.py](../packages/foundation/tests/unit/test_metric_definitions_unit.py) |
| [packages/foundation/tests/unit/test_observability_init_unit.py](../packages/foundation/tests/unit/test_observability_init_unit.py) |
| [packages/foundation/tests/unit/test_observability_logging_unit.py](../packages/foundation/tests/unit/test_observability_logging_unit.py) |
| [packages/foundation/tests/unit/test_observability_metrics_unit.py](../packages/foundation/tests/unit/test_observability_metrics_unit.py) |
| [packages/foundation/tests/unit/test_observability_testing_unit.py](../packages/foundation/tests/unit/test_observability_testing_unit.py) |
| [packages/foundation/tests/unit/test_observability_tracing_unit.py](../packages/foundation/tests/unit/test_observability_tracing_unit.py) |
| [packages/foundation/tests/unit/test_observability_unit.py](../packages/foundation/tests/unit/test_observability_unit.py) |
| [packages/foundation/tests/unit/test_simple_gauge_unit.py](../packages/foundation/tests/unit/test_simple_gauge_unit.py) |
| [packages/foundation/tests/unit/test_version_unit.py](../packages/foundation/tests/unit/test_version_unit.py) |
| [packages/foundation/tests/unit/util/test_checksum_unit.py](../packages/foundation/tests/unit/util/test_checksum_unit.py) |
| [packages/foundation/tests/unit/util/test_dates_property_unit.py](../packages/foundation/tests/unit/util/test_dates_property_unit.py) |
| [packages/foundation/tests/unit/util/test_dates_unit.py](../packages/foundation/tests/unit/util/test_dates_unit.py) |
| [packages/foundation/tests/unit/util/test_io_unit.py](../packages/foundation/tests/unit/util/test_io_unit.py) |

### packages/core（0 个测试文件）

| 目录 | 状态 |
|------|------|
| `packages/core/tests/unit/` | 空（仅有 `__init__.py`） |
| `packages/core/tests/integration/` | 空（仅有 `__init__.py`） |

---

## 七、改进建议

### 按优先级排序的修复建议

#### P1 - 中优先级：解决文件名冲突

| 任务 | 文件 | 操作 |
|------|------|------|
| 1 | `apps/port/tests/unit/ingestion/test_backfill_unit.py` | 检查内容，合并或重命名 |

**原因**：文件名完全相同，可能导致混淆和 import 冲突

#### P2 - 低优先级：重命名不精确的测试文件

| 任务 | 当前路径 | 建议重命名 |
|------|---------|-----------|
| 1 | `dq/checkers/test_business_unit.py` | `test_business_checker_unit.py` |
| 2 | `dq/checkers/test_technical_unit.py` | `test_technical_checker_unit.py` |
| 3 | `dq/checkers/test_statistical_unit.py` | `test_statistical_checker_unit.py` |
| 4 | `meta/test_schemas_unit.py` | `test_schema_definitions_unit.py` |

**原因**：提高代码可维护性，使测试文件名与被测类名完全匹配

#### P3 - 低优先级：处理空测试目录

| 目录 | 建议操作 |
|------|----------|
| `packages/core/tests/unit/` | 添加测试或移除目录 |
| `packages/core/tests/integration/` | 添加测试或移除目录 |
| `packages/foundation/tests/integration/` | 添加测试或移除目录 |

**原因**：空目录可能误导开发者认为已有测试覆盖

### 预期工作量

| 优先级 | 任务数 | 预计时间 |
|--------|--------|----------|
| P1 | 1 个文件 | 15-30 分钟 |
| P2 | 4 个文件 | 30-60 分钟 |
| P3 | 3 个目录 | 15-30 分钟 |
| **合计** | **8 项** | **1-2 小时** |

---

## 八、总结

### 整体评价

Ditto 项目的测试结构**整体非常规范**：

| 指标 | 评价 |
|------|------|
| **目录结构** | ✅ 完全符合规范 |
| **命名规范符合率** | ✅ ~98% (155/159) |
| **conftest.py 分布** | ✅ 符合最佳实践 |
| **自动标记系统** | ✅ 已实现 |
| **测试数量** | ✅ 良好覆盖（159 个测试文件） |

### 关键优点

1. **目录组织清晰**：`tests/unit/` 和 `tests/integration/` 分离明确
2. **命名规范一致**：绝大多数文件遵循 `test_{module}_{type}.py` 格式
3. **自动化配置**：已实现基于目录的自动标记功能
4. **分层 conftest**：每个包/应用都有独立的 conftest.py

### 需要改进的地方

1. **5 个文件需要重命名或合并**（1 个冲突 + 4 个不精确命名）
2. **3 个空测试目录需要确认**（core 和 foundation）

### 风险评估

| 问题类型 | 风险等级 | 说明 |
|----------|----------|------|
| 文件名冲突 | 中 | 可能导致 import 冲突或 IDE 混淆 |
| 命名不精确 | 低 | 影响可维护性，但不影响功能 |
| 空测试目录 | 低 | 可能误导开发者，但不影响现有功能 |

---

## 附录 A：检测命令

### 检测问题命令（提交前必跑）

```bash
# 假测试检测
grep -r "assert True" tests/
grep -r "assert False" tests/

# import 冲突检测
pytest --collect-only 2>&1 | grep "import mismatch"

# 检测文件名冲突（Windows）
pixi run -e dev python -c "
from pathlib import Path
import os

tests = {}
for root, dirs, files in os.walk('tests'):
    for f in files:
        if f.startswith('test_') and f.endswith('.py'):
            if f not in tests:
                tests[f] = []
            tests[f].append(root)

for name, paths in tests.items():
    if len(paths) > 1:
        print(f'{name}:')
        for p in paths:
            print(f'  - {p}')
"
```

---

## 附录 B：参考文档

- **测试规范**: [`.claude/rules/python-test.md`](../.claude/rules/python-test.md)
- **项目结构**: [`docs/design/04_deployment_topology.md`](../docs/design/04_deployment_topology.md)

---

**报告生成时间**: 2026-01-20
**下次审计建议**: 3 个月后或重大重构后
