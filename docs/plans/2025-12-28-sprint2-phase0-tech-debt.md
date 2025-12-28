# Sprint 2 Phase 0: 技术债务清理 - 实现计划

**日期**: 2025-12-28
**Sprint**: Sprint 2 - 数据层完善与验证
**Phase**: Phase 0 - 技术债务清理

## 概述

Phase 0 的核心功能已完整实现，本次工作主要是**补充专项测试**、**代码优化**和**文档更新**。

## 当前状态评估

| 任务 | 实现状态 | 测试状态 | 位置 |
|------|----------|----------|------|
| 0.1 混合资产查询检测 | ✅ | ✅ TestMixedAssetClass | bars.py:322-366 |
| 0.2-0.3 QFQ 排序验证 | ✅ | ✅ test_write_maintains_sid_and_date_sorting | adj_factor_store.py:144-149 |
| 0.4-0.5 复权因子缺失处理 | ✅ | ✅ 多个测试覆盖 | bars.py:432-469 (pl.coalesce) |
| 0.6 SQLite 外键启用 | ✅ | ✅ 外键约束测试 | sqlite_pool.py:35-36 |

## 需要完成的工作

### 1. 补充专项测试

**新增测试类：`TestAdjFactorEdgeCases`** (test_bars_repository.py)

- `test_qfq_with_all_missing_factors_returns_original()` - QFQ 所有复权因子缺失时返回原始价格
- `test_hfq_with_all_missing_factors_returns_original()` - HFQ 所有复权因子缺失时返回原始价格
- `test_qfq_year_boundary_continuity()` - QFQ 跨年数据排序连续性验证
- `test_qfq_large_dataset_performance()` - QFQ 大数据集性能测试（10000+ 条记录）
- `test_adj_factor_with_single_sid()` - 单个 SID 的复权处理
- `test_adj_factor_with_empty_sid_list()` - 空 SID 列表处理

**新增混合资产边界测试** (test_bars_repository.py - TestMixedAssetClass)

- `test_mixed_asset_with_boundary_sids()` - 测试 SID 范围边界值
- `test_mixed_asset_with_all_three_asset_classes()` - 测试同时包含 stock/etf/index

**新增排序验证增强测试** (test_adj_factor_store.py)

- `test_sorting_across_year_partitions()` - 跨年分区数据的排序正确性
- `test_sorting_with_duplicate_keys_uses_last()` - 重复键的正确处理
- `test_sorting_order_is_stable_after_merge()` - 合并后排序顺序的稳定性

### 2. 代码重构

**重构 `BarsRepository._apply_adj()` 方法**

- 当前：104 行，违反 ≤50 行规则
- 拆分为：
  - `_apply_adj()` - 主入口，20 行
  - `_apply_qfq_adj()` - QFQ 逻辑，40-50 行
  - `_apply_hfq_adj()` - HFQ 逻辑，20-30 行

### 3. 文档更新

**更新文件：** `docs/sprints/sprint-02-data-quality.md`

- 将 Phase 0 所有任务状态更新为 ✅
- 添加完成总结

## 执行步骤

### 步骤 1：补充测试用例（TDD Red → Green）

1. 新增 `TestAdjFactorEdgeCases` 测试类
2. 新增混合资产边界测试
3. 新增排序验证增强测试
4. 运行测试确保通过

### 步骤 2：代码重构

1. 拆分 `_apply_adj()` 方法
2. 运行测试确保无回归
3. 运行 ruff 检查

### 步骤 3：文档更新

1. 更新 Sprint 2 文档
2. 验证 CI 检查通过

## 验收标准

- [ ] 新增 9 个边缘测试用例
- [ ] `_apply_adj()` 拆分为 3 个方法，每个 ≤50 行
- [ ] 所有测试通过
- [ ] `pixi run -e dev ci-check` 通过
- [ ] Sprint 2 文档更新完成
- [ ] 无 linting 错误

## 关键文件路径

```
packages/datahub/src/ditto_datahub/repositories/bars.py:368-472
packages/datahub/tests/unit/repositories/test_bars_repository.py
packages/datahub/tests/test_adj_factor_store.py
docs/sprints/sprint-02-data-quality.md
```
