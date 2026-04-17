# V1 Sprint 审查修复计划

## 概述
- Sprint: V1 Sprint Review | Phase: 全量修复（功能缺陷 + 代码质量）
- 创建: 2026-04-12 | 更新: 2026-04-12（整合 P0/P1/P2 深度审查问题）
- 范围: 11 个功能缺陷（P0×3 + P1×6 + P2×2）+ 17 个代码质量改进，共 39 个修复任务

## 问题全景

### P0 — 合并阻断（功能完全不可用）

| ID | 问题 | 影响 |
|----|------|------|
| P0-1 | TradeService 在错误 Provider，测试失败 | DI 容器构建崩溃 |
| P0-2 | Schema 迁移非幂等 + 交易表未初始化 | 二次启动崩溃 + no such table |

### P1 — 功能缺陷（核心路径失效）

| ID | 问题 | 影响 |
|----|------|------|
| P1-1 | 因子桥接 compiled_expressions 断链 | 含 signal_expressions 的策略回测因子信号静默失效 |
| P1-2 | Retry endpoint 参数不完整 | 重试功能必然 TypeError 崩溃 |
| P1-3 | Prefect 绕过调度基础设施 | 异常吞没、无重试、无并发控制 |
| P1-4 | regime_config 未接入 catalog runtime | API 创建的策略无法启用 regime 风控 |
| P1-5 | 策略更新无 version 传递 | 第二次更新必版本冲突，功能完全阻断 |
| P1-6 | 手工成交无身份校验 | 跨策略/跨标的错配成交，持仓污染 |

### P2 — 数据正确性

| ID | 问题 | 影响 |
|----|------|------|
| P2-1 | ManualTracker 无 PIT 截断 | 回补历史快照会将未来成交算入 |
| P2-2 | StepChain 静默 break | step failure 被吞成少跑一天，无日志 |

---

## 技术方案

### 核心决策

**D1: TradeService 归属修正**
- 在 Data 层新建 `TradeProvider`，将 `TradeService` 注册移出 `AppProcessProvider`
- `TradeService` 本身是 Data 层服务（仅依赖 `SQLiteClient`），注册应在其所属层
- `init_schema()` 必须在 provider 中显式调用

**D2: Schema 幂等化**
- `schema.sql` 的 CREATE TABLE 直接包含 `config_json` 列，删除尾部的裸 ALTER TABLE
- 交易三表 DDL 纳入 `schema.sql`（作为 `CREATE TABLE IF NOT EXISTS`，幂等）
- `strategy_run_store._run_migrations()` 保留，但从 `_MIGRATIONS` 中移除与 CREATE TABLE 重复的列

**D3: 因子桥接贯通（P1-1 修复）**
- `PublishedBacktestRuntime` 新增 `compiled_expressions` 字段
- `BacktestRuntimeBuilder.build_published_runtime()` 传递 `compiled_expressions`
- `StrategyServiceFactory.build_backtest_service_from_catalog()` 将其塞入 `BacktestServiceOptions`

**D4: Retry 配置持久化（P1-2 修复）**
- 启用 `strategy_run.config_json` 列：`StrategyRunRecord` 新增字段，UPSERT/GET 接入
- `BacktestRunHandler.handle()` 在创建 run 时将 start_date/end_date/cost_config 等序列化为 JSON
- retry 路由从 `original_record.config_json` 恢复参数，补全 flow_params

**D5: 成交身份校验（P1-6 修复）**
- `RecordFillHandler` 从 `intent_record` 读取 strategy_id/instrument_id/direction，与 command 比对
- intent 状态前置校验（只允许 pending 状态录入成交）
- 支持部分成交：quantity 未完全满足时设为 `partially_filled`
- `UpdateIntentStatusHandler` 添加状态转换合法性校验

**D6: 策略版本修复（P1-5 修复）**
- `UpdateStrategyRequest` 新增 `version: int | None = None`
- 当 `version is None` 时，Handler 自动使用当前版本（跳过乐观锁），保留 `version` 字段供未来显式并发控制

**D7: regime_config 接入（P1-4 修复）**
- 在 `_spec_deserializer.py` 新增 `deserialize_regime_config()` 反序列化器
- 4 个 config builder 方法从 `spec.params.get("regime_config")` 提取并反序列化
- 支持 indicator 类型动态分发（trend/volatility/breadth/momentum）

**D8: Prefect 短期修复（P1-3 修复）**
- 短期：给 `_submit_flow` 包裹 try/except，异常时更新 RunRecord 状态为 failed
- 中期（后续 Sprint）：引入内存任务队列 + 独立 worker task
- 长期：部署 Prefect Server + Worker 独立进程

