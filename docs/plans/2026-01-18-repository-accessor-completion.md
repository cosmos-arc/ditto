# Repository → Accessor 重命名完善计划

## 概述

原计划 `2026-01-18-repository-accessor-refactor.md` 已标记为完成，但经检查发现以下遗漏项需要补充完成：

### 发现的主要遗漏

1. **源代码文件名**：`repository.py` 未改为 `accessor.py`
2. **测试目录名**：`tests/unit/repositories/` 未改为 `accessors/`
3. **测试文件名**：6个测试文件仍包含 `repository`
4. **测试变量名**：`self.repo` 未改为 `self.accessor`（5个文件，数百次引用）
5. **Fixture 函数名**：`index_repo` 未改为 `index_accessor`
6. **测试方法名**：5个方法名仍包含 `repository`
7. **文档字符串**：19处模块和类文档仍使用 `Repository`
8. **代码注释**：4处注释中的 `Repository` 引用
9. **文档文件**：8+ 个设计/Sprint/规范文档未更新

---

## Phase 1: 源代码文件重命名

### 1.1 Bars 模块文件重命名

**当前文件**: `packages/datahub/src/ditto_datahub/repositories/bars/repository.py`
**重命名为**: `packages/datahub/src/ditto_datahub/repositories/bars/accessor.py`

### 1.2 更新导入语句

**文件**: `packages/datahub/src/ditto_datahub/repositories/bars/__init__.py`
- [x] 更新：`from .repository import BarsAccessor` → `from .accessor import BarsAccessor`

**需要更新导入的文件**:
- [x] `packages/datahub/tests/unit/repositories/test_bars_repository_unit.py` (重命名后)
- [x] `packages/datahub/tests/unit/test_hub_unit.py`
- [x] `packages/datahub/src/ditto_datahub/hub.py`

---

## Phase 2: 测试目录和文件重命名

### 2.1 测试目录重命名

- [x] `packages/datahub/tests/unit/repositories/` → `accessors/`

### 2.2 测试文件重命名（6个文件）

| 当前文件 | 新文件 |
|---------|--------|
| `test_bars_repository_unit.py` | `test_bars_accessor_unit.py` |
| `test_calendar_repository_unit.py` | `test_calendar_accessor_unit.py` |
| `test_security_repository_unit.py` | `test_security_accessor_unit.py` |
| `test_universe_repository_unit.py` | `test_universe_accessor_unit.py` |
| `test_index_repository_unit.py` | `test_index_accessor_unit.py` |
| `test_adj_factor_repository_unit.py` | `test_adj_factor_accessor_unit.py` |

### 2.3 源代码目录重命名（Phase 2+ 新增任务）

- [x] `packages/datahub/src/ditto_datahub/repositories/` → `accessors/`

### 2.4 更新导入语句（Phase 2+ 新增任务）

**源代码文件更新（4个）**:
- [x] `packages/datahub/src/ditto_datahub/accessors/__init__.py`
- [x] `packages/datahub/src/ditto_datahub/accessors/bars/__init__.py`
- [x] `packages/datahub/src/ditto_datahub/accessors/bars/accessor.py`
- [x] `packages/datahub/src/ditto_datahub/hub.py`

**测试文件更新（8个）**:
- [x] `packages/datahub/tests/unit/accessors/test_bars_accessor_unit.py`
- [x] `packages/datahub/tests/unit/accessors/test_adj_factor_accessor_unit.py`
- [x] `packages/datahub/tests/unit/accessors/test_calendar_accessor_unit.py`
- [x] `packages/datahub/tests/unit/accessors/test_index_accessor_unit.py`
- [x] `packages/datahub/tests/unit/accessors/test_security_accessor_unit.py`
- [x] `packages/datahub/tests/unit/accessors/test_universe_accessor_unit.py`
- [x] `packages/datahub/tests/unit/accessors/test_filter_failed_rows.py`
- [x] `packages/datahub/tests/unit/accessors/bars/test_adjustment_unit.py`

