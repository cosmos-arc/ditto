# 废弃清理：移除 Legacy Derived Catalog 迁移路径

## 背景

Derived Catalog 已全面迁移到 SQLite 后端，旧的 JSON 文件读写器和一次性迁移服务不再有任何活跃的生产引用。项目处于开发阶段，无线上兼容需求。

## 清理范围

### 删除文件（8 个）

| # | 文件 | 原因 |
|---|------|------|
| 1 | `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/_json_records.py` | 旧 JSON I/O |
| 2 | `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/derived_catalog_reader.py` | 旧文件读卡器 |
| 3 | `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/derived_catalog_writer.py` | 旧文件写卡器 |
| 4 | `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/__init__.py` | 仅 re-export |
| 5 | `packages/datahub/src/ditto_datahub/services/derived_migration_service.py` | 一次性迁移服务 |
| 6 | `packages/datahub/tests/unit/stores/runtime/derived_catalog/test_derived_catalog_store_unit.py` | 旧读写器测试 |
| 7 | `packages/datahub/tests/unit/services/test_legacy_derived_catalog_migration_service.py` | 迁移服务测试 |
| 8 | `packages/datahub/tests/integration/runtime/test_legacy_derived_catalog_migration_query_integration.py` | 迁移集成测试 |

1-4 删除后 `derived_catalog/` 目录清空，整体删除。

### 编辑生产代码（6 处）

| # | 文件 | 改动 |
|---|------|------|
| 1 | `packages/datahub/src/ditto_datahub/services/__init__.py` | 移除 `LegacyDerivedCatalogMigration*` 的 import 和 `__all__` |
| 2 | `apps/port/src/ditto_port/registry/datahub/derived.py` | 移除 import 和 `legacy_derived_catalog_migration_service` provider |
| 3 | `apps/port/src/ditto_port/registry/contexts/materialization.py` | 移除 `migration_service` 上下文字段 |
| 4 | `apps/port/src/ditto_port/registry/contexts/bundle.py` | 移除 `migration_service` bundle 字段及其注入 |
| 5 | `apps/port/src/ditto_port/jobs/flows/materialization.py` | 删除 `migrate_legacy_derived_catalog_flow` 函数和 `__all__` 导出 |
| 6 | `apps/port/src/ditto_port/jobs/flows/__init__.py` | 移除 `migrate_legacy_derived_catalog_flow` 的 import 和 `__all__` |

### 编辑测试代码（4 处）

| # | 文件 | 改动 |
|---|------|------|
| 1 | `apps/port/tests/unit/jobs/flows/test_materialization_flows_unit.py` | 移除对 `migrate_legacy_derived_catalog_flow` 的测试断言 |
| 2 | `apps/port/tests/integration/flows/test_derived_materialization_query_repair_integration.py` | fixture 中移除 `migration_service` 注入 |
| 3 | `apps/port/tests/integration/flows/test_derived_publication_integration.py` | fixture 中移除 `migration_service` 注入 |
| 4 | `apps/port/tests/integration/flows/test_research_dataset_integration.py` | fixture 中移除 `migration_service` 注入和迁移调用 |

### 保留不动

- Publication Safety 整套子系统（含其 `_json_records.py`）
- SQLite derived catalog 读写
- 所有活跃业务代码

## 执行顺序

1. 先编辑测试代码和生产代码（移除引用）
2. 再删除源文件
3. 运行 `pixi run -e dev check` 验证

## 执行结果

**状态：已完成** (2026-03-17)

- ruff check：通过
- basedpyright：0 errors, 0 warnings
- pytest：2196 passed, 0 failed (27.76s)
