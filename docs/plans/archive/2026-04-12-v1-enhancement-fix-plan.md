# V1 增强修复完善计划

## 概述
- Sprint: V1 Enhancement Fix | Phase: 缺陷修复 + 功能补全
- 创建: 2026-04-12
- 前置: V1 Sprint Phase 0-3 + 增强计划 24 任务（20 完成、3 部分完成、1 未完成）
- 目标: 修复 4 处缺陷、补全 3 处遗漏、关闭 2 处技术债务

## 技术方案

### 缺陷清单（按严重度排序）

| # | 模块 | 严重度 | 类型 | 说明 |
|---|------|--------|------|------|
| D1 | R3 | **P0 阻断** | 缺陷 | Prefect flow 提交断裂 — 回测无法实际执行 |
| D2 | R6 | P1 | 缺陷 | CostConfig 管道未打通 — API 参数无法到达引擎 |
| D3 | R1 | P1 | 缺陷 | RegimeScoreEngine → Pipeline 集成点缺失 |
| D4 | R5 | P2 | 缺陷 | Universe Delete Handler 未实际删除数据 |
| O1 | R3 | P1 | 遗漏 | cancel/retry API 端点未实现 |
| O2 | R7 | P2 | 遗漏 | 端到端冒烟测试未创建 |
| O3 | R5 | P2 | 遗漏 | Universe API 路由层单元测试缺失 |
| T1 | R3 | P2 | 技术债 | schema.sql 缺少增量 migration |
| T2 | R5 | P3 | 技术债 | UniverseQueryFacade 访问私有属性 |

### 关键设计决策

| # | 决策 | 方案 | 原因 |
|---|------|------|------|
| K1 | Flow 提交位置 | API 层 `asyncio.to_thread` 后台提交 | Handler 保持纯 Command 职责；API 层负责异步编排 |
| K2 | RegimeScoringStep | Engine 层新建 DecisionStage，委托 RegimeScoreEngine | 符合 StepChain 模式，模板条件插入 |
| K3 | CostConfig → FeeModel | App 层 `build_fee_model()` 工厂函数，包装 AShareFeeModel + FeeSchedule 覆盖 | 不侵入 Engine 层，Protocol 兼容 |
| K4 | Cancel 端点 | 标记 `cancelled` 状态（复用 FAILED 路径） | RunStatus 为 TEXT 字段，无枚举扩展需求 |

### 依赖关系

```
批次 1（核心修复 — 解除功能阻断）:
  F1 (RegimeScoringStep) ──┐
  F2 (CostConfig 管道) ────┤── 并行开发
                           ↓
  F3 (Flow 提交 + 状态机) ──── 依赖 F1+F2（flow 需传递完整参数）

批次 2（功能补全 + 质量）:
  F4 (cancel/retry) ──── 依赖 F3（复用 flow 提交模式）
  F5 (Universe Delete) ──── 独立
  F6 (E2E 冒烟) ──── 依赖 F1+F2+F3（验证完整链路）
  F7 (Schema migration) ──── 独立
  F8 (Universe 测试) ──── 独立
```

---

## 批次 1: 核心修复

### F1: RegimeScoringStep — Regime 集成点 `[M]`

**问题**: `RegimeAwareAllocationStage` 期望读取 `regime_score`/`regime_label`/`position_ratio` 列，但 Pipeline 中无任何 Stage 写入这些列。

**方案**: 新建 `RegimeScoringStep`（Engine 层 DecisionStage），在 Allocate 之后、RegimeAware 之前插入，委托 `RegimeScoreEngine` 评分并写入三列。