**Apps 文件更新（4个）**:
- [x] `apps/port/src/ditto_port/jobs/tasks/dq_batch.py`
- [x] `apps/port/tests/unit/ingestion/test_coordinator_unit.py`
- [x] `apps/port/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py`
- [x] `apps/port/tests/integration/ingestion/test_adj_factor_ingestion_integration.py`

**导入替换模式**: `from ditto_datahub.repositories.*` → `from ditto_datahub.accessors.*`

---

## Phase 3: 测试变量名更新

### 3.1 `self.repo` → `self.accessor`（5个文件）

| 文件 | 行号 | 引用次数 | 状态 |
|------|------|---------|------|
| `test_calendar_accessor_unit.py` | 19 | ~24 | ✅ 完成 |
| `test_adj_factor_accessor_unit.py` | 23 | ~8 | ✅ 完成 |
| `test_universe_accessor_unit.py` | 29 | ~31 | ✅ 完成 |
| `test_security_accessor_unit.py` | 22 | ~36 | ✅ 完成 |
| `test_bars_accessor_unit.py` | 309, 433, 633, 900, 1091, 1327, 1623 | ~40 | ✅ 完成 |

### 3.2 Fixture 更新

**文件**: `test_index_accessor_unit.py`
- [x] 第 31 行：`def index_repo(...)` → `def index_accessor(...)`
- [x] 13个方法参数：`index_repo: IndexAccessor` → `index_accessor: IndexAccessor`

---

## Phase 4: 测试方法名更新

### 4.1 test_hub_unit.py

- [x] 第 143 行：`test_lazy_loading_bars_repository` → `test_lazy_loading_bars_accessor`
- [x] 第 208 行：`test_universe_repository_lazy_loading` → `test_universe_accessor_lazy_loading`
- [x] 第 231 行：`test_index_repository_lazy_loading` → `test_index_accessor_lazy_loading`

### 4.2 Repository 测试文件

- [x] `test_index_accessor_unit.py` 第 53 行：`test_repository_init` → `test_accessor_init`
- [x] `test_universe_accessor_unit.py` 第 47 行：`test_repository_init` → `test_accessor_init`

---

## Phase 5: 文档字符串更新（19处）

### 5.1 模块文档字符串（12处）

**universe.py**
- [x] 第 2 行：`Universe Repository for...` → `Universe Accessor for...`
- [x] 第 20 行：`Security universe repository.` → `Security universe accessor.`

**calendar.py**
- [x] 第 1 行：`Calendar Repository for...` → `Calendar Accessor for...`
- [x] 第 15 行：`Trading calendar repository.` → `Trading calendar accessor.`

**security.py**
- [x] 第 1 行：`Security Repository for...` → `Securities Accessor for...`
- [x] 第 17 行：`Securities master data repository.` → `Securities master data accessor.`

**index.py**
- [x] 第 1 行：`Index Repository for...` → `Index Accessor for...`
- [x] 第 15 行：`Index data repository.` → `Index data accessor.`

**adj_factor.py**
- [x] 第 1 行：`AdjFactor Repository for...` → `AdjFactor Accessor for...`
- [x] 第 15 行：`Adjustment factor repository for...` → `Adjustment factor accessor for...`

**bars/repository.py** → **bars/accessor.py**
- [x] 第 1 行：`Bars Repository for...` → `Bars Accessor for...`
- [x] 第 117 行：`Market data repository for...` → `Market data accessor for...`

### 5.2 DataHub 类文档字符串（7处）

**文件**: `hub.py`
- [x] 第 52 行：`- Repository Layer:` → `- Accessor Layer:`
- [x] 第 170 行：`Securities master data repository.` → `Securities master data accessor.`
- [x] 第 178 行：`OHLCV bars repository.` → `OHLCV bars accessor.`
- [x] 第 191 行：`Adjustment factor repository.` → `Adjustment factor accessor.`
- [x] 第 199 行：`Trading calendar repository.` → `Trading calendar accessor.`
- [x] 第 206 行：`Security universe repository.` → `Security universe accessor.`
- [x] 第 215 行：`Index data repository.` → `Index data accessor.`

