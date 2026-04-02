# 代码规模改进计划

## 概述

**创建**: 2026-01-22
**依据**: [架构审计报告](../reviews/2026-01-22-architecture-audit.md) + [代码规模规范](../../.claude/rules/core.md#代码规模规范)

**目标**: 混合方案
1. 创建代码规模检查脚本（自动化）
2. 重构关键类（按单一职责原则）

---

## 技术方案

### 1. 代码规模检查脚本

**实现方式**: AST 分析 + 命令行输出

**检查项**:
| 指标 | 阈值 | 检查方法 |
|------|------|----------|
| 单文件行数 | ≤ 800 | 文件物理行数统计 |
| 类 public 方法数 | ≤ 20 | AST 分析，排除 `__*` 方法 |

**输出格式**:
```
🔍 Code Size Check Report

📁 Files exceeding 800 lines: 0
🔧 Classes with >20 public methods: 1
  ⚠️ IngestionCoordinator: 18 methods (coordinator.py:26)

✅ All checks passed
```

**集成**:
- 独立命令: `pixi run -e dev python scripts/check_code_size.py`
- CI 集成: 警告模式，不阻断合并

---

### 2. 重构策略

#### IngestionCoordinator (18 个方法)

**当前问题**:
- 包含 18 个方法，职责边界模糊
- 混合了流程编排 + 结果处理 + 数据写入

**重构方案**:

```python
# 重构前
class IngestionCoordinator:
    def ingest_date(self): ...
    def _check_should_skip(self): ...
    def _handle_fetch_error(self): ...
    def _handle_write_error(self): ...
    def _handle_success(self): ...
    # ... 18 个方法

# 重构后
class IngestionCoordinator:  # 流程编排（主入口）
    def ingest_date(self): ...

class IngestionResultHandler:  # 结果处理
    def handle_fetch_error(self): ...
    def handle_write_error(self): ...
    def handle_success(self): ...

class IngestionDataWriter:  # 数据写入
    def write_data(self): ...
    def write_stock_basic(self): ...
```

#### TushareSource (648 行)

**当前问题**:
- 职责过多：fetch + transform + validate
- 违反单一职责原则

**重构方案**:
- 提取 `TushareTransformer` 独立模块
- 提取 `TushareValidator` 独立模块
- `TushareSource` 保留为组合入口

#### BarsAccessor (644 行)

**当前问题**:
- 包含复杂查询构建 + 数据转换
- 职责边界模糊

**重构方案**:
- 提取 `BarsQueryBuilder` (查询构建)
- 提取 `BarsDataProcessor` (数据转换)
- `BarsAccessor` 简化为协调器

---

## 任务清单

### Phase 1: 检查脚本 (优先级: P0)

- [ ] **Task: 创建代码规模检查脚本** `[M]`
  - **验收**: 能正确检测文件行数和类 public 方法数
  - **文件**: `scripts/check_code_size.py`
  - **子任务**:
    - [ ] 实现 AST 分析器
    - [ ] 实现文件行数统计
    - [ ] 实现类 public 方法数统计
    - [ ] 实现格式化输出
    - [ ] 添加单元测试

### Phase 2: IngestionCoordinator 重构 (优先级: P1)

- [ ] **Task: 提取 IngestionResultHandler** `[S]`
  - **验收**: 测试通过，无行为变化
  - **文件**: `apps/port/src/ditto_port/services/ingestion/`
  - **测试**: `apps/port/tests/unit/services/ingestion/`

- [ ] **Task: 提取 IngestionDataWriter** `[S]`
  - **验收**: 测试通过，无行为变化
  - **文件**: `apps/port/src/ditto_port/services/ingestion/`
  - **测试**: `apps/port/tests/unit/services/ingestion/`

- [ ] **Task: 简化 IngestionCoordinator** `[S]`
  - **验收**: 方法数 < 15，测试通过
  - **文件**: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
  - **测试**: `apps/port/tests/unit/services/ingestion/test_coordinator_unit.py`

### Phase 3: TushareSource 重构 (优先级: P2)

- [ ] **Task: 提取 TushareTransformer** `[M]`
  - **验收**: 测试通过，独立模块可测试
  - **文件**: `packages/data/src/ditto_data/sources/tushare/`
  - **测试**: `packages/data/tests/unit/sources/tushare/`

- [ ] **Task: 提取 TushareValidator** `[S]`
  - **验收**: 测试通过，独立模块可测试
  - **文件**: `packages/data/src/ditto_data/sources/tushare/`
  - **测试**: `packages/data/tests/unit/sources/tushare/`

- [ ] **Task: 重构 TushareSource 为组合模式** `[M]`
  - **验收**: 文件行数 < 500，测试通过
  - **文件**: `packages/data/src/ditto_data/sources/tushare/tushare_source.py`
  - **测试**: `packages/data/tests/unit/sources/tushare/`

### Phase 4: BarsAccessor 重构 (优先级: P2)

- [ ] **Task: 提取 BarsQueryBuilder** `[M]`
  - **验收**: 测试通过，查询构建逻辑独立
  - **文件**: `packages/data/src/ditto_data/accessors/bars/`
  - **测试**: `packages/data/tests/unit/accessors/`

- [ ] **Task: 提取 BarsDataProcessor** `[M]`
  - **验收**: 测试通过，数据转换逻辑独立
  - **文件**: `packages/data/src/ditto_data/accessors/bars/`
  - **测试**: `packages/data/tests/unit/accessors/`

- [ ] **Task: 简化 BarsAccessor** `[S]`
  - **验收**: 文件行数 < 500，测试通过
  - **文件**: `packages/data/src/ditto_data/accessors/bars/accessor.py`
  - **测试**: `packages/data/tests/unit/accessors/test_bars_accessor_unit.py`

### Phase 5: 更新 DI 容器 (优先级: P3)

- [ ] **Task: 更新 DataHub Provider** `[S]`
  - **验收**: DI 容器正确注入新的依赖
  - **文件**: `apps/port/src/ditto_port/registry/datahub.py`
  - **测试**: `apps/port/tests/registry/`

---

## 验证命令

```bash
# 代码规模检查
pixi run -e dev python scripts/check_code_size.py

# 完整检查
pixi run -e dev ci

# 单元测试
pixi run -e dev test --unit

# 类型检查
pixi run -e dev type
```

---

## 参考文档

- [架构审计报告](../reviews/2026-01-22-architecture-audit.md)
- [代码规模规范](../../.claude/rules/core.md#代码规模规范)
- [重构指导](../../.claude/rules/core.md#重构指导)
