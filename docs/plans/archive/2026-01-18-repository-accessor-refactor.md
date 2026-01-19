# Repository → Accessor 重命名计划

## 概述

将 Ditto 项目中的数据访问层命名统一化：
- **外部数据源**：`SourcesAccessor` → `DataSources`（提供数据）
- **内部数据访问**：`*Repository` → `*Accessor`（访问数据）

**设计决策背景：**
- 原命名 `Repository` 来自 DDD 模式，但 Ditto 的实现更接近 Table Data Gateway（Fowler）+ DAO 混合模式
- Repository 在 DDD 中表示聚合根容器，需要完整生命周期管理和事务边界，但 Ditto 实际是 DataFrame 操作（贫血模型）
- 新命名更准确反映实际职责：
  - `DataSources` - 外部数据提供者（pull data）
  - `*Accessor` - 内部数据访问（expose data with business logic）

## 重命名映射表

| 当前名称 | 新名称 | 文件路径 |
|---------|--------|----------|
| `SourcesAccessor` | `DataSources` | `packages/datahub/src/ditto_datahub/sources/accessor.py` |
| `BarsRepository` | `BarsAccessor` | `packages/datahub/src/ditto_datahub/repositories/bars/repository.py` |
| `SecurityRepository` | `SecuritiesAccessor` | `packages/datahub/src/ditto_datahub/repositories/security.py` |
| `CalendarRepository` | `CalendarAccessor` | `packages/datahub/src/ditto_datahub/repositories/calendar.py` |
| `IndexRepository` | `IndexAccessor` | `packages/datahub/src/ditto_datahub/repositories/index.py` |
| `UniverseRepository` | `UniverseAccessor` | `packages/datahub/src/ditto_datahub/repositories/universe.py` |
| `AdjFactorRepository` | `AdjFactorAccessor` | `packages/datahub/src/ditto_datahub/repositories/adj_factor.py` |

---

## Phase 1: 核心实现文件重命名

### 1.1 Sources 模块

**文件**: `packages/datahub/src/ditto_datahub/sources/accessor.py`
- [x] 类名：`SourcesAccessor` → `DataSources`
- [x] 文件名：`accessor.py` → `provider.py`
- [x] 类文档字符串更新

**文件**: `packages/datahub/src/ditto_datahub/sources/__init__.py`
- [x] 导入语句更新

### 1.2 Repository 模块

**文件**: `packages/datahub/src/ditto_datahub/repositories/bars/repository.py`
- [x] 类名：`BarsRepository` → `BarsAccessor`
- [x] 类文档字符串更新
- [x] 内部注释更新

**文件**: `packages/datahub/src/ditto_datahub/repositories/security.py`
- [x] 类名：`SecurityRepository` → `SecuritiesAccessor`
- [x] 类文档字符串更新

**文件**: `packages/datahub/src/ditto_datahub/repositories/calendar.py`
- [x] 类名：`CalendarRepository` → `CalendarAccessor`
- [x] 类文档字符串更新

**文件**: `packages/datahub/src/ditto_datahub/repositories/index.py`
- [x] 类名：`IndexRepository` → `IndexAccessor`
- [x] 类文档字符串更新

**文件**: `packages/datahub/src/ditto_datahub/repositories/universe.py`
- [x] 类名：`UniverseRepository` → `UniverseAccessor`
- [x] 类文档字符串更新

**文件**: `packages/datahub/src/ditto_datahub/repositories/adj_factor.py`
- [x] 类名：`AdjFactorRepository` → `AdjFactorAccessor`
- [x] 类文档字符串更新

### 1.3 模块导出更新

**文件**: `packages/datahub/src/ditto_datahub/repositories/__init__.py`
- [x] 更新所有导出的类名
- [x] 更新模块文档字符串

**文件**: `packages/datahub/src/ditto_datahub/repositories/bars/__init__.py`
- [x] 更新导出类名

### 1.4 DataHub 门面更新

**文件**: `packages/datahub/src/ditto_datahub/hub.py`
- [x] 类型注解更新
- [x] 属性文档字符串更新（保持属性名不变）

---

## Phase 2: 测试文件更新

### 2.1 单元测试文件