---

## Phase 6: 代码注释更新（4处）

**hub.py**
- [x] 第 165 行：`# Repository Layer` → `# Accessor Layer`

**test_hub_unit.py**
- [x] 第 197 行：`# Universe Store and Repository Tests` → `# Universe Store and Accessor Tests`
- [x] 第 220 行：`# Index Store and Repository Tests` → `# Index Store and Accessor Tests`

**coordinator.py** (apps/port)
- [x] 第 386 行：`# 使用 Repository 层以获得...` → `# 使用 Accessor 层以获得...`

---

## Phase 7: 文档更新

### 7.1 规范文档（P0 - 立即修改）

**README.md**
- [x] 第 38 行：架构图中的 `Repository` → `Accessor`
- [x] 第 140 行：目录结构中的 `repositories/` → `accessors/`

**.claude/rules/datahub.md**
- [x] 第 12 行：`Repository | 业务封装` → `Accessor | 业务封装`
- [x] 第 48 行：`Repository 直接写 Parquet` → `Accessor 直接写 Parquet`

**.claude/rules/python-test.md**
- [x] 第 35 行：`测 Repository 逻辑` → `测 Accessor 逻辑`

**.claude/rules/core.md**
- [x] 确保使用 `Accessor` 术语

### 7.2 设计文档（P1）

**docs/design/02_data_design.md**
- [x] 概念描述更新：`Repository` → `Accessor` (12处)
- [x] 架构说明更新：路径和类名更新

### 7.3 Sprint 文档（P1）

**docs/sprints/sprint-01-data-foundation.md**
- [x] 表格中的类名和文件路径更新 (14处)

**docs/sprints/sprint-02-data-quality.md**
- [x] 多处 `Repository` → `Accessor` (58处)
- [x] `repositories/` → `accessors/`

### 7.4 测试文档

**packages/datahub/tests/README.md**
- [x] `repositories/` → `accessors/`

---

## Phase 8: 验证

完成所有修改后执行：

```bash
# 1. 搜索遗留的 repository 变量名
git grep "self\.repo" -- "*.py"

# 2. 搜索测试方法中的 repository
git grep "test_.*repository" -- "*.py"

# 3. 搜索代码中的 Repository 引用（排除注释）
git grep -i "Repository" -- "*.py" | grep -v "#" | grep -v "\"\"\""

# 4. 类型检查
pixi run -e dev type --all

# 5. 代码检查
pixi run -e dev lint

# 6. 格式检查
pixi run -e dev fmt --check

# 7. 单元测试
pixi run -e dev test --unit

# 8. 集成测试
pixi run -e dev test --integration

# 9. 完整 CI
pixi run -e dev ci
```

---

## 关键文件清单

### 需要重命名的文件（8个）

| 当前路径 | 新路径 |
|---------|--------|
| `repositories/bars/repository.py` | `repositories/bars/accessor.py` |
| `tests/unit/repositories/` (目录) | `tests/unit/accessors/` |
| `tests/unit/repositories/test_bars_repository_unit.py` | `tests/unit/accessors/test_bars_accessor_unit.py` |
| `tests/unit/repositories/test_calendar_repository_unit.py` | `tests/unit/accessors/test_calendar_accessor_unit.py` |
| `tests/unit/repositories/test_security_repository_unit.py` | `tests/unit/accessors/test_security_accessor_unit.py` |
| `tests/unit/repositories/test_universe_repository_unit.py` | `tests/unit/accessors/test_universe_accessor_unit.py` |
| `tests/unit/repositories/test_index_repository_unit.py` | `tests/unit/accessors/test_index_accessor_unit.py` |
| `tests/unit/repositories/test_adj_factor_repository_unit.py` | `tests/unit/accessors/test_adj_factor_accessor_unit.py` |