**D9: PIT 截断 + StepChain 日志（P2 修复）**
- `ManualTracker.compute_positions` 增加 `fill.trade_date <= snapshot_date` 过滤
- `EngineLoop._step` 在 break 时记录 `logger.warning`，`EngineResult` 新增 `skipped_dates` 字段

**D10-D15: 代码质量改进（原审查计划）**
- 见下方各 Phase 中的 D 标注

## 任务清单

### Phase 0: P0 阻断修复（必须首先完成）

- [x] T01: TradeService 归属修正 — 移至 Data 层 TradeProvider `[M]`
  - 验收: 测试通过，DI 容器可独立构建 AppQueryProvider
  - 文件:
    - 新增 `packages/data/src/ditto_data/di/trade.py` — `TradeProvider` 注册 `TradeService` + 调用 `init_schema()`
    - 更新 `packages/data/src/ditto_data/di/__init__.py` — 导出 `TradeProvider`
    - `packages/app/src/ditto_app/providers.py` — 从 `AppProcessProvider` 移除 `trade_service` 方法
    - 更新所有使用 `*get_app_providers()` 的容器组装，加入 `TradeProvider`
    - `interfaces/src/ditto_interfaces/registry/init_providers.py` — 确保注册 `TradeProvider`
  - 测试: `interfaces/tests/unit/registry/test_research_dataset_facade_unit.py` 恢复通过
  - 风险加权: +1（DI 全局影响）

- [x] T02: Schema 幂等化 + 交易表初始化 `[M]`
  - 验收: 二次启动不崩溃，API 主路径交易表可用
  - 文件:
    - `packages/data/src/ditto_data/scripts/schema.sql`:
      - strategy_run CREATE TABLE 直接包含 `config_json TEXT NOT NULL DEFAULT ''`
      - 删除尾部的 `ALTER TABLE strategy_run ADD COLUMN config_json` 裸迁移
      - 新增 trade_intents/execution_fills/actual_positions 三表 `CREATE TABLE IF NOT EXISTS`
    - `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`:
      - `_MIGRATIONS` 移除 `config_json` 条目（已在 CREATE TABLE 中）
      - 保留其他增量迁移的幂等检测逻辑
  - 依赖: 无

### Phase 1: P1 功能缺陷修复

- [x] T03: 因子桥接 compiled_expressions 贯通 `[M]`
  - 验收: 含 signal_expressions 的策略通过 catalog 回测时因子信号生效
  - 文件:
    - `packages/app/src/ditto_app/builders/service_factory.py`:
      - `PublishedBacktestRuntime` 新增 `compiled_expressions: CompiledExpressions | None = None`
      - `BacktestRuntimeBuilder.build_published_runtime()` 传递 `runtime.compiled_expressions`
      - `build_backtest_service_from_catalog()` 将 `runtime.compiled_expressions` 传入 `resolved_options`
    - `packages/app/src/ditto_app/process/execution/backtest_process.py` — 无需改动（消费端已正确等待 compiled_expressions）
  - 依赖: 无

- [x] T04: Retry 配置持久化 — 启用 config_json `[L]`
  - 验收: Retry 功能完整可用，重跑参数与原始回测一致
  - 文件:
    - `packages/data/src/ditto_data/models/strategy_run.py` — 新增 `config_json: str = ""`
    - `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py` — UPSERT/GET SQL 和 `_row_to_record` 接入 config_json
    - `packages/app/src/ditto_app/command/backtest.py`:
      - `BacktestRunHandler.handle()` 在创建 run 时将回测配置序列化为 JSON 写入 config_json
      - 需更新 `RunLifecycleService.create_run` 协议和 `StrategyRunService` 实现，增加 `config_json` 参数
    - `interfaces/src/ditto_interfaces/api/routes/backtest.py`:
      - `retry_run()` 从 `original_record.config_json` 恢复 start_date/end_date/cost_config 等
      - 补全 `flow_params` 的所有必需参数
  - 依赖: T02（schema 已幂等化）

- [x] T05: 策略更新版本修复 `[S]`
  - 验收: 策略可多次更新，乐观锁正确传递
  - 文件:
    - `interfaces/src/ditto_interfaces/models/strategy.py` — `UpdateStrategyRequest` 新增 `version: int | None = Field(default=None, description="版本号（乐观锁）")`
    - `interfaces/src/ditto_interfaces/api/routes/strategy.py` — 路由传递 `version=request.version`
    - `packages/app/src/ditto_app/command/strategy.py`:
      - `UpdateStrategyCommand.version` 默认值改为 `None`
      - Handler 中 `if command.version is None` 时自动使用 `existing.version`（跳过乐观锁检查）
  - 依赖: 无

