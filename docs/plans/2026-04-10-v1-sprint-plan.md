# V1 Sprint Plan: 控制面 + 人工执行闭环

## 概述

- **Sprint**: V1 | **来源**: [v1-version-design.md](2026-04-10-v1-version-design.md)
- **创建**: 2026-04-10
- **范围**: Phase 0 (Foundation) → Phase 1 (回测闭环) → Phase 2 (人工执行闭环) → Phase 3 (Lineage)
- **目标**: 打通"研究结果 → 交易意图 → 人工执行 → 偏差复盘"完整闭环

## 技术方案

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| EngineLoop 拆分策略 | TradingStep chain + 保持行为不变 | 632 行单体拆分，最小风险 |
| DecisionFrame 保护 | debug-mode 校验 | 零生产开销 |
| 跨层对象映射 | data 层 *Record + app 层双向映射 | importlinter 禁止 data → app |
| Signal Delivery Protocol | app process ports 定义，interfaces 实现 | 保持 app 层纯编排 |
| 基准 NAV | 读模型注入，复用 build_report | 不造轮子 |

### 现状验证（探索结论）

| 组件 | 当前状态 | 差距 |
|------|---------|------|
| EngineLoop | 632 行，`_step()` 承担 7+ 职责 | 需拆分为 TradingStep chain |
| DecisionFrame | `type DecisionFrame = pl.DataFrame` | 零运行时保护 |
| RunManifest | 258 行，`input_refs: tuple[InstrumentId, ...]` | 无数据指纹 |
| StrategySpec params | `dict[str, object]` | 有 ParamConstraint 元数据但未用于校验 |
| API 路由 | 14 个端点，无 strategy/backtest/execution | 需新建 |
| App CQRS | 4 子模块，R8 互斥规则健全 | 可直接扩展 |
| FillEvent | accounting 模块，11 字段 frozen dataclass | 设计文档正确：不添加人工执行字段 |
| Import Linter | 24 合约，全部通过 | 新文件必须维持 |

### 风险识别

| 风险 | 影响 | 缓解 |
|------|------|------|
| Phase 0 EngineLoop 拆分改变行为 | 回测结果不一致 | Golden baseline 测试保护 |
| Phase 2 SQLite schema 设计 | 数据模型返工 | 设计阶段先审批 |
| Phase 2 跨层映射复杂度 | 代码膨胀 | 双向映射集中在 app 层 |
| PostTrade 前置顺序被破坏 | 风控失效 | 明确 RiskScanStep 在 StrategyStep 前执行 |

---

## Phase 0: Foundation Sprint

> **依赖**: 无 | **前置**: 所有后续 Phase
> **目标**: 解决架构审计 P0/P1 项，为后续工作打基础

### 0.1 TradingStep Protocol + StepResult 定义 `[S]`

**验收**:
- `TradingStep` Protocol 定义在 `steps.py`
- `StepResult` 数据类包含 success/errors/audit_data
- `StepContext` 包含 date/account/brokerage/pipeline 等共享状态

**文件**: `packages/engine/src/ditto_engine/backtest/steps.py`（新建）

---

### 0.2 提取 DataFetchStep `[S]`

**验收**:
- 从 `_step()` 提取 Slice 获取 + 账户快照 + lock 清除逻辑
- 独立单元测试覆盖

**文件**:
- 新建: `packages/engine/src/ditto_engine/backtest/steps.py`
- 修改: `packages/engine/src/ditto_engine/backtest/engine.py`
- 测试: `packages/engine/tests/unit/backtest/test_steps_unit.py`

---

### 0.3 提取 RiskScanStep `[S]`

**验收**:
- PostTrade 风控扫描 + 锁管理前置逻辑提取
- **严格保持 engine.py:330 的前置顺序**（RiskScan 在 Pipeline 前）
- 独立单元测试覆盖

**文件**: 同 0.2

