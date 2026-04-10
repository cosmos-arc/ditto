# SQLite Schema 版本化迁移系统

## Context

当前 `SQLitePool.init_schema()` 在检测到列不匹配时，无条件调用 `_reset_all_user_tables()` 丢弃所有用户数据。`main` 分支曾有 `DITTO_ALLOW_SCHEMA_REBUILD=1` 守卫（fail-fast），当前分支在清理废弃代码时将其移除。

Schema 演进历史显示 15 次提交全部是加列/加表（从无 DROP），`CREATE TABLE IF NOT EXISTS` 已安全处理新表。真正风险仅在现有表加列时触发全量 DROP。

**目标**：用版本化增量迁移替代"全匹配或全丢弃"，加列零数据丢失，破坏性变更 fail-fast + 备份。

## 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 版本常量位置 | Data 层 `scripts/schema_version.py` | Infra 零业务逻辑约束 |
| 迁移函数位置 | Data 层 `scripts/migrations/` | 同上 |
| 注册方式 | 构造函数 `migrations` 参数 | 避免 Infra 层全局状态，显式依赖 |
| 初始版本号 | `schema.sql` = v1，无 `_schema_meta` 的 DB = v0 (legacy) | 干净基线 |
| Legacy 过渡 | 检测无 `_schema_meta` + 有用户表 → stamp v1 → 运行 v2+ 迁移 | 所有历史变更都是加列/加表，安全 |
| `schema.sql` 定位 | 仅用于全新安装 | 保持不变，`IF NOT EXISTS` 幂等 |

## 实施步骤

### Step 1: Infra 层 — 新增 `SchemaMigration` 类型

**新建** `packages/infra/src/ditto_infra/foundation/db/schema_migration.py`

```python
class SchemaMigration(NamedTuple):
    target_version: int
    description: str
    migrate: Callable[[sqlite3.Connection], None]

class SchemaMigrationError(Exception):
    def __init__(self, message, current_version, target_version, backup_path=None): ...
```

### Step 2: Infra 层 — 改造 `SQLitePool`

**修改** `packages/infra/src/ditto_infra/foundation/db/sqlite_pool.py`

构造函数新增 `migrations` 参数（`Sequence[SchemaMigration] | None = None`，向后兼容）。

`init_schema()` 新流程：

```
START
  ├─ 无 schema_path 且无 migrations → 跳过
  ├─ _ensure_meta_table(conn)
  ├─ current_version = _get_current_version(conn)  # 无则返回 0
  ├─ has_user_tables?
  │   ├─ 无 → 全新安装: executescript(schema), stamp 最新版本
  │   ├─ 有 且 version=0 → Legacy: stamp v1, 运行 v2+ 迁移
  │   └─ 有 且 version>0 → 已版本化: 运行 pending 迁移
```

新增方法：
- `_ensure_meta_table(conn)` — `CREATE TABLE IF NOT EXISTS _schema_meta (key TEXT PK, value TEXT)`
- `_get_current_version(conn)` / `_stamp_version(conn, v)`
- `_has_user_tables(conn)` — 查 `sqlite_master`（排除 `sqlite_%` 和 `_schema_meta`）
- `_latest_version()` — `self._migrations` 中最大的 `target_version`（或 1 如果无迁移）
- `_run_pending_migrations(conn, current)` — 按顺序执行 pending 迁移，每个成功后 stamp
- `_backup_database()` — `shutil.copy2` 到 `{db_path}/../backups/{stem}_{timestamp}.sqlite`，`:memory:` 返回 None

删除方法：`_needs_schema_rebuild`、`_handle_legacy_schema`、`_reset_all_user_tables`

### Step 3: Infra 层 — 更新导出

**修改** `packages/infra/src/ditto_infra/foundation/db/__init__.py` — 新增导出 `SchemaMigration`, `SchemaMigrationError`

**修改** `packages/infra/src/ditto_infra/foundation/__init__.py` — 同步导出