- [x] T06: 手工成交身份校验 `[M]`
  - 验收: 跨策略/跨标的/方向反转的成交被拒绝，支持部分成交
  - 文件:
    - `packages/app/src/ditto_app/command/trade.py`:
      - `RecordFillHandler.handle()`: 校验 intent 的 strategy_id/instrument_id/direction 与 command 一致
      - 校验 intent 状态为 `pending` 才允许录入
      - 比对 quantity 支持部分成交 → `partially_filled` 状态
      - `_recompute_positions()` 传入正确的 `strategy_id`（来自 intent，非 command）
    - `packages/app/src/ditto_app/command/trade.py`:
      - `UpdateIntentStatusHandler`: 添加合法状态枚举校验和状态转换矩阵
    - `interfaces/src/ditto_interfaces/models/trade.py`:
      - `RecordFillRequest.direction` → `Literal["buy", "sell"]`（从原计划 T17 合并）
      - `UpdateIntentStatusRequest.status` → `Literal["pending", "filled", "partially_filled", "cancelled", "expired"]`
  - 依赖: 无

- [x] T07: regime_config 接入 catalog runtime `[L]`
  - 验收: API 创建的策略可通过 params.regime_config 启用 regime 评估
  - 文件:
    - `packages/app/src/ditto_app/builders/_spec_deserializer.py` — 新增 `deserialize_regime_config(raw_value, field_name) -> RegimeConfig | None`
      - 支持从 JSON dict 反序列化 `RegimeConfig`（包含 indicators 数组的类型分发）
    - `packages/app/src/ditto_app/builders/runtime_builder.py`:
      - `_build_etf_rotation_config()` 从 `spec.params.get("regime_config")` 提取并反序列化
      - 同样修改其他 3 个 config builder
  - 依赖: 无

- [x] T08: Prefect 短期修复 — 异常传播 `[S]`
  - 验收: flow 异常不再被吞没，RunRecord 状态正确更新为 failed
  - 文件:
    - `interfaces/src/ditto_interfaces/api/routes/backtest.py`:
      - `_submit_flow()` 包裹 try/except
      - 异常时通过 `StrategyRunLifecycleService` 更新状态为 failed
      - 需要在 `_submit_flow` 中获取 run_service（可通过闭包或全局容器）
    - 同步替换 `asyncio.get_event_loop()` → `asyncio.get_running_loop()`（合并原 T01）
  - 依赖: T01（TradeService 位置可能影响 DI 获取方式）

### Phase 2: P2 数据正确性

- [x] T09: ManualTracker PIT 截断 `[S]`
  - 验收: 回补历史快照时不会将未来成交算入
  - 文件:
    - `packages/app/src/ditto_app/process/execution/manual_tracker.py`:
      - `compute_positions()` 的 fills 过滤增加 `f.trade_date <= snapshot_date`
    - 测试: 新增覆盖未来日期 fills 被截断的场景
  - 依赖: 无

