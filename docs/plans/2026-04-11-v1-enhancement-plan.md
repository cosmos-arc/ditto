# V1 增强实施计划

## 概述
- Sprint: V1 Enhancement | Phase: 核心闭环 + 运营闭环
- 创建: 2026-04-11
- 设计文档: [v1-enhancement-design.md](2026-04-11-v1-enhancement-design.md)
- 前置: V1 Sprint Phase 0-3 完成（4323+ 测试通过）

## 技术方案

### 关键决策修正（基于代码库探索）

| # | 设计文档方案 | 实际调整 | 原因 |
|---|-------------|---------|------|
| D1 | FactorBridge 编译为 callable | 直接产出 `pl.Expr` | Analytics 编译器产出 `pl.Expr`，无需额外抽象 |
| D2 | 新建独立 DeliveryChannel 四通道实现 | 复用 Infra NotificationSender/AlertManager | 已有 Telegram/Email/Webhook 完整实现 |
| D3 | R4 ~400 行 | 缩减至 ~200 行 | 70% 推送基础设施已存在 |
| D4 | DerivedSpec 手动构造 | 封装 `build_signal_spec()` 辅助函数 | 统一默认值（role=SIGNAL, grain=1d, calendar=cn_stock） |

### 现有基础设施映射

| 模块 | 已有 | 缺口 |
|------|------|------|
| R1 Regime | `RegimeStage`（MA_CROSS + VOLATILITY_THRESHOLD）| ScoreEngine + Indicator Protocol + AllocationStage |
| R2 因子 | 完整编译器（30 算子）+ DerivedSpec + CompiledDerivedExpression | 字符串→DerivedSpec 桥接 + signal_value 合成 |
| R3 回测 | BacktestService + RunLifecycleService + 8 个 API 端点 | POST 触发 + Prefect 异步 + 进度字段 |
| R4 推送 | SignalSnapshotProcess + TelegramSignalDelivery + Infra Notification 三通道 | DeliveryRouter + 策略级配置 |
| R5 Universe | UniverseService + Reader/Writer + PIT 查询 | API 端点 + QueryFacade |
| R6 成本 | AShareFeeModel + CostModelSpec（已在 StrategySpec）| API 参数透传 |
| R7 验证 | 数据层完整 | 端到端冒烟测试 |

### 依赖关系

```
批次 1（核心闭环）:
  R7 (数据验证) ─── 先行验证数据就绪
       ↓
  R1 (Regime) ──┐
  R2 (因子桥接) ─┤── 并行开发
                ↓
  R3 (回测触发) ──── 依赖 R1+R2

批次 2（运营闭环）:
  R5 (Universe) ──┐
  R6 (成本模型) ──┤── 并行开发
                 ↓
  R4 (信号推送) ──── 依赖 R3 产生的信号
```

---

## 批次 1: 核心闭环

### R7: 数据链路验证

- [x] Task: 数据就绪度审计 `[S]`
  - 验收: 输出 6 项数据验证清单报告（ETF日线/因子列/Universe/Regime/基准/行业分类），标注就绪/待补
  - 文件: `docs/reports/2026-04-11-data-readiness.md`（新建）
  - 说明: 手动验证 DataFetchStep 能获取 ETF 日线 bar；Analytics 列名（market.close 等）数据源覆盖；UniverseService 能查询 csi300/csi500 成分

- [x] Task: 端到端冒烟测试脚本 `[M]`
  - 验收: 从数据查询→因子编译→策略构建→回测执行完整流程可跑通
  - 文件: `tests/integration/test_e2e_smoke.py`（新建）
  - 测试: 集成测试
  - 说明: 验证 DataFeed → FactorBridge（mock 表达式）→ BacktestService（短日期范围）→ BacktestReport

---

### R1: Regime Score Engine（与 R2 并行）

