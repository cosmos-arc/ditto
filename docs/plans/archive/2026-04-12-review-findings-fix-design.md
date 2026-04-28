# V1 Sprint Review Findings — 修复设计

> 日期: 2026-04-12
> 状态: Approved
> 前置: [V1 Enhancement Design](2026-04-11-v1-enhancement-design.md), [V1 Sprint Plan](2026-04-10-v1-sprint-plan.md)

## 概述

基于代码审查发现的 11 个问题，按严重性分为 Blocking / High / Medium / Low 四级，设计对应的修复方案。R3 (Prefect Worker 异步执行) 采用方案 A — 正确实现 Prefect Deployment。

## 修改影响范围

| 包 | 修改类型 |
|---|---|
| `packages/data` | SQL 状态转换条件更新 |
| `packages/app` | service_factory / backtest_process / fee_override / command/backtest |
| `packages/engine` | steps 合并 + regime_allocation guard |
| `interfaces` | API 路由 / Prefect flow deploy / trade error handling |
| `docs/plans` | 设计文档路由描述更新 |

---

## Phase 0: 前置修复（Blocking）

### B1: steps.py 合并风险

**问题:** `steps.py` 是 tracked deletion，`steps/` 目录是 untracked。提交时漏 staging 会导致导入断裂。

**修复:**
```
git rm packages/engine/src/ditto_engine/backtest/steps.py
git add packages/engine/src/ditto_engine/backtest/steps/
```

同一 commit 中完成，确保 `steps/__init__.py` 的 re-export 覆盖原 `steps.py` 所有公共符号（已确认覆盖: StepContext, StepResult, TradingStep, DataFetchStep, RiskScanStep, StrategyStep, PlanningStep, PreTradeStep, ExecutionStep, AuditStep）。

### B2: pytest 冲突

**问题:** `interfaces/tests/unit/jobs/flows/test_backtest_unit.py` 与 `packages/app/tests/unit/query/test_backtest_unit.py` 同名，`pixi run -e dev test --fast` 报 import file mismatch。

**修复:** 运行 `pixi run -e dev test --fast` 确认具体报错。如果确为 pytest 收集冲突，重命名其中一个文件（如 `test_backtest_flow_unit.py`）。Prefect/fakeredis lupa 错误在 R3 修复后解决（API 测试不再触发 flow 执行路径）。

---

## Phase 1: High 单点修复（互不依赖，可并行）

### R2: FactorBridge compiled_expressions 丢失

**根因:** `_build_backtest_options()` 重建 `BacktestServiceOptions` 时漏传 `compiled_expressions`。

**修改文件:** `packages/app/src/ditto_app/builders/service_factory.py`

```python
# _build_backtest_options() return 语句中补充:
return BacktestServiceOptions(
    fee_model=options.fee_model,
    rule_provider=options.rule_provider,
    post_trade_guard=options.post_trade_guard,
    compiled_expressions=options.compiled_expressions,  # ← 补上
    audit_service=options.audit_service or self._audit_service,
    artifact_service=options.artifact_service or self._artifact_service,
    artifact_dir=options.artifact_dir,
    display_map=options.display_map,
    run_service=options.run_service or self._run_service,
)
```

**验证:** `backtest_process.py:234` 能正确拿到 compiled_expressions，factor-aware bundle builder 被创建。

### R4: RunRecord 配置覆盖

**根因:** API handler 正确写入 `config_json`，但 `BacktestService.run()` 的 `create_run()` 不传 `config_json`，`INSERT OR REPLACE` 覆盖原值。

**修改文件:** `packages/app/src/ditto_app/process/execution/backtest_process.py`

```python
# 当前:
if run_svc is not None:
    run_svc.create_run(run_id=run_id, ..., mode="backtest")
    run_svc.mark_running(run_id)

# 修复: get_or_create 语义
if run_svc is not None:
    existing = run_svc.get_run(run_id)
    if existing is None:
        run_svc.create_run(run_id=run_id, ..., mode="backtest")
    run_svc.mark_running(run_id)
```

### R5: Cancel 竞态条件

**根因:** TOCTOU 竞态 — cancel 和 completion/failure 的 UPDATE 无 `WHERE status = ?` 前置条件。

**修改文件:** `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`

SQL 层面添加状态转换条件:

```sql
-- mark_completed / mark_failed:
UPDATE strategy_run
SET status = ?, completed_at = ?, error_message = ?
WHERE run_id = ? AND status NOT IN ('cancelled', 'completed', 'failed')

-- mark_cancelled:
UPDATE strategy_run
SET status = 'cancelled', completed_at = ?
WHERE run_id = ? AND status IN ('pending', 'running')
```

应用层检查 `rowcount`，为 0 则记录日志或抛出异常。

### M2: Trade API 业务错误返回 500

**修改文件:** `interfaces/src/ditto_interfaces/api/routes/trade.py`

参考 backtest API 的错误处理模式，为 `record_fill` / `update_intent_status` 等路由添加:

```python
try:
    result = await asyncio.to_thread(handler.handle, cmd)
except ValueError as e:
    raise HTTPException(status_code=_map_error_code(e), detail=str(e))
```

错误码映射:
- `not found` → 404
- `status transition` → 409
- 其他 ValueError → 400

同时统一响应包装: `record_fill` 和 `compute_pnl` 改为返回 `APIResponse[...]`。

### L1: Regime allocation 缺列保护

**修改文件:** `packages/engine/src/ditto_engine/alpha/builtins/regime_allocation.py`

```python
# guard 中增加:
if (
    self.regime_score_column not in frame.columns
    or self.regime_label_column not in frame.columns
    or "weight" not in frame.columns
    or "position_ratio" not in frame.columns  # ← 补上
):
    return frame
```

---

## Phase 2: R6 CostConfig 修复（依赖 R2）

### 数据流目标

```
CostConfig（用户输入）
  ├── build_fee_model()    → BrokerageModel.fee_model    （影响真实成交费用）
  └── build_slippage_model() → BrokerageModel.slippage_model （影响滑点成本）
        ↓
  BrokerageModel → BacktestBrokerage → brokerage.py:304 真实 fill 费用
```

### 修改点

**1. 新增 `build_slippage_model(cost_config)` 工厂函数**

文件: `packages/app/src/ditto_app/process/execution/fee_override.py`

```python
def build_slippage_model(cost_config: CostConfig | None) -> SlippageModel:
    if cost_config is None or cost_config.impact_model == "none":
        return FixedBpsSlippage(bps=cost_config.slippage_bps if cost_config else 2.0)
    if cost_config.impact_model == "volume_share":
        return VolumeShareSlippage(
            base_bps=cost_config.slippage_bps,
            impact_factor=0.1,
        )
    msg = f"Unknown impact model: {cost_config.impact_model}"
    raise ValueError(msg)
```

**2. `BacktestRuntimeBuilder.build_published_runtime()` 接受费用模型**

文件: `packages/app/src/ditto_app/builders/service_factory.py`

```python
def build_published_runtime(
    self,
    *,
    fee_model: FeeModel | None = None,
    slippage_model: SlippageModel | None = None,
    ...
) -> BacktestRuntime:
    _fee_model = fee_model or AShareFeeModel()
    _slippage_model = slippage_model or FixedBpsSlippage()
    brokerage = BacktestBrokerage(
        account=Account(...),
        model=BrokerageModel(fee_model=_fee_model, slippage_model=_slippage_model),
    )
```

**3. `build_backtest_service_from_catalog` 替换 runtime 中的 BrokerageModel**

当前 `runtime.brokerage` 内部的 `BrokerageModel` 是硬编码的。需要:
- 从 `BacktestServiceOptions.fee_model` 取得用户指定的 fee model
- 构建新的 `BrokerageModel` + `BacktestBrokerage` 替换 runtime 中的

**4. `BacktestServiceOptions` 增强**

可选: 增加 `slippage_model: SlippageModel | None` 字段，与 `fee_model` 一同传递。

---

## Phase 3: R3 Prefect Worker 正确实现（依赖 R4 + R5）

### 架构变更

```
当前（错误）:
  API Route → run_in_executor → flow.func() → API 进程内同步执行

目标:
  API Route → Prefect Client.create_flow_run_from_deployment()
                    ↓
            Prefect Server（持久化 flow run）
                    ↓
            Prefect Worker（独立进程执行）
                    ↓
            Flow 内部更新 DB 状态
```

### 修改点

**1. deploy.py 注册 backtest flow**