**注意**: 当前 `_step()` 中 PostTrade 扫描在 Pipeline 前执行（engine.py:330），通过 `lock_instrument()` 影响 StrategyContext → Planning。拆分时 RiskScanStep 必须在 StrategyStep 之前。

---

### 0.4 提取 StrategyStep + PlanningStep `[M]`

**验收**:
- 策略 Pipeline 调用 → TargetPortfolio 提取（仅 rebalance day）
- ExecutionPlanner → ExecutionPlan 提取
- RuleProvider 规则获取集成
- 单元测试覆盖 rebalance/skip-rebalance 分支

**文件**: 同 0.2

---

### 0.5 提取 PreTradeStep + ExecutionStep + AuditStep `[L]`

**验收**:
- PreTrade 检查循环 → 过滤/resize 订单提取
- 订单提交 + 成交处理提取
- 每步审计记录（账户快照 + closed-trade drain）提取
- 单元测试覆盖 pre-trade accept/reject/resize 分支

**文件**: 同 0.2

**注意**: 逐日只做 closed-trade drain；真正的 flush() 在 run() 结束时执行（engine.py:268）。FinalizeStep 不能错误地放入 AuditStep。

---

### 0.6 EngineLoop 瘦身 + StepChain 编排 `[L]`

**验收**:
- `_step()` 仅编排 Steps，无内嵌业务逻辑
- `run()` 保持日历迭代 + StepChain 调度
- 添加 FinalizeStep（run 结束时 flush 未平仓交易 + 构建 RunManifest）
- **Golden baseline 测试通过**（回测端到端结果不变）
- `pixi run -e dev check` + `arch-check` 全通过

**文件**:
- 修改: `packages/engine/src/ditto_engine/backtest/engine.py`
- 修改: `packages/engine/src/ditto_engine/backtest/steps.py`
- 测试: `packages/engine/tests/integration/backtest/` 现有测试全部通过

---

### 0.7 DecisionFrame Schema 保护 `[S]`

**验收**:
- `FrameCol` 常量类定义在 `frame.py`
- `validate_frame()` 在 `__debug__` 模式下校验必需列
- release 模式下 no-op（零性能开销）
- 现有 Pipeline stage 通过 `validate_frame` 校验

**文件**:
- 新建: `packages/engine/src/ditto_engine/alpha/frame.py`
- 修改: `packages/engine/src/ditto_engine/alpha/protocols.py`（导入 FrameCol）
- 测试: `packages/engine/tests/unit/alpha/test_frame_unit.py`

---

### 0.8 StrategySpec.params 校验增强 `[S]`

**验收**:
- `validate_spec_params()` 利用 `ParamConstraint` 元数据校验类型和范围
- 对非法 params 抛出明确异常
- 现有模板 specs 通过校验

**文件**:
- 修改: `packages/engine/src/ditto_engine/alpha/specs.py`
- 修改: `packages/engine/src/ditto_engine/alpha/validation.py`
- 测试: `packages/engine/tests/unit/alpha/test_specs_unit.py`

---

### 0.9 RunManifest 丰富化 `[M]`

**验收**:
- `InputRef` 数据类：instrument_id + data_hash + date_range + source
- `RunManifest` 增加 input_refs（InputRef 版本）、universe_hash、spec_hash、dependency_versions、random_seed
- 向后兼容：新字段均有默认值
- `serialize_manifest()` 包含新字段
- 现有序列化/反序列化测试通过

**文件**:
- 修改: `packages/engine/src/ditto_engine/backtest/manifest.py`
- 测试: `packages/engine/tests/unit/backtest/test_manifest_unit.py`

---

### Phase 0 验收 Gate

- [ ] `pixi run -e dev check` + `arch-check` 全通过
- [ ] EngineLoop `_step()` 仅编排 Steps，无内嵌业务逻辑
- [ ] `validate_frame` 在 debug 模式下捕获列名错误
- [ ] RunManifest 包含 InputRef 数据指纹
- [ ] **现有回测端到端结果不变**（Golden baseline 验证）