- [x] Task: 核心类型定义 `[S]`
  - 验收: `RegimeIndicator` Protocol + `RegimeConfig` + `RegimeResult` + `RegimeScoreEngine` 类型定义完成，类型检查通过
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime.py`（重构）
  - 测试: 无（纯类型，在后续任务测试）
  - 说明: 重构现有 `regime.py`，新增 `RegimeIndicator` Protocol（`name: str`, `weight: float`, `compute(frame) -> float`）、`RegimeConfig`（indicators + 阈值 + position_mapping）、`RegimeResult`（score + label + position_ratio + indicators）。保留 `RegimeStage` 向后兼容

- [x] Task: TrendIndicator + VolatilityIndicator `[M]`
  - 验收: 两个 Indicator 从现有 RegimeStage 逻辑提取，`RegimeStage.process()` 委托到它们，现有 18 个测试全部通过
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime.py`（重构）
  - 测试: 单元测试（复用 + 扩展 `test_regime_unit.py`）
  - 说明: `_process_ma_cross()` 提取为 `TrendIndicator.compute()`，`_process_volatility_threshold()` 提取为 `VolatilityIndicator.compute()`。`RegimeStage` 变为薄包装，委托到 `RegimeScoreEngine`

- [x] Task: BreadthIndicator + MomentumIndicator `[M]`
  - 验收: BreadthIndicator（涨跌比 → 0-1）和 MomentumIndicator（N日涨幅 rank 分位 → 0-1）实现完成，边界值测试通过
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime.py`（追加）
  - 测试: 单元测试（新增 ~8 个用例）
  - 说明: BreadthIndicator 需 DecisionFrame 含 `up_count`/`down_count` 列；MomentumIndicator 需 `close` 列 + `rank()` 计算。缺失列时 graceful fallback 到 RegimeConfig.default_regime

- [x] Task: RegimeScoreEngine `[M]`
  - 验收: 多指标加权合成 → score(0-100) → label(BULL/BEAR/NEUTRAL) → position_ratio(0-1)，线性/阶梯映射均正确
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime.py`（追加）
  - 测试: 单元测试（新增 ~6 个用例）
  - 说明: `RegimeScoreEngine.__init__(config: RegimeConfig)` + `score(frame) -> RegimeResult`。加权: `score = sum(indicator.weight * indicator.compute(frame)) / sum(weights) * 100`。映射: linear 直接比例；stepped 按 label 分档（BULL=1.0, NEUTRAL=0.7, BEAR=0.3/0.0）

