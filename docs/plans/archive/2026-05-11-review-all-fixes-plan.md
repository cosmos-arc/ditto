# 审查全量修复计划 — 28 项问题

## 概述

- Sprint: remediation/cross-module-b1-b7 | Phase: Review All Fixes
- 创建: 2026-05-11
- 范围: 6 维度审查发现的 28 项问题全部修复
- 来源: docs/plans/2026-05-11-review-fixup-plan.md 审查修复的后续深化
- 风险: 低-中（9 文档 + 19 代码修复）

## 执行策略

按风险和依赖关系分 7 个阶段，阶段内尽量并行：
1. 文档修复（零风险，纯编辑）
2. 快速代码修复（低风险，小改动）
3. 类型安全改进（低-中风险，需 grep 全局影响）
4. 函数拆分重构（中风险，需测试验证）
5. 架构边界修复（需设计决策）
6. 测试覆盖补充（纯测试编写）
7. 剩余修复（参数减少、facade 清理、阈值提取）

---

## Phase 1: 文档修复（9 任务，纯编辑，零风险）

### Task D1: 修复 kernel/README.md 过时导入示例 (CRITICAL)
- 验收:
  - 第 105 行 `from ditto_kernel.strategy import DerivedSpec, DerivedRole, ExecutionPolicy` 改为 `from ditto_kernel.strategy import ExecutionPolicy, ImpactModel, RiskScope, RunStatus`
  - Changelog v0.3.0 条目添加 `（已在 v0.3.1 迁出）` 批注
- 文件: `packages/kernel/README.md`

### Task D2: 修复 strategy/CLAUDE.md 模板成熟度表
- 验收:
  - `stock_selection_trend` 从 "无独立测试" 改为实际描述
  - `stock_sector_rotation` 从 "无独立测试" 改为实际描述
- 文件: `packages/strategy/CLAUDE.md`

### Task D3: 同步修复 capability-maturity.md 模板描述
- 验收:
  - 策略模板行描述与 D2 修正后一致
  - Runtime/Risk 行进展描述更新（已完成项标注）
- 文件: `docs/architecture/capability-maturity.md`

### Task D4: 修复 application/CLAUDE.md config 目录结构
- 验收:
  - `config.py # 数据集配置` 改为 `config/ # 数据集配置（__init__.py + helpers.py + queries.py + specs.py）`
- 文件: `packages/application/CLAUDE.md`

### Task D5: 补充 kernel/CLAUDE.md "需叶模块导入" 表
- 验收:
  - 添加 strategy 子域 RunStatus 行
  - 添加 trading 子域的 FeeModel/FeeSchedule/InstrumentDefinition 等 6 类型行
  - 或添加说明段落解释这些低频类型直接从叶模块导入
- 文件: `packages/kernel/CLAUDE.md`

### Task D6: 修复 remediation-strategy.md B1 标记
- 验收:
  - B1 标题添加 `已完成（2026-05-09）` 标记
- 文件: `docs/plans/2026-05-08-cross-module-remediation-strategy.md`

### Task D7: 补充 risk/CLAUDE.md 测试文件列表
- 验收:
  - 测试目录树添加 `test_drawdown_snapshot_unit.py` 条目
- 文件: `packages/risk/CLAUDE.md`

---

## Phase 2: 快速代码修复（6 任务，低风险）

### Task Q1: 清理 engine.py 内部 re-export
- 验收:
  - 移除 `StepDeps`、`require_slice`、`build_steps`、`is_rebalance_day` 从 engine.py 的 re-export
  - 仅保留 `EngineOptions` 和 `assemble_engine_result`（公共 API）
  - 更新 engine.py 的 `__all__`
  - 搜索并更新所有从 engine.py 导入这些符号的消费者（改为从 engine_steps.py 直接导入）
- 文件: `packages/backtest/src/ditto_backtest/engine.py`

### Task Q2: 替换 quality_types.py 中 Any 类型
- 验收:
  - 定义 `type JsonValue = str | int | float | bool | None` 本地类型别名
  - `list[dict[str, Any]]` 改为 `list[dict[str, JsonValue]]`
  - 移除 `from typing import Any`（如无其他使用）
- 文件: `packages/data/src/ditto_data/quality/quality_types.py`

### Task Q3: 移除 TYPE_CHECKING 延迟导入
- 验收:
  - `instrument_ingestion.py`: MarketService/MetadataService 移至顶层导入
  - `post_ingest.py`: QualityCheckerProtocol 移至顶层导入
  - 移除 `TYPE_CHECKING` 块（如文件中无其他 TYPE_CHECKING 使用）
- 文件:
  - `packages/application/src/ditto_application/processes/ingestion/instrument_ingestion.py`
  - `packages/application/src/ditto_application/processes/ingestion/post_ingest.py`

### Task Q4: 消除默认值镜像
- 验收:
  - `deserialization.py` 中 `from ditto_kernel.trading import DEFAULT_SLIPPAGE_BPS` 直接引用
  - 移除 `_DEFAULT_SLIPPAGE_BPS = 1.0` 镜像常量
  - 检查是否有 deferred annotations 问题需要 TYPE_CHECKING guard（如需要可保留引用但不镜像值）
  - 类似处理 `_DEFAULT_MAX_WEIGHT` 和 `_DEFAULT_TRAILING_STOP_PCT`（如有 kernel 来源）
- 文件: `packages/application/src/ditto_application/builders/deserialization.py`

### Task Q5: 重定位 get_trading_calendar_range
- 验收:
  - 从 providers_command.py 提取到 providers_builder.py 或独立 helpers 模块
  - 更新 providers_command.py 的导入