文件: `interfaces/src/ditto_interfaces/jobs/flows/deploy.py`

```python
run_backtest_flow.deploy(
    name="backtest-prod",
    work_pool_name="default",
    parameters={},
    tags=["backtest"],
)
```

**2. API 路由改为 Prefect Client 异步提交**

文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py`

```python
from prefect import get_client

async def _submit_flow(
    params: dict[str, object],
    on_failure: Callable[[str, str], None] | None = None,
) -> str:
    run_id = str(params.get("run_id", ""))
    try:
        async with get_client() as client:
            flow_run = await client.create_flow_run_from_deployment(
                deployment_name="run-backtest/backtest-prod",
                parameters=params,
            )
            return str(flow_run.id)
    except Exception:
        logger.exception("Prefect flow submission failed", extra={"run_id": run_id})
        if on_failure is not None:
            on_failure(run_id, "Flow submission failed")
        raise
```

调用点从 `run_in_executor` 改为 `await _submit_flow(...)`。

**3. Cancel 通过 Prefect Client 传播**

```python
async with get_client() as client:
    await client.cancel_flow_run(flow_run_id=prefect_flow_run_id)
```

Flow 内部 step 间隙检查取消状态（配合 R5 的 DB 状态条件更新）。

**4. 开发环境 fallback**

当 Prefect Server 不可用时（开发模式），回退到进程内执行:

```python
PREFECT_API_URL = os.getenv("PREFECT_API_URL")

if PREFECT_API_URL:
    await _submit_to_prefect(params)
else:
    # fallback: 进程内执行（开发模式）
    asyncio.get_running_loop().run_in_executor(...)
```

**5. 测试适配**

- API 测试 mock Prefect Client，不触发真实 flow 执行
- Flow 测试独立于 API 测试，直接测试 flow 函数
- 消除 `fakeredis/lupa` 启动错误

**6. retry_run 端点同步修改**

`retry_run` 同样改用 Prefect Client 提交，不再调用 `flow.func()`。

---

## Phase 4: 收尾

### M1: 设计文档路由更新

更新 [2026-04-10-v1-sprint-plan.md](2026-04-10-v1-sprint-plan.md) Phase 2 路由描述，反映实际实现路径（`/trade/*` 而非 `/signals/*` + `/trades`）。

### M3: 时序因子标记为已知限制

R2 修复后 factor bridge 被激活，但时序因子因单日截面数据返回 null。此问题标记为 V1.1 改进项，需在 engine 回放循环中维护历史 bar buffer。

**V1.1 改进项**: `FactorBridge.compute_signals()` 当前仅使用单日截面 `market_data`，时序因子（如 `rolling_mean(20)`、`momentum(10)`）因缺少历史 bar buffer 返回 null。解决方向: EngineLoop 在 `StepContext` 中维护滚动 bar cache，FactorBridge 从 cache 读取历史数据计算时序指标。

---

## 实施顺序

```
Phase 0（前置）
├── B1: steps.py 合并风险修复
├── B2: pytest 冲突解决
└── Gate: pixi run -e dev check 通过

Phase 1（单点修复，可并行）
├── R2: compiled_expressions 修复
├── R4: RunRecord get_or_create
├── R5: Cancel 状态条件更新
├── L1: Regime allocation guard
├── M2: Trade API 错误处理
└── Gate: pixi run -e dev check 通过

Phase 2（R6 CostConfig，依赖 R2）
├── build_slippage_model 工厂函数
├── build_published_runtime 接受费用模型
├── _build_backtest_options 传递费用模型
└── Gate: 单元测试 + 成本对比

Phase 3（R3 Prefect，依赖 R4+R5）
├── deploy.py 注册 backtest flow
├── API 路由改为 Prefect Client 提交
├── Cancel 通过 Prefect Client 传播
├── 开发环境 fallback 模式
├── 测试适配
└── Gate: API 集成测试 + Prefect flow 测试

Phase 4（收尾）
├── M1: 更新设计文档
├── M3: 标记时序因子为 V1.1
└── Gate: pixi run -e dev check 全量通过
```

## 未覆盖项

- **R4 Signal Delivery**: 设计文档已标注推迟到 V1.1，不计入 V1 缺陷。
- **M3 时序因子历史 buffer**: 需要较大改动（engine 回放循环 + 表达式编译），V1.1 实施。