**文件**: `packages/datahub/tests/unit/sources/test_accessor_unit.py`
- [x] 文件名：`test_accessor_unit.py` → `test_provider_unit.py`
- [x] 类名：`TestSourcesAccessor` → `TestDataSources`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/unit/repositories/test_bars_repository_unit.py`
- [x] 类名：`TestBarsRepository` → `TestBarsAccessor`
- [x] 所有导入语句更新
- [x] 测试方法中的注释更新

**文件**: `packages/datahub/tests/unit/repositories/test_security_repository_unit.py`
- [x] 类名：`TestSecurityRepository` → `TestSecuritiesAccessor`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/unit/repositories/test_calendar_repository_unit.py`
- [x] 类名：`TestCalendarRepository` → `TestCalendarAccessor`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/unit/repositories/test_universe_repository_unit.py`
- [x] 类名：`TestUniverseRepository` → `TestUniverseAccessor`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/unit/repositories/test_index_repository_unit.py`
- [x] 类名：`TestIndexRepository` → `TestIndexAccessor`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/unit/repositories/test_adj_factor_repository_unit.py`
- [x] 类名：`TestAdjFactorRepository` → `TestAdjFactorAccessor`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/unit/test_hub_unit.py`
- [x] 所有导入语句更新
- [x] 测试中的注释更新

### 2.2 集成测试文件