- [x] T10: StepChain 失败日志 `[S]`
  - 验收: step failure 不再静默，有明确的 warning 日志
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/engine.py`:
      - `_step()` 中 break 时 `logger.warning("Step %s failed on %s: %s", ...)`
    - `packages/engine/src/ditto_engine/backtest/engine.py`:
      - `EngineResult` 新增 `skipped_dates: tuple[str, ...] = ()` 字段
      - `_step()` 收集失败日期
      - `run()` 结束时输出 skipped_dates 摘要
  - 依赖: 无

### Phase 3: 快速清理（原 Phase 1 独立 S 任务）

- [x] T11: 删除死代码 `telegram_signal.py` `[S]`
  - 验收: 文件已删除，无残留引用
  - 文件: 删除 `interfaces/src/ditto_interfaces/services/telegram_signal.py`
  - 检查: `services/__init__.py` 是否有导出需清理

- [x] T12: 移除 `process/execution/types.py` re-export shim `[S]`
  - 验收: 文件已删除，所有消费者直接从 `ditto_app.types` 导入
  - 文件: 删除 `packages/app/src/ditto_app/process/execution/types.py`
  - 更新引用: `ports.py`, `comparison.py`, `signal_snapshot.py`, `manual_tracker.py`, `delivery.py`, `query/portfolio_actual.py`

- [x] T13: Sprint 计划文档 API 路径同步 `[S]`
  - 验收: 计划文档中 API 路径与实际实现一致
  - 文件: `docs/plans/2026-04-10-v1-sprint-plan.md` 2.7 节

### Phase 4: 常量与共享类型集中化

- [x] T14: 费率常量集中化 + CostConfig 迁移 `[M]`
  - 验收: 费率唯一定义点，CostConfig 在 contracts.py
  - 文件:
    - `packages/app/src/ditto_app/contracts.py` — 添加 `CostConfig` dataclass（从 command/backtest.py 移入）
    - `packages/app/src/ditto_app/command/backtest.py` — CostConfig 引用 engine 常量 + 从 contracts 导入
    - `packages/app/src/ditto_app/builders/runtime_builder.py` — 删除 `_DEFAULT_COMMISSION_RATE`
    - `interfaces/src/ditto_interfaces/models/backtest.py` — 引用 engine 常量
    - `interfaces/src/ditto_interfaces/jobs/flows/backtest.py` — 引用 engine 常量
    - `packages/app/src/ditto_app/process/execution/fee_override.py` — 从 contracts 导入 CostConfig
  - 依赖: 无

- [x] T15: Pearson 相关系数去重 `[M]`
  - 验收: 唯一 `pearson_correlation` 公共实现，退化行为统一
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/replay.py` — `_pearson_correlation` → `pearson_correlation`（公共）
    - `packages/app/src/ditto_app/query/comparison.py` — 删除本地实现，从 engine 导入
  - 退化行为: 统一为 replay.py 版本（n≤1 返回 1.0，零方差 isclose → 1.0）

- [x] T16: `_find_artifact` 去重 `[S]`
  - 验收: 共享 artifact 查找实现
  - 文件: 新增 `packages/app/src/ditto_app/query/_artifact_utils.py`
  - 消费者: `query/backtest.py`, `query/backtest_trade.py`, `process/execution/replay_process.py`

### Phase 5: Universe 公共 API（消除私有属性访问）

- [x] T17: MetadataService 新增 Universe CRUD 方法 `[M]`
  - 验收: 4 个新公共方法，委托到内部 reader/writer
  - 文件: `packages/data/src/ditto_data/services/metadata_service.py`
  - 方法: `create_universe()`, `delete_universe()`, `get_universe_detail()`, `list_universes_df()`

- [x] T18: Universe command/query 使用公共方法 `[M]`
  - 验收: 零 `reportPrivateUsage`
  - 文件: `command/universe.py` (7处), `query/universe.py` (2处)
  - 依赖: T17

### Phase 6: 类型精度修复

- [x] T19: 修复 StepContext + AuditStep 类型 `[M]`
  - 验收: 消除 steps.py + engine.py 中全部 14 处 `# type: ignore`
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/steps.py`:
      - `StepContext.target_portfolio`: `object | None` → `TargetPortfolio | None`
      - `StepContext.pre_trade_decisions`: `list[object]` → `list[PreTradeDecisionRecord]`
      - `AuditStep.trade_builder`: `object` → `TradeBuilder`
      - Optional narrowing: assert 或重构 None 检查
    - `packages/engine/src/ditto_engine/backtest/engine.py`:
      - 删除 `# type: ignore[arg-type]`、`# type: ignore[union-attr]`
      - fee_model 断言或 Optional 处理
  - 依赖: 无
  - 风险加权: +1（引擎核心）

- [x] T20: 替换 interfaces/models 中的 Any 参数 `[M]`
  - 验收: 零 `# noqa: ANN401`
  - 文件: `interfaces/src/ditto_interfaces/models/backtest.py`, `trade.py`, `strategy.py`
  - 方案: 替换为具体 App 层类型（`StrategyRunRecord`, `TradeIntent`, `ManualExecutionFill` 等）

- [x] T21: Pydantic 约束增强 `[M]`
  - 验收: direction/status 使用 Literal，日期使用 DateField
  - 文件: `interfaces/src/ditto_interfaces/models/trade.py`, `backtest.py`
  - 注意: T06 已包含 direction/status 约束，此处补充 CreateBacktestRunRequest 日期校验
  - 依赖: T06（避免冲突）

### Phase 7: Manifest 可复现性

