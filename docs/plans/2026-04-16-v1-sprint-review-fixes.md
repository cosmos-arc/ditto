# V1 Sprint Review Fixes — 代码审查修复

## 概述
- Sprint: V1 RC | Phase: Post-Review
- 创建: 2026-04-16
- 来源: 6 维度代码审查报告（feat/v1-sprint 分支）

## 审查结论回顾

6 维度全部通过，无严重问题。本计划仅处理改进建议，按优先级排列。

## 技术方案

### 决策 1：trade_service.py 拆分策略

当前 583 行单文件包含 3 张表的全部 CRUD + SQL DDL + 行映射。
拆分为 `TradeService` 门面 + 3 个内部 Writer，保持公共 API 不变。

```
ditto_data/services/trade/
├── __init__.py          # re-export TradeService
├── service.py           # TradeService 门面（编排 3 个 Writer）
├── intents.py           # TradeIntentWriter（intents 表 CRUD）
├── fills.py             # FillWriter（fills 表 CRUD）
└── positions.py         # PositionWriter（positions 表 CRUD）
```

**理由**：TradeService 的消费者（app/providers_portfolio.py、command/trade.py）仅依赖 TradeService 公共接口，拆分是内部重构，不影响外部。

### 决策 2：comparison.py 纯计算函数抽取

将 `compute_comparison_from_raw` 及其辅助函数抽取为 `comparison_math.py`，
`comparison.py` 仅保留 `ComparisonQueryFacade` 和 `ComparisonMetrics` DTO。

### 决策 3：engine.py 结果组装抽取

将 `_assemble_result` + `_build_manifest` 抽取到 `backtest/result.py`，
降低 engine.py 复杂度。EngineLoop 保留核心循环逻辑。

## 任务清单

### Phase 1：trade_service 拆分（L）

- [x] Task 1.1: 创建 `ditto_data/services/trade/` 包结构 `[S]`
  - 验收: 目录存在，`__init__.py` re-export TradeService
  - 文件: `packages/data/src/ditto_data/services/trade/__init__.py`

- [x] Task 1.2: 抽取 intents 表 CRUD 到 `intents.py` `[M]`
  - 验收: TradeIntentWriter 类，包含 save_intent/get_intent/list_intents/update_intent_status + 行映射
  - 文件: `packages/data/src/ditto_data/services/trade/intents.py`
  - 测试: 更新 `test_trade_service_unit.py` 确保 intents 相关测试通过

- [x] Task 1.3: 抽取 fills 表 CRUD 到 `fills.py` `[S]`
  - 验收: FillWriter 类，包含 save_fill/get_fill/find_fill/list_fills + 行映射
  - 文件: `packages/data/src/ditto_data/services/trade/fills.py`
  - 测试: 更新 `test_trade_service_unit.py` 确保 fills 相关测试通过

- [x] Task 1.4: 抽取 positions 表 CRUD 到 `positions.py` `[S]`
  - 验收: PositionWriter 类，包含 save_position/get_latest_position/list_positions + 行映射
  - 文件: `packages/data/src/ditto_data/services/trade/positions.py`
  - 测试: 更新 `test_trade_service_unit.py` 确保 positions 相关测试通过

- [x] Task 1.5: 重构 TradeService 为门面，委托 3 个 Writer `[M]`
  - 验收: TradeService 保留原公共 API（init_schema + 所有公开方法），内部委托 Writer
  - 文件: `packages/data/src/ditto_data/services/trade/service.py`
  - 测试: 全部 `test_trade_service_unit.py` 测试通过，无 import 路径变更

- [x] Task 1.6: 删除旧 `trade_service.py`，更新 import 路径 `[S]`
  - 验收: `pixi run -e dev check` 全部通过，importlinter 无新增违规
  - 文件: `packages/data/src/ditto_data/services/trade_service.py`（删除）
  - 影响文件: `providers_portfolio.py`, `command/trade.py`, `di/trade.py`, CLAUDE.md

### Phase 2：comparison.py 纯计算函数抽取（M）

- [x] Task 2.1: 抽取 `compute_comparison_from_raw` 及辅助函数到 `comparison_math.py` `[M]`
  - 验收: `compute_comparison_from_raw` + `_build_actual_navs` + `_extract_*` 辅助函数移至新文件
  - 文件: `packages/app/src/ditto_app/query/comparison_math.py`
  - 测试: `test_comparison_unit.py` 全部通过

- [x] Task 2.2: 精简 `comparison.py` 仅保留 Facade + DTO `[S]`
  - 验收: comparison.py 仅含 ComparisonMetrics、ComparisonQueryFacade、import from comparison_math
  - 文件: `packages/app/src/ditto_app/query/comparison.py`
  - 测试: `pixi run -e dev check` 通过

### Phase 3：engine.py 结果组装抽取（M）

- [x] Task 3.1: 抽取 `_assemble_result` + `_build_manifest` 到 `backtest/result.py` `[M]`
  - 验收: 新模块包含 `assemble_engine_result` + `build_run_manifest` 函数
  - 文件: `packages/engine/src/ditto_engine/backtest/result.py`
  - 测试: `test_engine_loop_unit.py` 全部通过

- [x] Task 3.2: EngineLoop 调用新模块，精简 engine.py `[S]`
  - 验收: engine.py 行数减少约 80 行，功能不变
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py`
  - 测试: `pixi run -e dev check` 通过

### Phase 4：文档同步 + 收尾（S）

- [x] Task 4.1: 更新 CLAUDE.md 反映 trade_service 拆分 `[S]`
  - 验收: data/CLAUDE.md 中 trade_service 路径更新为 trade/service.py
  - 文件: `packages/data/CLAUDE.md`

- [x] Task 4.2: 全量验证 `[S]`
  - 验收: `pixi run -e dev check` 通过（lint + fmt + type + test）
  - 命令: `pixi run -e dev check`

## 依赖关系

```
Phase 1 (trade_service 拆分)
  1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6
Phase 2 (comparison 拆分)      — 可与 Phase 1 并行
  2.1 → 2.2
Phase 3 (engine 拆分)         — 可与 Phase 1/2 并行
  3.1 → 3.2
Phase 4 (收尾)                — 依赖 Phase 1/2/3 全部完成
  4.1 + 4.2
```

## 排除项

以下审查建议经二次确认为合理设计，不纳入修复：

| 建议 | 排除理由 |
|------|---------|
| `eod.py:72` except Exception | 已有 `logger.exception` 记录，告警发送失败不应阻断 Flow |
| `dq_batch.py:301` except Exception | 已有 `logger.warning` 记录，DQ 告警失败不应阻断 Task |
| `main.py:272` except Exception | 紧接 `raise` 重新抛出，仅用于请求日志记录 |
| `ops.py` 异常粒度 | CLI 入口点的 DI 容器异常捕获 + 友好退出是标准模式 |
| kernel/__init__.py re-export | 当前 2 层深度合规，增长到 3 层时再处理 |
| backtest.py / trade.py API 路由行数 | 标准 CRUD 模式，结构清晰，无需拆分 |
| Sprint 计划文档归档 | 低优先级文档整理，不影响代码质量 |
| providers smoke test | 通过集成测试间接覆盖，非阻塞项 |