**文件**: `packages/datahub/tests/integration/runtime/test_sid_allocator_integration.py`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/integration/runtime/test_sql_engine_integration.py`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/integration/runtime/test_sqlite_pool_integration.py`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/integration/stores/test_calendar_store_concurrent_integration.py`
- [x] 所有导入语句更新

**文件**: `packages/datahub/tests/integration/stores/test_ingestion_log_concurrent_integration.py`
- [x] 所有导入语句更新

---

## Phase 3: 应用层文件更新

### 3.1 Port 应用

**文件**: `apps/port/src/ditto_port/jobs/tasks/dq_batch.py`
- [x] 所有导入语句更新

**文件**: `apps/port/tests/conftest.py`
- [x] Mock fixture 中的类型注解更新
- [x] 注释更新

**文件**: `apps/port/tests/unit/conftest.py`
- [x] Mock fixture 中的类型注解更新

---

## Phase 4: 设计文档更新

### 4.1 系统设计文档

**文件**: `docs/design/01_system_design.md`
- [x] 架构图更新（Repository 层 → Accessor 层）
- [x] 所有类名引用更新
- [x] 所有代码示例更新

**文件**: `docs/design/02_data_design.md`
- [x] 架构图更新
- [x] 类定义代码块更新
- [x] `SourcesAccessor` → `DataSources`
- [x] 所有 `*Repository` → `*Accessor`

**文件**: `docs/design/11_port_architecture.md`
- [x] 架构图更新
- [x] 类名引用更新

### 4.2 Sprint 文档

**文件**: `docs/sprints/sprint-01-data-foundation.md`
- [x] Task 描述中的类名更新
- [x] 完成状态中的类名更新

**文件**: `docs/sprints/sprint-02-data-quality.md`
- [x] Task 描述中的类名更新
- [x] 完成状态中的类名更新

**文件**: `docs/sprints/backlog.md`
- [x] 所有相关引用更新

---

## Phase 5: README 和规范文档更新

### 5.1 DataHub README

**文件**: `packages/datahub/README.md`
- [x] 架构图更新（Repository 层 → Accessor 层）
- [x] 层级表格更新
- [x] 所有代码示例更新
- [x] 复权实现说明更新
- [x] 文件路径引用更新

### 5.2 子模块 README

**文件**: `packages/datahub/src/ditto_datahub/repositories/README.md`
- [x] 目录说明更新（如果目录名也改）
- [x] 所有类名引用更新

**文件**: `packages/datahub/tests/unit/repositories/README.md`
- [x] 所有类名引用更新

**文件**: `packages/datahub/tests/unit/sources/README.md`
- [x] `SourcesAccessor` → `DataSources`

**文件**: `packages/datahub/src/ditto_datahub/sources/README.md`
- [x] 所有类名引用更新

### 5.3 规范文档

**文件**: `.claude/rules/datahub.md`
- [x] Repository 层 → Accessor 层
- [x] 所有类名引用更新
- [x] 所有代码示例更新

**文件**: `.claude/rules/core.md`
- [x] 代码示例中的类名更新

---

## Phase 6: 计划和归档文档更新

### 6.1 计划文档

**文件**: `docs/plans/2026-01-17-architecture-refactor-plan.md`
- [x] 所有类名引用更新

**文件**: `docs/plans/archive/*.md`（多个）
- [x] 历史计划文档中的类名更新

---

## Phase 7: Core 包示例代码更新

### 7.1 Core README

**文件**: `packages/core/README.md`
- [x] 示例代码中的类名更新

**文件**: `packages/core/tests/unit/README.md`
- [x] 示例代码中的类名更新

**文件**: `packages/core/tests/README.md`
- [x] 示例代码中的类名更新

---

## Phase 8: 注释和文档字符串更新

### 8.1 代码注释

**所有源文件**：
- [x] 类定义中的注释
- [x] 方法中的注释
- [x] 行内注释

### 8.2 文档字符串

**所有类和方法**：
- [x] 类文档字符串
- [x] 方法文档字符串
- [x] 参数说明中的类名引用

---

## 验证清单

完成所有修改后，执行以下验证：

### 代码验证

```bash
# 1. 类型检查
pixi run -e dev type --all

# 2. 代码检查
pixi run -e dev lint

# 3. 格式检查
pixi run -e dev fmt --check

# 4. 单元测试
pixi run -e dev test --unit

# 5. 集成测试
pixi run -e dev test --integration

# 6. 完整 CI
pixi run -e dev ci
```

### 引用验证

```bash
# 使用 git grep 查找遗漏的引用
git grep -i "Repository" -- "*.py" | grep -v "test_repository"
git grep -i "SourcesAccessor" -- "*.py"
git grep -i "repository" -- "*.md"
```

### 语义验证

- [x] 确认所有类名引用已更新
- [x] 确认所有文档字符串已更新
- [x] 确认所有注释已更新
- [x] 确认 DataHub 属性名保持不变（用户接口不变）
- [x] 确认所有测试通过

---

## 关键文件清单

### 核心实现（11 个文件）

```
packages/datahub/src/ditto_datahub/hub.py
packages/datahub/src/ditto_datahub/sources/accessor.py → provider.py
packages/datahub/src/ditto_datahub/sources/__init__.py
packages/datahub/src/ditto_datahub/repositories/__init__.py
packages/datahub/src/ditto_datahub/repositories/bars/repository.py
packages/datahub/src/ditto_datahub/repositories/bars/__init__.py
packages/datahub/src/ditto_datahub/repositories/security.py
packages/datahub/src/ditto_datahub/repositories/calendar.py
packages/datahub/src/ditto_datahub/repositories/index.py
packages/datahub/src/ditto_datahub/repositories/universe.py
packages/datahub/src/ditto_datahub/repositories/adj_factor.py
```

### 测试文件（8+ 个文件）

```
packages/datahub/tests/unit/sources/test_accessor_unit.py → test_provider_unit.py
packages/datahub/tests/unit/repositories/test_bars_repository_unit.py
packages/datahub/tests/unit/repositories/test_security_repository_unit.py
packages/datahub/tests/unit/repositories/test_calendar_repository_unit.py
packages/datahub/tests/unit/repositories/test_universe_repository_unit.py
packages/datahub/tests/unit/repositories/test_index_repository_unit.py
packages/datahub/tests/unit/repositories/test_adj_factor_repository_unit.py
packages/datahub/tests/unit/test_hub_unit.py
packages/datahub/tests/integration/**/*.py
```

### 应用层（3 个文件）

```
apps/port/src/ditto_port/jobs/tasks/dq_batch.py
apps/port/tests/conftest.py
apps/port/tests/unit/conftest.py
```

### 文档（20+ 个文件）

```
docs/design/*.md
docs/sprints/*.md
docs/plans/*.md
packages/datahub/README.md
packages/datahub/**/README.md
.claude/rules/*.md
packages/core/**/README.md
```

---

## 执行建议

1. **按 Phase 顺序执行**，每个 Phase 完成后运行测试验证
2. **使用 Git 频繁提交**，每个 Phase 一个 commit
3. **使用 IDE 重构功能**（如 PyCharm 的 Rename Symbol）确保完整性
4. **最后统一更新文档**，避免中间状态混淆
5. **完成所有修改后**，运行完整的 CI 验证

---

## 统计

| 类型 | 数量 |
|------|------|
| 重命名类 | 7 个 |
| 核心实现文件 | 11 个 |
| 测试文件 | 15+ 个 |
| 应用层文件 | 3 个 |
| 文档文件 | 20+ 个 |
| 导入语句 | 50+ 处 |

---

## 参考资料

- [DAO vs Repository Patterns - Baeldung](https://www.baeldung.com/java-dao-vs-repository)
- [Table Data Gateway - Martin Fowler](https://martinfowler.com/eaaCatalog/tableDataGateway.html)
- [Data Pipeline Design in an Algorithmic Trading System - Medium](https://medium.com/@edwinsalguero/data-pipeline-design-in-an-algorithmic-trading-system-ac0d8109c4b9)
