# V1 Sprint Review Fixes — 审查问题全量修复

## 概述
- Sprint: v1-sprint | Phase: Review Fixes (Round 2)
- 创建: 2026-04-16
- 完成状态: **全部 19 项已修复，验证通过**
- 来源:
  - 6 维度并行审查（架构/PIT/规约/可维护/质量/文档）— 14 项问题
  - PR #62 Code Review（5 个 ≥80 分 + 2 个 ≥75 分问题）— 7 项问题
- 前置: Round 1 拆分任务已全部完成，本计划修复两轮审查发现的问题
- 去重后: **19 个独立问题**（2 项重叠合并）

## 问题清单

| # | 严重度 | 来源 | 维度 | 描述 | 状态 |
|---|--------|------|------|------|------|
| M1 | major | 6D/CR#1 | 规约/架构 | `result.py` 使用 `TYPE_CHECKING` 规避循环依赖 | ✅ |
| M2 | major | 6D/CR#6 | 可维护 | `FillWriter.list()` 未使用共享 `build_where_clause` | ✅ |
| M3 | major | 6D | 文档 | `engine/CLAUDE.md` 描述 `result.py` 职责不符实际 | ✅ |
| CR2 | high | CR#2 | 质量 | `signal_weights` 为空时 `compile_and_validate` 崩溃 | ✅ |
| CR3 | high | CR#3 | 可维护 | `actual_snapshots` 死参数从未使用 | ✅ |
| CR4 | high | CR#4 | 质量 | `fill_to_record`/`snapshot_to_record` 缺少 `created_at` 时间戳 | ✅ |
| m1 | minor | 6D | 规约 | `ComparisonMetrics` 通过 `comparison.py` 间接 re-export | ✅ |
| m2 | minor | 6D | 规约 | `fills.py`/`intents.py`/`positions.py` 缺少 `__all__` | ✅ |
| m3 | minor | 6D | 可维护 | `_sql.py` 白名单缺少 `trade_date` | ✅ |
| m4 | minor | 6D | 可维护 | `result.py` 命名与内容不匹配 | ✅ |
| m5 | minor | 6D | 质量 | `_compute_sharpe_from_navs` 两次检查缺注释 | ✅ |
| m6 | minor | 6D | 质量 | `FillWriter.list()` `end_date < trade_date` 边界行为未文档化 | ✅ |
| m7 | minor | 6D | 质量 | `result.py` SHA-256 `[:16]` magic number | ✅ |
| m8 | minor | 6D | 质量 | `build_actual_navs_simple` 被 `__all__` 导出但无外部消费者 | ✅ |
| m9 | minor | 6D | 质量 | `build_where_clause` ValueError 调用方说明缺失 | ✅ |
| CR5 | minor | CR#5 | 文档 | `ComparisonMetrics.backtest_return` docstring 写"总收益率"实为年化 | ✅ |
| CR7 | minor | CR#7 | 可观测性 | `_is_rebalance_day` date 不在 index 时静默 fallback | ✅ |
| n1 | nit | 6D | 可维护 | `TradeService` 门面纯委托方法 docstring 过于冗长 | ✅ |
| n2 | nit | 6D | 质量 | `comparison_math.py` 中 `10_000.0` 基点因子可提取为常量 | ✅ |

## 技术方案

### 核心决策

1. **EngineConfig 提取**: 新建 `backtest/config.py`，存放 `EngineMode` + `EngineConfig`，消除 `engine.py ↔ result.py` 循环依赖
2. **result.py 重命名**: 合并进已有 `manifest.py`，精确反映职责（RunManifest 构建）
3. **build_where_clause 扩展**: 支持 `tuple[str, str]` 范围查询值，`str` 值保持等值语义；参数类型改为 `dict[str, str | tuple[str, str] | None]` 消除 Any 传播
4. **ComparisonMetrics 直导**: 消费者直接引用 `comparison_math.py`，`comparison.py` 停止 re-export
5. **signal_weights 等权 fallback**: `signal_weights` 为空时自动生成等权，避免运行时崩溃
6. **created_at 自动生成**: 映射函数内部生成 RFC3339 时间戳，与 `build_run_manifest` 一致

### 影响范围

- `EngineConfig` 消费者: 6 个测试文件 + `result.py`（共 7 处 import 变更）
- `ComparisonMetrics` 消费者: 3 个源文件 + 3 个测试文件（共 6 处 import 变更）
- `result.py → manifest.py`: 1 个消费者 `engine.py`

## 任务清单

### Phase 1: 架构修正（消除循环依赖 + 命名修正）