- [x] T22: 填充 `random_seed` 和 `dependency_versions` `[M]`
  - 验收: RunManifest 包含随机种子和依赖版本
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/engine.py` — 从 EngineOptions 传入
    - `EngineOptions` 新增 `random_seed: int = 42`

- [x] T23: 填充 `input_ref_details` 数据指纹 `[L]`
  - 验收: replay 验证可检测数据变更
  - 文件: `engine/backtest/steps.py`, `engine.py`, `manifest.py`
  - 方案: 对每个 instrument 的 bar 数据计算确定性 hash
  - 风险加权: +1（引擎核心）

### Phase 8: 测试覆盖补全

- [x] T24: ReplayProcess 单元测试 `[L]`
  - 验收: 覆盖 replay(), _load_manifest, _build_config, _extract_nav 等
  - 文件: 新增 `packages/app/tests/unit/process/execution/test_replay_process_unit.py`
  - 依赖: T12（import 路径变更后）

- [x] T25: PortfolioActualQueryFacade 单元测试 `[M]`
  - 验收: 覆盖 get_latest_positions, compute_pnl 等
  - 文件: 新增 `packages/app/tests/unit/query/test_portfolio_actual_unit.py`

- [x] T26: CancelRunHandler/RetryRunHandler 测试 `[S]`
  - 验收: 覆盖状态守卫、parent_run_id 传递
  - 文件: 扩展 `packages/app/tests/unit/command/test_backtest_unit.py`

- [x] T27: BacktestService._build_factor_aware_bundle_builder 测试 `[M]`
  - 验收: 覆盖 compiled_expressions 非空/空/编译失败
  - 文件: 扩展 `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py`

- [x] T28: 成交校验 + PIT 截断测试 `[M]`
  - 验收: 覆盖身份校验拒绝、部分成交、PIT 截断
  - 文件: 扩展 `packages/app/tests/unit/command/test_trade_unit.py`, `packages/app/tests/unit/process/execution/test_manual_tracker_unit.py`
  - 依赖: T06, T09

### Phase 9: Schema 与文档

- [x] T29: MomentumIndicator 文档标注限制 `[S]`
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime.py`

- [x] T30: 设计文档差异标注 `[S]`
  - 文件: `docs/plans/2026-04-11-v1-enhancement-design.md` R4 部分

- [x] T31: BacktestService run_service 生命周期测试 `[S]`
  - 文件: 扩展 `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py`

---

## 依赖关系图

```
Phase 0 (P0 阻断):
  T01 ─── TradeService 归属
  T02 ─── Schema 幂等化

Phase 1 (P1 功能缺陷):
  T03 ─── 因子桥接 (独立)
  T04 ─── Retry 持久化 (依赖 T02)
  T05 ─── 版本修复 (独立)
  T06 ─── 成交校验 (独立)
  T07 ─── regime_config (独立)
  T08 ─── Prefect 短期修复 (依赖 T01)

Phase 2 (P2 正确性):
  T09 ─── PIT 截断 (独立)
  T10 ─── StepChain 日志 (独立)

Phase 3-7 (代码质量，原审查计划):
  T11-T13 ─── 快速清理 (独立)
  T14 ─── 常量集中 (独立)
  T15-T16 ─── 去重 (独立)
  T17 → T18 ─── Universe 公共 API
  T19-T21 ─── 类型精度 (T21 依赖 T06)
  T22-T23 ─── Manifest (独立)

Phase 8 (测试):
  T24-T28 ─── 多数依赖前置功能修复完成

Phase 9 (文档):
  T29-T31 ─── 独立
```

## 执行策略

1. **Phase 0**: 串行 T01 → T02（P0 阻断，最高优先）
2. **Phase 1**: T03/T05/T06/T07 可并行；T04 等 T02；T08 等 T01
3. **Phase 2**: T09/T10 可并行
4. **Phase 3-7**: 使用 subagent 并行处理独立任务组
5. **Phase 8**: 测试任务在前置功能修复完成后并行
6. **Phase 9**: 收尾文档

## 验收标准

- [ ] `pixi run -e dev check` 全部通过（lint + fmt + type + test --fast）
- [ ] 零 `reportPrivateUsage`（universe 模块）
- [ ] 零 `# noqa: ANN401`（interfaces/models/）
- [ ] 零 steps.py/engine.py 中与类型精度相关的 `# type: ignore`
- [ ] 二次启动不崩溃（schema 幂等）
- [ ] API 主路径交易表可用
- [ ] Retry 功能完整可用
- [ ] 策略可多次更新（无版本冲突）
- [ ] 含 signal_expressions 的策略因子信号生效
- [ ] 跨策略/跨标的成交被拒绝
- [ ] 分支覆盖率 ≥ 80%