### 需要大量修改的文件

| 文件 | 修改类型 | 预估数量 |
|------|---------|---------|
| `test_bars_accessor_unit.py` | `self.repo` → `self.accessor` | ~200 处 |
| `test_hub_unit.py` | 方法名、注释、导入 | 5+ 处 |
| `hub.py` | 文档字符串、注释 | 8+ 处 |
| 各 `*.py` 文件 | 文档字符串 | 每文件 2 处 |

---

## 执行建议

1. **Phase 1-2**: 先重命名文件和目录
2. **更新所有导入语句**
3. **Phase 3-4**: 修改变量名和方法名
4. **Phase 5-6**: 更新文档字符串和注释
5. **Phase 7**: 更新文档文件
6. **每个 Phase 后运行测试验证**
7. **Phase 8**: 最后运行完整 CI

---

## 统计

| 类型 | 数量 |
|------|------|
| 重命名文件（源+测试） | 8 个 |
| 重命名目录 | 1 个 |
| 修改变量名的文件 | 5 个 |
| 修改 fixture 的文件 | 1 个 |
| 修改方法名的文件 | 2 个 |
| 更新文档字符串的文件 | 7 个 |
| 更新注释的文件 | 3 个 |
| 更新的文档 | 8+ 个 |

---

## 相关文档

- 原计划：`docs/plans/archive/2026-01-18-repository-accessor-refactor.md`
- 此计划补充完成原计划的遗漏项

---

## 后续任务

### Sources 目录命名统一（Phase 9: 待执行）

**方案确认**: 按照项目规范统一使用 **Provider 命名**

#### 命名规则

- `DataSource` → `DataProvider`（基类）
- `TushareSource` → `TushareProvider`（具体实现）
- `SourcesProvider` 保持不变（已经是 Provider）
- 所有异常类：`*SourceError` → `*ProviderError`

#### Phase 9.1 文件重命名

- [ ] `packages/datahub/src/ditto_datahub/sources/base.py` → `provider.py`
- [ ] `packages/datahub/src/ditto_datahub/sources/tushare/source.py` → `tushare_provider.py`

#### Phase 9.2 类名重命名

- [ ] `DataSource` → `DataProvider`（基类）
- [ ] `TushareSource` → `TushareProvider`（具体实现）
- [ ] `DataSourceError` → `DataProviderError`
- [ ] `SourceConfigurationError` → `ProviderConfigurationError`
- [ ] `SourceAuthenticationError` → `ProviderAuthenticationError`
- [ ] `SourceRateLimitError` → `ProviderRateLimitError`
- [ ] `SourceFetchError` → `ProviderFetchError`
- [ ] `SourceTransformationError` → `ProviderTransformationError`

#### Phase 9.3 导入语句更新（需要更新的文件）

**源代码文件**:
- [ ] `packages/datahub/src/ditto_datahub/sources/__init__.py`
- [ ] `packages/datahub/src/ditto_datahub/sources/provider.py` (SourcesProvider)
- [ ] `packages/datahub/src/ditto_datahub/sources/tushare/__init__.py`
- [ ] `packages/datahub/src/ditto_datahub/hub.py`

**测试文件**:
- [ ] `packages/datahub/tests/unit/sources/test_*.py`（所有测试文件）
- [ ] `packages/datahub/tests/integration/sources/`（如有）

#### Phase 9.4 文档和注释更新

- [ ] `packages/datahub/src/ditto_datahub/sources/README.md`
- [ ] 所有文档字符串中的 `Source` → `Provider`（语义保持一致）
- [ ] 所有注释中的 `Source` → `Provider`

#### Phase 9.5 验证

- [ ] 类型检查: `pixi run -e dev type --all`
- [ ] 代码检查: `pixi run -e dev lint`
- [ ] 单元测试: `pixi run -e dev test --unit`
- [ ] 集成测试: `pixi run -e dev test --integration`

**注意**: 此任务需要在新的计划文档中详细规划并执行。
