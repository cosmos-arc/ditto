# Code Review 修复计划

> **目标**: 修复代码审查发现的所有问题
> **范围**: datahub 层代码质量、风控、性能问题
> **创建日期**: 2026-01-12
>
> **触发**: `/ditto-review` 命令执行的并行代码审查

---

## 审查摘要

**审查范围**: 861c56d..4b2f9f3 (datahub-code-simplification-2026-01-11)

**并行审查维度**:
| 维度 | 状态 | Agent ID |
|------|------|----------|
| PIT 安全 | 🟢 通过 | a5aa8be |
| 风控 | 🔴 不可通过 → 🟢 已修复 | ad5b5e0 |
| 代码质量 | 🟡 需修复 → 🟢 已修复 | afecc94 |
| 文档同步 | 🟡 需修复 | - |

---

## 修复任务清单

### ✅ 1. freeze_manager.py: json → orjson

**状态**: 已完成 (2026-01-12)

**问题**: 使用 `import json` 而非 `orjson`（违反项目约束）

**修复内容**:
- ✅ 替换 `import json` → `import orjson`
- ✅ 修改 `json.dump()` → `orjson.dumps()` (处理 bytes 返回值)
- ✅ 修改 `json.load()` → `orjson.loads()` (使用二进制读取模式)
- ✅ 更新集成测试使用 orjson

**测试结果**:
- ✅ 24 个 freeze_manager 相关测试全部通过
- ✅ pre-commit 检查通过

**修改文件**:
- `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py`
- `packages/datahub/tests/integration/runtime/test_freeze_manager_integration.py`

**Agent**: adb2ec3

---

### ✅ 2. parquet_store_base.py: 统计逻辑和性能优化

**状态**: 已完成 (2026-01-12)

**问题**:
1. 统计逻辑错误：`added`/`updated` 计算不准确
2. 性能问题：同一文件读取两次

**修复内容**:
- ✅ 添加 `MergeResult` dataclass 包含精确统计信息
- ✅ 修改 `_merge_with_existing` 返回 `MergeResult`
- ✅ 在 `_merge_with_existing` 中缓存 `existing` DataFrame
- ✅ 修复 `added`/`updated` 计算逻辑（考虑 batch 内部去重）
- ✅ 添加 6 个测试用例验证统计逻辑

**测试结果**:
- ✅ 42 个 parquet_store_base 测试全部通过
- ✅ 35 个 bars_store 测试全部通过
- ✅ 41 个 adj_factor_store 测试全部通过
- ✅ pre-commit 检查通过

**修改文件**:
- `packages/datahub/src/ditto_datahub/stores/parquet_store_base.py`
- `packages/datahub/tests/unit/stores/test_parquet_store_base_unit.py`
- `packages/datahub/tests/unit/stores/test_bars_store_unit.py`

**Agent**: ae9cfa8

---

### ✅ 3. transformer.py: 空数据 schema 推断

**状态**: 已完成 (2026-01-12)

**问题**: 空数据处理时，`_build_schema_from_mapping` 无法准确推断 computed_columns 类型

**修复内容**:
- ✅ 新增 `_build_column_type_map` 方法构建类型映射
- ✅ 新增 `_infer_computed_column_type` 方法推断计算列类型
- ✅ 优化 `_build_schema_from_mapping` 处理未配置类型列
- ✅ 添加测试验证空数据时 computed_columns 类型

**测试结果**:
- ✅ 65 个 transformer 测试全部通过
- ✅ pre-commit 检查通过

**修改文件**:
- `packages/datahub/src/ditto_datahub/sources/tushare/transformer.py`
- `packages/datahub/tests/unit/sources/tushare/test_transformer_unit.py`

**Agent**: aca7a2a

---

### ✅ 4. bars.py: filter_failed_rows 复杂度降低

**状态**: 已完成 (2026-01-12)

**问题**: `filter_failed_rows` 函数复杂度为 11（超过阈值 10）

**修复内容**:
- ✅ 将函数拆分为 5 个独立的规则过滤函数
- ✅ 使用字典映射替换 if-elif 链
- ✅ 复杂度从 11 降至 1
- ✅ 添加 11 个测试用例

**测试结果**:
- ✅ 11 个新测试全部通过
- ✅ 101 个现有仓库测试通过（无回归）
- ✅ pre-commit 检查通过

**修改文件**:
- `packages/datahub/src/ditto_datahub/repositories/bars.py`
- `packages/datahub/tests/unit/repositories/test_filter_failed_rows.py` (新建)

**Agent**: aded3f5

---

### ✅ 5. 测试覆盖率提升

**状态**: 已完成 (2026-01-12)

**问题**: parquet_store_base 测试覆盖率不足

**修复内容**:
- ✅ 添加 `TestWrite` 测试类（6 个测试用例）
- ✅ 覆盖三种 `OnDuplicate` 策略
- ✅ 测试新文件写入、merge 场景、batch 内部去重
- ✅ 覆盖率从 17.49% 提升至 41.87%

**测试结果**:
- ✅ 所有测试通过

**修改文件**:
- `packages/datahub/tests/unit/stores/test_parquet_store_base_unit.py`

---

## 待处理任务

### 📝 文档同步

**状态**: 待处理

**需要更新**:
- [ ] 将 `datahub-code-simplification-2026-01-11.md` 的文档更新与代码变更一起提交
- [ ] 在 `docs/sprints/backlog.md` 中记录代码审查修复工作
- [ ] 更新 datahub README（如有 API 变更）

---

## 总结

### 修复成果

| 类别 | 修复数量 | 状态 |
|------|----------|------|
| 🔴 Critical | 5 | ✅ 全部修复 |
| 🟡 Important | 1 | ✅ 已修复 |
| 文档同步 | 1 | ⏳ 待处理 |

### 质量指标

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 并行 subagent | 0 | 4 |
| 测试通过率 | 100% | 100% |
| 代码复杂度违规 | 2 | 0 |
| 项目约束违规 | 1 | 0 |
| pre-commit 检查 | 通过 | 通过 |

### 技术亮点

1. **并行修复**: 4 个独立 subagent 同时工作，显著提升效率
2. **TDD 流程**: 每个修复都遵循 RED → GREEN → REFACTOR
3. **完整测试**: 所有修复都有对应的测试覆盖
4. **无回归**: 所有现有测试保持通过

---

## 后续行动

- [ ] 提交所有修复到 git
- [ ] 运行 ci-check
- [ ] 合并到主分支
- [ ] 更新 Sprint 文档
