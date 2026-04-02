# [Sprint 1] Code Quality: DataHub 代码修复

**日期**: 2025-12-26
**状态**: ❌ 未开始
**分支**: `fix/datahub-code-quality`

---

## 🎯 技能使用计划

> 本任务的 Superpowers 工作流：

| 阶段 | 使用 Skill | 产出 |
|------|-----------|------|
| 设计 | `brainstorming` | 已完成（用户确认业务逻辑） |
| 计划 | `writing-plans` | 本文件 |
| 执行 | `executing-plans` + `test-driven-development` | 代码实现 |
| 审查 | `requesting-code-review` | 代码质量检查 |
| 完成 | `finishing-a-development-branch` | PR/合并决策 |

---

## 一、任务概述

### 目标
修复 DataHub 模块中发现的 14 个代码质量问题，涵盖业务逻辑正确性、数据安全和代码质量三个维度。

### 问题汇总

| 严重性 | 数量 | 主要问题 |
|--------|------|----------|
| **High** | 5 | 混合资产查询、QFQ 因子排序、SQL 注入风险、类型安全 |
| **Medium** | 6 | 复权因子缺失、日期规范化、SQLite 外键、函数过长 |
| **Low** | 3 | symbol 多重匹配、代码一致性、灵活性 |

### 用户确认的业务逻辑
1. **混合资产查询**: 抛出错误，不允许混合查询
2. **复权因子缺失**: 可能缺失，应使用原始价格（未复权价格）
3. **QFQ 最新因子**: 两者结合（存储时排序 + 查询时显式排序）

### 依赖
- 无前置任务
- 依赖：现有测试框架已就绪

### 复杂度评估
- **任务规模**: L (复杂)
- **是否需要 Plan 文件**: ✅ 是
- **预估子任务数**: 14 个

---

## 二、设计阶段

### 2.1 用户确认项
- [x] 功能边界已明确（混合资产查询行为）
- [x] 接口设计已确认（复权因子缺失处理策略）
- [x] 数据结构已定义（使用 pl.coalesce 处理 null）
- [x] 边界条件已讨论（所有业务逻辑已确认）

### 2.2 关键设计决策

| 决策 | 理由 |
|------|------|
| 混合资产查询抛出 ValueError | 防止静默数据丢失，强制用户明确意图 |
| 复权因子缺失使用 pl.coalesce(..., 1.0) | 保证返回数据完整性，缺失时返回原始价格 |
| QFQ 双重排序（存储+查询） | 防御性编程，即使数据未排序也能正确工作 |
| SQLite 启用外键约束 | 确保 referential integrity，防止孤立记录 |

---

## 三、实施计划

> **使用 Skill**: `executing-plans` + `test-driven-development`
> **TDD 原则**: 红色测试 → 绿色实现 → 重构优化

### Phase 1: 关键业务逻辑修复（必须）

#### 1.1 混合资产类别查询检测
- **文件**: `packages/data/src/ditto_data/repositories/bars.py`
- **修改**: `_determine_dataset()` 方法
- **测试**: `packages/data/tests/unit/repositories/test_bars_repository.py`
- **Commit**: `fix(bars): detect and reject mixed asset class queries`
- **状态**: [ ] 未完成

```python
# 在 _determine_dataset 中添加混合检测
if has_stock and has_etf:
    raise ValueError("Mixed asset class query detected...")
```

#### 1.2 QFQ 前复权因子排序（存储层）
- **文件**: `packages/data/src/ditto_data/stores/adj_factor_store.py`
- **修改**: `_write_impl()` 排序逻辑
- **测试**: `packages/data/tests/test_adj_factor_store.py`
- **Commit**: `fix(adj_factor_store): ensure sid, trade_date sorting on write`
- **状态**: [ ] 未完成

```python
# 添加 sid 到排序键
combined = combined.sort(["sid", "trade_date"])
```

#### 1.3 QFQ 前复权因子排序（查询层）
- **文件**: `packages/data/src/ditto_data/repositories/bars.py`
- **修改**: `_apply_adj()` 方法
- **测试**: `packages/data/tests/unit/repositories/test_bars_repository.py`
- **Commit**: `fix(bars): sort adj_df before last() aggregation`
- **状态**: [ ] 未完成

```python
adj_df = adj_df.sort(["sid", "trade_date"])
```

#### 1.4 复权因子缺失处理（QFQ）
- **文件**: `packages/data/src/ditto_data/repositories/bars.py`
- **修改**: `_apply_adj()` QFQ 分支
- **测试**: `packages/data/tests/unit/repositories/test_bars_repository.py`
- **Commit**: `fix(bars): use coalesce for missing adj_factor in QFQ`
- **状态**: [ ] 未完成

