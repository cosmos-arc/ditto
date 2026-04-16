# Code Review Fixes — PR #62 审查问题修复

## 概述

- Sprint: V1 Sprint | Phase: Review Fix
- 创建: 2026-04-16
- 来源: PR #62 全量 Code Review（5 个 ≥80 分问题 + 2 个 ≥75 分问题）

## 技术方案

7 个问题按影响范围和修复策略分为 3 组：

| 组 | 问题 | 严重度 | 核心策略 |
|----|------|--------|----------|
| A | #1 TYPE_CHECKING 循环依赖 | 高 | 架构重构 — 提取 EngineConfig 到独立模块 |
| A | #2 缺少默认权重导致崩溃 | 高 | 防御性编程 — 等权 fallback |
| B | #3 actual_snapshots 死参数 | 中 | 清理死代码 |
| B | #4 created_at 审计轨迹缺失 | 中 | 映射函数补充时间戳 |
| B | #5 docstring 年化 vs 总收益率 | 低 | 文档修正 |
| C | #6 FillWriter.list() 绕过共享 SQL | 低 | 扩展白名单 + 重构查询构建 |
| C | #7 _is_rebalance_day 静默 fallback | 低 | 添加 warning 日志 |

---

## 任务清单

### Task 1: 提取 EngineConfig 消除 TYPE_CHECKING 循环依赖 `[L]`

> **Issue #1** — Score: 100 | CLAUDE.md 硬性禁止

**问题**: `result.py` 通过 `TYPE_CHECKING` 导入 `engine.py` 的 `EngineConfig`，形成循环依赖。已跨 3 个 PR 反复出现。

**方案**: 将 `EngineConfig` 提取到 `packages/engine/src/ditto_engine/backtest/config.py`，`engine.py` 和 `result.py` 均从此模块导入。

- 验收:
  - `result.py` 无 `TYPE_CHECKING` 导入
  - `engine.py` 从 `config.py` 导入 `EngineConfig`
  - `build_run_manifest` 签名不变（接受 `EngineConfig` 类型）
  - `pixi run -e dev check` 通过
  - 文件: `packages/engine/src/ditto_engine/backtest/config.py`（新建）, `engine.py`, `result.py`

### Task 2: 策略缺少 signal_weights 时默认等权 `[S]`

> **Issue #5** — Score: 90 | 运行时崩溃

**问题**: `_extract_signal_weights` 返回 `()` 时，`compile_and_validate` 因 `len(expressions) != len(weights)` 抛出 `ValueError`。

**方案**: 在 `backtest.py` 的 handler 中，当 `signal_weights` 为空但 `signal_expressions` 非空时，默认等权 `(1.0 / n,) * n`。

```python
# backtest.py:110-111 修改为
if signal_expressions:
    weights = signal_weights or tuple(
        1.0 / len(signal_expressions) for _ in signal_expressions
    )
    self._factor_bridge.compile_and_validate(signal_expressions, weights)
```

- 验收:
  - 策略 spec 含 `signal_expressions` 但不含 `signal_weights` 时不崩溃
  - 等权权重正确归一化
  - 新增测试用例覆盖此路径
  - `pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/command/backtest.py`, 对应测试文件

### Task 3: 移除 actual_snapshots 死参数 `[S]`

> **Issue #2** — Score: 100 | 误导性死代码

**问题**: `compute_comparison()` 接受 `actual_snapshots` 参数但从未使用。

**方案**: 从函数签名和文档中移除 `actual_snapshots` 参数，同时清理 `ActualPositionSnapshot` 的无用导入。检查所有调用点并更新。

- 验收:
  - `compute_comparison` 签名不含 `actual_snapshots`
  - 无 `ActualPositionSnapshot` 导入
  - 所有调用点更新
  - `pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/execution/comparison.py`, 调用方

### Task 4: fill/snapshot 映射补充 created_at 时间戳 `[M]`

> **Issue #3** — Score: 100 | 审计轨迹完整性

**问题**: `fill_to_record()` 和 `snapshot_to_record()` 未设置 `created_at`，导致所有持久化记录的 `created_at=""`。

**方案**: 在 `execution_dto.py` 的映射函数中生成 RFC3339 时间戳。映射函数需要接收或生成 `created_at`。

- 方案 A（推荐）: 映射函数内部生成 `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`
- 方案 B: 由调用方传入 `created_at`

采用方案 A，与 `result.py` 中 `build_run_manifest` 的 `created_at` 生成方式一致。

- 验收:
  - `fill_to_record` 和 `snapshot_to_record` 返回的 record 含非空 `created_at`
  - `intent_to_record` 同理补充
  - 格式为 RFC3339 (`2026-04-16T10:30:00Z`)
  - 新增/更新测试验证时间戳非空
  - `pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/execution_dto.py`, 对应测试文件

### Task 5: 修正 ComparisonMetrics.backtest_return docstring `[S]`

> **Issue #4** — Score: 100 | 文档错误

**问题**: `ComparisonMetrics.backtest_return` 文档写"回测总收益率 (%)"，但实际值是年化收益率。

**方案**: 修改 docstring 为"回测年化收益率 (%)"。

- 验收:
  - docstring 与实际语义一致
  - `pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/query/comparison_math.py:36`

### Task 6: FillWriter.list() 对齐共享 SQL 工具 `[M]`

> **Issue #6** — Score: 75 | 架构一致性

**问题**: `FillWriter.list()` 手动构建 SQL，绕过 `_sql.py` 的 `build_where_clause()`，违反模块文档声明的"三个 Writer 共用"约定。

**方案**:
1. 扩展 `_sql.py` 白名单: `ALLOWED_COLUMNS` 增加 `trade_date`, `intent_id`；`ALLOWED_ORDER_BY` 增加 `trade_date ASC`
2. 增强 `build_where_clause` 支持范围查询（`trade_date >= ?` 模式），或新增 `build_where_clause_range` 函数
3. 重构 `FillWriter.list()` 使用共享工具

- 验收:
  - `FillWriter.list()` 使用 `build_where_clause` 或扩展版本
  - 白名单覆盖 fills 表实际使用的列
  - 查询结果不变
  - 新增/更新测试
  - `pixi run -e dev check` 通过
  - 文件: `packages/data/src/ditto_data/services/trade/_sql.py`, `fills.py`, 对应测试

### Task 7: _is_rebalance_day fallback 添加 warning 日志 `[S]`

> **Issue #7** — Score: 75 | 可观测性

**问题**: `_is_rebalance_day` 在 date 不在 `_trading_day_index` 中时静默返回 `True`，可能隐藏数据错误。

**方案**: 在 fallback 路径添加 `logger.warning`。

```python
idx = self._trading_day_index.get(date)
if idx is None:
    logger.warning("_is_rebalance_day: date '{}' not in trading_day_index, fallback to True", date)
    return True
```

- 验收:
  - fallback 路径输出 warning 日志
  - 不影响正常逻辑
  - `pixi run -e dev check` 通过
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py:527-529`

---

## 执行顺序

```
Task 1 (L) ──── 架构重构，独立
Task 2 (S) ──── 防御性修复，独立
Task 3 (S) ──── 死代码清理，独立
Task 4 (M) ──── 映射修复，独立
Task 5 (S) ──── 文档修正，独立
Task 6 (M) ──── SQL 重构，独立
Task 7 (S) ──── 日志增强，独立
```

所有任务互不依赖，可并行执行。建议分 2 批：
- **Batch 1**: Task 1 + Task 2（高严重度）
- **Batch 2**: Task 3-7（中低严重度）