- [x] Task 1.1: 提取 `EngineMode` + `EngineConfig` → `backtest/config.py` `[M]`
  - 验收: `engine.py` 和 `manifest.py` 均从 `config.py` 导入；`TYPE_CHECKING` 块完全移除；`pixi run -e dev type` 通过
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/config.py` (新建)
    - `packages/engine/src/ditto_engine/backtest/engine.py` (修改 import)
    - `packages/engine/src/ditto_engine/backtest/manifest.py` (移除 TYPE_CHECKING)
    - `packages/engine/tests/unit/backtest/test_engine_loop_unit.py` (修改 import)
    - `packages/engine/tests/unit/backtest/test_engine_events_unit.py` (修改 import)
    - `packages/engine/tests/unit/backtest/test_post_trade_unit.py` (修改 import)
    - `packages/engine/tests/unit/alpha/test_stock_selection_trend_unit.py` (修改 import)
    - `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py` (修改 import)
  - 影响: M1, CR#1

- [x] Task 1.2: 合并 `result.py` → `manifest.py` + 修正 CLAUDE.md `[S]`
  - 验收: `build_run_manifest` 函数合并进已有 manifest.py；`engine.py` import 更新；`engine/CLAUDE.md` 描述修正；`pixi run -e dev check` 通过
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/result.py` (删除)
    - `packages/engine/src/ditto_engine/backtest/manifest.py` (合并 build_run_manifest)
    - `packages/engine/src/ditto_engine/backtest/engine.py` (修改 import)
    - `packages/engine/src/ditto_engine/backtest/__init__.py` (更新 re-export)
    - `packages/engine/CLAUDE.md` (修正描述)
  - 影响: M3, M4
  - 依赖: Task 1.1

### Phase 2: Data 层一致性（SQL 构建 + __all__）

- [x] Task 2.1: 扩展 `_sql.py` 支持范围查询 + 补全白名单 `[M]`
  - 验收: `build_where_clause` 支持 `tuple[str, str]` 值表示范围查询；`ALLOWED_ORDER_BY` 含 `trade_date ASC/DESC`；`ALLOWED_COLUMNS` 含 `trade_date`/`intent_id`；参数类型从 `dict[str, Any]` 改为 `dict[str, str | tuple[str, str] | None]`；新增白名单测试；`pixi run -e dev test` 通过
  - 文件:
    - `packages/data/src/ditto_data/services/trade/_sql.py` (扩展函数 + 补全白名单 + 类型优化)
    - `packages/data/tests/unit/services/test_trade_service_unit.py` (新增范围查询测试)
  - 影响: M2, m3, CR#6

- [x] Task 2.2: 重构 `FillWriter.list()` 使用共享 `build_where_clause` `[M]`
  - 验收: `FillWriter.list()` 使用 `build_where_clause` 构建 WHERE 子句；行为不变；`pixi run -e dev test` 通过
  - 文件:
    - `packages/data/src/ditto_data/services/trade/fills.py` (重构 list 方法)
  - 影响: M2, CR#6
  - 依赖: Task 2.1

- [x] Task 2.3: 为 Writer 文件添加 `__all__` `[S]`
  - 验收: `fills.py`、`intents.py`、`positions.py` 均有 `__all__`；导出符号与实际 public API 一致
  - 文件:
    - `packages/data/src/ditto_data/services/trade/fills.py`
    - `packages/data/src/ditto_data/services/trade/intents.py`
    - `packages/data/src/ditto_data/services/trade/positions.py`
  - 影响: m2

### Phase 3: App 层清理（re-export + 死代码 + 防御性修复）

- [x] Task 3.1: `ComparisonMetrics` 直导 + `build_actual_navs_simple` 内联化 `[S]`
  - 验收: 所有消费者直接 `from ditto_app.query.comparison_math import ComparisonMetrics`；`comparison.py` 停止 re-export `ComparisonMetrics`；`_build_actual_navs_simple` 逻辑内联到 `comparison.py` 并从 `comparison_math.py` 删除；`pixi run -e dev check` 通过
  - 文件:
    - `packages/app/src/ditto_app/query/comparison_math.py` (删除 _build_actual_navs_simple + 修改 __all__)
    - `packages/app/src/ditto_app/query/comparison.py` (移除 ComparisonMetrics re-export + 内联 NAV 逻辑)
    - `packages/app/src/ditto_app/process/execution/comparison.py` (修改 import)
    - `interfaces/src/ditto_interfaces/api/routes/trade.py` (拆分 import)
    - `packages/app/tests/unit/query/test_comparison_unit.py` (修改 import)
    - `packages/app/tests/unit/process/execution/test_comparison_unit.py` (修改 import + 移除 actual_snapshots)
    - `interfaces/tests/integration/api/test_trade_api_integration.py` (修改 import)
  - 影响: m1, m8