---

## Phase 1: 回测闭环基础 (P0)

> **依赖**: Phase 0 | **前置**: Phase 2
> **目标**: 策略生命周期 API + 回测结果查询 API + 基准数据注入 + Trade 查询服务

### 1.1 BacktestTradeQueryFacade — 回测成交查询 `[M]`

**验收**:
- 从 parquet 产物读取成交明细
- 返回结构化 `list[TradeRecord]`
- 支持分页和日期范围过滤
- 单元测试 + 集成测试

**文件**:
- 新建: `packages/app/src/ditto_app/query/backtest_trade.py`
- 测试: `packages/app/tests/unit/query/test_backtest_trade_unit.py`

---

### 1.2 RunReadModel — 统一 Run 查询 `[M]`

**验收**:
- 跨策略列表查询
- 支持按状态/策略 ID/时间范围过滤
- 复用 `StrategyRunService`（data 层）扩展查询面
- 单元测试

**文件**:
- 新建: `packages/app/src/ditto_app/query/run.py`
- 修改: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`（扩展查询方法）
- 测试: `packages/app/tests/unit/query/test_run_unit.py`

---

### 1.3 审计扩展 — trade_fill record_type `[S]`

**验收**:
- `ExecutionAuditService` 扩展 record_type 支持 `trade_fill`
- 审计查询 API 可返回成交审计记录
- 不影响现有 risk_log / pre_trade_log

**文件**:
- 修改: `packages/data/src/ditto_data/services/audit/execution_audit_service.py`
- 修改: `packages/data/src/ditto_data/models/strategy_audit.py`
- 修改: `packages/engine/src/ditto_engine/backtest/statistics.py`

---

### 1.4 BacktestQueryFacade — 回测查询编排 `[M]`

**验收**:
- 编排 BacktestTradeQueryFacade + RunReadModel + 审计查询
- 基准 NAV 通过读模型路径自动获取并注入报告
- 复用 `BacktestService.build_report` 已支持的 `benchmark_navs` 参数
- 单元测试

**文件**:
- 新建: `packages/app/src/ditto_app/query/backtest.py`
- 测试: `packages/app/tests/unit/query/test_backtest_unit.py`

---

### 1.5 StrategyCommandHandler — 策略 CRUD `[M]`

**验收**:
- 创建/更新/发布策略 Spec
- 复用 `StrategyCatalogService`（data 层，80 行薄 facade）
- Command DTO + Handler 分离
- 单元测试覆盖全 CRUD

**文件**:
- 新建: `packages/app/src/ditto_app/command/strategy.py`
- 测试: `packages/app/tests/unit/command/test_strategy_unit.py`

---

### 1.6 API 路由 — 策略 + 回测 `[L]`

**验收**:
- 策略 CRUD API: `POST/GET/PUT /api/v1/strategies`, `POST /api/v1/strategies/{id}/publish`
- 回测查询 API: `GET /api/v1/backtests/runs`, `GET /api/v1/backtests/runs/{id}`, `GET /api/v1/backtests/runs/{id}/report`, `GET /api/v1/backtests/runs/{id}/trades`, `GET /api/v1/backtests/runs/{id}/audit`
- 遵循现有路由模式（参考 market.py：Dishka DI + asyncio.to_thread + APIResponse[T]）
- 请求/响应 Pydantic 模型
- DI 注册（providers.py）

**文件**:
- 新建: `interfaces/src/ditto_interfaces/api/routes/strategy.py`
- 新建: `interfaces/src/ditto_interfaces/api/routes/backtest.py`
- 新建: `interfaces/src/ditto_interfaces/models/strategy.py`（Pydantic 模型）
- 修改: `interfaces/src/ditto_interfaces/api/routes/__init__.py`（注册路由）
- 修改: `packages/app/src/ditto_app/providers.py`（DI 注册）

---

### Phase 1 验收 Gate

- [x] `pixi run -e dev check` 全通过（4158 passed, 0 failed, 6 pre-existing errors）
- [x] `arch-check` 全通过（24/24 contracts KEPT）
- [x] 策略 CRUD 完整可用（CreateStrategyHandler + UpdateStrategyHandler + PublishStrategyHandler + StrategyQueryFacade）
- [x] 回测报告/成交/审计可通过 API 查询（BacktestQueryFacade 编排 1.1+1.2+1.3）
- [x] Run 列表支持跨策略、按状态/时间范围过滤（RunReadModel + strategy_run_store.list_runs）
- [x] 架构违规已修复：strategy routes 通过 StrategyQueryFacade 间接访问 data 层

---

## Phase 2: 人工执行闭环 (P0)

> **依赖**: Phase 1 | **前置**: Phase 3
> **目标**: 信号快照 → 交易意图 → 人工成交录入 → 实际持仓/P&L → 回测 vs 实际对比

### 2.1 领域对象定义 — app 层 DTO + data 层 Record `[M]`

**验收**:
- app 层 DTO: `TradeIntent`、`ManualExecutionFill`、`ActualPositionSnapshot`
- data 层 Record: `TradeIntentRecord`、`ManualExecutionFillRecord`、`ActualPositionSnapshotRecord`
- Record 仅含标准库类型 + kernel types（InstrumentId）
- 类型全部 frozen dataclass

**文件**:
- 新建: `packages/app/src/ditto_app/process/execution/types.py`
- 新建: `packages/data/src/ditto_data/models/trade.py`
- 测试: `packages/app/tests/unit/process/execution/test_types_unit.py`

---

### 2.2 TradeService — data 层 CRUD `[M]`

**验收**:
- Intent/Fill/Position CRUD 服务
- **仅操作 `*Record` 对象**（零 app/engine 依赖）
- SQLite 存储（需审批 schema 设计）
- 单元测试覆盖全 CRUD

**文件**:
- 新建: `packages/data/src/ditto_data/services/trade_service.py`
- 测试: `packages/data/tests/unit/services/test_trade_service_unit.py`

**审批 Gate**: SQLite schema 变更（`trade_intents` / `execution_fills` / `actual_positions` 表设计）需人工审批

---

### 2.3 SignalSnapshotProcess — 信号快照 + 交易意图推导 `[L]`

**验收**:
- 从 Pipeline 输出的 TargetPortfolio 生成 SignalSnapshot
- 对比当前持仓 → 生成 TradeIntent 列表（delta_weight ≠ 0）
- 信号推送通知（via SignalDeliveryProtocol，Telegram 渠道）
- Protocol 定义在 `app/process/execution/ports.py`

**文件**:
- 新建: `packages/app/src/ditto_app/process/execution/signal_snapshot.py`
- 新建: `packages/app/src/ditto_app/process/execution/ports.py`（SignalDeliveryProtocol）
- 新建: `interfaces/src/ditto_interfaces/services/signal_delivery.py`（Protocol 实现）
- 测试: `packages/app/tests/unit/process/execution/test_signal_snapshot_unit.py`

---

### 2.4 TradeExecutionCommandHandler — 成交录入 `[M]`

**验收**:
- 验证 intent_id 有效
- 创建 ManualExecutionFill（app DTO）→ 映射为 ManualExecutionFillRecord → 持久化
- 触发 ManualTracker 聚合
- app → data 跨层映射集中在 CommandHandler

**文件**:
- 新建: `packages/app/src/ditto_app/command/trade.py`
- 测试: `packages/app/tests/unit/command/test_trade_unit.py`

---

### 2.5 ManualTracker — Fill 聚合 → 实际持仓/P&L `[L]`

**验收**:
- 从所有 Fill 聚合 → ActualPositionSnapshot
- 计算 Actual P&L（已实现/未实现）
- 含 T+1 交收规则（复用 `AShareSettlementModel`）
- 单元测试覆盖部分成交、多笔成交、T+1 场景

**文件**:
- 新建: `packages/app/src/ditto_app/process/execution/manual_tracker.py`
- 测试: `packages/app/tests/unit/process/execution/test_manual_tracker_unit.py`

---

### 2.6 ComparisonReport — 回测 vs 实际对比 `[M]`

**验收**:
- 对比维度: Sharpe / Return / 成本 / 偏离度
- 输出结构化 ComparisonReport
- 复用 engine 层统计工具（如有）

**文件**:
- 新建: `packages/app/src/ditto_app/process/execution/comparison.py`
- 新建: `packages/app/src/ditto_app/query/portfolio_actual.py`（查询 Facade）
- 测试: `packages/app/tests/unit/process/execution/test_comparison_unit.py`

---

### 2.7 API 路由 — 成交/持仓/对比 `[L]`

**验收**:
- 信号与意图: `GET /api/v1/signals/latest`, `GET /api/v1/signals/{id}/intents`
- 成交记录: `POST/GET/PUT/DELETE /api/v1/trades`
- 实际持仓与对比: `GET /api/v1/portfolio/actual`, `GET /api/v1/portfolio/actual/pnl`, `GET /api/v1/portfolio/comparison`
- DI 注册完整
- `pixi run -e dev check` + `arch-check` 全通过

**文件**:
- 新建: `interfaces/src/ditto_interfaces/api/routes/trade.py`
- 修改: `interfaces/src/ditto_interfaces/api/routes/__init__.py`
- 修改: `packages/app/src/ditto_app/providers.py`

---

### Phase 2 验收 Gate

- [x] 信号推送 Protocol 定义完成（SignalDeliveryProtocol in ports.py，Telegram 实现待 Phase 3）
- [x] TradeIntent 从 Pipeline 输出自动生成（SignalSnapshotProcess + generate_intents）
- [x] 成交记录 CRUD 完整可用（RecordFillHandler + TradeService + API routes）
- [x] 实际持仓正确计算（ManualTracker 含 T+1 交收 + 加权平均成本）
- [x] 回测 vs 实际对比报告含 Sharpe/Return/成本/偏离度（ComparisonMetrics 12 字段）
- [x] `pixi run -e dev check` + `arch-check` 全通过（4272 passed, 114 Phase 2 tests）

---

## Phase 3: Run Lineage / Replayability (P1)

> **依赖**: Phase 0（RunManifest 丰富化）| **前置**: V1.1 Phase 4
> **目标**: 实验级复现能力

### 3.1 ReplayValidator + ReplayValidationResult `[L]`

**验收**:
- `ReplayValidationResult`: is_reproducible / nav_correlation / max_nav_diff_bps / manifest_diff / input_data_match
- `ReplayValidator.validate()`: 对比两次运行的 manifest
- `ReplayValidator.replay()`: 基于原始 manifest 重放
- manifest 差异分类报告（数据/配置/版本/随机种子）

**文件**:
- 新建: `packages/engine/src/ditto_engine/backtest/replay.py`
- 测试: `packages/engine/tests/unit/backtest/test_replay_unit.py`

---

### 3.2 Lineage API `[M]`

**验收**:
- `POST /api/v1/backtests/runs/{id}/replay`: 基于原始 manifest 重放
- `GET /api/v1/backtests/runs/{id}/lineage`: 查询运行血统
- 两次相同输入回测，nav_series 完全一致

**文件**:
- 修改: `interfaces/src/ditto_interfaces/api/routes/backtest.py`
- 测试: 集成测试验证复现性

---

### Phase 3 验收 Gate

- [x] `pixi run -e dev check` 全通过（4323 passed, 0 failed, 6 pre-existing errors）
- [x] `arch-check` 无新增违规（23 kept, 1 pre-existing broken）
- [x] ReplayValidator 纯函数实现 — manifest 对比 + NAV 序列验证 + Pearson 相关系数
- [x] manifest 差异可被检测并分类报告（config/data/version/seed 四类）
- [x] Lineage API 返回完整的运行血统链（GET lineage + POST replay）
- [x] StrategyRunRecord 支持 parent_run_id 血统追踪
- [x] schema.sql 同步更新 parent_run_id 列 + 索引
- [x] 39 个 ReplayValidator 单元测试 + 7 个 lineage 单元测试 + 6 个 facade 单元测试

---

## 依赖关系图

```
Phase 0 ─────────────────────────────────────────────────────
  0.1 Protocol定义 ──→ 0.2 DataFetch ──→ 0.3 RiskScan ──→ 0.4 Strategy+Planning
                         ──→ 0.5 PreTrade+Exec+Audit ──→ 0.6 EngineLoop瘦身
  0.7 DecisionFrame (独立)
  0.8 SpecParams (独立)
  0.9 RunManifest (独立)

