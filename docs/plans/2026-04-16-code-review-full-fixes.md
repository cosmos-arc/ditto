# 代码审查全量修复计划 [COMPLETED]

## 概述

- Sprint: V1 Sprint | Phase: 代码审查修复
- 创建: 2026-04-16
- 范围: `feat/v1-sprint` HEAD~3...HEAD 审查发现的 11 项问题全量修复

## 审查来源

6 维度并行审查（架构/PIT/规约/可维护/质量/文档），自动化检查全部通过：
- ruff lint: 0 errors
- basedpyright: 0 errors, 0 warnings
- importlinter (24 合约): 0 broken

## 技术方案

所有修复均为低风险变更（删除残留代码、补充测试、更新文档），不涉及架构或逻辑变更。

---

## 任务清单

### Phase 1: 代码修复（规约 + 质量）

- [x] Task 1: 删除 comparison.py 空 `TYPE_CHECKING` 块 `[S]`
  - 验收: `from typing import TYPE_CHECKING, Any` → `from typing import Any`，删除 `if TYPE_CHECKING: pass`
  - 文件: `packages/app/src/ditto_app/query/comparison.py`
  - 风险: 无（纯删除残留代码）

- [x] Task 2: 收紧 engine.py 对 EngineConfig/EngineMode 的 re-export `[S]`
  - 验收: 从 `engine.py` 的 `__all__` 中移除 `EngineConfig` 和 `EngineMode`；测试文件改为从 `config.py` 或 `__init__.py` 导入
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py` + 测试文件（5 个）
  - 风险: 低（re-export 链仍在 2 层内，`__init__.py` 已聚合导出）
  - 影响: 5 个测试文件的 import 路径需更新

- [x] Task 3: source.py `any([...])` 改为直接条件判断 `[S]`
  - 验收: `any([params.ticker, params.standard_ticker, params.instrument_id])` → `not (params.ticker or params.standard_ticker or params.instrument_id)`
  - 文件: `interfaces/src/ditto_interfaces/api/routes/source.py:174`
  - 风险: 无（语义等价，消除临时列表分配）

- [x] Task 4: manifest.py 异常静默吞没添加 logger.debug `[S]`
  - 验收: `except (TypeError, ValueError, AttributeError): continue` 前添加 `logger.debug(...)` 记录跳过原因
  - 文件: `packages/engine/src/ditto_engine/backtest/manifest.py:257`
  - 风险: 无（仅添加日志）

- [x] Task 5: `_is_rebalance_day` fallback 业务原因注释补充 `[S]`
  - 验收: 在 fallback `return True` 处添加注释说明：fallback 为 daily 是保守策略，确保非交易日边界不会意外跳过调仓
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py:467-483`
  - 风险: 无（仅添加注释）

### Phase 2: 测试补充

- [x] Task 6: 补充 `_process_single_ticket` 单元测试 `[M]`
  - 验收: 覆盖以下场景：
    1. MarketSnapshot 缺失返回 None
    2. 结算不可交易返回 None
    3. `_is_order_executable` 返回 False 返回 None
    4. 成功成交路径（FILLED）
    5. NoFill with can_retry=False 标记 INVALID
  - 文件: `packages/engine/tests/unit/execution/test_brokerage_helpers_unit.py`
  - 风险: 中（核心撮合逻辑，需确保 mock 正确）

- [x] Task 7: 补充 `comparison_math.py` 纯计算函数独立单元测试 `[M]`
  - 验收: 覆盖以下边界：
    1. `_compute_sharpe_from_navs`: variance == 0（连续相同 NAV）
    2. `_daily_returns`: navs[i-1] == 0 的防御分支
    3. `_align_nav_series`: 空输入、无共同日期
    4. `_compute_tracking_error_bps`: min_len < _MIN_PAIRED_POINTS
    5. `_compute_total_return`: initial == 0
    6. `_compute_max_nav_diff_bps`: 正常/空输入
  - 文件: `packages/app/tests/unit/query/test_comparison_math_unit.py`（新建）
  - 风险: 低（纯函数测试，无外部依赖）

### Phase 3: 文档更新

- [x] Task 8: 更新 ADR 0008 代码示例与决策 `[M]`
  - 验收:
    1. 更新 `BacktestArtifactReader` 代码示例：方法签名改为 `read_json(file_path)` / `read_parquet(file_path)` / `exists(file_path)`，无 `__init__` 参数
    2. 更新 App 层调用示例：先 `find_artifact()` 定位路径，再调用 reader
    3. 修正"删除的依赖"表格：`Path` 导入未完全移除
    4. 添加补充决策段落：说明 Protocol 引入原因（测试 mock 需求），与原方案 C 决策的关系
  - 文件: `docs/adr/0008-strategy-artifact-io-layering.md`
  - 风险: 无（文档更新）

- [x] Task 9: 更新 packages/app/README.md 模块结构树 `[M]`
  - 验收:
    1. `query/` 补全所有新增模块（backtest, backtest_trade, comparison, comparison_math, lineage, portfolio_actual, run, signal, strategy, trade, universe, ingestion_status, _instrument_code_facade, _artifact_utils）
    2. `command/` 补全所有模块（backtest, trade, quality_check, quality_reconciliation, universe, protocols）
    3. `process/` 更新为子目录结构（ingestion/, materialization/, execution/, quality/）
    4. 删除已不存在的 `types.py`
    5. 补充 `contracts.py`, `execution_dto.py`
    6. 补充 `providers_market.py`, `providers_strategy.py`, `providers_portfolio.py`
  - 文件: `packages/app/README.md`
  - 风险: 无（文档更新）

- [x] Task 10: interfaces/CLAUDE.md 添加 shared_bars.py 说明 `[S]`
  - 验收: 在 API 路由分组部分添加备注，说明 `/fx` 和 `/commodity` POST 路由共享 `shared_bars.py` 处理器
  - 文件: `interfaces/CLAUDE.md`
  - 风险: 无（文档更新）

### Phase 4: 验证

- [x] Task 11: 运行完整验证 `[S]`
  - 验收:
    1. `pixi run -e dev check` 全部通过
    2. `pixi run -e dev arch-check` 24 合约 0 broken
    3. 新增测试通过
  - 文件: 无
  - 风险: 无

---

## 执行顺序

```
Phase 1 (代码修复): Task 1-5 → 可并行
Phase 2 (测试补充): Task 6-7 → 依赖 Phase 1（Task 2 修改 import 路径）
Phase 3 (文档更新): Task 8-10 → 与 Phase 1-2 可并行
Phase 4 (验证):     Task 11 → 依赖所有前序任务
```

## 统计

| Phase | 任务数 | 复杂度 |
|-------|--------|--------|
| Phase 1: 代码修复 | 5 | S × 5 |
| Phase 2: 测试补充 | 2 | M × 2 |
| Phase 3: 文档更新 | 3 | M × 2 + S × 1 |
| Phase 4: 验证 | 1 | S × 1 |
| **合计** | **11** | **5S + 2M + 2M + 1S** |