- [x] Task: RegimeScoringStep 实现 `[M]`
  - 验收: `RegimeScoringStep` 实现 DecisionStage Protocol；接受 `RegimeConfig`；调用 `RegimeScoreEngine.score(frame)` 获取 `RegimeResult`；将 `score`/`label`/`position_ratio` 写为 scalar 列；空 frame 原样返回
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime_scoring.py`（新建）
  - 测试: 14 用例全部通过
  - 说明: `RegimeScoreEngine` 内部 indicators 在缺列时 graceful fallback（返回 0.5），不影响 Pipeline 执行。V1 使用 frame 中可用列（signal_value 等）；后续增强可通过 `StrategyInputBundle` 扩展注入市场数据

- [x] Task: 4 模板集成 RegimeScoringStep `[M]`
  - 验收: 当 `regime_config is not None` 时，Pipeline 插入 `RegimeScoringStep(config)` 于 Allocate 之后、RegimeAwareAllocationStage 之前；`regime_config=None` 行为不变；现有模板测试通过
  - 文件:
    - `packages/engine/src/ditto_engine/alpha/templates/etf_rotation.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/templates/etf_trend_swing.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/templates/stock_selection_trend.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/templates/stock_sector_rotation.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/builtins/__init__.py`（导出更新）
  - 测试: 单元测试（每个模板 1 用例：有 regime_config 时 frame 包含 regime 三列）
  - 说明: 模板 pipeline 组装变为 `[...Allocate] → [RegimeScoringStep(config)] → [RegimeAware] → [Constraint]`。RegimeScoringStep 接收 RegimeConfig 而非 RegimeAwareAllocationStage

---

### F2: CostConfig 管道打通 `[M]`

**问题**: `CostConfig` 在 Command 层定义但 Handler 未使用，`BacktestService` 接受 Engine 层 `FeeModel`，缺少映射。

**方案**: App 层新增 `build_fee_model(CostConfig | None) -> FeeModel` 工厂函数，通过 `OverrideFeeModel` 包装 `AShareFeeModel`，覆盖 `FeeSchedule` 中的佣金/印花税率。

- [x] Task: OverrideFeeModel + build_fee_model 工厂 `[M]`
  - 验收: `OverrideFeeModel` 实现 `FeeModel` Protocol，接受 `CostConfig`，在 `calculate()/estimate()` 中用 CostConfig 费率覆盖 FeeSchedule 对应字段，其余委托 `AShareFeeModel`；`build_fee_model(None)` 返回 `AShareFeeModel()`（默认行为）；`build_fee_model(config)` 返回 `OverrideFeeModel(config)`
  - 文件: `packages/app/src/ditto_app/process/execution/fee_override.py`（新建）
  - 测试: 11 用例全部通过
  - 说明: `OverrideFeeModel` 内部持有 `AShareFeeModel` 实例。覆盖逻辑：构造临时 `FeeSchedule` 替换 `commission_rate`/`min_commission`/`stamp_duty_rate`，保留 `transfer_fee_rate` 原值。`slippage_bps` 和 `impact_model` 在 V1 记录但不参与 FeeModel 计算（Engine 的 Reality Model 独立处理滑点）

- [x] Task: BacktestRunHandler 传递 CostConfig `[S]`
  - 验收: `BacktestRunResult` 新增 `cost_config: CostConfig | None` 字段；`handler.handle()` 将 `command.cost_config` 透传到 `BacktestRunResult`
  - 文件: `packages/app/src/ditto_app/command/backtest.py`（修改）
  - 测试: 通过
  - 说明: 最小改动 — Handler 只负责透传，不负责 FeeModel 构建（FeeModel 构建在 Flow 中完成，保持 Handler 纯校验职责）

- [x] Task: run_backtest_flow 接受 CostConfig + 构建 FeeModel `[S]`
  - 验收: `run_backtest_flow` 新增 `cost_config: dict[str, float] | None = None` 参数；内部调用 `build_fee_model()` 构造 FeeModel；传入 `BacktestServiceOptions(fee_model=...)`
  - 文件: `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`（修改）
  - 测试: 通过
  - 说明: CostConfig 序列化为 dict 传递（跨进程边界需要可序列化参数）。Flow 内部反序列化为 CostConfig dataclass 再调用工厂

---

### F3: Prefect Flow 提交 + 状态机 `[M]`

**问题**: `run_backtest_flow` 已定义但 API 端点未调用。Flow 内部缺少状态更新（PENDING→RUNNING→COMPLETED/FAILED）。

**方案**: API 端点通过 `asyncio.to_thread` 后台提交 flow，Flow 内部通过 `RunLifecycleService` 更新状态和进度。

- [x] Task: run_backtest_flow 状态机 + 进度追踪 `[M]`
  - 验收: Flow 启动时调用 `run_service.mark_running(run_id)`；成功完成时调用 `mark_completed()`；异常时调用 `mark_failed(error_message)`；回测循环中每步更新进度（`writer.update_progress()`）
  - 文件:
    - `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`（修改）
    - `interfaces/src/ditto_interfaces/registry/contexts/strategy.py`（修改 — bundle 新增 strategy_run_writer）
  - 测试: 10 用例全部通过（状态流转、进度更新、异常传播、无 writer 兼容）
  - 说明: `create_strategy_bundle()` 返回的 bundle 新增 `run_writer: StrategyRunWriterProtocol` 字段。Flow 内部在关键节点更新状态。`run_writer` 通过 DI 容器获取

- [x] Task: API 端点后台提交 Flow `[M]`
  - 验收: `trigger_backtest` 端点创建 RunRecord 后，通过 `asyncio.to_thread` 后台启动 `run_backtest_flow`，立即返回 202 + run_id；前端可通过 GET 端点轮询进度
  - 文件:
    - `interfaces/src/ditto_interfaces/api/routes/backtest.py`（修改 — trigger_backtest 端点）
    - `interfaces/src/ditto_interfaces/models/backtest.py`（修改 — BacktestRunTriggerResponse 新增字段）
  - 测试: 单元测试（~3 用例：正常提交、flow 参数传递、handler 异常返回 400）
  - 说明: 使用 `asyncio.get_event_loop().run_in_executor(None, run_backtest_flow, ...)` 后台执行。Flow 参数包含 run_id + strategy_id + 日期 + cost_config 序列化 dict + signal_expressions/weights

---

## 批次 2: 功能补全 + 质量

### F4: Cancel/Retry API 端点 `[M]`

- [x] Task: Cancel + Retry 端点 `[M]`
  - 验收: `POST /backtests/runs/{run_id}/cancel` 检查 status ∈ {PENDING, RUNNING}，更新为 `cancelled`，返回 200；`POST /backtests/runs/{run_id}/retry` 检查 status ∈ {FAILED, CANCELLED}，创建新 RunRecord（parent_run_id 关联），提交 flow，返回 202；不存在返回 404；状态不合法返回 409
  - 文件:
    - `interfaces/src/ditto_interfaces/api/routes/backtest.py`（修改 — 新增 2 端点）
    - `interfaces/src/ditto_interfaces/models/backtest.py`（修改 — 新增响应模型）
    - `packages/app/src/ditto_app/command/backtest.py`（新增 CancelRunHandler + RetryRunHandler）
    - `packages/app/src/ditto_app/providers.py`（注册新 handler）
    - `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`（新增 mark_cancelled）
    - `packages/kernel/src/ditto_kernel/enums.py`（RunStatus.CANCELLED）
  - 测试: 15 用例全部通过（cancel 成功/409/404、retry 成功/409/404、RunStatus.CANCELLED 枚举）
  - 说明: Cancel/Retry 逻辑已提取到 App 层 `CancelRunHandler`/`RetryRunHandler`，API 路由仅做 HTTP 异常转换，符合 CQRS 和 importlinter 规范

---

### F5: Universe Delete 修复 `[S]`

- [x] Task: DeleteCustomUniverseHandler 实际删除 `[S]`
  - 验收: Handler 调用底层 writer 的删除方法；预设 universe 返回 403；不存在返回 404
  - 文件:
    - `packages/app/src/ditto_app/command/universe.py`（修改）
    - `packages/data/src/ditto_data/storage/metadata/universe_store.py`（查看/修改 — 确认 delete 方法存在）
  - 测试: 单元测试（2 用例：自定义 universe 删除成功、删除后查询返回空）
  - 说明: 先检查 UniverseWriter/UniverseStore 是否有 delete 方法。若无则新增 `delete_universe(universe_id)` 方法（DELETE FROM universe WHERE universe_id = ? AND universe_type = 'custom'）

---

### F6: 端到端冒烟测试 `[M]`

- [x] Task: E2E 冒烟测试脚本 `[M]`
  - 验收: 测试覆盖 DataFetch → FactorBridge（mock 表达式）→ BacktestService（短日期范围）→ BacktestReport；含 signal_expressions 策略可完整回测
  - 文件: `packages/engine/tests/integration/backtest/test_e2e_smoke.py`（新建）
  - 测试: 5 用例全部通过
  - 说明: 使用 mock DataFeed + 固定 10 日 ETF 数据。验证报告非空 + NAV 曲线单调性（无 NaN）。不依赖外部数据源

---

### F7: Schema Migration 脚本 `[S]`

- [x] Task: 增量 migration — strategy_run 新列 `[S]`
  - 验收: 提供幂等 `ALTER TABLE ... ADD COLUMN` SQL（通过 `PRAGMA table_info` 检测）；`strategy_run_store.py` 的 `init_schema()` 在 CREATE TABLE 后执行 migration
  - 文件:
    - `packages/data/src/ditto_data/scripts/schema.sql`（修改 — 追加 migration 块）
    - `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`（修改 — `_run_migrations()`）
  - 测试: 通过
  - 文件:
    - `packages/data/src/ditto_data/scripts/schema.sql`（修改 — 追加 migration 块）
    - `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`（修改 — init_schema 后执行 ALTER）
  - 测试: 单元测试（1 用例：旧 schema 升级后读写新字段正确）
  - 说明: SQLite 不支持 `IF NOT EXISTS` 在 ALTER TABLE 中，使用 try/except 或 `PRAGMA table_info` 检测列是否存在。参考项目现有 migration 模式

---

### F8: Universe API 路由测试 `[S]`

- [x] Task: Universe API 路由单元测试 `[S]`
  - 验收: 6 个端点（GET list/detail/members + POST create + PUT update + DELETE delete）各有 1-2 个测试用例；覆盖成功 + 错误路径
  - 文件: `interfaces/tests/unit/api/routes/test_universe_unit.py`（新建）
  - 测试: 25 用例全部通过
  - 说明: 参考 `test_backtest_trigger_unit.py` 的测试模式：mock DI 注入 + 验证请求/响应映射 + 错误处理

---

## 汇总

### 工作量估算

| 模块 | 任务数 | 复杂度 | 新建文件 | 修改文件 |
|------|--------|--------|----------|----------|
| F1 RegimeScoringStep | 2 | M+M | 1 | 5 |
| F2 CostConfig 管道 | 3 | M+S+S | 1 | 3 |
| F3 Flow 提交 + 状态机 | 2 | M+M | 0 | 4 |
| F4 Cancel/Retry | 1 | M | 0 | 3 |
| F5 Universe Delete | 1 | S | 0 | 1-2 |
| F6 E2E 冒烟 | 1 | M | 1 | 0 |
| F7 Schema Migration | 1 | S | 0 | 2 |
| F8 Universe 测试 | 1 | S | 1 | 0 |
| **总计** | **12** | **S×4, M×8** | **4** | **~18** |

### importlinter 合规验证

| 模块 | 涉及层级 | 合规说明 |
|------|----------|----------|
| F1 | Engine 内部 | 无跨层依赖，合规 |
| F2 | App → Engine（FeeModel Protocol） | App 可依赖 Engine Protocol，合规 |
| F3 | Interfaces → App + Engine | 标准方向，合规 |
| F4 | Interfaces → App → Data | 标准方向，合规 |
| F5 | App → Data | 标准方向，合规 |
| F6 | 跨层集成测试 | 合规（tests 无限制） |
| F7 | Data 内部 | 无跨层依赖，合规 |
| F8 | Interfaces 测试 | 合规 |

### 验证命令

每个任务完成后运行：
```bash
pixi run -e dev check    # lint + fmt + type + test --fast
```

全量完成前运行：
```bash
pixi run -e dev ci       # CI 完整检查
pixi run -e dev arch-check  # 分层验证
```