- 文件:
  - `packages/application/src/ditto_application/providers_command.py`
  - `packages/application/src/ditto_application/providers_builder.py`

### Task Q6: 修复测试辅助函数硬编码 timedelta
- 验收:
  - `_make_synchronizer` 中 `timedelta(days=1)` 改为 `timedelta(days=config.knowledge_lag_days)`
- 文件: `packages/backtest/tests/unit/test_engine_loop_unit.py`

---

## Phase 3: 类型安全改进（2 任务，低-中风险）

### Task T1: EventName 改为 StrEnum
- 验收:
  - `EventName` 从普通类改为 `StrEnum`
  - 所有常量值保持不变（字符串值兼容）
  - 搜索并更新所有 `EventName.XXX` 的消费者（StrEnum 值比较兼容字符串）
  - 测试通过
- 文件: `packages/kernel/src/ditto_kernel/events.py`

### Task T2: 统一时间工具函数
- 验收:
  - 评估 `now_iso()` 和 `utc_now()` 是否可统一
  - 如格式差异是有意的（ISO vs RFC3339），在文档中说明区别
  - 如可统一，提取到 kernel 时间工具模块
- 文件:
  - `packages/application/src/ditto_application/config/helpers.py`
  - `packages/strategy/src/ditto_strategy/_internal.py`

---

## Phase 4: 函数拆分重构（5 任务，中风险）

### Task R1: 拆分 EngineLoop.__init__ (51 行)
- 验收:
  - 提取 `_build_deps()` 方法构造 StepDeps
  - 提取 `_initialize_state()` 方法初始化索引等状态
  - `__init__` 降至 ≤ 30 行
- 文件: `packages/backtest/src/ditto_backtest/engine.py`

### Task R2: 拆分 EngineLoop.run (78 行)
- 验收:
  - 提取 `_run_main_loop()` 方法
  - 提取 `_flush_delayed_signals()` 方法
  - `run()` 降至 ≤ 30 行
- 文件: `packages/backtest/src/ditto_backtest/engine.py`

### Task R3: 拆分 EngineLoop._step (62 行)
- 验收:
  - 提取 `_process_delayed_signal()` 方法
  - 提取 `_record_audit()` 方法
  - `_step()` 降至 ≤ 30 行
- 文件: `packages/backtest/src/ditto_backtest/engine.py`

### Task R4: 拆分 build_steps (59 行)
- 验收:
  - 每类 Step 构造提取为 `_build_xxx_step(deps)` 辅助函数
  - `build_steps()` 降至 ≤ 30 行
- 文件: `packages/backtest/src/ditto_backtest/engine_steps.py`

### Task R5: 拆分 merge_with_existing (51 行 + 4 层嵌套)
- 验收:
  - 提取 `_merge_error()`、`_merge_keep_first()`、`_merge_keep_last()` 策略函数
  - 用策略字典替代 if/elif 嵌套
  - 嵌套深度 ≤ 3
- 文件: `packages/platform/src/ditto_platform/foundation/storage/parquet_write.py`

---

## Phase 5: 架构边界修复（1 任务，需设计决策）

### Task A1: 解决 apps→data.quality 边界问题
- 方案选项:
  - (a) 通过 application commands 层路由 DQ 类型
  - (b) 将 DQ 类型回移 kernel（3 个消费者：data/application/apps）
- 验收:
  - 消除 importlinter 临时豁免
  - 或将豁免记录为有意的架构债务
- 文件:
  - `packages/apps/src/ditto_apps/jobs/tasks/dq_batch.py`
  - `packages/apps/src/ditto_apps/jobs/tasks/monitoring.py`
  - `.importlinter`

---

## Phase 6: 测试覆盖补充（2 任务）

### Task TE1: ParquetStore 拆分模块测试
- 验收:
  - 新建 `test_parquet_write_unit.py` 测试 `prepare_for_write` 和 `merge_with_existing`
  - 新建 `test_parquet_metadata_unit.py` 测试 `get_years`/`get_date_range` 边界情况
- 文件: `packages/platform/tests/unit/`

### Task TE2: Execution 拆分模块测试
- 验收:
  - 新建 `test_quantity_rounding_unit.py` 测试 round_buy_qty 边界
  - 新建 `test_cost_estimate_unit.py` 测试 sell_quantities 拆分
  - 新建 `test_market_precheck_unit.py` 测试涨跌停判断
- 文件: `packages/execution/tests/unit/`

---

## Phase 7: 剩余修复（3 任务）

### Task M1: 减少函数参数数量
- 验收:
  - 为 `process_fetched_data` 等引入参数上下文 dataclass
  - 消除 `# noqa: PLR0913`
- 文件: ingestion 相关文件

### Task M2: coordinator.py facade 清理
- 验收:
  - 将 `_fetch_data` 提取到独立模块
  - coordinator.py 成为纯 facade
- 文件: `packages/application/src/ditto_application/processes/ingestion/coordinator.py`

### Task M3: 提取 regime_indicators 硬编码阈值
- 验收:
  - `MomentumIndicator.compute` 中 +/-10% 提取为构造参数
  - 默认值保持 `-0.10` / `+0.10`
- 文件: `packages/strategy/src/ditto_strategy/alpha/builtins/regime_indicators.py`

---

## 验证

每个 Phase 完成后运行:
```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev arch-check  # 架构契约
```

全部完成后运行:
```bash
pixi run -e dev ci       # 完整 CI
```