- [x] Task: RegimeAwareAllocationStage `[M]`
  - 验收: BEAR + score<20 → 完全空仓；其他 → 缩放权重；剩余归入现金；约束检查通过
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/regime_allocation.py`（新建）
  - 测试: 单元测试（新增 ~6 个用例）
  - 说明: 实现 `DecisionStage` Protocol。从 DecisionFrame 读取 `regime_score`/`regime_label` 列（由 RegimeScoreEngine 写入），缩放 `weight` 列。需要在 EngineConfig 或 StrategyContext 中传递 regime 配置

- [x] Task: 模板集成 — 4 个模板增加 regime_config `[M]`
  - 验收: 4 个策略模板 Config 增加 `regime_config: RegimeConfig | None = None`；Pipeline 在 Allocate 后可选插入 RegimeAwareAllocationStage；regime_config=None 时行为不变
  - 文件:
    - `packages/engine/src/ditto_engine/alpha/templates/etf_rotation.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/templates/etf_trend_swing.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/templates/stock_selection_trend.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/templates/stock_sector_rotation.py`（修改）
    - `packages/engine/src/ditto_engine/alpha/builtins/__init__.py`（导出更新）
  - 测试: 单元测试（每个模板 1-2 个用例，验证有/无 regime_config 的 Pipeline 输出）

---

### R2: 声明式因子配置桥接（与 R1 并行）

- [x] Task: FactorBridge 核心 — 字符串→DerivedSpec→pl.Expr `[M]`
  - 验收: `FactorBridge.compile_and_validate()` 接受 `tuple[str, ...]` + `tuple[float, ...]`，验证语法+语义，返回 `CompiledExpressions`（含 `tuple[pl.Expr, ...]`）；无效表达式抛 ValueError 含诊断信息
  - 文件: `packages/app/src/ditto_app/process/execution/factor_bridge.py`（新建）
  - 测试: 单元测试（~6 个用例：有效编译、语法错误、语义错误、权重不匹配、空表达式）
  - 说明: 内部辅助函数 `build_signal_spec(expr_str, index) -> DerivedSpec` 构造 DerivedSpec（role=SIGNAL, materialization_profile=SERIES, entity_keys=("instrument_id",), grain="1d", calendar="cn_stock"）。调用 `ExpressionCompiler().compile(spec)` 获取 `pl.Expr`。验证：权重非负、长度匹配、表达式非空

- [x] Task: signal_value 加权合成计算 `[M]`
  - 验收: `FactorBridge.compute_signals()` 在 DataFrame 上计算因子值 → rank 归一化 → 加权合成为 `signal_value` 列；空 DataFrame 返回空
  - 文件: `packages/app/src/ditto_app/process/execution/factor_bridge.py`（同文件）
  - 测试: 单元测试（~4 个用例：多因子加权、单因子、空数据、rank 归一化验证）
  - 说明: 步骤：(1) `df.with_columns([expr.alias(f"factor_{i}") for i, expr in enumerate(compiled)])` (2) 各因子列 `cs_rank()` 归一化 (3) `signal_value = sum(rank_f_i * w_i) / sum(w_i)`

- [x] Task: StrategySpec.signal_expressions 扩展 `[S]`
  - 验收: `StrategySpec` 新增 `signal_expressions: tuple[str, ...] = ()` + `signal_weights: tuple[float, ...] = ()`；StrategyRuntimeBuilder 传递到模板配置；非空时注入 FactorBridge
  - 文件:
    - `packages/engine/src/ditto_engine/alpha/specs.py`（修改）
    - `packages/app/src/ditto_app/builders/runtime_builder.py`（修改）
  - 测试: 单元测试（2 个用例：有/无 signal_expressions 的 spec 序列化+构建）
  - 说明: 注意 StrategySpec 在 Engine 层，FactorBridge 在 App 层。RuntimeBuilder 检查 `spec.signal_expressions` 非空时，编译因子并将 `signal_value` 列注入 DecisionFrame（通过自定义 SignalStage 或 Pipeline 预处理步骤）

- [x] Task: FactorBridge 集成到回测流程 `[M]`
  - 验收: 回测流程中 DataFetchStep → FactorBridge.compute_signals() → DecisionFrame 含 signal_value → SignalStage 使用 signal_value；端到端集成测试通过
  - 文件:
    - `packages/app/src/ditto_app/process/execution/backtest_process.py`（修改）
    - `packages/app/src/ditto_app/builders/runtime_builder.py`（修改）
  - 测试: 集成测试（1 个用例：含因子表达式的策略完整回测）
  - 说明: BacktestService 新增可选 `compiled_expressions: CompiledExpressions | None` 参数。引擎循环中 DataFetchStep 之后、StrategyStep 之前插入因子计算步骤

---

### R3: API 回测触发

- [x] Task: StrategyRunRecord 进度字段扩展 `[S]`
  - 验收: 新增 `progress_pct`, `current_step`, `completed_days`, `total_days` 字段；SQLite migration；Reader/Writer 兼容
  - 文件:
    - `packages/data/src/ditto_data/models/strategy_run.py`（修改）
    - `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`（修改）
    - `packages/data/src/ditto_data/scripts/schema.sql`（修改）
  - 测试: 单元测试（2 个用例：新字段读写、向后兼容）
  - 说明: 新字段均有默认值（frozen dataclass 兼容）。Writer 新增 `update_progress()` 方法。SQLite ALTER TABLE ADD COLUMN

- [x] Task: BacktestRunHandler + Command `[M]`
  - 验收: `BacktestRunHandler.handle(command)` 完成参数校验→因子预编译→创建 RunRecord→提交 Prefect flow→返回 run_id；策略不存在返回 404；日期非法返回 400；因子编译失败返回 400
  - 文件:
    - `packages/app/src/ditto_app/command/backtest.py`（新建）
    - `packages/app/src/ditto_app/command/__init__.py`（导出更新）
  - 测试: 单元测试（~5 个用例：正常流程、策略不存在、日期非法、因子编译失败、参数覆盖）
  - 说明: handler 组合 `StrategyCatalogService`（读策略）+ `FactorBridge`（预编译）+ `RunLifecycleService`（创建 RunRecord）+ Prefect flow 提交

- [x] Task: Prefect 异步回测 Flow `[M]`
  - 验收: `run_backtest_flow` 在 Prefect Worker 执行回测；状态机 PENDING→RUNNING→COMPLETED/FAILED；失败自动重试一次；ProgressCallback 更新 RunRecord 进度
  - 文件: `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`（新建）
  - 测试: 单元测试（mock Prefect，验证状态机流转 + 进度更新）
  - 说明: 复用现有 `create_prefect_host()` 模式。内部调用 `BacktestService.run()`，注入 ProgressCallback 在每步完成后更新进度。异常时 `mark_failed()`

- [x] Task: API 端点 — POST /backtests/runs `[M]`
  - 验收: POST 触发返回 202 Accepted + run_id；GET 查询含进度；POST cancel 优雅退出；POST retry 创建新 RunRecord 关联 parent_run_id
  - 文件:
    - `interfaces/src/ditto_interfaces/api/routes/backtest.py`（修改 — 新增端点）
    - `interfaces/src/ditto_interfaces/models/backtest.py`（修改 — 新增请求/响应模型）
  - 测试: 单元测试（~4 个用例：触发、取消、重试、参数覆盖）
  - 说明: 新增 3 个端点。请求模型 `CreateBacktestRunRequest`（strategy_id + start_date + end_date + 可选参数）。响应 `BacktestRunResponse`（run_id + status + created_at）

---

## 批次 2: 运营闭环

### R5: Universe 管理 API

- [x] Task: UniverseQueryFacade `[S]`
  - 验收: `UniverseQueryFacade` 封装 UniverseService，提供 `list_universes()` + `get_universe(id)` + `get_members(id, asof)` 方法
  - 文件: `packages/app/src/ditto_app/query/universe.py`（新建）
  - 测试: 单元测试（3 个用例：列表查询、详情查询、成分查询）
  - 说明: 薄 Facade 层，委托到 `UniverseService`。转换 Data 层模型为 App 层 DTO

- [x] Task: Universe API 路由 `[M]`
  - 验收: 6 个端点（GET list + GET detail + GET members + POST create + PUT update + DELETE delete）全部可用；预设 universe 不可删除
  - 文件:
    - `interfaces/src/ditto_interfaces/api/routes/universe.py`（新建）
    - `interfaces/src/ditto_interfaces/api/routes/__init__.py`（注册路由）
    - `interfaces/src/ditto_interfaces/models/universe.py`（新建 — 请求/响应模型）
  - 测试: 单元测试（~6 个用例：各端点 + 预设不可删）
  - 说明: DELETE 端点检查 universe_type=="custom"，否则返回 403。POST/PUT 需要 CreateCustomUniverseCommand + Handler（App 层 command/universe.py 新建）

- [x] Task: Universe Command Handler `[S]`
  - 验收: CreateCustomUniverseCommand + UpdateCustomUniverseCommand + DeleteCustomUniverseCommand handlers 完成自定义 universe CRUD
  - 文件: `packages/app/src/ditto_app/command/universe.py`（新建）
  - 测试: 单元测试（3 个用例：创建/更新/删除自定义 universe）

---

### R6: 成本模型 API 配置

- [x] Task: CostConfig API 模型 + 参数透传 `[S]`
  - 验收: `CostConfig` 模型（commission_rate/commission_min/stamp_duty_rate/slippage_bps/impact_model）在 API 请求中可配置；BacktestRunHandler 透传到 BacktestService
  - 文件:
    - `interfaces/src/ditto_interfaces/models/backtest.py`（修改 — 新增 CostConfig）
    - `packages/app/src/ditto_app/command/backtest.py`（修改 — 注入 CostConfig）
    - `packages/app/src/ditto_app/process/execution/backtest_process.py`（修改 — BacktestService 接受 CostConfig）
  - 测试: 单元测试（3 个用例：默认值正确、自定义覆盖、参数验证）
  - 说明: CostConfig 直接映射到现有 `CostModelSpec`（已在 StrategySpec 中）。默认值 = A 股标准费率（commission_rate=0.0003, min=5.0, stamp_duty=0.001, slippage_bps=1.0, impact_model="none"）

---

### R4: 全渠道信号推送

- [x] Task: DeliveryRouter — 复用 Infra 通知系统 `[M]`
  - 验收: `DeliveryRouter` 将 `SignalMessage` 转换为 `Notification`，委托 `AlertManager` 推送；fire-and-forget 模式（推送失败不阻塞信号生成）
  - 文件: `packages/app/src/ditto_app/process/execution/delivery.py`（新建）
  - 测试: 单元测试（7 个用例：正常推送、空 intents、fire-and-forget、上下文校验、Markdown 渲染、空渲染、send_signal 委托）
  - 说明: `DeliveryRouter` 注入 `NotificationPort`（Protocol），支持可选依赖。V1 实现 fire-and-forget + Markdown 渲染

- [x] Task: 信号模板渲染 `[S]`
  - 验收: 信号内容包含策略名/日期/买卖意图/持仓信息；支持 Markdown 格式
  - 文件: `packages/app/src/ditto_app/process/execution/delivery.py`（同文件 render_markdown 方法）
  - 测试: 单元测试（2 个用例：Markdown 格式包含关键信息、空 intents 返回空字符串）

- [x] Task: 策略级推送通道配置 `[S]`
  - 验收: DI 注册更新；SignalDeliveryProvider 提供 NotificationPort + DeliveryRouter + SignalDeliveryProtocol
  - 文件:
    - `interfaces/src/ditto_interfaces/registry/infra/signal_delivery.py`（修改 — DI 注册 DeliveryRouter）
  - 测试: DI 容器集成测试通过
  - 说明: V1 简单方案：环境变量配置 Telegram 通道。SignalDeliveryProvider 三层链：NotificationPort → DeliveryRouter → SignalDeliveryProtocol

- [x] Task: SignalSnapshotProcess 集成 DeliveryRouter `[S]`
  - 验收: DeliveryRouter 实现 `send_signal()` 满足 `SignalDeliveryProtocol`；通过 DI 自动注入 SignalSnapshotProcess
  - 文件: `packages/app/src/ditto_app/process/execution/delivery.py`（send_signal 方法）
  - 测试: 单元测试（1 个用例：send_signal 委托到 deliver）
  - 说明: DeliveryRouter.send_signal() 实现 SignalDeliveryProtocol，由 SignalDeliveryProvider 通过 DI 注入

---

## 汇总

### 工作量估算

| 模块 | 任务数 | 复杂度 | 新建文件 | 修改文件 |
|------|--------|--------|----------|----------|
| R7 | 2 | S+M | 2 | 0 |
| R1 | 6 | S+M+M+M+M+M | 1 | 5 |
| R2 | 4 | M+M+S+M | 1 | 3 |
| R3 | 4 | S+M+M+M | 1 | 4 |
| R5 | 3 | S+M+S | 3 | 1 |
| R6 | 1 | S | 0 | 3 |
| R4 | 4 | M+S+S+S | 1 | 3 |
| **总计** | **24** | **S×7, M×13** | **9** | **19** |

### importlinter 合规验证

| 模块 | 涉及层级 | 合规说明 |
|------|----------|----------|
| R1 | Engine 内部 | 无跨层依赖，合规 |
| R2 | App → Analytics + Engine | App 可依赖 Analytics 和 Engine，合规 |
| R3 | Interfaces → App → Engine | 标准方向，合规 |
| R4 | App → Infra（通过 DI） | App 只访问 infra.foundation（notification 在 infra.services，需 DI 注入），合规 |
| R5 | Interfaces → App → Data | 标准方向，合规 |
| R6 | Interfaces → App | 参数透传，合规 |
| R7 | 无层变更 | 合规 |

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