```python
pl.col("open") * pl.coalesce("latest_factor", 1.0) / pl.coalesce("adj_factor", 1.0)
```

#### 1.5 复权因子缺失处理（HFQ）
- **文件**: `packages/data/src/ditto_data/repositories/bars.py`
- **修改**: `_apply_adj()` HFQ 分支
- **测试**: `packages/data/tests/unit/repositories/test_bars_repository.py`
- **Commit**: `fix(bars): use coalesce for missing adj_factor in HFQ`
- **状态**: [ ] 未完成

```python
pl.col("open") * pl.coalesce("adj_factor", 1.0)
```

---

### Phase 2: 数据安全修复（必须）

#### 2.1 SQLite 外键启用
- **文件**: `packages/data/src/ditto_data/runtime/sqlite_pool.py`
- **修改**: `get_connection()` 方法
- **测试**: `packages/data/tests/unit/runtime/test_sqlite_pool.py` (新建)
- **Commit**: `fix(sqlite_pool): enable foreign key constraints`
- **状态**: [ ] 未完成

```python
conn.execute("PRAGMA foreign_keys = ON;")
```

#### 2.2 SQL 注入风险修复
- **文件**: `packages/data/src/ditto_data/stores/security_store.py`
- **修改**: 创建 `_build_in_clause()` 辅助函数
- **测试**: `packages/data/tests/unit/stores/test_security_store.py`
- **Commit**: `fix(security_store): refactor IN clause with helper function`
- **状态**: [ ] 未完成

#### 2.3 AdjFactorStore 日期规范化
- **文件**: `packages/data/src/ditto_data/stores/adj_factor_store.py`
- **修改**: `_write_impl()` 添加日期类型检查
- **测试**: `packages/data/tests/test_adj_factor_store.py`
- **Commit**: `fix(adj_factor_store): normalize trade_date type on write`
- **状态**: [ ] 未完成

---

### Phase 3: 代码质量提升（推荐）

#### 3.1 拆分 _write_impl 函数
- **文件**: `packages/data/src/ditto_data/stores/bars_store.py`
- **修改**: 提取 `_ensure_dataset_dir()`, `_merge_with_existing()`, `_prepare_for_write()`
- **测试**: 现有测试应继续通过
- **Commit**: `refactor(bars_store): extract helper methods from _write_impl`
- **状态**: [ ] 未完成

#### 3.2 添加 BarsStore 输入验证
- **文件**: `packages/data/src/ditto_data/stores/bars_store.py`
- **修改**: 添加 `_validate_bars_schema()` 函数
- **测试**: `packages/data/tests/unit/stores/test_bars_store.py`
- **Commit**: `feat(bars_store): add DataFrame schema validation`
- **状态**: [ ] 未完成

#### 3.3 添加 AdjFactorStore 输入验证
- **文件**: `packages/data/src/ditto_data/stores/adj_factor_store.py`
- **修改**: 添加 `_validate_adj_factor_schema()` 函数
- **测试**: `packages/data/tests/test_adj_factor_store.py`
- **Commit**: `feat(adj_factor_store): add DataFrame schema validation`
- **状态**: [ ] 未完成

#### 3.4 移除冗余类型断言
- **文件**: `packages/data/src/ditto_data/runtime/sqlite_pool.py`
- **修改**: 移除 `assert isinstance(...)` 行
- **测试**: 现有测试应继续通过
- **Commit**: `refactor(sqlite_pool): remove redundant type assertion`
- **状态**: [ ] 未完成

---

### Phase 4: 代码风格改进（可选）

#### 4.1 symbol 多重匹配警告
- **文件**: `packages/data/src/ditto_data/repositories/bars.py`
- **修改**: `get_single()` 添加警告日志
- **测试**: `packages/data/tests/unit/repositories/test_bars_repository.py`
- **Commit**: `feat(bars): add warning for ambiguous symbol resolution`
- **状态**: [ ] 未完成

#### 4.2 统一 DataFrame 类型注解
- **文件**: 多个 Store 文件
- **修改**: 统一使用 `pl.DataFrame`
- **测试**: 无需测试
- **Commit**: `style(datahub): standardize DataFrame type annotations`
- **状态**: [ ] 未完成

#### 4.3 增强日期参数灵活性
- **文件**: 多个 read() 方法
- **修改**: 添加 `_normalize_date()` 辅助函数
- **测试**: 相关测试
- **Commit**: `feat(datahub): support datetime objects in date parameters`
- **状态**: [ ] 未完成