- [x] Task 3.2: 移除 `actual_snapshots` 死参数 `[S]`
  - 验收: `compute_comparison` 签名不含 `actual_snapshots`；无用 `ActualPositionSnapshot` 导入清理；所有调用点更新；`pixi run -e dev check` 通过
  - 文件:
    - `packages/app/src/ditto_app/process/execution/comparison.py` (修改签名 + 清理导入)
    - `packages/app/tests/unit/process/execution/test_comparison_unit.py` (5 处调用点移除 actual_snapshots)
  - 影响: CR#3

- [x] Task 3.3: `signal_weights` 空时默认等权 fallback `[S]`
  - 验收: 策略 spec 含 `signal_expressions` 但不含 `signal_weights` 时不崩溃；等权权重正确归一化；`pixi run -e dev check` 通过
  - 文件:
    - `packages/app/src/ditto_app/command/backtest.py` (添加等权 fallback)
  - 影响: CR#2

### Phase 4: 数据完整性 + 文档修正

- [x] Task 4.1: `fill_to_record`/`snapshot_to_record` 补充 `created_at` `[M]`
  - 验收: 映射函数返回的 record 含非空 `created_at`（RFC3339 格式）；`intent_to_record` 同理；`pixi run -e dev check` 通过
  - 文件:
    - `packages/app/src/ditto_app/execution_dto.py` (三个映射函数内部生成时间戳)
  - 影响: CR#4

- [x] Task 4.2: 修正 `ComparisonMetrics.backtest_return` docstring `[S]`
  - 验收: docstring 改为"回测年化收益率 (%)"，与实际语义一致
  - 文件:
    - `packages/app/src/ditto_app/query/comparison_math.py:36`
  - 影响: CR#5

- [x] Task 4.3: `_is_rebalance_day` fallback 添加 warning 日志 `[S]`
  - 验收: date 不在 `_trading_day_index` 时输出 `logger.warning`；不影响正常逻辑
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/engine.py:_is_rebalance_day`
  - 影响: CR#7

### Phase 5: 代码质量（注释 + 常量 + docstring）

- [x] Task 5.1: 代码质量改进 `[M]`
  - 验收: 所有注释和常量提取完成；docstring 更新；`pixi run -e dev check` 通过
  - 变更明细:
    - `comparison_math.py`: `_compute_sharpe_from_navs` 两次检查添加注释 (m5)；提取 `_BPS_FACTOR = 10_000.0` (n2)；删除未使用的 `_build_actual_navs_simple` (m8)
    - `fills.py`: `list()` docstring 补充日期过滤逻辑说明 (m6)
    - `_sql.py`: `build_where_clause` docstring 补充调用方说明 (m9)；提取 `_RANGE_TUPLE_LEN = 2` 常量
    - `manifest.py`: 提取 `_HASH_TRUNCATE_LEN = 16` (m7)；模块 docstring 更新
    - `service.py`: 纯委托方法 docstring 简化为单行 (n1)
  - 文件:
    - `packages/app/src/ditto_app/query/comparison_math.py`
    - `packages/data/src/ditto_data/services/trade/fills.py`
    - `packages/data/src/ditto_data/services/trade/_sql.py`
    - `packages/engine/src/ditto_engine/backtest/manifest.py`
    - `packages/data/src/ditto_data/services/trade/service.py`
  - 影响: m5, m6, m7, m8, m9, n1, n2
  - 依赖: Task 1.2 (manifest.py 重命名后修改)

### Phase 6: 验证

- [x] Task 6.1: 全量验证 `[S]`
  - 验收: `pixi run -e dev check` 全部通过（lint + fmt + type + test --fast）
  - 结果: 5459 passed, 25 skipped; 0 type errors; lint/fmt clean
  - 依赖: 所有前置任务

## 执行顺序

```
Phase 1 (架构):     Task 1.1 → Task 1.2
Phase 2 (Data):     Task 2.1 → Task 2.2 + Task 2.3(并行)
Phase 3 (App):      Task 3.1 + Task 3.2 + Task 3.3 (并行)
Phase 4 (完整性):    Task 4.1 + Task 4.2 + Task 4.3 (并行)
Phase 5 (质量):     Task 5.1
Phase 6 (验证):     Task 6.1
```

Phase 1-4 之间无依赖，可并行。Phase 5 依赖 Phase 1 的 manifest.py 重命名。