### Step 4: Infra 层 — 测试

**修改** `packages/infra/tests/unit/db/test_db_unit.py`

替换 `TestLegacySchemaProtection`（3 个旧测试）为 `TestSchemaVersioning`：

| 测试 | 验证 |
|------|------|
| `test_fresh_install_stamps_version` | 全新 DB 创建 `_schema_meta`，version=1 |
| `test_fresh_install_applies_schema` | 全新 DB 有 schema.sql 中的表 |
| `test_legacy_db_detected_and_migrated` | 有表无 `_schema_meta` → stamp v1 → 运行迁移 |
| `test_versioned_db_runs_pending_migrations` | version=1 + 注册 v2 迁移 → 迁移被执行 |
| `test_migration_failure_raises_error` | 迁移异常 → `SchemaMigrationError` |
| `test_idempotent_init_schema` | 重复调用不重复执行迁移 |
| `test_no_schema_no_migrations_skips` | 无 schema_path 无 migrations → 跳过 |
| `test_backup_creates_copy` | `_backup_database()` 产生备份文件 |
| `test_backup_memory_returns_none` | `:memory:` 返回 None |

迁移测试使用 mock migration 函数，验证调用次数和 stamp 行为。

### Step 5: Data 层 — 版本常量 + 迁移注册

**新建** `packages/data/src/ditto_data/scripts/schema_version.py`

```python
CURRENT_SCHEMA_VERSION = 1  # schema.sql = v1
```

**新建** `packages/data/src/ditto_data/scripts/migrations/__init__.py`

```python
def get_migrations() -> list[SchemaMigration]:
    return []  # 当前无迁移，schema.sql 即 v1
```

### Step 6: Data 层 — 注册迁移

**修改** `packages/data/src/ditto_data/di/runtime.py` — `sqlite_pool()` 方法

```python
from ditto_data.scripts.migrations import get_migrations

pool = SQLitePool(
    str(db_path),
    schema_path=schema_path,
    migrations=get_migrations(),
)
```

**修改** `interfaces/src/ditto_interfaces/registry/init_providers.py` — `MetadataDbInitProvider`

仅首次初始化（`not db_path.exists()`），不需要迁移。但为保持一致性，也传入 `migrations=get_migrations()`。

### Step 7: Data 层 — 测试

**新建** `packages/data/tests/unit/scripts/test_migrations.py`

验证 `get_migrations()` 返回有效列表（当前为空）。

### Step 8: 集成测试更新

**修改** `packages/data/tests/integration/runtime/test_sqlite_pool_integration.py`

新增：
- `test_init_schema_creates_meta_table` — 验证 `_schema_meta` 存在
- `test_init_schema_stamps_version` — 验证 version 正确
- `test_reinit_preserves_data` — 写入数据 → 重新 init → 数据完整

### Step 9: 验证

```bash
pixi run -e dev check
```

## 关键文件清单

| 文件 | 操作 |
|------|------|
| `packages/infra/src/ditto_infra/foundation/db/schema_migration.py` | 新建 |
| `packages/infra/src/ditto_infra/foundation/db/sqlite_pool.py` | 修改 |
| `packages/infra/src/ditto_infra/foundation/db/__init__.py` | 修改 |
| `packages/infra/src/ditto_infra/foundation/__init__.py` | 修改 |
| `packages/infra/tests/unit/db/test_db_unit.py` | 修改 |
| `packages/data/src/ditto_data/scripts/schema_version.py` | 新建 |
| `packages/data/src/ditto_data/scripts/migrations/__init__.py` | 新建 |
| `packages/data/src/ditto_data/di/runtime.py` | 修改 |
| `packages/data/tests/unit/scripts/test_migrations.py` | 新建 |
| `packages/data/tests/integration/runtime/test_sqlite_pool_integration.py` | 修改 |
| `interfaces/src/ditto_interfaces/registry/init_providers.py` | 修改 |