Phase 1 ──(依赖 Phase 0)──────────────────────────────────────
  1.1 TradeQuery ──→ 1.4 BacktestQueryFacade ──→ 1.6 API路由
  1.2 RunReadModel ──→ 1.4 ──→ 1.6
  1.3 审计扩展 ──→ 1.4 ──→ 1.6
  1.5 StrategyCommand ──→ 1.6

Phase 2 ──(依赖 Phase 1)──────────────────────────────────────
  2.1 领域对象 ──→ 2.2 TradeService ──→ 2.4 CommandHandler ──→ 2.7 API
                  ──→ 2.3 SignalSnapshot ──→ 2.4 ──→ 2.7
                  ──→ 2.5 ManualTracker ──→ 2.6 Comparison ──→ 2.7

Phase 3 ──(依赖 Phase 0.9)───────────────────────────────────
  3.1 ReplayValidator ──→ 3.2 Lineage API
```

---

## 跨 Phase 关注点

### importlinter 合规

| 层 | 约束 | 验证 |
|----|------|------|
| engine 新模块 | 不依赖 data/infra/app | `engine-no-data-dependency`, `engine-no-infra-dependency` |
| data trade_service | 不依赖 engine/app/interfaces | `data-boundary` |
| app process | 不依赖 interfaces | `app-no-interfaces-import` |
| SignalDeliveryProtocol | 定义在 app process，实现在 interfaces | 合规（app 定义 Port，interfaces 实现） |
| analytics 归因 | 零 IO | Phase 7 实施 |

### DI 容器变更计划

| Phase | Provider | 新增注册 |
|-------|---------|---------|
| 1 | AppCommandProvider | `StrategyCommandHandler` |
| 1 | AppQueryProvider | `BacktestQueryFacade`, `BacktestTradeQueryFacade`, `RunReadModel` |
| 2 | AppCommandProvider | `RecordFillHandler`, `UpdateIntentStatusHandler` |
| 2 | AppQueryProvider | `PortfolioActualQueryFacade`, `TradeQueryFacade` |
| 2 | AppProcessProvider | `TradeService`, `ManualTracker` |

### 测试要求

- 每个模块分支覆盖率 ≥ 80%
- TDD 流程（RED → GREEN → REFACTOR）
- Phase 0: Golden baseline 验证（回测结果不变）
- Phase 1-2: API 端点集成测试
- Phase 3: 复现性验证测试

---

## 任务统计

| Phase | 任务数 | S | M | L | XL | 新增文件 | 修改文件 |
|-------|--------|---|---|---|-----|---------|---------|
| 0 | 9 | 4 | 2 | 2 | 1→拆分 | ~2 | ~4 |
| 1 | 6 | 1 | 3 | 1 | 0 | ~5 | ~5 |
| 2 | 7 | 0 | 3 | 3 | 0 | ~8 | ~3 |
| 3 | 2 | 0 | 1 | 1 | 0 | ~1 | ~1 |
| **合计** | **24** | **5** | **9** | **7** | **0** | **~16** | **~13** |