---

## 四、Git 提交策略

### 提交粒度原则
- ✅ 每个 TDD 循环独立提交（RED → GREEN → REFACTOR）
- ✅ 完成一个独立功能点立即提交
- ❌ 不将多个不相关改动混在一个提交

### 预期提交序列

```bash
# Phase 1: 业务逻辑修复
git commit -m "test(bars): add test for mixed asset class detection"
git commit -m "fix(bars): detect and reject mixed asset class queries"

git commit -m "test(adj_factor_store): add test for sorting behavior"
git commit -m "fix(adj_factor_store): ensure sid, trade_date sorting on write"

git commit -m "test(bars): add test for unsorted adj_factor handling"
git commit -m "fix(bars): sort adj_df before last() aggregation"

git commit -m "test(bars): add test for missing adj_factor in QFQ"
git commit -m "fix(bars): use coalesce for missing adj_factor in QFQ"

git commit -m "test(bars): add test for missing adj_factor in HFQ"
git commit -m "fix(bars): use coalesce for missing adj_factor in HFQ"

# Phase 2: 数据安全修复
git commit -m "test(sqlite_pool): add test for foreign key enforcement"
git commit -m "fix(sqlite_pool): enable foreign key constraints"

git commit -m "test(security_store): add test for IN clause safety"
git commit -m "fix(security_store): refactor IN clause with helper function"

git commit -m "test(adj_factor_store): add test for date normalization"
git commit -m "fix(adj_factor_store): normalize trade_date type on write"

# Phase 3: 代码质量
git commit -m "refactor(bars_store): extract helper methods from _write_impl"
git commit -m "feat(bars_store): add DataFrame schema validation"
git commit -m "feat(adj_factor_store): add DataFrame schema validation"
git commit -m "refactor(sqlite_pool): remove redundant type assertion"

# Phase 4: 风格改进（可选）
git commit -m "feat(bars): add warning for ambiguous symbol resolution"
# ...
```

---

## 五、验收标准

### 功能
- [ ] 混合资产查询抛出 ValueError
- [ ] QFQ 复权在任何情况下使用正确的最新因子
- [ ] 复权因子缺失时返回原始价格
- [ ] SQLite 外键约束生效
- [ ] SQL IN 子句使用参数化查询
- [ ] 日期输入自动规范化

### 质量
- [ ] 所有新测试通过
- [ ] 现有测试不被破坏
- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 覆盖率保持 ≥80%

### 性能
- [ ] 排序操作不影响读取性能（需验证）

---

## 六、文件清单

### 需要修改的文件

```
packages/data/src/ditto_data/
├── repositories/
│   └── bars.py                    # 混合资产检测、QFQ 排序、null 处理、symbol 警告
├── stores/
│   ├── adj_factor_store.py        # 存储排序、日期规范化
│   ├── bars_store.py              # 函数拆分、输入验证
│   └── security_store.py          # SQL IN 子句重构
└── runtime/
    └── sqlite_pool.py             # 外键启用、移除断言
```

### 需要添加测试的文件

```
packages/data/tests/
├── unit/
│   ├── repositories/
│   │   └── test_bars_repository.py    # 混合资产、复权缺失、排序测试
│   ├── stores/
│   │   ├── test_bars_store.py         # 输入验证测试
│   │   └── test_security_store.py     # SQL 安全测试
│   └── runtime/
│       └── test_sqlite_pool.py        # 外键约束测试（新建）
└── test_adj_factor_store.py           # 日期规范化测试
```

---

## 七、完成阶段

> **使用 Skill**: `finishing-a-development-branch`

### 7.1 完成前验证
- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 所有新测试通过
- [ ] 所有现有测试不被破坏
- [ ] 代码已 Polishing
- [ ] DoD 全部勾选

### 7.2 决策点
- [ ] 创建 PR → 继续下一步
- [ ] 本地合并 → 不适用（多文件修改）
- [ ] 保留分支 → 如需进一步调整
- [ ] 丢弃分支 → 不适用

### 7.3 创建 PR
```bash
git push -u origin fix/datahub-code-quality
gh pr create --base main --title "fix(datahub): code quality fixes and data safety improvements"
```

---

## 八、完成总结

<!-- 任务完成后填写 -->

### 已实现
- [ ] Phase 1: 业务逻辑修复
- [ ] Phase 2: 数据安全修复
- [ ] Phase 3: 代码质量提升
- [ ] Phase 4: 风格改进

### 遗留问题
- [ ] ...

### 经验教训
- [ ] ...

---

**最后更新**: 2025-12-26
